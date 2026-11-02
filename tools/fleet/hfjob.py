"""hfjob.py INSTANCE SCRIPT [--pull] [--wait]: run SCRIPT on INSTANCE as the systemd unit `hfjob`, in the bench's
checkout with HF_TOKEN in its environment, logging to ~/hfjob/hfjob.log; it can outlast an SSM command. `--pull`
first resets the checkout to main; `--wait` follows it to the end and prints the log's tail.

The token (huggingface_hub's login) crosses SSM encrypted to a key the VM makes for this job, and reaches the unit
through a file the unit reads and deletes, never its command line or environment settings."""
import argparse
import base64
import time
from pathlib import Path

from huggingface_hub import get_token

from common import opener, sealer, setting, ssm

KEYS = "/run/hfjob"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("instance")
    parser.add_argument("script", type=Path)
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    bench = setting("FLEET_BENCH", "~/bench")
    token = sealer(args.instance, KEYS)(get_token())
    pull = f"cd {bench} && git fetch -q origin && git reset -q --hard origin/main\n" if args.pull else ""
    print(ssm(args.instance, f"""set -e
umask 077
mkdir -p ~/hfjob
echo '{base64.b64encode(args.script.read_bytes()).decode()}' | base64 -d > ~/hfjob/job.sh
{opener(KEYS)}
dec '{token}' > {KEYS}/token
rm -f {KEYS}/key.pem
{pull}cat > ~/hfjob/unit.sh <<'UNIT'
export HF_TOKEN="$(cat {KEYS}/token)" HF_REPO={setting("HF_REPO", "")} BENCH={bench}
rm -f {KEYS}/token
cd {bench} && bash ~/hfjob/job.sh
UNIT
sudo systemctl reset-failed hfjob 2>/dev/null || true
sudo systemd-run --unit hfjob --property=LimitNOFILE=65536 --uid ubuntu --gid ubuntu --setenv=HOME=/home/ubuntu \\
  --setenv=PATH=/home/ubuntu/.local/bin:/usr/bin:/bin \\
  bash -c 'bash ~/hfjob/unit.sh > ~/hfjob/hfjob.log 2>&1; echo "exit $?" >> ~/hfjob/hfjob.log'
echo started"""))
    while args.wait:
        time.sleep(30)
        state = ssm(args.instance, "systemctl is-active hfjob; tail -20 ~/hfjob/hfjob.log").splitlines()
        if state and state[0] not in ("active", "activating"):
            print("\n".join(state[1:]))
            return


if __name__ == "__main__":
    main()
