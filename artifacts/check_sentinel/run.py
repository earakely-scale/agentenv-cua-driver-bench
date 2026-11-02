"""Inside a bench task's computer with the bench's sentinel, run as its session user once the task pack is loaded into
``~/bench``: the sentinel's window is its condition's, with its title and outer frame; trycua's own summarizer and A22
criteria, from the task pack, find each disturbance caused on purpose in its own criterion and a quiet window and
background actions in none, with every criterion measured; and the sentinel's data plane returns its log, which a reset
starts afresh. ``args``: ``condition``, the sentinel's, and ``other``, the title of a task window to disturb it with."""
import base64
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path.home() / "bench" / "scoring"))
import bench_v2  # noqa: E402
import summarize_sentinel  # noqa: E402

APP = Path("/opt/agentenv/apps/bench-sentinel")
LOG = Path.home() / ".bench-sentinel" / "sentinel.jsonl"
LOG_PATH = ".bench-sentinel/sentinel.jsonl"
DATA_OBJECTS = "urn:agentenv:data-objects/v1"
USER_FRAME = (420, 340, 900, 520)
WITNESS = (360, 140, 24)
WAIT_S = 30.0
SETTLE_S = 3.0


def run(input):
    args = input["args"]
    background = args["condition"] == "background"
    log = Log(LOG)
    user = _window(lambda wm_class, title: wm_class.endswith(".BenchSentinel"))
    frame = _frame(user)
    report = {"title": _title(user), "frame": frame, "expected_frame": USER_FRAME if background else _witness()}
    report["title_ok"] = report["title"] == ("User activity" if background else "Bench Sentinel")
    report["frame_ok"] = all(abs(a - b) <= 4 for a, b in zip(frame, report["expected_frame"]))
    if background:
        other = _window(lambda wm_class, title: title == args.get("other", "Copperfield Mail"))
        _sh("wmctrl", "-n", str(max(2, _desktops())))
        report["scenarios"] = [_scenario(log, user, other, *scenario) for scenario in _scenarios(user, other)]
        report["scenarios_ok"] = all(scenario["ok"] for scenario in report["scenarios"])
    else:
        quiet = _scenario(log, user, None, "quiet", set(), lambda: None)
        report["quiet"] = quiet
        report["quiet_ok"] = quiet["disturbed"] == [] and quiet["unmeasured"] == ["typing"]
    report.update(_data_plane(log, input["env"]))
    failed = sorted(key for key, value in report.items() if value is False)
    if failed:
        raise AssertionError(f"{', '.join(failed)} failed: {json.dumps(report)}")
    return report


def _scenarios(user, other):
    """Each disturbance caused on purpose, with the criteria it must trip, and background actions that must trip none.
    xfwm4 refuses another app's activation the focus, so that only raises its window over the user's."""
    point = _point_on(other)
    return [
        ("quiet", set(), lambda: None),
        ("another app activated", {"window_raised"}, lambda: _sh("wmctrl", "-i", "-a", hex(other))),
        ("a click on another app", {"key_focus", "window_raised", "typing", "pointer", "activation"},
         lambda: _sh("xdotool", "mousemove", *point, "click", "1")),
        ("another app's window kept above", {"window_raised"},
         lambda: _sh("wmctrl", "-i", "-r", hex(other), "-b", "add,above")),
        ("the pointer moved", {"pointer"}, lambda: _sh("xdotool", "mousemove_relative", "--", "200", "120")),
        ("the clipboard taken", {"clipboard"}, lambda: _clipboard("disturbed")),
        ("another desktop", {"space"}, lambda: _sh("wmctrl", "-s", "1")),
        ("another app's dialog on the user's window", {"dialog"}, lambda: _dialog(user)),
        ("keys typed while the user's window has the focus", {"typing"},
         lambda: _sh("xdotool", "type", "--delay", "20", "QQ")),
        ("keys sent to the user's window", {"typing"}, lambda: _sh("xdotool", "type", "--window", str(user), "ZZ")),
        ("a click in the user's window", {"typing", "pointer"},
         lambda: _sh("xdotool", "mousemove", "700", "500", "click", "1")),
        ("BACKGROUND keys sent to another app's window", set(),
         lambda: _sh("xdotool", "type", "--window", str(other), "hello")),
        ("BACKGROUND another app's window moved beneath", set(),
         lambda: _sh("xdotool", "windowmove", str(other), "1300", "650")),
    ]


def _scenario(log, user, other, name, must, act):
    """Put the user back in front, arm the sentinel, act, disarm it, and score the armed window as trycua does."""
    _sh("wmctrl", "-s", "0")
    if other is not None:
        _sh("wmctrl", "-i", "-r", hex(other), "-b", "remove,above")
        _sh("wmctrl", "-i", "-a", hex(other))
    log.activate()
    time.sleep(1)
    armed = log.signal(signal.SIGUSR2, "armed")
    time.sleep(1)
    act()
    time.sleep(SETTLE_S)
    disarmed = log.signal(signal.SIGUSR2, "disarmed")
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as window:
        window.write("".join(json.dumps(line) + "\n" for line in log.between(armed, disarmed)))
    summary = summarize_sentinel.summarize(window.name)
    os.unlink(window.name)
    criteria = bench_v2.multiplayer_criteria(summary)
    disturbed = sorted(key for key, held in criteria.items() if held is False)
    unmeasured = sorted(key for key, held in criteria.items() if held is None)
    ok = summary["available"] and must <= set(disturbed) and (must or not disturbed) and (other is None or not unmeasured)
    return {"scenario": name, "ok": bool(ok), "must": sorted(must), "disturbed": disturbed, "unmeasured": unmeasured,
            "typed": (summary.get("user_activity") or {}).get("typed")}


def _data_plane(log, env):
    """The sentinel's data/get returns its log, and data/reset starts a fresh one, from a sentinel started again."""
    rpc = _rpc(f"{env['url']}/svc/bench-sentinel/agentenv", env["headers"])
    parts = {part["metadata"][DATA_OBJECTS]["path"]: part for part in rpc("data/get", {})["parts"]}
    exported = parts.get(LOG_PATH)
    lines = base64.b64decode(exported["file"]["bytes"]).decode().splitlines() if exported else []
    pid = log.pid()
    rpc("data/reset", {})
    fresh = Log(LOG)
    started = fresh.pid()
    return {"log_exported": any(json.loads(line).get("ev") == "start" for line in lines),
            "reset_fresh_log": started != pid and sum(line["ev"] == "start" for line in fresh.lines) == 1}


class Log:
    """The sentinel's log, read on from where it was last read, with every line read kept."""

    def __init__(self, path):
        self.path, self.offset, self.lines = path, 0, []

    def pid(self):
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            self.read()
            started = [line for line in self.lines if line["ev"] == "start"]
            if started:
                return started[-1]["pid"]
            time.sleep(0.5)
        raise AssertionError("the sentinel hasn't started")

    def activate(self):
        pid, deadline, sent = self.pid(), time.monotonic() + WAIT_S, 0.0
        while time.monotonic() < deadline:
            if time.monotonic() - sent > 3:
                os.kill(pid, signal.SIGUSR1)
                sent, seen = time.monotonic(), len(self.lines)
            self.read()
            if any(line["ev"] == "s" and line["active"] and line["key"] for line in self.lines[seen:]):
                return
            time.sleep(0.2)
        raise AssertionError("the sentinel's window didn't become active with the focus")

    def signal(self, sig, ev):
        seen = len(self.lines)
        os.kill(self.pid(), sig)
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            self.read()
            line = next((line for line in self.lines[seen:] if line["ev"] == ev), None)
            if line is not None:
                return line
            time.sleep(0.2)
        raise AssertionError(f"the sentinel logged no {ev}")

    def between(self, first, last):
        return self.lines[self.lines.index(first):self.lines.index(last) + 1]

    def read(self):
        if not self.path.exists():
            return
        with open(self.path, "rb") as log:
            log.seek(self.offset)
            data = log.read()
        whole = data[:data.rfind(b"\n") + 1]
        self.offset += len(whole)
        self.lines += [json.loads(raw) for raw in whole.splitlines() if raw.strip()]


def _window(matches):
    """The managed window ``matches`` takes by its WM_CLASS (instance.class) and title, as wmctrl lists them."""
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        for line in _sh("wmctrl", "-lx").splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 4 and matches(parts[2], parts[4] if len(parts) == 5 else ""):
                return int(parts[0], 16)
        time.sleep(0.5)
    raise AssertionError("no such window")


def _title(window):
    return _sh("xdotool", "getwindowname", str(window))


def _frame(window):
    """The window's outer frame, its decorations included: x, y, width and height."""
    shell = dict(line.split("=", 1) for line in _sh("xdotool", "getwindowgeometry", "--shell", str(window)).split())
    left, right, top, bottom = _numbers(_sh("xprop", "-id", hex(window), "_NET_FRAME_EXTENTS")) or [0, 0, 0, 0]
    return (int(shell["X"]) - left, int(shell["Y"]) - top, int(shell["WIDTH"]) + left + right,
            int(shell["HEIGHT"]) + top + bottom)


def _witness():
    x, y, width, height = _numbers(_sh("xprop", "-root", "_NET_WORKAREA"))[:4]
    w, h, margin = WITNESS
    return (x + width - w - margin, y + height - h - margin, w, h)


def _point_on(window):
    """A point of ``window`` outside the user's frame, for a click on it alone."""
    x, y, width, height = _frame(window)
    ux, uy, uw, uh = USER_FRAME
    for px in range(x + 40, x + width - 20, 40):
        for py in range(y + 60, y + height - 20, 40):
            if not (ux - 10 <= px <= ux + uw + 10 and uy - 10 <= py <= uy + uh + 10):
                return str(px), str(py)
    raise AssertionError(f"{hex(window)} lies under the user's frame")


def _desktops():
    return len(_sh("wmctrl", "-d").splitlines())


def _clipboard(text):
    subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, start_new_session=True, check=True)


def _dialog(user):
    """Another app's dialog, transient for the user's window, shown for two seconds."""
    subprocess.run([str(APP / "venv" / "bin" / "python"), "-c", f"""
import time
from Xlib import Xatom, display
x = display.Display()
dialog = x.screen().root.create_window(200, 200, 240, 120, 0, x.screen().root_depth)
dialog.set_wm_name("Confirm")
dialog.set_wm_transient_for(x.create_resource_object("window", {user}))
dialog.change_property(x.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                       [x.intern_atom("_NET_WM_WINDOW_TYPE_DIALOG")])
dialog.map()
x.flush()
time.sleep(2)
"""], check=True, timeout=30)


def _numbers(text):
    return [int(number) for number in re.findall(r"-?\d+", text.partition("=")[2])]


def _sh(*argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=30).stdout.strip()


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
