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
    windows = [app["window"] for app in spec["apps"] if "window" in app]
    rpc = _rpc(f"{input['env']['url']}/svc/{task}/agentenv", input["env"]["headers"])
    report = {"pristine_at_boot": _pristine(task, workspace), "windows_at_boot": _shown_all(windows, 5),
              "one_of_each_window_at_boot": _one_each(windows), "placed_at_boot": _placed(windows, 60),
              "no_tip_dialogs": not _search(r"Tip [Oo]f [Tt]he Day")}
    launcher = _launchers(task)

    rpc("data/add", {"parts": [{"kind": "file", "file": {"bytes": base64.b64encode(b"a note\n").decode()},
                                "metadata": {DATA_OBJECTS: {"path": f"{task}/{NOTE}"}}}]})
    report["loaded"] = (workspace / NOTE).read_text() == "a note\n"
    started = time.monotonic()
    rpc("data/reset", {})
    report["reset_s"] = round(time.monotonic() - started, 1)
    report["reset_removed"] = not (workspace / NOTE).exists()
    report["pristine_after_reset"] = _pristine(task, workspace)
    report["windows_after_reset"] = _shown_all(windows, 180)
    report["one_of_each_window_after_reset"] = _one_each(windows)
    report["placed_after_reset"] = _placed(windows, 90)
    relaunched = _launchers(task)
    report["one_launcher_before_and_after"] = len(launcher) == 1 and len(relaunched) == 1
    report["launcher_relaunched"] = launcher.isdisjoint(relaunched)
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
        missing = [window for window, ids in zip(windows, _claimed(windows)) if not ids]
        if not missing or time.monotonic() > deadline:
            if missing:
                print("not shown:", missing)
            return not missing
        time.sleep(2)


def _one_each(windows):
    counts = [len(ids) for ids in _claimed(windows)]
    if any(count != 1 for count in counts):
        print("windows by match:", list(zip([json.dumps(w) for w in windows], counts)))
    return all(count == 1 for count in counts)


def _placed(windows, wait_s):
    """Whether each window with bounds has their size and, give or take the window manager's frame, their place."""
    deadline = time.monotonic() + wait_s
    while True:
        off = [(window["bounds"], _geometry(ids[0]) if ids else None)
               for window, ids in zip(windows, _claimed(windows)) if window.get("bounds")
               and not (ids and _at(_geometry(ids[0]), window["bounds"]))]
        if not off or time.monotonic() > deadline:
            if off:
                print("not at their bounds:", off)
            return not off
        time.sleep(2)


def _claimed(windows):
    """Each window's matching shown windows, one matched by more than one belonging to the most specific match: a
    whole title first, then the longest part of one, as the task app's launcher claims them."""
    order = sorted(range(len(windows)), key=lambda i: ("title" not in windows[i],
                                                       -len(windows[i].get("title_contains", ""))))
    taken, found = set(), [[] for _ in windows]
    for i in order:
        title = windows[i].get("title")
        found[i] = [wid for wid in _search(f"^{_literal(title)}$" if title else _literal(windows[i]["title_contains"]))
                    if wid not in taken]
        taken.update(found[i])
    return found


def _search(pattern):
    return subprocess.run(["xdotool", "search", "--onlyvisible", "--name", pattern],
                          capture_output=True, text=True).stdout.split()


def _geometry(wid):
    shell = subprocess.run(["xdotool", "getwindowgeometry", "--shell", wid], capture_output=True, text=True).stdout
    return {key: int(value) for key, value in (line.split("=", 1) for line in shell.split()) if key != "SCREEN"}


def _at(geometry, bounds):
    return (abs(geometry.get("WIDTH", 0) - bounds["width"]) <= 8 and abs(geometry.get("HEIGHT", 0) - bounds["height"]) <= 8
            and abs(geometry.get("X", -999) - bounds["x"]) <= 40 and abs(geometry.get("Y", -999) - bounds["y"]) <= 60)


def _launchers(task):
    """The pids of the task app's launcher, which runs from its folder as bench_app.py."""
    found = subprocess.run(["pgrep", "-f", f"{APPS / task}.*bench_app.py|venv/bin/python bench_app.py"],
                           capture_output=True, text=True)
    return {pid for pid in found.stdout.split() if _cwd(pid) == APPS / task}


def _cwd(pid):
    try:
        return Path(f"/proc/{pid}/cwd").resolve()
    except OSError:
        return None


def _literal(text):
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", text)
