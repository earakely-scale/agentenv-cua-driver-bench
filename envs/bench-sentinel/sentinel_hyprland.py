"""The app's launch on Omarchy: trycua's BenchSentinel for Hyprland as their runner starts it, their
``hyprland/sentinel.py`` on Wayland with Omarchy's own Python, which ships GTK 3's PyGObject, logging afresh to the app's
log and taking its commands from ``sentinel.control`` beside it, in the condition of the app's settings: in the
background the user's window at ``USER_WINDOW_FRAME``, typing; in the foreground the witness at their runner's frame for
it; once their window rules are applied (``bench.lua``). The condition is written beside the log (``condition``), which
the sentinel's lines don't carry. It and their sentinel talk to Hyprland through their ``hypr.py`` made to wait out a
busy Hyprland (``hyprland_ipc.py``). And trycua's GUI-only guard on Hyprland, which their runner runs beside it, here every
``GUARD_S`` while it's armed: a terminal started since arming, outside this launch's own processes, is a violation, and
is ended, as their runner ends it; one cua-driver's own program started is the tool's, logged as ``gui_only_helper``, as
their Windows guard has it; a terminal's window in front ``FRONT_GRACE_SAMPLES`` looks in a row is a violation, in front
for less a ``gui_only_transient``; and Omarchy's launchers in front, its shell's menu and its Apps panel, a
``gui_only_transient`` however long they stay, as they run only their own rows, never a typed command, and any shell
they open is a terminal's window, which fails; each logged once into the same log. Staying while BenchSentinel runs."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app import LOG_FOLDER, BenchSentinel
from hyprland_ipc import patient

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab"
sys.path[:0] = [str(LAB / "hyprland"), str(LAB / "scoring")]
import bench_v2 as v2  # noqa: E402
import guard as G  # noqa: E402
import hypr as H  # noqa: E402

patient(H)

RULES = LAB / "hyprland" / "bench.lua"
#: trycua's runner's frame for the witness, the sentinel in the foreground: x, y, width, height.
WITNESS_FRAME = (1000, 640, 600, 320)
#: The driver's own programs: a terminal one of them starts for itself is the tool's, as trycua's Windows runner's
#: ``--tool-exe``.
TOOL_PROGRAMS = ("cua-driver",)
#: Omarchy's launchers, its shell's menu (Super+Space) and its Apps panel (Super+Alt+Space), by their layer surfaces'
#: namespaces: transients in front, never violations.
LAUNCHERS = {"omarchy-menu": "omarchy-menu", "omarchy-dock-apps": "omarchy-apps"}
#: Hyprland's layers drawn over windows: top and overlay.
OVER_WINDOWS = ("2", "3")
GUARD_S = 0.5
READ_S = 0.1


def main(settings) -> None:
    folder = Path.home() / LOG_FOLDER
    folder.mkdir(exist_ok=True)
    log, control = folder / "sentinel.jsonl", folder / "sentinel.control"
    log.write_bytes(b"")
    control.write_bytes(b"")
    (folder / "condition").write_text(settings.condition + "\n")
    background = settings.condition == "background"
    frame = v2.USER_WINDOW_FRAME if background else WITNESS_FRAME
    apply_rules(RULES)
    with open(folder / "sentinel.stderr", "ab") as output:
        sentinel = subprocess.Popen(["/usr/bin/python3", str(HERE / "hyprland_ipc.py"),
                                     str(LAB / "hyprland" / "sentinel.py"), "--log", str(log),
                                     "--control", str(control), "--frame", ",".join(map(str, frame)),
                                     *(["--user-activity"] if background else [])],
                                    env={**os.environ, "GDK_BACKEND": "wayland", "NO_AT_BRIDGE": "0"},
                                    stdin=subprocess.DEVNULL, stdout=output, stderr=output)
    lines = Log(log)
    guard, armed, look = Guard(lines, os.getpid()), False, 0.0
    while sentinel.poll() is None:
        for line in lines.read():
            if line["ev"] in ("armed", "disarmed"):
                armed = line["ev"] == "armed"
                if armed:
                    guard.arm()
        if armed and time.monotonic() >= look:
            guard.sample()
            look = time.monotonic() + GUARD_S
        time.sleep(READ_S)
    sys.exit(sentinel.returncode)


def apply_rules(rules: Path) -> None:
    """The window rules of trycua's ``bench.lua``, each sent to Hyprland as their runner sends it; named, so applying
    them again replaces them."""
    for chunk in rules.read_text(encoding="utf-8").split("hl.window_rule(")[1:]:
        depth, end = 1, 0
        for i, ch in enumerate(chunk):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0:
                end = i
                break
        H.request("eval hl.window_rule(" + chunk[:end + 1])


class Guard:
    """trycua's GUI-only guard on Hyprland (their ``hyprland/guard.py``), through Hyprland's IPC, for the launch whose
    pid is ``runner``, logging into the sentinel's log."""

    def __init__(self, log: "Log", runner: int) -> None:
        self.log, self.runner = log, runner
        self.arm()

    def arm(self) -> None:
        rows = G.process_rows()
        self.baseline = {pid for pid, _, _ in rows}
        self.own = G.descendants(rows, self.runner)
        self.front = G.FrontWatch()
        self._logged: set[tuple[str, str]] = set()

    def sample(self) -> None:
        rows = G.process_rows()
        self.own |= G.descendants(rows, self.runner)
        for pid, label in G.new_side_doors(rows, self.baseline, self.runner, self.own):
            if by := started_by_tool(rows, pid):
                self._log("gui_only_helper", "process", f"process:{label}", pid=pid, parent=by)
                continue
            self._log("gui_only_violation", "process", f"process:{label}", pid=pid)
            _kill(pid)
        try:
            window = H.active_window().get("class", "")
            launcher = launcher_shown(H.query("layers") or {})
        except (OSError, ValueError, RuntimeError):
            return
        if hit := self.front.sample(window):
            self._log("gui_only_violation", "front", f"front:{hit}", window_class=window)
        elif label := terminal_class(window):
            self._log("gui_only_transient", "front", f"front:{label}", window_class=window)
        if launcher:
            self._log("gui_only_transient", "front", f"front:{launcher}", window_class=window)

    def _log(self, ev: str, kind: str, detail: str, **evidence: object) -> None:
        if (ev, detail) not in self._logged:
            self._logged.add((ev, detail))
            self.log.write({"ev": ev, "t": time.time() * 1000, "armed": True, "kind": kind, "detail": detail,
                            "evidence": evidence})


def started_by_tool(rows: list[tuple[int, int, str]], pid: int) -> str | None:
    """The name of ``pid``'s parent when that parent is one of the driver's own programs, ``TOOL_PROGRAMS``, else None:
    their Windows guard's ``started_by_tool``, on /proc's process names."""
    parent = {p: pp for p, pp, _ in rows}.get(pid)
    name = {p: comm for p, _, comm in rows}.get(parent, "") if parent is not None else ""
    return name if name in TOOL_PROGRAMS else None


def terminal_class(window_class: str) -> str | None:
    """The terminal a window's class is, as their ``FrontWatch`` reads it; None for any other window."""
    name = (window_class or "").lower()
    return G.TERMINAL_CLASSES.get(name) or ("Omarchy TUI" if name.startswith("org.omarchy.") else None)


def launcher_shown(layers: dict) -> str | None:
    """Omarchy's launcher that shows as a layer over the windows; else None."""
    for monitor in layers.values():
        for level in OVER_WINDOWS:
            for layer in (monitor.get("levels") or {}).get(level, []):
                if launcher := LAUNCHERS.get(str(layer.get("namespace", "")).lower()):
                    return launcher
    return None


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


class Log:
    """BenchSentinel's log, read on from where it was last read, and appended to one whole line a write."""

    def __init__(self, path: Path) -> None:
        self.path, self.offset = path, 0

    def read(self) -> list[dict]:
        with open(self.path, "rb") as log:
            log.seek(self.offset)
            data = log.read()
        whole = data[:data.rfind(b"\n") + 1]
        self.offset += len(whole)
        return [json.loads(raw) for raw in whole.splitlines() if raw.strip()]

    def write(self, line: dict) -> None:
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, (json.dumps(line) + "\n").encode())
        finally:
            os.close(fd)


if __name__ == "__main__":
    main(BenchSentinel().settings)
