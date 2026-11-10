"""Inside an Omarchy computer with BenchLab and the bench's sentinel, run as its session user once the task pack is loaded
into ``~/bench``: the sentinel's window is its condition's, with its title and frame as Hyprland places it; trycua's own
summarizer and A22 criteria, from the task pack, find each disturbance their Hyprland oracle causes on purpose
(``oracle.py --disturb``) in its own criterion, and a quiet window and a background action in none, with every criterion
measured; their GUI-only guard on Hyprland, beside the sentinel, logs a terminal opened, and Omarchy's launcher in
front, and nothing else; and the sentinel's data plane returns its log, which a reset starts afresh. Their oracle moves
the pointer and types through /dev/uinput; where the session user can't open it, their same ``disturb`` runs here with
the pointer moved through Hyprland's IPC, as their runner parks it, and each scenario says which it took (``via``).
``args``: ``condition``, the sentinel's."""
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

BENCH = Path.home() / "bench"
sys.path[:0] = [str(BENCH / "scoring"), str(BENCH / "hyprland")]
import bench_v2  # noqa: E402
import hypr  # noqa: E402
import summarize_sentinel  # noqa: E402

LOG = Path.home() / ".bench-sentinel" / "sentinel.jsonl"
LOG_PATH = ".bench-sentinel/sentinel.jsonl"
DATA_OBJECTS = "urn:agentenv:data-objects/v1"
ORACLE = BENCH / "hyprland" / "oracle.py"
WITNESS_FRAME = (1000, 640, 600, 320)
#: Each disturbance trycua's oracle causes, with the criteria it must trip.
DISTURBANCES = (("focus", {"key_focus", "activation"}), ("raise", {"window_raised"}), ("pointer", {"pointer"}),
                ("clipboard", {"clipboard"}), ("typing", {"typing"}), ("space", {"space"}))
TERMINAL = "alacritty"
WAIT_S = 30.0
SETTLE_S = 3.0


def run(input):
    args = input["args"]
    background = args["condition"] == "background"
    log = Log(LOG)
    user = _window(lambda client: client.get("class") == "BenchSentinel")
    frame = [*user.get("at", ()), *user.get("size", ())]
    report = {"title": user.get("title"), "frame": frame,
              "expected_frame": list(bench_v2.USER_WINDOW_FRAME if background else WITNESS_FRAME)}
    report["title_ok"] = report["title"] == ("User activity" if background else "Bench Sentinel")
    report["frame_ok"] = all(abs(a - b) <= 4 for a, b in zip(frame, report["expected_frame"]))
    if background:
        report["uinput"] = os.access("/dev/uinput", os.W_OK)
        report["scenarios"] = [_scenario(log, user, *scenario) for scenario in _scenarios(report["uinput"])]
        report["scenarios_ok"] = all(scenario["ok"] for scenario in report["scenarios"])
    else:
        quiet = _scenario(log, user, "quiet", set(), set(), lambda: None)
        report["quiet"] = quiet
        report["quiet_ok"] = quiet["disturbed"] == [] and quiet["unmeasured"] == ["typing"]
    report.update(_data_plane(log, input["env"]))
    failed = sorted(key for key, value in report.items() if value is False)
    if failed:
        raise AssertionError(f"{', '.join(failed)} failed: {json.dumps(report)}")
    return report


def _scenarios(uinput):
    """Each disturbance trycua's oracle causes, with the criteria it must trip; a terminal opened and Omarchy's
    launcher shown, with the guard violations each must log; and a quiet window and a background action, which must do
    neither."""
    lab = _window(lambda client: client.get("class") == "BenchLab")
    scenarios = [("quiet", set(), set(), lambda: None)]
    scenarios += [(f"oracle: {kind}", must, set(), (lambda kind=kind: _disturb(kind, uinput))) for kind, must in
                  DISTURBANCES]
    if shutil.which(TERMINAL):
        scenarios.append(("a terminal opened", set(), {"process:Alacritty"}, _terminal))
    scenarios.append(("Omarchy's launcher shown", set(), {"front:walker"}, _launcher))
    scenarios.append(("BACKGROUND another app's window moved beneath", set(), set(),
                      lambda: hypr.dispatch(f"hl.dsp.window.move({{ x = 1300, y = 650, {hypr.window_ref(lab['address'])} }})")))
    return scenarios


def _scenario(log, user, name, must, guard_must, act):
    """Put the user back in front, arm the sentinel, act, disarm it, and score the armed window as trycua does, with
    the guard's violations in it."""
    log.activate(user["address"])
    time.sleep(1)
    armed = log.signal(signal.SIGUSR2, "armed")
    time.sleep(1)
    via = act()
    time.sleep(SETTLE_S)
    disarmed = log.signal(signal.SIGUSR2, "disarmed")
    lines = log.between(armed, disarmed)
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as window:
        window.write("".join(json.dumps(line) + "\n" for line in lines))
    summary = summarize_sentinel.summarize(window.name)
    os.unlink(window.name)
    criteria = bench_v2.multiplayer_criteria(summary)
    disturbed = sorted(key for key, held in criteria.items() if held is False)
    unmeasured = sorted(key for key, held in criteria.items() if held is None)
    guarded = sorted({line["detail"] for line in lines if line["ev"] == "gui_only_violation"})
    ok = (summary["available"] and must <= set(disturbed) and (must or guard_must or not disturbed)
          and guard_must <= set(guarded) and (guard_must or not guarded) and not unmeasured)
    return {"scenario": name, "ok": bool(ok), "must": sorted(must), "disturbed": disturbed, "unmeasured": unmeasured,
            "guard_must": sorted(guard_must), "guarded": guarded, **({"via": via} if via else {}),
            "typed": (summary.get("user_activity") or {}).get("typed")}


def _disturb(kind, uinput):
    """trycua's oracle's disturbance ``kind``, on Omarchy's own Python, which has their oracle's PyGObject: their
    oracle itself where the session user can open /dev/uinput, else their ``disturb`` with the pointer moved through
    Hyprland's IPC (``IPC_DISTURB``); which it took."""
    argv = ([str(ORACLE), "--mode", "disturb", "--seed", "0", "--disturb", kind] if uinput
            else ["-c", IPC_DISTURB, str(ORACLE.parent), kind])
    subprocess.run(["/usr/bin/python3", *argv], check=True, timeout=120)
    return "oracle" if uinput else "ipc"


#: trycua's oracle's ``disturb`` with the real pointer moved through Hyprland's IPC, as their runner parks it, in place
#: of their uinput device: ``python3 -c IPC_DISTURB HYPRLAND_FOLDER KIND``.
IPC_DISTURB = """
import sys, time
sys.path.insert(0, sys.argv[1])
import hypr, oracle

class Pointer:
    def move(self, x, y):
        hypr.dispatch("hl.dsp.cursor.move({ x = %d, y = %d })" % (x, y))
        time.sleep(0.03)

oracle.IN = Pointer()
oracle.disturb(sys.argv[2])
"""


def _terminal():
    """A terminal opened in front of the user, which the guard ends."""
    terminal = subprocess.Popen([TERMINAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
    time.sleep(SETTLE_S)
    if terminal.poll() is None:
        terminal.terminate()
        terminal.wait(timeout=10)


def _launcher():
    """Omarchy's launcher shown past the guard's grace, then closed."""
    subprocess.run(["omarchy-launch-walker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    time.sleep(SETTLE_S)
    subprocess.run(["wtype", "-k", "Escape"], timeout=30)


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
    return {"log_exported": any(json.loads(line).get("ev") == "ready" for line in lines),
            "reset_fresh_log": started != pid and sum(line["ev"] == "ready" for line in fresh.lines) == 1}


class Log:
    """The sentinel's log, read on from where it was last read, with every line read kept."""

    def __init__(self, path):
        self.path, self.offset, self.lines = path, 0, []

    def pid(self):
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            self.read()
            ready = [line for line in self.lines if line["ev"] == "ready"]
            if ready:
                return ready[-1]["pid"]
            time.sleep(0.5)
        raise AssertionError("the sentinel hasn't started")

    def activate(self, address):
        """Activate the sentinel until its window is the active window and the topmost, as trycua's Hyprland runner
        checks it."""
        pid, deadline, sent = self.pid(), time.monotonic() + WAIT_S, 0.0
        while time.monotonic() < deadline:
            if time.monotonic() - sent > 3:
                os.kill(pid, signal.SIGUSR1)
                sent = time.monotonic()
            if hypr.active_window().get("address") == address and (hypr.clients() or [{}])[-1].get("address") == address:
                return
            time.sleep(0.2)
        raise AssertionError("the sentinel's window didn't become the active window on top")

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
    """The first mapped client ``matches`` takes, as Hyprland lists it."""
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        found = next((client for client in hypr.clients() if matches(client)), None)
        if found is not None:
            return found
        time.sleep(0.5)
    raise AssertionError("no such window")


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
