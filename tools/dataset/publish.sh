#!/bin/bash
# publish.sh: rebuild the dataset's tables, card, figures, hero and web videos, and the replay Space, from every trial
# the dataset holds, and upload them. Run it in the bench's checkout with HF_TOKEN set (tools/fleet/hfjob.py does), on
# a machine with ffmpeg; it needs some GB of disk for the recordings. HF_REPO picks the dataset and Space (default
# earakely-scale/CuaDriverBench-AgentEnv), WORK where it works (default ~/publish), JOBS its parallel video encodes;
# DRY_RUN=1 builds everything under WORK and uploads nothing.
set -euo pipefail
bench=${BENCH:-$(cd "$(dirname "$0")/../.." && pwd)}
work=${WORK:-$HOME/publish}
export HF_REPO=${HF_REPO:-earakely-scale/CuaDriverBench-AgentEnv}
python=$work/venv/bin/python
[ -x "$python" ] || { python3 -m venv "$work/venv" && "$work/venv/bin/pip" install -q -r "$bench/tools/space/requirements.txt" -r "$bench/tools/dataset/requirements.txt"; }
rm -rf "$work/dataset" "$work/out"
"$python" - "$work/dataset" <<'PY'
import os, sys
from huggingface_hub import snapshot_download
snapshot_download(os.environ["HF_REPO"], repo_type="dataset", local_dir=sys.argv[1], allow_patterns=["runs/**"],
                  ignore_patterns=["**/trajectory.json", "**/workspace/**", "**/web.mp4"], max_workers=16)
PY
"$python" "$bench/tools/dataset/tables.py" "$bench" "$work/dataset"
"$python" "$bench/tools/space/build.py" "$work/dataset" "$work/out" --jobs "${JOBS:-8}"
"$python" "$bench/tools/dataset/card.py" "$work/out" "$work/dataset"
[ -n "${DRY_RUN:-}" ] && { echo "built in $work; nothing uploaded"; exit 0; }
"$python" - "$work/dataset" "$work/out/space" <<'PY'
import os, sys
from huggingface_hub import HfApi
api, repo = HfApi(), os.environ["HF_REPO"]
print(api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=sys.argv[1], commit_message="Tables, card, figures, hero and web copies",
                        allow_patterns=["README.md", "LICENSE.md", "licenses/*", "assets/**", "results/*.parquet", "tasks/*.parquet", "runs/**/web.mp4"]))
api.create_repo(repo, repo_type="space", space_sdk="static", exist_ok=True)
print(api.upload_folder(repo_id=repo, repo_type="space", folder_path=sys.argv[2], commit_message="Replay Space",
                        delete_patterns=["data/**"]))
PY
