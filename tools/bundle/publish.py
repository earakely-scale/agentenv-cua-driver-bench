"""publish.py [REPO] [--dry-run DIR]: the bench as a bundle on the Hugging Face Hub, for ``agent-env run hf://REPO``
(default earakely-scale/cua-driver-bench): the bundle's committed files (bundle.toml and its kind folders), trycua's
task pack in artifacts/taskpack/ as taskpack.lock.toml pins it, checked against the lock and under its own licence,
the licences, and the card. Each publish mirrors the repo to the bench's commit in one commit; ``--dry-run`` stages it
in DIR and uploads nothing. Needs a clean checkout with the task pack fetched (``python tools/taskpack.py``)."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import taskpack  # noqa: E402

REPO = "earakely-scale/cua-driver-bench"
#: What a run downloads of a bundle at a repo's root: its kind folders and bundle.toml.
BUNDLE = ("bundle.toml", "envs/", "agents/", "artifacts/", "skills/", "tasks/", "evals/")
PACK = "artifacts/taskpack"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=REPO)
    parser.add_argument("--dry-run", type=Path)
    args = parser.parse_args()
    commit = staged_commit()
    with tempfile.TemporaryDirectory() as scratch:
        stage = args.dry_run or Path(scratch)
        files = staged(stage, commit, args.repo)
        print(len(files), "files staged in", stage)
        if args.dry_run:
            return
        api = HfApi()
        api.create_repo(args.repo, repo_type="dataset", exist_ok=True)
        print(api.upload_folder(repo_id=args.repo, repo_type="dataset", folder_path=stage, delete_patterns="*",
                                commit_message=f"The bench at {commit[:7]}, with trycua's task pack at "
                                               f"{taskpack.read_lock().commit[:7]}"))


def staged_commit() -> str:
    """The bench's commit, refusing a checkout whose bundle files differ from it."""
    dirty = _git("status", "--porcelain", "--", *BUNDLE)
    if dirty.strip():
        raise SystemExit(f"the bundle's files differ from the commit:\n{dirty}")
    return _git("rev-parse", "HEAD").strip()


def staged(stage: Path, commit: str, repo: str) -> list[str]:
    """The bundle's files in ``stage``: the committed ones, the task pack, the licences and the card; their paths."""
    taskpack.verify(taskpack.read_lock())
    files = [f for f in _git("ls-files", "--", *BUNDLE).splitlines() if f]
    files += sorted(str(p.relative_to(ROOT)) for p in (ROOT / PACK).rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts)
    for name in files:
        (stage / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, stage / name)
    shutil.copy(HERE / "LICENSE.md", stage / "LICENSE.md")
    shutil.copytree(ROOT / "tools" / "dataset" / "licenses", stage / "licenses", dirs_exist_ok=True)
    lock = taskpack.read_lock()
    card = (HERE / "README.md").read_text()
    for key, value in {"REPO": repo, "COMMIT": commit, "PACK_COMMIT": lock.commit, "PACK_SHA256": lock.sha256}.items():
        card = card.replace("{{" + key + "}}", value)
    (stage / "README.md").write_text(card)
    return [*files, "LICENSE.md", "README.md"]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


if __name__ == "__main__":
    main()
