"""The bench's grade, offline, with trycua's files from the fetched task pack in its cache: trycua's evaluator runs on the
workspace the task's app returns, here the task's untouched one, which fails; GUI-only holds only for a trajectory of
the computer env's tools, with no code in them, and no violation from the guard; the background condition adds
trycua's A22 criteria, the foreground none; and a workspace solved as trycua's own tests solve it, by a trial that left
the user undisturbed in the GUI, is a background completion. Also its table: every trycua file it fetches, at the lock's commit."""
import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_sentinel import OTHER, Run, sentinel_module  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"
TASK = PACK / "taskpack" / "tasks" / "shared" / "cdb-s02"


def _tool(name, /, **tool_input):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


CLICK = _tool("mcp__desktop-s02__computer_click", x=10, y=20)


def _init(*tools):
    return {"type": "system", "subtype": "init", "tools": ["Skill", "Read", "mcp__desktop-s02__computer_click", *tools]}


def _trajectory(*calls, offered=()):
    return [[_init(*offered), *calls]]


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


def _home(tmp_path, run, condition="background", solved=False, edit=None):
    home = tmp_path / "home"
    if solved:
        shutil.copytree(_solved(tmp_path / "solving"), home / "cdb-s02")
    else:
        subprocess.run([sys.executable, "reset/setup.py", "--workspace", str(home / "cdb-s02")], cwd=TASK, check=True)
    log = home / ".bench-sentinel" / "sentinel.jsonl"
    log.parent.mkdir(parents=True)
    lines = [json.loads(line) for line in run.lines]
    if condition is not None:
        lines[0]["condition"] = condition
    log.write_text("".join(json.dumps(line) + "\n" for line in (edit or (lambda lines: lines))(lines)))
    return home


def _solved(scratch):
    """The task's workspace as trycua's own tests of their evaluator solve it."""
    spec = importlib.util.spec_from_file_location("trycua_test_cdb_s02", TASK / "tests" / "test_cdb_s02.py")
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    scratch.mkdir()
    workspace = tests.Workspace(scratch)
    workspace.complete()
    return workspace.root


def _results(grader, tmp_path, run, trajectory, condition="background", solved=False, edit=None):
    home = _home(tmp_path, run, condition, solved, edit)
    return {result["id"]: result for result in grader.grade("cdb-s02", home, tmp_path / "scratch", trajectory)}


def test_an_untouched_workspace_fails_trycuas_evaluator_and_a_quiet_gui_only_trial_holds_the_rest(
        grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), _trajectory(CLICK))

    assert results["task"]["result"] is False and results["task"]["checks"]["mail_preserved"] is True
    assert results["gui_only"] == {**results["gui_only"], "result": True, "violations": [], "trajectory_checked": True}
    assert results["user_undisturbed"]["result"] is True and results["user_undisturbed"]["unmeasured"] == []
    assert results["user_undisturbed"]["background_completion"] is False


def test_a_solved_trial_that_left_the_user_undisturbed_in_the_gui_is_a_background_completion(
        grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), _trajectory(CLICK), solved=True)

    assert results["task"]["result"] is True and results["task"]["score"] == 1.0
    assert all(result["result"] for result in results.values())
    assert results["user_undisturbed"]["background_completion"] is True


def test_a_solved_trial_that_took_the_users_focus_is_not_a_background_completion(grader, sentinel_module, tmp_path):
    def steal(run):
        run.desktop.active_window = run.desktop.focus_window = OTHER
        run.sentinel.focus_changed(False)
        run.sentinel.changed("active", OTHER)

    results = _results(grader, tmp_path, Run(sentinel_module).trial(steal), _trajectory(CLICK), solved=True)

    assert results["task"]["result"] is True and results["gui_only"]["result"] is True
    assert results["user_undisturbed"]["result"] is False
    assert {key for key, held in results["user_undisturbed"]["criteria"].items() if not held} == {
        "key_focus", "typing", "activation"}


@pytest.mark.parametrize("call, violation", [
    (_tool("Bash", command="ls"), "builtin:Bash"),
    (_tool("WebFetch", url="http://example.com"), "builtin:WebFetch"),
    (_tool("ToolSearch", query="terminal"), "builtin:ToolSearch"),
    (_tool("mcp__desktop-s02__type_text", text="bash -c 'cat ~/cdb-s02/x'"), "mcp__desktop-s02__type_text:bash -c"),
], ids=["a forbidden built-in", "any other built-in", "tool search", "code in a tool input"])
def test_a_tool_call_out_of_the_gui_fails_gui_only(grader, sentinel_module, tmp_path, call, violation):
    trajectory = _trajectory(CLICK, call)

    gui_only = _results(grader, tmp_path, Run(sentinel_module).trial(), trajectory)["gui_only"]

    assert gui_only["result"] is False and violation in gui_only["violations"]


def test_skills_reading_the_agents_own_files_and_opening_an_app_are_gui_only(grader, sentinel_module, tmp_path):
    trajectory = _trajectory(_tool("Skill", skill="computer"), _tool("Read", file_path="SKILL.md"), CLICK, _tool(
        "mcp__desktop-s02__launch_app", launch_path="/usr/share/applications/libreoffice-calc.desktop"))

    assert _results(grader, tmp_path, Run(sentinel_module).trial(), trajectory)["gui_only"]["result"] is True


def test_a_violation_the_guard_logged_fails_gui_only(grader, sentinel_module, tmp_path):
    run = Run(sentinel_module)
    run.trial(lambda run: run.processes.append((50, "xterm", 0)))

    assert _results(grader, tmp_path, run, _trajectory(CLICK))["gui_only"]["violations"] == ["process:xterm"]


@pytest.mark.parametrize("trajectory", [
    None, [None], [[]], [[CLICK]], [{"format": "claude-code-stream-json/1", "events": [_init(), CLICK]}],
    [[_init(), CLICK], None],
], ids=["none", "none for its turn", "no events", "not claude-code's", "another shape", "a turn without one"])
def test_without_claude_codes_tool_calls_a_trial_isnt_gui_only(grader, sentinel_module, tmp_path, trajectory):
    gui_only = _results(grader, tmp_path, Run(sentinel_module).trial(), trajectory)["gui_only"]

    assert gui_only["result"] is False and gui_only["trajectory_checked"] is False


@pytest.mark.parametrize("launch, violation", [
    ({"name": "python3", "additional_arguments": ["-c", "open('x', 'w')"]}, "arguments"),
    ({"launch_path": "sed -i s/a/b/ ~/cdb-s02/calendar/events.json"}, "launch_path"),
    ({"name": "/usr/bin/python3"}, "command"),
    ({"name": "xdg-open x; rm y"}, "command"),
], ids=["arguments", "a command as its launch path", "a path as its name", "a shell line as its name"])
def test_a_command_run_through_launch_app_fails_gui_only(grader, sentinel_module, tmp_path, launch, violation):
    trajectory = _trajectory(_tool("mcp__desktop-s02__launch_app", **launch))

    gui_only = _results(grader, tmp_path, Run(sentinel_module).trial(), trajectory)["gui_only"]

    assert gui_only["result"] is False and f"mcp__desktop-s02__launch_app:{violation}" in gui_only["violations"]


def test_a_built_in_tool_claude_code_was_offered_fails_gui_only(grader, sentinel_module, tmp_path):
    gui_only = _results(grader, tmp_path, Run(sentinel_module).trial(), _trajectory(CLICK, offered=["Bash"]))["gui_only"]

    assert gui_only["violations"] == ["offered:Bash"]


@pytest.mark.parametrize("edit, problem", [
    (lambda lines: [line for line in lines if line["ev"] != "disarmed"], "stopped before it was disarmed"),
    (lambda lines: [line for line in lines if line["ev"] != "armed" and not line["armed"]], "never armed"),
    (lambda lines: [*lines[:-2], {"ev": "sample_error", "t": lines[-2]["t"], "armed": True, "error": "BadAtom"},
                    *lines[-2:]], "a sample failed: BadAtom"),
], ids=["not disarmed", "never armed", "a sample failed"])
def test_a_log_that_doesnt_show_the_whole_trial_fails_the_grade(grader, sentinel_module, tmp_path, edit, problem):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), _trajectory(CLICK), edit=edit)

    assert results["sentinel"]["result"] is False and any(problem in p for p in results["sentinel"]["problems"])
    assert results["gui_only"]["result"] is False and results["user_undisturbed"]["result"] is False


def test_a_sentinel_without_a_condition_fails_the_grade(grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), _trajectory(CLICK), condition=None)

    assert results["sentinel"]["problems"] == ["the sentinel's condition is None"]


def test_the_users_window_asked_to_close_disturbs_the_user(grader, sentinel_module, tmp_path):
    run = Run(sentinel_module).trial(lambda run: run.sentinel.emit("close_refused"))

    undisturbed = _results(grader, tmp_path, run, _trajectory(CLICK))["user_undisturbed"]

    assert undisturbed["result"] is False and undisturbed["close_refused"] == 1


def test_the_node_the_grade_fetches_is_the_one_cdb_s04_pins(grader):
    pinned = (ROOT / "envs" / "cdb-s04" / "bench_app.py").read_text()

    assert f'NODE = "{grader.NODE}"' in pinned and all(sha in pinned for sha in grader.NODE_SHA256.values())


def test_the_foreground_has_no_a22_result(grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module, background=False).trial(), _trajectory(CLICK), "foreground")

    assert set(results) == {"sentinel", "task", "gui_only"}


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
