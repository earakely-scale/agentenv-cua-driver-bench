"""The trajectory's half of the bench's GUI-only check, outside the computer: trycua's scan of the agent's tool calls
(their ``bench_v2``, fetched at the lock's commit and checked against its sha256, as ``TRYCUA`` pins it, written by
``python tools/taskpack.py grader``), on claude-code's stream-json; the grade in its container is the guard's half.

It holds when claude-code was offered no built-in tool but Skill and Read beside the computer env's, tried none trycua
forbids, put no code in a tool input, and ran no command through cua-driver's ``launch_app``, which on Linux runs one
where macOS's opens apps only. A trial whose agent's trajectory the verifier isn't given, or isn't claude-code's
stream-json, doesn't hold, since its tool calls can't be checked."""
import hashlib
import importlib.util
import os
import re
import tempfile
import urllib.request
from pathlib import Path

#: The built-in tools besides the computer env's that a GUI-only claude-code keeps, trycua's less the tool search its
#: CLI hasn't: its skills, and Read, which reads only the agent's own container, never the computer.
ALLOWED_BUILTINS = ("Skill", "Read")
CACHE = Path.home() / ".cache" / "agentenv-cua-driver-bench"
#: A launch_app name that a shell would read as more than an app's name.
_COMMAND = re.compile(r"[;|&$`<>]|^[/.~]")

TRYCUA = {
 "commit": "6c0a8c3bb2d32580c3231592f60739c33edc567a",
 "bench_v2.py": {
  "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/automated-eval/macos_bench/bench_v2.py",
  "sha256": "c3f73c0360dd4369c5e21458e23c0098f36a27b21d948e8c3bd25aabe6223a49"
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
    """claude-code's stream-json events, every turn's document a list of them that opens with the CLI's init; None
    without one, since the scan reads claude-code's tool calls and can't vouch for a turn it can't read."""
    documents = list(trajectory or [])
    if not documents or not all(isinstance(document, list) and document and isinstance(document[0], dict)
                                and (document[0].get("type"), document[0].get("subtype")) == ("system", "init")
                                for document in documents):
        return None
    return [event for document in documents for event in document]


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
    return sorted({*hard, *offered, *launches}), soft


def _refused(v2, events):
    """The tools the agent called that the CLI never offered it, which ran nothing, with how often."""
    offered = {name for event in events if (event.get("type"), event.get("subtype")) == ("system", "init")
               for name in event.get("tools") or []}
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
