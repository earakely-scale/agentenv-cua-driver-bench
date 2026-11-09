"""start.py INSTANCE RUN MODEL SPECS [--run-specs FILE] [--os OS] [--taskpack TGZ] [--keep] [--fresh]: start the fleet
worker on INSTANCE for the trials SPECS lists (a file plan.py wrote; FILE, its run.txt, lists the whole run's, which
the run's manifest pins), on the bench's main, as the systemd unit `fleet` on a Linux VM, or
on an EC2 Mac (`--os macos`) as the launchd job `dev.fleet.worker` of ec2-user's login session, where the lume
provider runs its macOS computers; a Windows run (`--os windows`) runs on a Linux VM with KVM, as a Linux run does;
its trials and manifest go under runs/OS/RUN (OS linux by default).

The model key (`FLEET_MODEL_KEY`) and the Hugging Face token (huggingface_hub's login) are encrypted to a key the VM
makes for this job; the job decrypts them into its own environment and deletes the files. `--taskpack` ships a task
pack fetched elsewhere (`tar czf taskpack.tgz -C artifacts taskpack`), since many VMs behind one address run out of
GitHub's API calls fetching it. `--keep` runs the checkout already there instead of main; `--fresh` forgets the
worker's earlier progress, which it otherwise resumes."""
import argparse
import base64
from pathlib import Path

from huggingface_hub import get_token

from common import HOSTS, opener, sealer, setting, ship, ssm

#: Where each OS's worker keeps the job's key pair: a folder its boot empties.
KEYS = {"linux": "/run/trialkey", "macos": "/private/var/run/trialkey", "windows": "/run/trialkey"}
#: The launchd job a Mac worker runs as, in ec2-user's login session.
MAC_JOB = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>dev.fleet.worker</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>-c</string>
<string>ulimit -n 65536; bash ~/fleet/job.sh &gt; ~/fleet/job.log 2&gt;&amp;1</string></array>
<key>RunAtLoad</key><true/>
<key>EnvironmentVariables</key><dict><key>PATH</key>
<string>/Users/ec2-user/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
<key>SoftResourceLimits</key><dict><key>NumberOfFiles</key><integer>65536</integer></dict>
</dict></plist>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("instance")
    parser.add_argument("run")
    parser.add_argument("model")
    parser.add_argument("specs", type=Path)
    parser.add_argument("--run-specs", type=Path)
    parser.add_argument("--os", default="linux", choices=sorted(HOSTS))
    parser.add_argument("--taskpack", type=Path)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--set", dest="settings", action="append", default=[], metavar="envs/NAME.KEY=VALUE",
                        help="a setting agent-env run gives each trial (agentenv-framework 0.9.1453 or later); repeatable")
    args = parser.parse_args()
    venv, bench = setting("FLEET_VENV", "~/venv"), setting("FLEET_BENCH", "~/bench")
    os_type, keys, home = args.os, KEYS[args.os], HOSTS[args.os][2]
    if args.taskpack:
        ship(args.instance, args.taskpack, f"{home}/fleet/taskpack.tgz", os_type)
    settings = base64.b64encode("".join(line + "\n" for line in args.settings).encode()).decode()
    seal = sealer(args.instance, keys, os_type)
    key, token = seal(setting("FLEET_MODEL_KEY")), seal(get_token())
    pull = "" if args.keep else "git fetch -q origin && git reset -q --hard origin/main && "
    unpack = "rm -rf artifacts/taskpack && tar xzf ~/fleet/taskpack.tgz -C artifacts && " if args.taskpack else ""
    sandbox = '[sandbox]\ndefault = "lume"\n' if os_type == "macos" else ""
    state = f"export XDG_STATE_HOME={setting('FLEET_STATE', '$HOME/.local/state')}\n" if os_type == "macos" else ""
    print(ssm(args.instance, f"""set -e
umask 077
{"rm -rf ~/fleet/progress.jsonl ~/fleet/out ~/fleet/logs" if args.fresh else ""}
rm -f ~/fleet/stop
mkdir -p ~/fleet/logs ~/fleet/out
echo '{base64.b64encode(args.specs.read_bytes()).decode()}' | base64 -d > ~/fleet/specs.txt
echo '{base64.b64encode((args.run_specs or args.specs).read_bytes()).decode()}' | base64 -d > ~/fleet/run-specs.txt
echo '{settings}' | base64 -d > ~/fleet/settings.txt
printf %s '{key}' > {keys}/model.enc
printf %s '{token}' > {keys}/hf.enc
cat > ~/fleet/config.toml <<'CFG'
{sandbox}[model]
base_url = "{setting("FLEET_MODEL_BASE_URL")}"
api_key = "env:LITELLM_API_KEY"
default = "{args.model}"
CFG
cat > ~/fleet/job.sh <<'JOB'
{opener(keys)}
export LITELLM_API_KEY="$(dec "$(cat {keys}/model.enc)")" HF_TOKEN="$(dec "$(cat {keys}/hf.enc)")"
rm -f {keys}/key.pem {keys}/model.enc {keys}/hf.enc
{state}export AGENT_ENV_CONFIG=$HOME/fleet/config.toml VENV={venv} BENCH={bench} HF_REPO={setting("HF_REPO", "")}
export RUN_OS={os_type} RUN_MODEL={args.model}
cd {bench} && {pull}{unpack}{venv}/bin/python tools/taskpack.py >/dev/null
{venv}/bin/python tools/fleet/worker.py {args.run} ~/fleet/specs.txt
JOB
{_launch(os_type)}
echo started""", os_type=os_type))


def _launch(os_type):
    """The worker's job started where it runs its computers: a systemd unit, or a launchd job of the login session."""
    if os_type == "macos":
        return f"""cat > ~/fleet/dev.fleet.worker.plist <<'PLIST'
{MAC_JOB}
PLIST
uid=$(id -u)
sudo launchctl bootout gui/$uid/dev.fleet.worker 2>/dev/null || true
sudo launchctl bootstrap gui/$uid ~/fleet/dev.fleet.worker.plist"""
    return """sudo systemctl reset-failed fleet 2>/dev/null || true
sudo systemd-run --unit fleet --property=LimitNOFILE=65536 --uid ubuntu --gid ubuntu --setenv=HOME=/home/ubuntu \\
  --setenv=PATH=/home/ubuntu/.local/bin:/usr/bin:/bin --working-directory=/home/ubuntu \\
  bash -c 'bash ~/fleet/job.sh > ~/fleet/job.log 2>&1'"""


if __name__ == "__main__":
    main()
