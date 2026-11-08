"""The trajectory's half of the GUI-only check, offline, with trycua's scan from the fetched task pack in its cache: it
holds for claude-code offered and calling only the computer env's tools and Skill and Read, with no code in a tool
input and no command run through launch_app; a call to a tool the CLI never offered ran nothing; and a trajectory that
isn't claude-code's stream-json can't be checked; codex-cli's events read as trycua's runner reads its Codex arm's.
Also its table: trycua's scan at the lock's commit."""
import asyncio
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"


def _tool(name, /, **tool_input):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


def _init(*tools):
    return {"type": "system", "subtype": "init", "tools": ["Skill", "Read", "mcp__desktop-s02__computer_click", *tools]}


def _trajectory(*calls, offered=()):
    return [[_init(*offered), *calls]]


CLICK = _tool("mcp__desktop-s02__computer_click", x=10, y=20)


@pytest.fixture
def gui_only(tmp_path, monkeypatch):
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    spec = importlib.util.spec_from_file_location("bench_gui_only", ROOT / "artifacts" / "gui_only" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache = tmp_path / "cache"
    cache.mkdir()
    shutil.copy(PACK / "scoring" / "bench_v2.py", cache / module.TRYCUA["bench_v2.py"]["sha256"])
    shutil.copy(PACK / "windows" / "guard.py", cache / module.TRYCUA["guard.py"]["sha256"])
    monkeypatch.setattr(module, "CACHE", cache)

    def verify(trajectory, os=None):
        monkeypatch.setattr(module, "_os", lambda env_url: os)
        return asyncio.run(module.verify("http://mcp", "http://env", trajectory))[0]
    return verify


def test_skills_reading_the_agents_own_files_and_opening_an_app_are_gui_only(gui_only):
    result = gui_only(_trajectory(_tool("Skill", skill="computer"), _tool("Read", file_path="SKILL.md"), CLICK, _tool(
        "mcp__desktop-s02__launch_app", launch_path="/usr/share/applications/libreoffice-calc.desktop")))

    assert result["result"] is True and result["trajectory_checked"] is True


@pytest.mark.parametrize("call, violation", [
    (_tool("Bash", command="ls"), "builtin:Bash"),
    (_tool("WebFetch", url="http://example.com"), "builtin:WebFetch"),
    (_tool("mcp__desktop-s02__type_text", text="bash -c 'cat ~/cdb-s02/x'"), "mcp__desktop-s02__type_text:bash -c"),
], ids=["a forbidden built-in", "another", "code in a tool input"])
def test_a_tool_call_out_of_the_gui_fails(gui_only, call, violation):
    result = gui_only(_trajectory(CLICK, call))

    assert result["result"] is False and violation in result["violations"]


def test_on_windows_a_shell_or_script_host_in_a_tool_input_fails_as_trycuas_windows_guard_scans_it(gui_only):
    call = _tool("mcp__desktop-benchlab-windows__type_text", text="powershell -c Get-ChildItem")

    windows = gui_only(_trajectory(CLICK, call), os="windows")
    linux = gui_only(_trajectory(CLICK, call), os="linux")

    assert windows["result"] is False
    assert "mcp__desktop-benchlab-windows__type_text:powershell" in windows["violations"]
    assert "mcp__desktop-benchlab-windows__type_text:powershell" not in linux["violations"]


@pytest.mark.parametrize("launch, violation", [
    ({"name": "python3", "additional_arguments": ["-c", "open('x', 'w')"]}, "arguments"),
    ({"launch_path": "sed -i s/a/b/ ~/cdb-s02/calendar/events.json"}, "launch_path"),
    ({"name": "/usr/bin/python3"}, "command"),
    ({"name": "xdg-open x; rm y"}, "command"),
], ids=["arguments", "a command as its launch path", "a path as its name", "a shell line as its name"])
def test_a_command_run_through_launch_app_fails(gui_only, launch, violation):
    result = gui_only(_trajectory(_tool("mcp__desktop-s02__launch_app", **launch)))

    assert result["result"] is False and f"mcp__desktop-s02__launch_app:{violation}" in result["violations"]


@pytest.mark.parametrize("launch, violation", [
    ({"app": "TextEdit", "args": ["-NSDocumentRevisionsDebugMode", "YES"]}, "args"),
    ({"app": "Google Chrome", "cdp": 9222}, "cdp"),
    ({"app": "TextEdit", "env": ["DYLD_INSERT_LIBRARIES=/tmp/x.dylib"]}, "env"),
    ({"app": "TextEdit", "cwd": "/Users/lume/cdb-s02"}, "cwd"),
    ({"app": "/bin/sh"}, "command"),
], ids=["arguments", "a devtools port", "an environment", "a working directory", "a path as its app"])
def test_a_command_run_through_agent_desktops_launch_fails_alone_or_in_a_batch(gui_only, launch, violation):
    alone = gui_only(_trajectory(_tool("mcp__desktop-s02-macos-agent-desktop__desktop_launch", **launch)))
    batched = gui_only(_trajectory(_tool("mcp__desktop-s02-macos-agent-desktop__desktop_batch", commands_json=json.dumps(
        [{"command": "snapshot", "args": {"app": "TextEdit"}}, {"command": "launch", "args": launch}]))))

    assert f"mcp__desktop-s02-macos-agent-desktop__desktop_launch:{violation}" in alone["violations"]
    assert f"mcp__desktop-s02-macos-agent-desktop__desktop_batch:launch:{violation}" in batched["violations"]
    assert gui_only(_trajectory(_tool("mcp__desktop-s02-macos-agent-desktop__desktop_launch", app="TextEdit",
                                      activate=True)))["result"] is True


def test_a_built_in_tool_claude_code_was_offered_fails(gui_only):
    assert gui_only(_trajectory(CLICK, offered=["Bash"]))["violations"] == ["offered:Bash"]


def test_a_call_to_a_tool_the_cli_never_offered_ran_nothing(gui_only):
    result = gui_only(_trajectory(CLICK, _tool("computer_click", x=1, y=2), _tool("ToolSearch", query="click")))

    assert result["result"] is True and result["refused_calls"] == {"computer_click": 1, "ToolSearch": 1}


@pytest.mark.parametrize("trajectory", [
    None, [None], [[]], [[CLICK]], [{"format": "claude-code-stream-json/1", "events": [_init(), CLICK]}],
    [[_init(), CLICK], None],
], ids=["none", "none for its turn", "no events", "not claude-code's", "another shape", "a turn without one"])
def test_without_claude_codes_tool_calls_it_doesnt_hold(gui_only, trajectory):
    result = gui_only(trajectory)

    assert result["result"] is False and result["trajectory_checked"] is False


def _codex(*items):
    """codex-cli's exec events for its items, each started and completed, after its thread's start."""
    events = [{"type": "thread.started", "thread_id": "t-1"}, {"type": "turn.started"}]
    for item in items:
        if item == "resume":
            events.append({"type": "thread.started", "thread_id": "t-1"})
            continue
        events += [{"type": "item.started", "item": {**item, "status": "in_progress"}},
                   {"type": "item.completed", "item": {**item, "status": "completed"}}]
    return [events + [{"type": "turn.completed"}, {"type": "agentenv.usage", "model_requests": 2}]]


def _mcp(item_id, tool, **arguments):
    return {"id": item_id, "type": "mcp_tool_call", "server": "desktop-s02", "tool": tool, "arguments": arguments}


def test_codexs_mcp_calls_and_text_are_gui_only_each_call_once_across_a_resumed_run(gui_only):
    trajectory = _codex({"id": "item_0", "type": "reasoning", "text": "look first"},
                        _mcp("item_1", "launch_app", launch_path="/usr/share/applications/libreoffice-calc.desktop"),
                        "resume", _mcp("item_1", "launch_app", name="bash -c 'cat ~/x'"),
                        {"id": "item_2", "type": "agent_message", "text": "done"})

    result = gui_only(trajectory)

    assert (result["result"], result["trajectory_checked"], result["refused_calls"]) == (False, True, {})
    assert result["violations"] == ["mcp__desktop-s02__launch_app:bash -c"]
    assert gui_only(_codex(_mcp("item_0", "click", x=1, y=2)))["result"] is True


@pytest.mark.parametrize("item, violation", [
    ({"type": "command_execution", "command": "ls ~"}, "builtin:Bash"),
    ({"type": "file_change", "changes": [{"path": "/app/x", "kind": "add"}]}, "builtin:Edit"),
    ({"type": "web_search", "query": "calendar"}, "builtin:WebSearch"),
    ({"type": "collab_tool_call", "tool": "spawn_agent"}, "builtin:Agent"),
    ({"type": "image_generation"}, "builtin:Task"),
], ids=["shell", "patch", "web search", "sub-agent", "any other item"])
def test_codexs_own_tools_fail_as_trycuas_runner_reads_them(gui_only, item, violation):
    result = gui_only(_codex(_mcp("item_0", "click", x=1, y=2), {"id": "item_1", **item}))

    assert (result["result"], result["violations"]) == (False, [violation])


def test_its_table_pins_trycuas_scan_at_the_locks_commit():
    spec = importlib.util.spec_from_file_location("bench_gui_only", ROOT / "artifacts" / "gui_only" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    manifest = dict(reversed(line.split("  ", 1)) for line in (PACK / "MANIFEST.sha256").read_text().splitlines())

    assert f'commit = "{module.TRYCUA["commit"]}"' in (ROOT / "taskpack.lock.toml").read_text()
    assert module.TRYCUA["bench_v2.py"]["sha256"] == manifest["scoring/bench_v2.py"]
    assert module.TRYCUA["bench_v2.py"]["url"].startswith(
        f"https://raw.githubusercontent.com/trycua/cua/{module.TRYCUA['commit']}/")
    assert module.TRYCUA["guard.py"]["sha256"] == manifest["windows/guard.py"]
    assert module.TRYCUA["guard.py"]["url"].endswith("/automated-eval/macos_bench/windows/guard.py")
