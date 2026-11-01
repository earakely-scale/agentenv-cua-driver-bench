"""The bench task apps, read as a computer reads them at put: each declares the task's files at the lock's commit, its
runtimes, packages, workspace and launch; the files every app shares are the same in each; and the launcher's commands
and lock cleanup."""
import importlib
import json
import sys
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("agentenv_protocol.computer")

from agentenv_protocol.computer._load import load_class  # noqa: E402
from agentenv_protocol.computer.app import ComputerAppEnvironment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TASKS = {"cdb-s02": "CdbS02", "cdb-s03": "CdbS03", "cdb-s04": "CdbS04"}
SHARED = ("bench_app.py", "install.sh")


def _declared(task):
    for name in ("app", "bench_app"):
        sys.modules.pop(name, None)
    return load_class(ROOT / "envs" / task / "app.py", TASKS[task], ComputerAppEnvironment)


@pytest.fixture
def bench_app():
    sys.modules.pop("bench_app", None)
    sys.path.insert(0, str(ROOT / "envs" / "cdb-s02"))
    try:
        yield importlib.import_module("bench_app")
    finally:
        sys.path.remove(str(ROOT / "envs" / "cdb-s02"))
        sys.modules.pop("bench_app", None)


def test_the_files_every_task_app_shares_are_the_same_in_each():
    for name in SHARED:
        assert len({(ROOT / "envs" / task / name).read_bytes() for task in TASKS}) == 1, name


@pytest.mark.parametrize("task", TASKS)
def test_a_task_app_lists_its_tasks_files_at_the_locks_commit(task):
    commit = tomllib.loads((ROOT / "taskpack.lock.toml").read_text())["commit"]
    listed = json.loads((ROOT / "envs" / task / "files.json").read_text())

    assert listed["commit"] == commit
    assert {f["path"].split("/")[0] for f in listed["files"]} <= {"apps", "fixture", "reset", "platform", "brief.md",
                                                                  "task.cuabench.json"}
    assert "platform/launch.linux.json" in {f["path"] for f in listed["files"]}
    for f in listed["files"]:
        assert f["url"].startswith(f"https://raw.githubusercontent.com/trycua/cua/{commit}/libs/cua-driver-bench/"
                                   f"taskpack/tasks/shared/{task}/")
        assert not f["path"].startswith(("tests/", "evaluator/", "tools/"))
        assert not (f["path"].startswith("apps/") and "/tests/" in f["path"])


@pytest.mark.parametrize("task", TASKS)
def test_a_task_app_declares_its_files_runtimes_workspace_and_launch(task):
    declared = _declared(task).declaration()
    linux = declared.os["linux"]
    files = json.loads((ROOT / "envs" / task / "files.json").read_text())["files"]

    tos = [download["to"] for download in linux.install["downloads"]]
    assert tos[:len(files)] == [f"task/{f['path']}" for f in files]
    assert sorted(tos[len(files):]) == sorted(
        ["runtime/electron-amd64.zip", "runtime/electron-arm64.zip",
         *(["runtime/node-amd64.tar.xz", "runtime/node-arm64.tar.xz"] if task == "cdb-s04" else [])])
    apt = linux.install["packages"]["apt"]
    assert ("gnucash" in apt) == (task == "cdb-s03") and ("libreoffice-calc" in apt) == (task != "cdb-s04")
    assert linux.paths == [task]
    assert linux.launch.command == ["venv/bin/python", "bench_app.py"] and linux.launch.at == "boot"
    assert [step.name for step in declared.install_steps] == ["workspace"]
    assert [check.name for check in declared.ready_checks] == ["windows"]


def test_the_launcher_runs_the_apps_runtimes_in_place_of_npx_and_node(bench_app, tmp_path):
    values = {"${bundle}": "/opt/b/task", "${workspace}": "/home/user/cdb-s02", "${workspace_uri}": "file:///x",
              "${python}": "/py"}
    electron = {"id": "mail", "command": ["npx", "electron", ".", "--surface=mail", "--workspace=${workspace}"]}
    node = {"id": "archive", "command": ["node", "server.js"]}
    calc = {"id": "calc", "command": ["libreoffice", "--calc", "${workspace}/planning/a.ods"]}

    assert bench_app._command(electron, values) == [
        str(bench_app.HERE / "runtime/electron/electron"), ".", "--surface=mail", "--workspace=/home/user/cdb-s02",
        "--no-sandbox", "--user-data-dir=/home/user/cdb-s02/.runtime/electron-mail"]
    assert bench_app._command(node, values) == [str(bench_app.HERE / "runtime/node/bin/node"), "server.js"]
    assert bench_app._command(calc, values) == ["libreoffice", "--calc", "/home/user/cdb-s02/planning/a.ods"]
    assert bench_app._sub("${unknown}/x", values) == "${unknown}/x"


def test_the_launcher_matches_a_whole_title_or_part_of_one_literally(bench_app):
    assert bench_app._title({"title": "Copperfield Mail"}) == "^Copperfield Mail$"
    assert bench_app._title({"title_contains": "a.b (1)"}) == r"a\.b \(1\)"


def test_a_launch_removes_the_locks_stopped_apps_left_and_nothing_else(bench_app, tmp_path):
    for name in ("planning/.~lock.replan.ods#", "book/k.gnucash.LCK", "book/k.gnucash.LNK", "book/k.gnucash",
                 "planning/replan.ods", "mail/messages.json"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")

    bench_app._unlock(tmp_path)

    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == [
        "book/k.gnucash", "mail/messages.json", "planning/replan.ods"]
