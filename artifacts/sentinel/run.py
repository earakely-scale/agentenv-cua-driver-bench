"""Inside a bench task's computer, as its session user: arm the bench's sentinel just before the agent starts, or disarm it
just after, as trycua's runner does. Arming empties the clipboard, on X11 goes to the first desktop, and activates
the sentinel until its window is active and holds the focus (on Windows, is the foreground window; on Hyprland, is the
active window and the topmost, as their Hyprland runner checks it through Hyprland's IPC, which also takes it to its
workspace), then arms it, and fails unless the armed line says so too and, with ``condition``, unless the sentinel runs
in that condition. On Windows, which has no signals, the sentinel takes each command as a line of its control file, as
their runner sends it. Each waits for the sentinel's log to say it's
done, and does nothing when the sentinel is already in that state; disarming a sentinel that's no longer running says
so, for the grade to fail the trial. ``args``: ``action``, ``arm`` or ``disarm``, and ``condition``. Returns the log's
armed or disarmed line."""
import ctypes
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

LOG = Path.home() / ".bench-sentinel" / "sentinel.jsonl"
#: The condition the sentinel's launch writes beside its log on macOS, Windows and Omarchy, whose lines don't carry it.
CONDITION = LOG.parent / "condition"
#: Where the sentinel takes its commands on Windows: a line each, applied once, in order.
CONTROL = LOG.parent / "sentinel.control"
#: The identity trycua's sentinel on Windows and Hyprland gives its own window in its samples.
SENTINEL_BID = "ai.cua.benchsentinel"
#: trycua's Hyprland IPC client, which the sentinel's app installs on an Omarchy computer alone.
HYPR = Path("/opt/agentenv/apps/bench-sentinel/lab/hyprland/hypr.py")
MACOS = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"
HYPRLAND = not MACOS and not WINDOWS and HYPR.is_file()
WAIT_S = 30.0
ACTIVATE_EVERY_S = 3.0


def run(input):
    action = input["args"]["action"]
    if action not in ("arm", "disarm"):
        raise ValueError(f"action is arm or disarm, not {action!r}")
    log = Log(LOG)
    sentinel, armed, condition = log.state()
    if input["args"].get("condition") not in (None, condition):
        raise RuntimeError(f"the sentinel runs in the {condition} condition, not {input['args']['condition']}")
    if armed == (action == "arm"):
        return {"action": action, "already": True, "line": log.last(("armed", "disarmed"))}
    if action == "arm" and WINDOWS:
        _empty_clipboard()
        _activate_window(sentinel)
    elif action == "arm" and MACOS:
        subprocess.run(["pbcopy"], input=b"", check=True)
        log.activate(sentinel)
    elif action == "arm" and HYPRLAND:
        subprocess.run(["wl-copy", "--clear"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, start_new_session=True, check=True)
        _activate_on_hyprland(sentinel, log.started["address"])
    elif action == "arm":
        subprocess.run(["xclip", "-selection", "clipboard", "-i", "/dev/null"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, check=True)
        subprocess.run(["wmctrl", "-s", "0"], check=True)
        log.activate(sentinel)
    try:
        _command(sentinel, action)
    except ProcessLookupError:
        if action == "arm":
            raise
        return {"action": action, "already": False, "line": None, "sentinel": "gone"}
    line = log.wait(lambda line: line["ev"] == ("armed" if action == "arm" else "disarmed"))
    if action == "arm" and not _in_front(line):
        raise RuntimeError(f"the sentinel armed without its window active and focused: {line}")
    return {"action": action, "already": False, "line": line}


def _command(sentinel, action):
    """Send ``action`` to the sentinel: on Windows a line of its control file, its window ``sentinel`` gone raising
    ProcessLookupError; elsewhere SIGUSR2 to its pid ``sentinel``, which toggles it."""
    if not WINDOWS:
        os.kill(sentinel, signal.SIGUSR2)
        return
    if not _user32().IsWindow(sentinel):
        raise ProcessLookupError(f"the sentinel's window {sentinel} is gone")
    with open(CONTROL, "a", encoding="utf-8") as control:
        control.write(f"{action}\n")


def _in_front(armed):
    """Whether the armed line says the sentinel's window is active and holds the focus: its own flags, or on Windows and
    Hyprland its sample's front window, the sentinel's."""
    if "front" in armed and "active" not in armed:
        return (armed["front"] or {}).get("bid") == SENTINEL_BID
    return bool(armed["active"] and armed["key"])


def _activate_window(window):
    """Activate the sentinel on Windows until its window ``window`` is the foreground window."""
    user32, deadline, sent = _user32(), time.monotonic() + WAIT_S, 0.0
    while time.monotonic() < deadline:
        if time.monotonic() - sent > ACTIVATE_EVERY_S:
            with open(CONTROL, "a", encoding="utf-8") as control:
                control.write("activate\n")
            sent = time.monotonic()
        if user32.GetForegroundWindow() == window:
            return
        time.sleep(0.2)
    raise RuntimeError("the sentinel's window didn't become the foreground window")


def _activate_on_hyprland(pid, address):
    """Activate the sentinel on Hyprland until its window ``address`` is the active window and the topmost, as
    trycua's Hyprland runner checks it."""
    hypr, deadline, sent = _module(HYPR), time.monotonic() + WAIT_S, 0.0
    while time.monotonic() < deadline:
        if time.monotonic() - sent > ACTIVATE_EVERY_S:
            os.kill(pid, signal.SIGUSR1)
            sent = time.monotonic()
        if hypr.active_window().get("address") == address and (hypr.clients() or [{}])[-1].get("address") == address:
            return
        time.sleep(0.2)
    raise RuntimeError("the sentinel's window didn't become the active window on top")


def _module(path):
    spec = importlib.util.spec_from_file_location(f"trycua_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _empty_clipboard():
    """Empty the clipboard on Windows, waiting while another program holds it open."""
    user32, deadline = _user32(), time.monotonic() + WAIT_S
    while not user32.OpenClipboard(None):
        if time.monotonic() > deadline:
            raise RuntimeError("the clipboard stayed open in another program")
        time.sleep(0.1)
    try:
        user32.EmptyClipboard()
    finally:
        user32.CloseClipboard()


def _user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.IsWindow.argtypes = user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    return user32


class Log:
    """The sentinel's log, read on from where it was last read."""

    def __init__(self, path):
        self.path, self.offset, self.started = path, 0, None

    def state(self):
        """The running sentinel, its pid from its last start or ready line (on Windows its window from its ready line),
        its condition, and whether it's armed, waiting for it to start; that line is ``started``."""
        deadline = time.monotonic() + WAIT_S
        while True:
            sentinel, armed, condition = None, False, None
            for line in self.read():
                if line["ev"] in ("start", "ready"):
                    sentinel, self.started = line["hwnd"] if "hwnd" in line else line["pid"], line
                    armed, condition = False, line.get("condition") or _condition()
                elif line["ev"] in ("armed", "disarmed"):
                    armed = line["ev"] == "armed"
            if sentinel is not None:
                return sentinel, armed, condition
            if time.monotonic() > deadline:
                raise RuntimeError(f"the sentinel hasn't started: {self.path} has no start line")
            self.offset = 0
            time.sleep(0.5)

    def last(self, events):
        self.offset = 0
        return next((line for line in reversed(self.read()) if line["ev"] in events), None)

    def activate(self, pid):
        """Activate the sentinel until a sample says its window is active and holds the focus."""
        deadline, sent = time.monotonic() + WAIT_S, 0.0
        while time.monotonic() < deadline:
            if time.monotonic() - sent > ACTIVATE_EVERY_S:
                os.kill(pid, signal.SIGUSR1)
                sent = time.monotonic()
            if any(line["ev"] == "s" and line["active"] and line["key"] for line in self.read()):
                return
            time.sleep(0.2)
        raise RuntimeError("the sentinel's window didn't become active with the focus")

    def wait(self, wanted):
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            line = next((line for line in self.read() if wanted(line)), None)
            if line is not None:
                return line
            time.sleep(0.2)
        raise RuntimeError("the sentinel didn't answer its signal")

    def read(self):
        """The whole lines written since the last read; a torn last line is left for the next."""
        if not self.path.exists():
            return []
        with open(self.path, "rb") as log:
            log.seek(self.offset)
            data = log.read()
        whole = data[:data.rfind(b"\n") + 1]
        self.offset += len(whole)
        return [json.loads(raw) for raw in whole.splitlines() if raw.strip()]


def _condition():
    """The condition the sentinel's launch wrote beside its log, when it did."""
    return CONDITION.read_text().strip() if CONDITION.is_file() else None
