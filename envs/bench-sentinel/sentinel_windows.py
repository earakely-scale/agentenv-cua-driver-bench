"""The app's launch on Windows: trycua's BenchSentinel as their runner starts it, their ``windows/sentinel.py`` run by
``BenchSentinel.exe``, the copy of pythonw.exe the install made beside the Python, logging afresh to the app's log and
taking its commands from ``sentinel.control`` beside it, in the condition of the app's settings: in the background the
user's window at ``USER_WINDOW_FRAME``, typing; in the foreground the witness at their runner's frame for it. The
condition is written beside the log (``condition``), which the sentinel's lines don't carry. And trycua's GUI-only guard
on Windows, which their runner runs beside it, here every ``GUARD_S`` while it's armed: a side door started in the
session since arming, outside this launch's own processes, is a violation, and is ended, as their runner ends it; one
the driver's own program started for itself is the tool's, logged as ``gui_only_helper``; a side door in front
``FRONT_GRACE_SAMPLES`` looks in a row is a violation, in front for less a ``gui_only_transient``; each logged once
into the same log. Staying while BenchSentinel runs."""
import json
import os
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

from app import LOG_FOLDER, BenchSentinel

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab"
sys.path[:0] = [str(LAB / "windows"), str(LAB / "scoring")]
import bench_v2 as v2  # noqa: E402
import guard as G  # noqa: E402
import winenv as W  # noqa: E402

SENTINEL = Path(sys.base_prefix) / "BenchSentinel.exe"
#: trycua's runner's frame for the witness, the sentinel in the foreground: x, y, width, height.
WITNESS_FRAME = (1000, 640, 600, 320)
#: The driver's own programs: a shell one of them starts for itself is the tool's, as trycua's runner's ``--tool-exe``.
TOOL_EXES = ("cua-driver.exe", "codex-computer-use.exe")
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
    with open(folder / "sentinel.stderr", "ab") as output:
        sentinel = subprocess.Popen([str(SENTINEL), str(LAB / "windows" / "sentinel.py"), "--log", str(log),
                                     "--control", str(control), "--frame", ",".join(map(str, frame)),
                                     *(["--user-activity"] if background else [])],
                                    env={**os.environ, "PYTHONPATH": sysconfig.get_paths()["purelib"]},
                                    stdin=subprocess.DEVNULL, stdout=output, stderr=output)
    lines = Log(log)
    guard, armed, look = Guard(lines, W, os.getpid()), False, 0.0
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


class Guard:
    """trycua's GUI-only guard on Windows, through ``win``'s Win32 reads (their ``winenv``), for the launch whose pid is
    ``runner``, logging into the sentinel's log."""

    def __init__(self, log: "Log", win, runner: int) -> None:
        self.log, self.win, self.runner = log, win, runner
        self.arm()

    def arm(self) -> None:
        rows = self.win.processes()
        self.baseline = {pid for pid, _, _ in rows}
        self.own = G.descendants(rows, self.runner)
        self.session = self.win.session_of(self.runner)
        self.front = G.FrontWatch()
        self._logged: set[tuple[str, str]] = set()

    def sample(self) -> None:
        rows = self.win.processes()
        self.own |= G.descendants(rows, self.runner)
        here = [row for row in rows if self.win.session_of(row[0]) == self.session]
        for pid, label in G.new_side_doors(here, self.baseline, self.runner, self.own):
            if by := G.started_by_tool(rows, pid, TOOL_EXES):
                self._log("gui_only_helper", "process", f"process:{label}", pid=pid, parent=by)
                continue
            self._log("gui_only_violation", "process", f"process:{label}", pid=pid)
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        window = self.win.user32.GetForegroundWindow()
        exe = self.win.process_path(self.win.window_pid(window)) if window else ""
        if hit := self.front.sample(exe):
            self._log("gui_only_violation", "front", f"front:{hit}", exe=exe)
        elif G.name_of(exe) in G.SIDE_DOOR_PROCESSES:
            self._log("gui_only_transient", "front", f"front:{G.SIDE_DOOR_PROCESSES[G.name_of(exe)]}", exe=exe)

    def _log(self, ev: str, kind: str, detail: str, **evidence: object) -> None:
        if (ev, detail) not in self._logged:
            self._logged.add((ev, detail))
            self.log.write({"ev": ev, "t": time.time() * 1000, "armed": True, "kind": kind, "detail": detail,
                            "evidence": evidence})


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
