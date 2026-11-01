"""Inside a bench task's computer, run as its session user: the task's workspace checks out against the task's own
fixture with trycua's verify.py, apart from what its open apps write there; a file the task app's data plane is given
lands in the workspace; a reset through the driver takes it away and opens every window again; and the data plane
returns the workspace. ``args``: ``task``, the app's name, which is its workspace's too."""
import base64
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

APPS = Path("/opt/agentenv/apps")
DATA_OBJECTS = "urn:agentenv:data-objects/v1"
NOTE = "agent-note.txt"


def run(input):
    task = input["args"]["task"]
    workspace, spec = Path.home() / task, json.loads((APPS / task / "task/platform/launch.linux.json").read_text())
    windows = [app["window"] for app in spec["apps"] if app["kind"] != "browser" and "window" in app]
    rpc = _rpc(f"{input['env']['url']}/svc/{task}/agentenv", input["env"]["headers"])
    report = {"pristine_at_boot": _pristine(task, workspace), "windows_at_boot": _shown_all(windows, 5)}

    rpc("data/add", {"parts": [{"kind": "file", "file": {"bytes": base64.b64encode(b"a note\n").decode()},
                                "metadata": {DATA_OBJECTS: {"path": f"{task}/{NOTE}"}}}]})
    report["loaded"] = (workspace / NOTE).read_text() == "a note\n"
    rpc("data/reset", {})
    report["reset_removed"] = not (workspace / NOTE).exists()
    report["pristine_after_reset"] = _pristine(task, workspace)
    report["windows_after_reset"] = _shown_all(windows, 180)
    parts = rpc("data/get", {})["parts"]
    exported = {part["metadata"][DATA_OBJECTS]["path"] for part in parts}
    report["exported"] = len(exported)
    report["facts_exported"] = f"{task}/{task}.workspace.json" in exported

    failed = sorted(key for key, value in report.items() if value is False)
    if failed:
        raise AssertionError(f"{task}: {', '.join(failed)} failed: {json.dumps(report)}")
    return report


def _rpc(url, headers):
    def call(method, params):
        request = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                                               "params": params}).encode(),
                                         headers={"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.load(response)
        if "error" in body:
            raise AssertionError(f"{method}: {body['error']}")
        return body["result"]
    return call


def _pristine(task, workspace):
    """Whether verify.py passes on the workspace less what the task's running apps write into it: their runtime
    folder, LibreOffice's and GnuCash's locks, and GnuCash's logs and backups beside the book."""
    with tempfile.TemporaryDirectory() as copy:
        shutil.copytree(workspace, copy, dirs_exist_ok=True, ignore=_written_by_apps)
        result = subprocess.run(["python3", "reset/verify.py", "--workspace", copy], cwd=APPS / task / "task",
                                capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, result.stderr)
    return result.returncode == 0


def _written_by_apps(folder, names):
    return [name for name in names if name == ".runtime" or re.fullmatch(r"\.~lock\..*#", name)
            or name.endswith((".LCK", ".LNK")) or re.search(r"\.gnucash\.\d{14}\.(log|gnucash)$", name)]


def _shown_all(windows, wait_s):
    deadline = time.monotonic() + wait_s
    while True:
        missing = [window for window in windows if not _shown(window)]
        if not missing or time.monotonic() > deadline:
            if missing:
                print("not shown:", missing)
            return not missing
        time.sleep(2)


def _shown(window):
    title = window.get("title")
    pattern = f"^{_literal(title)}$" if title else _literal(window["title_contains"])
    return subprocess.run(["xdotool", "search", "--onlyvisible", "--name", pattern],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _literal(text):
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", text)
