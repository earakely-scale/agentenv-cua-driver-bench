"""start.py INSTANCE RUN MODEL SPECS [--taskpack TGZ] [--keep] [--fresh]: start the fleet worker on INSTANCE for the
trials SPECS lists (a file plan.py wrote), on the bench's main, as the systemd unit `fleet`.

The model key (`FLEET_MODEL_KEY`) and the Hugging Face token (huggingface_hub's login) are encrypted to a key the VM
makes for this job; the job decrypts them into its own environment and deletes the files. `--taskpack` ships a task
pack fetched elsewhere (`tar czf taskpack.tgz -C artifacts taskpack`), since many VMs behind one address run out of
GitHub's API calls fetching it. `--keep` runs the checkout already there instead of main; `--fresh` forgets the
worker's earlier progress, which it otherwise resumes."""
import argparse
import base64
from pathlib import Path

from huggingface_hub import get_token

from common import opener, sealer, setting, ship, ssm

KEYS = "/run/trialkey"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("instance")
    parser.add_argument("run")
    parser.add_argument("model")
    parser.add_argument("specs", type=Path)
    parser.add_argument("--taskpack", type=Path)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    venv, bench = setting("FLEET_VENV", "~/venv"), setting("FLEET_BENCH", "~/bench")
    if args.taskpack:
        ship(args.instance, args.taskpack, "/home/ubuntu/fleet/taskpack.tgz")
    seal = sealer(args.instance, KEYS)
    key, token = seal(setting("FLEET_MODEL_KEY")), seal(get_token())
    pull = "" if args.keep else "git fetch -q origin && git reset -q --hard origin/main && "
    unpack = "rm -rf artifacts/taskpack && tar xzf ~/fleet/taskpack.tgz -C artifacts && " if args.taskpack else ""
    print(ssm(args.instance, f"""set -e
umask 077
{"rm -rf ~/fleet/progress.jsonl ~/fleet/out ~/fleet/logs" if args.fresh else ""}
rm -f ~/fleet/stop
mkdir -p ~/fleet/logs ~/fleet/out
echo '{base64.b64encode(args.specs.read_bytes()).decode()}' | base64 -d > ~/fleet/specs.txt
printf %s '{key}' > {KEYS}/model.enc
printf %s '{token}' > {KEYS}/hf.enc
cat > ~/fleet/config.toml <<'CFG'
[model]
base_url = "{setting("FLEET_MODEL_BASE_URL")}"
api_key = "env:LITELLM_API_KEY"
default = "{args.model}"
CFG
cat > ~/fleet/job.sh <<'JOB'
{opener(KEYS)}
export LITELLM_API_KEY="$(dec "$(cat {KEYS}/model.enc)")" HF_TOKEN="$(dec "$(cat {KEYS}/hf.enc)")"
rm -f {KEYS}/key.pem {KEYS}/model.enc {KEYS}/hf.enc
export AGENT_ENV_CONFIG=$HOME/fleet/config.toml VENV={venv} BENCH={bench} HF_REPO={setting("HF_REPO", "")}
cd {bench} && {pull}{unpack}{venv}/bin/python tools/taskpack.py >/dev/null
{venv}/bin/python tools/fleet/worker.py {args.run} ~/fleet/specs.txt
JOB
sudo systemctl reset-failed fleet 2>/dev/null || true
sudo systemd-run --unit fleet --property=LimitNOFILE=65536 --uid ubuntu --gid ubuntu --setenv=HOME=/home/ubuntu \\
  --setenv=PATH=/home/ubuntu/.local/bin:/usr/bin:/bin --working-directory=/home/ubuntu \\
  bash -c 'bash ~/fleet/job.sh > ~/fleet/job.log 2>&1'
echo started"""))


if __name__ == "__main__":
    main()
