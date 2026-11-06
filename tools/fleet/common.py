"""The fleet's settings, from the environment or `tools/fleet/fleet.env` (git-ignored; `fleet.env.example` lists them),
and what every fleet tool does over SSM: run a script as the VM's user, copy a small file, make a key pair on the VM
and encrypt a secret to it, so that only ciphertext ever crosses SSM. A worker is a Linux VM, its user ubuntu, or an EC2
Mac, its user ec2-user (`HOSTS`)."""
import base64
import hashlib
import os
import subprocess
import tempfile
import time
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CHUNK = 80_000
#: Each OS's worker: its user, the user's group and home, and the command that prints a file's sha256.
HOSTS = {"linux": ("ubuntu", "ubuntu", "/home/ubuntu", "sha256sum"),
         "macos": ("ec2-user", "staff", "/Users/ec2-user", "shasum -a 256")}


def _load(path):
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


_load(HERE / "fleet.env")
SSM = boto3.Session(region_name=os.environ.get("FLEET_REGION") or None).client("ssm")


def setting(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        raise SystemExit(f"{name} isn't set: put it in the environment or tools/fleet/fleet.env")
    return value


def ssm(instance, script, timeout=300, os_type="linux"):
    """``script`` run on ``instance`` as its worker user; its output, or exit with its error."""
    command = SSM.send_command(
        InstanceIds=[instance], DocumentName="AWS-RunShellScript", TimeoutSeconds=60,
        Parameters={"commands": [f"sudo -iu {HOSTS[os_type][0]} bash <<'__FLEET__'\n{script}\n__FLEET__"],
                    "executionTimeout": [str(timeout)]})["Command"]["CommandId"]
    while True:
        time.sleep(4)
        try:
            out = SSM.get_command_invocation(CommandId=command, InstanceId=instance)
        except SSM.exceptions.InvocationDoesNotExist:
            continue
        if out["Status"] not in ("Pending", "InProgress", "Delayed"):
            if out["Status"] != "Success":
                raise SystemExit(f"{instance}: {out['Status']}: {out['StandardErrorContent'][-1500:]}")
            return out["StandardOutputContent"]


def ship(instance, local, remote, os_type="linux"):
    """A small file copied to ``remote`` on the VM in base64 chunks an SSM command can hold, checked by sha256; nothing
    is sent when the VM has it already."""
    digest = hashlib.sha256(local.read_bytes()).hexdigest()
    if ssm(instance, f"{HOSTS[os_type][3]} {remote} 2>/dev/null || true", os_type=os_type).split()[:1] == [digest]:
        return
    data = base64.b64encode(local.read_bytes()).decode()
    ssm(instance, f"mkdir -p $(dirname {remote}) && rm -f {remote}.b64", os_type=os_type)
    for start in range(0, len(data), CHUNK):
        ssm(instance, f"printf %s '{data[start:start + CHUNK]}' >> {remote}.b64", os_type=os_type)
    got = ssm(instance, f"base64 -d < {remote}.b64 > {remote} && rm {remote}.b64 && {HOSTS[os_type][3]} {remote}",
              os_type=os_type).split()[0]
    if got != hashlib.sha256(local.read_bytes()).hexdigest():
        raise SystemExit(f"{instance}: {remote} arrived changed")


def sealer(instance, folder, os_type="linux"):
    """A key pair made on the VM in ``folder`` (root-made, not /dev/shm, which logind empties when each SSM session
    ends); a function that encrypts a secret to it."""
    user, group, _, _ = HOSTS[os_type]
    public = ssm(instance, f"""sudo install -d -m 700 -o {user} -g {group} {folder}
umask 077; openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out {folder}/key.pem 2>/dev/null
openssl pkey -in {folder}/key.pem -pubout""", os_type=os_type)
    pem = public[public.index("-----BEGIN"):]
    return lambda secret: _encrypt(pem, secret)


def opener(folder):
    """The shell function that decrypts what ``sealer`` sealed, on the VM."""
    return (f"dec() {{ for part in $(printf %s \"$1\" | tr . ' '); do printf %s \"$part\" | base64 -d | "
            f"openssl pkeyutl -decrypt -inkey {folder}/key.pem -pkeyopt rsa_padding_mode:oaep; done; }}")


def _encrypt(pem, secret):
    """RSA-OAEP over 300-byte chunks, joined by dots, since one block of a 3072-bit key holds at most 342 bytes."""
    data = secret.encode()
    with tempfile.NamedTemporaryFile("w", suffix=".pub") as public:
        public.write(pem)
        public.flush()
        return ".".join(_block(public.name, data[i:i + 300]) for i in range(0, len(data), 300))


def _block(public, chunk):
    done = subprocess.run(["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", public, "-pkeyopt",
                           "rsa_padding_mode:oaep"], input=chunk, capture_output=True)
    if done.returncode:
        raise SystemExit(f"encrypting failed: {done.stderr.decode()[:300]}")
    return base64.b64encode(done.stdout).decode()
