"""The app's launch on macOS: trycua's BenchSentinel.app as their runner starts it, logging afresh to the app's log, in
the condition of the app's settings (in the background, the user's window at ``USER_WINDOW_FRAME``), with a throwaway
home and their runner's clean environment; the condition written beside the log (``condition``), which BenchSentinel's
start line doesn't carry; and trycua's GUI-only guard on macOS, which their runner runs beside it, here reading the
front app from BenchSentinel's samples, every 0.5 s while it's armed: a side door in front three samples in a row, a
side door's program running, or a program started on a terminal since arming is a violation, logged once into the same
log as ``gui_only_violation``, a side door in front for less once as ``gui_only_transient``. Staying while
BenchSentinel runs."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app import LOG_FOLDER, BenchSentinel

HERE = Path(__file__).resolve().parent
SENTINEL = HERE / "apps" / "BenchSentinel.app" / "Contents" / "MacOS" / "BenchSentinel"
USER_WINDOW_FRAME = (420, 340, 900, 520)
SIDE_DOOR_BUNDLES = {"com.apple.Terminal": "Terminal", "com.googlecode.iterm2": "iTerm",
                     "com.apple.ScriptEditor2": "Script Editor", "com.apple.automator": "Automator",
                     "com.apple.shortcuts": "Shortcuts"}
SIDE_DOOR_PROCESSES = ("Script Editor", "Automator", "iTerm2", "Shortcuts")
FRONT_GRACE_SAMPLES = 3
#: BenchSentinel samples at 20 Hz; the guard looks at every tenth sample while it's armed.
GUARD_EVERY_SAMPLES = 10
READ_S = 0.1


def main(settings) -> None:
    folder = Path.home() / LOG_FOLDER
    folder.mkdir(exist_ok=True)
    log = folder / "sentinel.jsonl"
    log.write_bytes(b"")
    (folder / "condition").write_text(settings.condition + "\n")
    background = settings.condition == "background"
    args = ["--user-activity", "--frame", ",".join(map(str, USER_WINDOW_FRAME))] if background else []
    with open(folder / "sentinel.stderr", "ab") as output:
        sentinel = subprocess.Popen([str(SENTINEL), "--log", str(log), *args], env=clean_env(),
                                    stdin=subprocess.DEVNULL, stdout=output, stderr=output)
    lines = Log(log)
    guard, armed, samples = Guard(lines), False, 0
    while sentinel.poll() is None:
        for line in lines.read():
            if line["ev"] in ("armed", "disarmed"):
                armed, samples = line["ev"] == "armed", 0
                if armed:
                    guard.arm()
            elif armed and line["ev"] == "s":
                samples += 1
                if samples % GUARD_EVERY_SAMPLES == 0:
                    guard.sample(line.get("front") or {})
        time.sleep(READ_S)
    sys.exit(sentinel.returncode)


class Guard:
    """trycua's GUI-only guard on macOS, logging into the sentinel's log."""

    def __init__(self, log: "Log") -> None:
        self.log = log
        self.arm()

    def arm(self) -> None:
        self._run_of: dict[str, int] = {}
        self._logged: set[tuple[str, str]] = set()
        self._on_terminals = {pid for pid, _, _ in _on_terminals()}

    def sample(self, front: dict) -> None:
        door = SIDE_DOOR_BUNDLES.get(front.get("bid") or "")
        for name in list(self._run_of):
            if name != door:
                del self._run_of[name]
        if door is not None:
            self._run_of[door] = self._run_of.get(door, 0) + 1
            ev = "gui_only_violation" if self._run_of[door] >= FRONT_GRACE_SAMPLES else "gui_only_transient"
            self._log(ev, "front", f"front:{door}", front=front)
        for name in SIDE_DOOR_PROCESSES:
            if subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0:
                self._log("gui_only_violation", "process", f"process:{name}")
        for pid, tty, name in _on_terminals():
            if pid not in self._on_terminals:
                self._log("gui_only_violation", "terminal", "terminal:session", pid=pid, name=name, tty=tty)

    def _log(self, ev: str, kind: str, detail: str, **evidence: object) -> None:
        if (ev, detail) not in self._logged:
            self._logged.add((ev, detail))
            self.log.write({"ev": ev, "t": time.time() * 1000, "armed": True, "kind": kind, "detail": detail,
                            "evidence": evidence})


class Log:
    """BenchSentinel's log, read on from where it was last read, and appended to one whole line a write, as
    BenchSentinel appends."""

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


def _on_terminals() -> list[tuple[int, str, str]]:
    """Each process on a terminal: its pid, terminal and name."""
    out = subprocess.run(["ps", "-axo", "pid=,tty=,comm="], capture_output=True, text=True, timeout=5).stdout
    rows = [line.split(None, 2) for line in out.splitlines()]
    return [(int(pid), tty, name) for pid, tty, name in (row for row in rows if len(row) == 3) if tty != "??"]


def clean_env() -> dict[str, str]:
    """trycua's runner's environment for a bench app on macOS, in a home of its own."""
    home = Path(tempfile.mkdtemp(prefix="sentinel-home-"))
    (home / "tmp").mkdir()
    return {"HOME": str(home), "TMPDIR": str(home / "tmp"), "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "USER": os.environ.get("USER", ""), "LANG": "en_US.UTF-8", "CUA_DRIVER_RS_TELEMETRY_ENABLED": "false",
            "DO_NOT_TRACK": "1"}


if __name__ == "__main__":
    main(BenchSentinel().settings)
