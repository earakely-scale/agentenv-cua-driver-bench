"""The app's launch: trycua's BenchLab as their runner starts it, ``/usr/bin/python3 benchlab.py`` in the mode and with
the seed of the app's settings and a throwaway home, writing its state and events into the app's data folder; its
window placed as their macOS BenchLab places its own, the outer frame's top left at ``FRAME_AT``, which their Linux port
leaves to the window manager; staying while BenchLab runs."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app import DATA, BenchLab

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab" / "linux" / "benchlab.py"
FRAME_AT = (60, 80)
PLACE_S = 30.0


def main(settings) -> None:
    data = Path.home() / DATA
    data.mkdir(exist_ok=True)
    home = tempfile.mkdtemp(prefix="benchlab-home-")
    lab = subprocess.Popen(["/usr/bin/python3", str(LAB), "--mode", settings.mode, "--seed", str(settings.seed),
                            "--state", str(data / "state.json"), "--events", str(data / "events.jsonl")],
                           env={**os.environ, "HOME": home}, stdin=subprocess.DEVNULL)
    _place(lab)
    sys.exit(lab.wait())


def _place(lab: subprocess.Popen) -> None:
    """Move BenchLab's window to ``FRAME_AT`` until it stays there three looks in a row."""
    deadline, held = time.monotonic() + PLACE_S, 0
    while time.monotonic() < deadline and lab.poll() is None and held < 3:
        ids = _sh("xdotool", "search", "--onlyvisible", "--pid", str(lab.pid), "--class", "^BenchLab$").split()
        if not ids:
            time.sleep(0.2)
            continue
        if _at(ids[0]):
            held += 1
        else:
            held = 0
            _sh("xdotool", "windowmove", ids[0], *map(str, FRAME_AT))
        time.sleep(0.5)


def _at(wid: str) -> bool:
    """Whether the window's frame is at ``FRAME_AT``, give or take the window manager's frame, which xdotool counts
    twice under xfwm4."""
    geometry = dict(line.split("=", 1) for line in _sh("xdotool", "getwindowgeometry", "--shell", wid).split())
    x, y = int(geometry.get("X", -1000)), int(geometry.get("Y", -1000))
    return abs(x - FRAME_AT[0]) <= 40 and abs(y - FRAME_AT[1]) <= 60


def _sh(*argv: str) -> str:
    return subprocess.run(argv, capture_output=True, text=True, check=False).stdout


if __name__ == "__main__":
    main(BenchLab().settings)
