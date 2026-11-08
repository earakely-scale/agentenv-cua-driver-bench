"""Fetch trycua's Cua Driver Bench task pack into ``artifacts/taskpack/`` as ``taskpack.lock.toml`` pins it: the files
each include names, at one commit of trycua's repo, checked file by file against that commit's tree and as a whole
against the lock's digest. The task pack is never copied into this repo.

    python tools/taskpack.py              fetch it, or keep what's there when it matches the lock
    python tools/taskpack.py verify       check what's there against the lock
    python tools/taskpack.py pin COMMIT   fetch it at COMMIT and write that commit and its digest to the lock
    python tools/taskpack.py apps         write each app's files.json: the task pack's files its computer installs
    python tools/taskpack.py grader       write into artifacts/gui_only/verify.py the trycua file its scan fetches

A task app's computer fetches its task's files itself, at put, by the URL and sha256 its ``files.json`` lists, and the
GUI-only check of a trial's trajectory fetches trycua's scan by those its ``TRYCUA`` lists; this repo holds those
hashes, never the files.

``GITHUB_TOKEN``, when set, is sent to GitHub's API, which allows few calls without one."""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "taskpack.lock.toml"
TARGET = ROOT / "artifacts" / "taskpack"
ENVS = ROOT / "envs"
GRADER = ROOT / "artifacts" / "gui_only" / "verify.py"
#: trycua's scan of an agent's tool calls, which the trajectory's GUI-only check fetches, and their Windows guard, whose
#: scan adds Windows' shells and script hosts, which it fetches for a Windows trial.
SCAN = "scoring/bench_v2.py"
WINDOWS_SCAN = "windows/guard.py"
_TABLE = re.compile(r"(?ms)^TRYCUA = \{.*?^\}$")
#: The bench tasks with an app of their own, each in envs/<task>/, and where their folders are in the task pack.
TASKS = ("cdb-s02", "cdb-s03", "cdb-s04")
TASK_DIR = "taskpack/tasks/shared"
#: trycua's macOS BenchLab and BenchSentinel, built together from their Swift sources.
SWIFT = ("swift/BenchLab.swift", "swift/BenchLabInterrupts.swift", "swift/BenchLabModes.swift",
         "swift/BenchSentinel.swift", "swift/build.sh")
#: The bench's apps of trycua's own windows, each in envs/<app>/, and the task pack's files each installs on each OS,
#: by the list its files.json keeps them in: ``files``, a Linux computer's, else the OS type's.
LABS = {"benchlab": {"files": ("linux/benchlab.py", "probes/_common/benchlab_common.py"), "macos": SWIFT,
                     "windows": ("windows/benchlab.py", "probes/_common/benchlab_common.py")},
        "bench-sentinel": {"macos": SWIFT,
                           "windows": ("windows/sentinel.py", "windows/winenv.py", "windows/guard.py",
                                       "scoring/bench_v2.py")}}
MANIFEST = "MANIFEST.sha256"
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
_FILE_MODES = {"100644": 0o644, "100755": 0o755}


@dataclass(frozen=True)
class Lock:
    repo: str
    commit: str
    sha256: str
    include: tuple[tuple[str, str], ...]


def read_lock(path: Path = LOCK) -> Lock:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    include = tuple((entry["from"], entry["to"]) for entry in data["include"])
    for source, to in include:
        _relative(source), _relative(to)
    return Lock(data["repo"], data["commit"], data.get("sha256", ""), include)


def fetch(lock: Lock, target: Path = TARGET) -> str:
    """The task pack at ``target``, fetched unless what's there already matches the lock; its digest."""
    if target.is_dir() and digest(target) == lock.sha256:
        return lock.sha256
    staged = download(lock, _staging(target))
    try:
        got = digest(staged)
        if got != lock.sha256:
            raise SystemExit(f"{lock.repo} at {lock.commit} gives digest {got}, not the lock's {lock.sha256}; "
                             "nothing was changed")
        _replace(target, staged)
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    return got


def verify(lock: Lock, target: Path = TARGET) -> None:
    if not target.is_dir():
        raise SystemExit(f"{target} isn't there: run python tools/taskpack.py")
    if (got := digest(target)) != lock.sha256:
        raise SystemExit(f"{target} has digest {got}, not the lock's {lock.sha256}: fetch it again")


def pin(commit: str, lock_path: Path = LOCK, target: Path = TARGET) -> str:
    """Fetch the task pack at ``commit`` and write the commit and its digest to the lock, keeping the lock's other
    lines; its digest."""
    staged = download(replace(read_lock(lock_path), commit=commit), _staging(target))
    try:
        got = digest(staged)
        text = lock_path.read_text(encoding="utf-8")
        text = re.sub(r'(?m)^commit = ".*"$', f'commit = "{commit}"', text)
        text = re.sub(r'(?m)^sha256 = ".*"$', f'sha256 = "{got}"', text)
        lock_path.write_text(text, encoding="utf-8")
        _replace(target, staged)
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    return got


def apps(lock: Lock, target: Path = TARGET, envs: Path = ENVS, tasks: tuple[str, ...] = TASKS,
         labs: dict[str, dict[str, tuple[str, ...]]] = LABS) -> list[Path]:
    """Write ``files.json`` in each app's folder: a task's files its computer installs, or a lab's on each OS, each by
    its URL at the lock's commit and its sha256 as the verified task pack's manifest has it; the files written."""
    verify(lock, target)
    hashes = {name: sha for sha, name in (line.split("  ", 1) for line in (target / MANIFEST).read_text().splitlines())}
    listed = {}
    for task in tasks:
        prefix = f"{TASK_DIR}/{task}/"
        listed[task] = {"files": [{"path": name[len(prefix):], "url": _url(lock, name), "sha256": sha}
                                  for name, sha in sorted(hashes.items())
                                  if name.startswith(prefix) and _for_the_computer(name[len(prefix):])]}
    for lab, lists in labs.items():
        if missing := [name for names in lists.values() for name in names if name not in hashes]:
            raise SystemExit(f"the task pack has no {', '.join(missing)}, which {lab} installs")
        listed[lab] = {key: [{"path": name, "url": _url(lock, name), "sha256": hashes[name]} for name in names]
                       for key, names in lists.items()}
    written = []
    for app, lists in listed.items():
        if not any(lists.values()):
            raise SystemExit(f"the task pack has no files of {app}")
        if not (envs / app).is_dir():
            raise SystemExit(f"{envs / app} isn't there: it's the app of {app}")
        path = envs / app / "files.json"
        path.write_text(json.dumps({"commit": lock.commit, **lists}, indent=1) + "\n", encoding="utf-8")
        written.append(path)
    return written


def grader(lock: Lock, target: Path = TARGET, verifier: Path = GRADER) -> Path:
    """Write the ``TRYCUA`` of the trajectory's GUI-only verifier: trycua's scan and their Windows guard, each by its
    URL at the lock's commit and its sha256 as the verified task pack's manifest has it."""
    verify(lock, target)
    hashes = {name: sha for sha, name in (line.split("  ", 1) for line in (target / MANIFEST).read_text().splitlines())}
    table = {"commit": lock.commit, **{PurePosixPath(name).name: {"url": _url(lock, name), "sha256": hashes[name]}
                                       for name in (SCAN, WINDOWS_SCAN)}}
    text = verifier.read_text(encoding="utf-8")
    if not _TABLE.search(text):
        raise SystemExit(f"{verifier} has no TRYCUA = {{...}} to write")
    verifier.write_text(_TABLE.sub(lambda _: "TRYCUA = " + json.dumps(table, indent=1), text, count=1), encoding="utf-8")
    return verifier


def _for_the_computer(path: str) -> bool:
    """Whether a file of a task's folder goes into its computer: its apps, reset scripts and fixture, its launch on
    each OS, brief and manifest; never its evaluator, tests or tools, which grade and build it outside."""
    parts = PurePosixPath(path).parts
    if parts[0] == "apps":
        return "tests" not in parts
    return (parts[0] in ("reset", "fixture") or path in ("brief.md", "task.cuabench.json")
            or (parts[0] == "platform" and parts[-1].startswith("launch.") and parts[-1].endswith(".json")))


def _url(lock: Lock, name: str) -> str:
    """The URL of the task pack's file ``name`` at the lock's commit, by the include that put it there."""
    for source, to in lock.include:
        if name == to or name.startswith(f"{to}/"):
            return f"{RAW}/{lock.repo}/{lock.commit}/{urllib.parse.quote(source + name[len(to):])}"
    raise SystemExit(f"{name} isn't under any include of the lock")


def download(lock: Lock, parent: Path) -> Path:
    """A new folder in ``parent`` holding the files each include names at the lock's commit, under its ``to``, and
    their manifest; each file checked against the git blob its tree lists."""
    staged = Path(tempfile.mkdtemp(prefix=".taskpack-", dir=parent))
    try:
        for source, to in lock.include:
            for path, entry in _files(lock.repo, lock.commit, source):
                data = get_raw(f"{RAW}/{lock.repo}/{lock.commit}/{urllib.parse.quote(path)}")
                if _blob_sha(data) != entry["sha"]:
                    raise SystemExit(f"{path} at {lock.commit} didn't arrive as its tree lists it")
                local = staged / to / PurePosixPath(path).relative_to(source) if path != source else staged / to
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(data)
                local.chmod(_FILE_MODES[entry["mode"]])
        (staged / MANIFEST).write_text(manifest(staged), encoding="utf-8")
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return staged


def manifest(folder: Path) -> str:
    """Each file under ``folder`` but the manifest and Python's caches, which running trycua's tests there writes, as
    ``sha256sum`` prints it, by path."""
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")
                   if (p.is_file() or p.is_symlink()) and "__pycache__" not in p.relative_to(folder).parts)
    return "".join(f"{hashlib.sha256((folder / name).read_bytes()).hexdigest()}  {name}\n"
                   for name in files if name != MANIFEST)


def digest(folder: Path) -> str:
    return hashlib.sha256(manifest(folder).encode()).hexdigest()


def get_api(url: str) -> bytes:
    token = os.environ.get("GITHUB_TOKEN")
    return _get(url, {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})})


def get_raw(url: str) -> bytes:
    return _get(url, {})


def _get(url: str, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "agentenv-cua-driver-bench", **headers})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _files(repo: str, commit: str, source: str) -> list[tuple[str, dict]]:
    """Each file at or under ``source`` in the commit, with its tree entry; a link or a submodule is refused."""
    entry = _entry(repo, commit, source)
    if entry["type"] == "blob":
        found = [(source, entry)]
    else:
        found = [(f"{source}/{e['path']}", e) for e in _tree(repo, entry["sha"], True) if e["type"] != "tree"]
    for path, e in found:
        if e["type"] != "blob" or e["mode"] not in _FILE_MODES:
            raise SystemExit(f"{path} at {commit} is a {e['type']} of mode {e['mode']}, not a file")
        _relative(path)
    if not found:
        raise SystemExit(f"{source} at {commit} holds no files")
    return found


def _entry(repo: str, commit: str, path: str) -> dict:
    """The tree entry at ``path`` in the commit, found one folder at a time from its root, so no listing is cut short."""
    entry = {"type": "tree", "sha": json.loads(get_api(f"{API}/repos/{repo}/git/commits/{commit}"))["tree"]["sha"]}
    for part in PurePosixPath(path).parts:
        if entry["type"] != "tree":
            raise SystemExit(f"{path} isn't in {repo} at {commit}")
        entry = next((e for e in _tree(repo, entry["sha"], False) if e["path"] == part), None)
        if entry is None:
            raise SystemExit(f"{path} isn't in {repo} at {commit}")
    return entry


@functools.cache
def _tree(repo: str, sha: str, recursive: bool) -> tuple:
    body = json.loads(get_api(f"{API}/repos/{repo}/git/trees/{sha}" + ("?recursive=1" if recursive else "")))
    if body.get("truncated"):
        raise SystemExit(f"GitHub cut its listing of {repo}'s tree {sha} short")
    return tuple(body["tree"])


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _relative(path: str) -> None:
    parts = PurePosixPath(path).parts
    if not parts or PurePosixPath(path).is_absolute() or ".." in parts:
        raise SystemExit(f"{path!r} isn't a relative path inside the task pack")


def _staging(target: Path) -> Path:
    """Beside the bundle's artifacts folder, not in it, where a fetch cut short would read as an artifact."""
    return target.parent.parent


def _replace(target: Path, staged: Path) -> None:
    old = staged.parent / f".{target.name}-old"
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged.rename(target)
    shutil.rmtree(old, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/taskpack.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("verify", help="check artifacts/taskpack against the lock")
    pinned = sub.add_parser("pin", help="fetch at a commit and write it and its digest to the lock")
    pinned.add_argument("commit")
    sub.add_parser("apps", help="write each task app's files.json from the verified task pack")
    sub.add_parser("grader", help="write the trycua file the trajectory's scan fetches into artifacts/gui_only/verify.py")
    args = parser.parse_args(argv)
    if args.command == "grader":
        print(f"wrote {grader(read_lock()).relative_to(ROOT)}")
    elif args.command == "apps":
        for path in apps(read_lock()):
            print(f"wrote {path.relative_to(ROOT)}")
    elif args.command == "pin":
        print(f"pinned {args.commit}: {pin(args.commit)}")
    elif args.command == "verify":
        verify(read_lock())
        print("artifacts/taskpack matches the lock")
    else:
        lock = read_lock()
        print(f"artifacts/taskpack: {lock.repo} at {lock.commit[:12]}, {fetch(lock)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
