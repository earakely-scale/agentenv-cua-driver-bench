"""The bench's grade, offline, with trycua's files from the fetched task pack in its cache: trycua's evaluator runs on the
workspace the task's app returns, here the task's untouched one, which fails; GUI-only holds only for a trajectory of
the computer env's tools, with no code in them, and no violation from the guard; and the background condition adds
trycua's A22 criteria, the foreground none. Also its table: every trycua file it fetches, at the lock's commit."""
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_sentinel import Run, sentinel_module  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"
TASK = PACK / "taskpack" / "tasks" / "shared" / "cdb-s02"


def _tool(name, **tool_input):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


CLICK = _tool("mcp__desktop-s02__computer_click", x=10, y=20)


@pytest.fixture
def grader(tmp_path, monkeypatch):
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    cache = tmp_path / "cache"
    cache.mkdir()
    for line in (PACK / "MANIFEST.sha256").read_text().splitlines():
        sha, name = line.split("  ", 1)
        shutil.copy(PACK / name, cache / sha)
    sys.path.insert(0, str(ROOT / "artifacts" / "grade"))
    try:
        module = importlib.import_module("verify")
        monkeypatch.setattr(module, "CACHE", cache)
        yield module
    finally:
        sys.path.remove(str(ROOT / "artifacts" / "grade"))
        sys.modules.pop("verify", None)


def _home(tmp_path, run, condition="background"):
    home = tmp_path / "home"
    subprocess.run([sys.executable, "reset/setup.py", "--workspace", str(home / "cdb-s02")], cwd=TASK, check=True)
    log = home / ".bench-sentinel" / "sentinel.jsonl"
    log.parent.mkdir(parents=True)
    lines = [json.loads(line) for line in run.lines]
    lines[0]["condition"] = condition
    log.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return home


def _results(grader, tmp_path, run, trajectory, condition="background"):
    home = _home(tmp_path, run, condition)
    return {result["id"]: result for result in grader.grade("cdb-s02", home, tmp_path / "scratch", trajectory)}


def test_an_untouched_workspace_fails_trycuas_evaluator_and_a_quiet_gui_only_trial_holds_the_rest(
        grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), [[CLICK]])

    assert results["task"]["result"] is False and results["task"]["checks"]["mail_preserved"] is True
    assert results["gui_only"] == {**results["gui_only"], "result": True, "violations": [], "trajectory_checked": True}
    assert results["user_undisturbed"]["result"] is True and results["user_undisturbed"]["unmeasured"] == []
    assert results["user_undisturbed"]["background_completion"] is False


@pytest.mark.parametrize("call, violation", [
    (_tool("Bash", command="ls"), "builtin:Bash"),
    (_tool("Read", file_path="/etc/passwd"), "builtin:Read"),
    (_tool("mcp__desktop-s02__type_text", text="bash -c 'cat ~/cdb-s02/x'"), "mcp__desktop-s02__type_text:bash -c"),
], ids=["a forbidden built-in", "any other built-in", "code in a tool input"])
def test_a_tool_call_out_of_the_gui_fails_gui_only(grader, sentinel_module, tmp_path, call, violation):
    trajectory = [{"format": "claude-code-stream-json/1", "events": [CLICK, call]}]

    gui_only = _results(grader, tmp_path, Run(sentinel_module).trial(), trajectory)["gui_only"]

    assert gui_only["result"] is False and violation in gui_only["violations"]


def test_skills_and_tool_search_are_gui_only(grader, sentinel_module, tmp_path):
    trajectory = [[_tool("Skill", skill="computer"), _tool("ToolSearch", query="click"), CLICK]]

    assert _results(grader, tmp_path, Run(sentinel_module).trial(), trajectory)["gui_only"]["result"] is True


def test_a_violation_the_guard_logged_fails_gui_only(grader, sentinel_module, tmp_path):
    run = Run(sentinel_module)
    run.trial(lambda run: run.processes.append((50, "xterm", 0)))

    assert _results(grader, tmp_path, run, [[CLICK]])["gui_only"]["violations"] == ["process:xterm"]


def test_without_the_agents_trajectory_a_trial_isnt_gui_only(grader, sentinel_module, tmp_path):
    gui_only = _results(grader, tmp_path, Run(sentinel_module).trial(), None)["gui_only"]

    assert gui_only["result"] is False and gui_only["trajectory_checked"] is False


def test_the_foreground_has_no_a22_result(grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module, background=False).trial(), [[CLICK]], "foreground")

    assert set(results) == {"task", "gui_only"}


def test_its_table_pins_each_trycua_file_it_fetches_at_the_locks_commit(grader):
    lock = (ROOT / "taskpack.lock.toml").read_text()
    manifest = {name: sha for sha, name in (line.split("  ", 1)
                                            for line in (PACK / "MANIFEST.sha256").read_text().splitlines())}

    assert f'commit = "{grader.TRYCUA["commit"]}"' in lock
    for task, files in grader.TRYCUA["tasks"].items():
        assert "evaluator/evaluate.py" in files and "evaluator/oracle.json" in files
        for name, pinned in files.items():
            assert manifest[f"taskpack/tasks/shared/{task}/{name}"] == pinned["sha256"]
            assert pinned["url"].startswith(f"https://raw.githubusercontent.com/trycua/cua/{grader.TRYCUA['commit']}/")
    assert {name: pinned["sha256"] for name, pinned in grader.TRYCUA["scoring"].items()} == {
        "summarize_sentinel.py": manifest["scoring/summarize_sentinel.py"], "bench_v2.py": manifest["scoring/bench_v2.py"]}
