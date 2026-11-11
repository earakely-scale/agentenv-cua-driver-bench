#!/bin/bash
# publish.sh: rebuild the dataset's tables, card, figures, hero and web videos, and the replay Space, from every trial
# the dataset holds, and upload them. Run it in the bench's checkout with HF_TOKEN set (tools/fleet/hfjob.py does), on
# a machine with ffmpeg; it needs some GB of disk for the recordings. HF_REPO picks the dataset and Space (default
# earakely-scale/CuaDriverBench-AgentEnv), WORK where it works (default ~/publish), JOBS its parallel video encodes;
# DRY_RUN=1 builds everything under WORK and uploads nothing. The web copies the dataset holds are downloaded after
# their recordings, so only a trial without one, or whose recording is newer, is encoded again. Both downloads read one
# commit of the dataset, recorded with the tables as results/snapshot.json; the upload is refused when the dataset
# already holds a publish built from a later commit, since a slow download would otherwise put older tables over newer.
# A download the Hub cuts short resumes: at a pinned commit, the files already fetched are kept without asking again.
set -euo pipefail
bench=${BENCH:-$(cd "$(dirname "$0")/../.." && pwd)}
work=${WORK:-$HOME/publish}
export HF_REPO=${HF_REPO:-earakely-scale/CuaDriverBench-AgentEnv}
python=$work/venv/bin/python
[ -x "$python" ] || { python3 -m venv "$work/venv" && "$work/venv/bin/pip" install -q -r "$bench/tools/space/requirements.txt" -r "$bench/tools/dataset/requirements.txt"; }
rm -rf "$work/dataset" "$work/out"
"$python" - "$work/dataset" <<'PY'
import json, os, sys, time
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download
info = HfApi().repo_info(os.environ["HF_REPO"], repo_type="dataset")
for attempt in range(8):
    try:
        snapshot_download(os.environ["HF_REPO"], repo_type="dataset", local_dir=sys.argv[1], allow_patterns=["runs/**"],
                          ignore_patterns=["**/trajectory.json", "**/workspace/**", "**/web.mp4"], max_workers=16,
                          revision=info.sha)
        snapshot_download(os.environ["HF_REPO"], repo_type="dataset", local_dir=sys.argv[1],
                          allow_patterns=["runs/**/web.mp4"], max_workers=16, revision=info.sha)
        break
    except Exception as error:
        if attempt == 7:
            raise
        print(f"download cut short ({str(error)[:120]}); resuming in {60 * (attempt + 1)} s", flush=True)
        time.sleep(60 * (attempt + 1))
(Path(sys.argv[1]) / "results").mkdir(parents=True, exist_ok=True)
(Path(sys.argv[1]) / "results" / "snapshot.json").write_text(
    json.dumps({"commit": info.sha, "committed_at": info.last_modified.isoformat()}) + "\n")
PY
"$python" "$bench/tools/dataset/tables.py" "$bench" "$work/dataset"
"$python" "$bench/tools/space/build.py" "$work/dataset" "$work/out" --jobs "${JOBS:-8}"
"$python" "$bench/tools/dataset/card.py" "$work/out" "$work/dataset"
[ -n "${DRY_RUN:-}" ] && { echo "built in $work; nothing uploaded"; exit 0; }
"$python" - "$work/dataset" "$work/out/space" <<'PY'
import json, os, sys, time
from datetime import datetime
from pathlib import Path
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import EntryNotFoundError
api, repo = HfApi(), os.environ["HF_REPO"]
ours = json.loads((Path(sys.argv[1]) / "results" / "snapshot.json").read_text())
try:
    theirs = json.loads(Path(hf_hub_download(repo, "results/snapshot.json", repo_type="dataset",
                                             force_download=True)).read_text())
except EntryNotFoundError:
    theirs = None
if theirs and datetime.fromisoformat(theirs["committed_at"]) > datetime.fromisoformat(ours["committed_at"]):
    sys.exit(f"refused: the dataset's tables were built from {theirs['commit'][:8]} ({theirs['committed_at']}), later "
             f"than this build's {ours['commit'][:8]} ({ours['committed_at']}); publish again from a fresh snapshot")


def retried(call, attempts=12):
    for attempt in range(attempts):
        try:
            return call()
        except Exception as error:
            if attempt == attempts - 1:
                raise
            print(f"upload refused ({str(error)[:120]}); again in {min(300, 30 * (attempt + 1))} s", flush=True)
            time.sleep(min(300, 30 * (attempt + 1)))


print(retried(lambda: api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=sys.argv[1], commit_message="Tables, card, figures, hero and web copies",
                                        allow_patterns=["README.md", "LICENSE.md", "licenses/*", "assets/**", "results/*.parquet", "results/snapshot.json", "tasks/*.parquet", "runs/**/web.mp4"])))
api.create_repo(repo, repo_type="space", space_sdk="static", exist_ok=True)
print(retried(lambda: api.upload_folder(repo_id=repo, repo_type="space", folder_path=sys.argv[2], commit_message="Replay Space",
                                        delete_patterns=["data/**"])))
PY
