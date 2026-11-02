"""tools/taskpack.py against a stand-in for GitHub's tree API and raw files: what a fetch writes, keeps and refuses,
verify, and pin."""
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import taskpack  # noqa: E402

REPO = "trycua/cua"
FILES = {
    "libs/bench/LICENSE": b"FSL-1.1-MIT\n",
    "libs/bench/taskpack/README.md": b"the pack\n",
    "libs/bench/taskpack/tasks/s02/brief.md": b"reconcile the ledger\n",
    "libs/bench/taskpack/tasks/s02/reset/setup.py": b"print('setup')\n",
    "libs/bench/other/big.bin": b"not in the pack\n",
}
LOCK = """# the pack, pinned
repo = "trycua/cua"
commit = "c1"
sha256 = ""

[[include]]
from = "libs/bench/LICENSE"
to = "LICENSE"

[[include]]
from = "libs/bench/taskpack"
to = "taskpack"
"""


class GitHub:
    """Commits of trycua's repo, each a map of path to bytes; links and submodules by path."""

    def __init__(self, commits, odd_modes=None):
        self.commits, self.odd_modes, self.corrupt, self.raw = commits, odd_modes or {}, set(), []

    def api(self, url):
        path = url.removeprefix(f"{taskpack.API}/repos/{REPO}/git/")
        if path.startswith("commits/"):
            return json.dumps({"tree": {"sha": f"{path.split('/')[1]}:"}}).encode()
        sha, recursive = path.removeprefix("trees/").split("?")[0], url.endswith("?recursive=1")
        commit, folder = sha.split(":", 1)
        return json.dumps({"tree": self._entries(commit, folder, recursive), "truncated": False}).encode()

    def get(self, url):
        commit, path = url.removeprefix(f"{taskpack.RAW}/{REPO}/").split("/", 1)
        self.raw.append(path)
        data = self.commits[commit][path]
        return data + b"!" if path in self.corrupt else data

    def _entries(self, commit, folder, recursive):
        prefix = f"{folder}/" if folder else ""
        entries = {}
        for path, data in self.commits[commit].items():
            if not path.startswith(prefix):
                continue
            parts = PurePosixPath(path[len(prefix):]).parts
            for depth in range(1, len(parts) if recursive else 1):
                sub = "/".join(parts[:depth])
                entries[sub] = {"path": sub, "type": "tree", "mode": "040000", "sha": f"{commit}:{prefix}{sub}"}
            if not recursive and len(parts) > 1:
                entries[parts[0]] = {"path": parts[0], "type": "tree", "mode": "040000",
                                     "sha": f"{commit}:{prefix}{parts[0]}"}
                continue
            name = "/".join(parts)
            mode, kind = self.odd_modes.get(path, ("100644", "blob"))
            entries[name] = {"path": name, "type": kind, "mode": mode,
                             "sha": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}
        return list(entries.values())


@pytest.fixture
def github(monkeypatch):
    hub = GitHub({"c1": dict(FILES)})
    monkeypatch.setattr(taskpack, "get_api", hub.api)
    monkeypatch.setattr(taskpack, "get_raw", hub.get)
    taskpack._tree.cache_clear()
    yield hub
    taskpack._tree.cache_clear()


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / "taskpack.lock.toml").write_text(LOCK)
    (tmp_path / "artifacts" / "check").mkdir(parents=True)
    return tmp_path


def _pinned(bundle):
    lock_path, target = bundle / "taskpack.lock.toml", bundle / "artifacts" / "taskpack"
    taskpack.pin("c1", lock_path, target)
    return taskpack.read_lock(lock_path), target


def _leftovers(bundle):
    return sorted(p.name for p in bundle.iterdir() if p.name.startswith(".")) + sorted(
        p.name for p in (bundle / "artifacts").iterdir() if p.name != "taskpack" and p.name != "check")


def test_pin_writes_each_include_under_its_name_with_a_manifest_and_its_digest_to_the_lock(github, bundle):
    lock, target = _pinned(bundle)

    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        "LICENSE", "MANIFEST.sha256", "taskpack/README.md", "taskpack/tasks/s02/brief.md",
        "taskpack/tasks/s02/reset/setup.py"]
    assert (target / "taskpack/tasks/s02/brief.md").read_bytes() == FILES["libs/bench/taskpack/tasks/s02/brief.md"]
    assert (target / "MANIFEST.sha256").read_text().splitlines()[0] == (
        f"{hashlib.sha256(FILES['libs/bench/LICENSE']).hexdigest()}  LICENSE")
    assert lock.commit == "c1" and lock.sha256 == taskpack.digest(target)
    assert (bundle / "taskpack.lock.toml").read_text().startswith("# the pack, pinned\n")
    assert _leftovers(bundle) == []


def test_a_fetch_keeps_a_copy_that_matches_the_lock_and_fetches_one_that_doesnt(github, bundle):
    lock, target = _pinned(bundle)
    github.raw.clear()

    assert taskpack.fetch(lock, target) == lock.sha256 and github.raw == []
    (target / "taskpack/README.md").write_text("edited\n")
    assert taskpack.fetch(lock, target) == lock.sha256
    assert (target / "taskpack/README.md").read_bytes() == FILES["libs/bench/taskpack/README.md"]
    assert _leftovers(bundle) == []


def test_a_fetch_whose_digest_isnt_the_locks_is_refused_and_changes_nothing(github, bundle):
    lock, target = _pinned(bundle)
    github.commits["c1"]["libs/bench/taskpack/README.md"] = b"changed upstream\n"
    (target / "taskpack/README.md").write_text("edited\n")
    taskpack._tree.cache_clear()

    with pytest.raises(SystemExit, match="not the lock's"):
        taskpack.fetch(lock, target)

    assert (target / "taskpack/README.md").read_text() == "edited\n" and _leftovers(bundle) == []


def test_a_file_that_arrives_unlike_its_tree_entry_is_refused(github, bundle):
    github.corrupt.add("libs/bench/taskpack/tasks/s02/brief.md")

    with pytest.raises(SystemExit, match="didn't arrive as its tree lists it"):
        _pinned(bundle)

    assert not (bundle / "artifacts" / "taskpack").exists() and _leftovers(bundle) == []


@pytest.mark.parametrize("mode", [("120000", "blob"), ("160000", "commit")], ids=["link", "submodule"])
def test_a_link_or_a_submodule_in_an_include_is_refused(github, bundle, mode):
    github.odd_modes["libs/bench/taskpack/tasks/s02/reset/setup.py"] = mode

    with pytest.raises(SystemExit, match="not a file"):
        _pinned(bundle)

    assert _leftovers(bundle) == []


def test_verify_takes_the_pinned_copy_and_refuses_an_edited_added_or_missing_one(github, bundle):
    lock, target = _pinned(bundle)
    taskpack.verify(lock, target)

    (target / "taskpack" / "__pycache__").mkdir()
    (target / "taskpack" / "__pycache__" / "test.cpython-312.pyc").write_bytes(b"run in place")
    taskpack.verify(lock, target)
    (target / "taskpack" / "extra.txt").write_text("added\n")
    with pytest.raises(SystemExit, match="fetch it again"):
        taskpack.verify(lock, target)
    (target / "taskpack" / "extra.txt").unlink()
    (target / "LICENSE").write_text("MIT\n")
    with pytest.raises(SystemExit, match="fetch it again"):
        taskpack.verify(lock, target)
    with pytest.raises(SystemExit, match="isn't there"):
        taskpack.verify(lock, bundle / "artifacts" / "missing")


def test_repinning_writes_the_new_commit_and_digest_and_replaces_the_copy(github, bundle):
    lock, target = _pinned(bundle)
    github.commits["c2"] = {**FILES, "libs/bench/taskpack/tasks/s03/brief.md": b"a new task\n"}

    taskpack.pin("c2", bundle / "taskpack.lock.toml", target)

    repinned = taskpack.read_lock(bundle / "taskpack.lock.toml")
    assert repinned.commit == "c2" and repinned.sha256 not in ("", lock.sha256)
    assert (target / "taskpack/tasks/s03/brief.md").read_text() == "a new task\n"
    taskpack.verify(repinned, target)


def test_apps_lists_each_tasks_files_its_computer_installs_by_url_at_the_commit_and_sha256(github, bundle):
    task = "libs/bench/taskpack/tasks/shared/cdb-s02"
    github.commits["c1"] = {**FILES, **{f"{task}/{path}": f"{path}\n".encode() for path in (
        "apps/desk/main.js", "apps/desk/renderer/app.js", "apps/desk/tests/store.test.js", "evaluator/evaluate.py",
        "fixture/mail/messages.json", "platform/launch.linux.json", "platform/launch.macos.json", "reset/setup.py",
        "tests/test_cdb_s02.py", "tools/build.py", "brief.md", "task.cuabench.json", "README.md")}}
    lock, target = _pinned(bundle)
    (bundle / "envs" / "cdb-s02").mkdir(parents=True)

    [written] = taskpack.apps(lock, target, bundle / "envs", ("cdb-s02",))

    listed = json.loads(written.read_text())
    assert listed["commit"] == "c1"
    assert [f["path"] for f in listed["files"]] == [
        "apps/desk/main.js", "apps/desk/renderer/app.js", "brief.md", "fixture/mail/messages.json",
        "platform/launch.linux.json", "reset/setup.py", "task.cuabench.json"]
    first = listed["files"][0]
    assert first["url"] == f"{taskpack.RAW}/{REPO}/c1/{task}/apps/desk/main.js"
    assert first["sha256"] == hashlib.sha256(b"apps/desk/main.js\n").hexdigest()
    with pytest.raises(SystemExit, match="isn't there"):
        taskpack.apps(lock, target, bundle / "missing", ("cdb-s02",))


def test_apps_refuses_a_copy_that_doesnt_match_the_lock(github, bundle):
    lock, target = _pinned(bundle)
    (target / "LICENSE").write_text("edited\n")

    with pytest.raises(SystemExit, match="fetch it again"):
        taskpack.apps(lock, target, bundle / "envs", ("cdb-s02",))


@pytest.mark.parametrize("to", ["../outside", "/abs", ""])
def test_an_include_outside_the_task_pack_is_refused(bundle, to):
    (bundle / "taskpack.lock.toml").write_text(LOCK.replace('to = "taskpack"', f'to = "{to}"'))

    with pytest.raises(SystemExit, match="isn't a relative path"):
        taskpack.read_lock(bundle / "taskpack.lock.toml")
