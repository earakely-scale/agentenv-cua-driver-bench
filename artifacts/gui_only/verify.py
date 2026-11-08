"""The trajectory's half of the bench's GUI-only check, outside the computer: trycua's scan of the agent's tool calls
(their ``bench_v2``, fetched at the lock's commit and checked against its sha256, as ``TRYCUA`` pins it, written by
``python tools/taskpack.py grader``), on claude-code's stream-json, or codex-cli's exec events read as trycua's runner
reads its Codex arm's: its own tools as the built-ins trycua forbids; the grade in its container is the guard's half.

It holds when claude-code was offered no built-in tool but Skill and Read beside the computer env's, tried none trycua
forbids, put no code in a tool input, and ran no command through cua-driver's ``launch_app``, which on Linux runs one
where macOS's opens apps only, nor through agent-desktop's ``launch``, alone or in a batch. A trial whose agent's trajectory the verifier isn't given, or is neither claude-code's
stream-json nor codex-cli's events, doesn't hold, since its tool calls can't be checked. Codex's events don't list the
tools it was offered: that its own were off rests on the task's agent step, which deploy checks against its card."""
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import urllib.request
from pathlib import Path

#: The built-in tools besides the computer env's that a GUI-only claude-code keeps, trycua's less the tool search its
#: CLI hasn't: its skills, and Read, which reads only the agent's own container, never the computer.
ALLOWED_BUILTINS = ("Skill", "Read")
CACHE = Path.home() / ".cache" / "agentenv-cua-driver-bench"
#: codex-cli's items that are tool calls of its own, as the built-in trycua's runner maps each to, with the field it
#: passes on; an item neither these, an MCP call nor text is a ``Task``, as trycua's runner fails closed on it.
CODEX_TOOLS = {"command_execution": ("Bash", "command"), "file_change": ("Edit", "changes"),
               "web_search": ("WebSearch", "query"), "collab_tool_call": ("Agent", None)}
CODEX_TEXT = ("agent_message", "reasoning", "todo_list", "error")
#: A launch_app name that a shell would read as more than an app's name.
_COMMAND = re.compile(r"[;|&$`<>]|^[/.~]")

TRYCUA = {
 "commit": "69b459b33ca001a5e7026dee4f57da1ec02ee53f",
 "bench_v2.py": {
  "url": "https://raw.githubusercontent.com/trycua/cua/69b459b33ca001a5e7026dee4f57da1ec02ee53f/libs/cua-driver-bench/automated-eval/macos_bench/bench_v2.py",
  "sha256": "204eaeadb97b2f20225bd99f52b706d26a11aaec270ee364f3fb3def25446727"
 }
}


async def verify(mcp_url, env_url, trajectory=None):
    with tempfile.TemporaryDirectory() as scratch:
        v2 = _module(_fetched(TRYCUA["bench_v2.py"], Path(scratch) / "bench_v2.py"))
    events = _events(trajectory)
    violations, mentions = _scan(v2, events or [])
    return [{"id": "gui_only_trajectory", "result": bool(events) and not violations, "violations": violations,
             "trajectory_checked": bool(events), "refused_calls": _refused(v2, events or []), "mentions": mentions,
             "description": "no way out of the GUI in the agent's tool calls"}]


def _events(trajectory):
    """claude-code's stream-json events, every turn's document a list of them that opens with the CLI's init, or
    codex-cli's tool calls as claude-code's, every turn's document its exec events from its thread's start; None
    without one, since the scan reads claude-code's tool calls and can't vouch for a turn it can't read."""
    documents = list(trajectory or [])
    if documents and all(_opens(document, ("thread.started", None)) for document in documents):
        return [event for document in documents for event in _codex_calls(document)]
    if not documents or not all(_opens(document, ("system", "init")) for document in documents):
        return None
    return [event for document in documents for event in document]


def _opens(document, kind):
    return (isinstance(document, list) and bool(document) and isinstance(document[0], dict)
            and (document[0].get("type"), document[0].get("subtype")) == kind)


def _codex_calls(document):
    """codex-cli's tool calls as claude-code's assistant events: an MCP call as ``mcp__SERVER__TOOL``, its own tools as
    CODEX_TOOLS maps them. Each item once, by its id within its CLI run, which numbers them afresh (a turn resumed
    after a transient error runs the CLI again, from a thread.started of its own)."""
    seen, run, calls = set(), 0, []
    for event in document:
        run += event.get("type") == "thread.started"
        item = event.get("item") if event.get("type") in ("item.started", "item.completed") else None
        if not isinstance(item, dict) or item.get("type") in CODEX_TEXT or (run, item.get("id")) in seen:
            continue
        seen.add((run, item.get("id")))
        if item.get("type") == "mcp_tool_call":
            name, tool_input = f"mcp__{item.get('server')}__{item.get('tool')}", item.get("arguments")
        else:
            name, field = CODEX_TOOLS.get(item.get("type"), ("Task", None))
            tool_input = {field: item.get(field)} if field else item
        calls.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name,
                                                                     "input": tool_input}]}})
    return calls


def _scan(v2, events):
    """trycua's scan, a forbidden built-in tried or code in a tool input; any built-in the CLI offered beside the
    computer env's tools and Skill and Read; and launch_app running a command: with arguments, a launch path that isn't
    an app's .desktop file, or a name a shell would read as more than an app's. A call to a tool the CLI never offered
    ran nothing, so it isn't one, unless trycua forbids it. The violations, and the side doors merely named."""
    hard, soft = v2.scan_events(events)
    offered = {f"offered:{name}" for event in events if (event.get("type"), event.get("subtype")) == ("system", "init")
               for name in event.get("tools") or [] if not name.startswith("mcp__") and name not in ALLOWED_BUILTINS}
    launches = set()
    for name, tool_input in (call for event in events for call in v2.tool_uses(event)):
        if name.endswith("__launch_app") and isinstance(tool_input, dict):
            if tool_input.get("additional_arguments"):
                launches.add(f"{name}:arguments")
            if tool_input.get("launch_path") and not str(tool_input["launch_path"]).endswith(".desktop"):
                launches.add(f"{name}:launch_path")
            if _COMMAND.search(str(tool_input.get("name") or "")):
                launches.add(f"{name}:command")
        if name.endswith("__desktop_launch") and isinstance(tool_input, dict):
            launches |= {f"{name}:{how}" for how in _desktop_launch(tool_input)}
        if name.endswith("__desktop_batch") and isinstance(tool_input, dict):
            launches |= {f"{name}:launch:{how}" for command in _batch(tool_input) if command.get("command") == "launch"
                         for how in _desktop_launch(command.get("args") or {})}
    return sorted({*hard, *offered, *launches}), soft


def _desktop_launch(tool_input):
    """How agent-desktop's launch ran a command rather than opened an app, as cua-driver's launch_app is judged: with
    arguments, a DevTools port, an environment or a working directory of its own, or a name a shell would read as more
    than an app's."""
    found = [how for how in ("args", "cdp", "env", "cwd") if tool_input.get(how) not in (None, [], "")]
    return found + (["command"] if _COMMAND.search(str(tool_input.get("app") or "")) else [])


def _batch(tool_input):
    """The commands an agent-desktop batch carries, from its ``commands_json``."""
    try:
        commands = json.loads(tool_input.get("commands_json") or "[]")
    except ValueError:
        return []
    return [command for command in commands if isinstance(command, dict)] if isinstance(commands, list) else []


def _refused(v2, events):
    """The tools the agent called that the CLI never offered it, which ran nothing, with how often; none for Codex,
    whose events don't say what it was offered."""
    offered = {name for event in events if (event.get("type"), event.get("subtype")) == ("system", "init")
               for name in event.get("tools") or []}
    if not offered:
        return {}
    refused = {}
    for event in events:
        for name, _ in v2.tool_uses(event):
            if name not in offered:
                refused[name] = refused.get(name, 0) + 1
    return refused


def _module(path):
    spec = importlib.util.spec_from_file_location("trycua_bench_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fetched(pinned, path):
    """``pinned``'s file at ``path``, from the cache or its URL, checked against its sha256 either way; the cache is
    written whole, under its name only once complete, so trials grading at once read it whole."""
    cached = CACHE / pinned["sha256"]
    data = cached.read_bytes() if cached.exists() else b""
    if hashlib.sha256(data).hexdigest() != pinned["sha256"]:
        with urllib.request.urlopen(pinned["url"], timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != pinned["sha256"]:
            raise RuntimeError(f"{pinned['url']} isn't the file the lock pins")
        CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as part:
            part.write(data)
        os.replace(part.name, cached)
    path.write_bytes(data)
    return path
