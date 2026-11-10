"""The app's launch on Omarchy: trycua's BenchLab as their Hyprland runner starts it, ``/usr/bin/python3 benchlab.py``
on Wayland with the accessibility bridge on, in the mode and with the seed of the app's settings, writing its state and
events afresh into the app's data folder, once their window rules are applied (``bench.lua``: BenchLab and its dialogs
float and never take the focus as they open, its dialogs over its top left); its window placed at their frame for
BenchLab through Hyprland's IPC (their ``hypr.py``) and, in the foreground, focused, as their runner does. Staying
while BenchLab runs."""
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

from app import DATA, FRAME, BenchLab

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab"
RULES = LAB / "hyprland" / "bench.lua"
PLACE_S = 30.0


def main(settings) -> None:
    hypr = module(LAB / "hyprland" / "hypr.py")
    data = Path.home() / DATA
    data.mkdir(exist_ok=True)
    for name in ("state.json", "events.jsonl"):
        (data / name).unlink(missing_ok=True)
    apply_rules(hypr, RULES)
    with open(data / "lab.log", "ab") as log:
        lab = subprocess.Popen(["/usr/bin/python3", str(LAB / "linux" / "benchlab.py"), "--mode", settings.mode,
                                "--seed", str(settings.seed), "--state", str(data / "state.json"),
                                "--events", str(data / "events.jsonl")],
                               env={**os.environ, "GDK_BACKEND": "wayland", "NO_AT_BRIDGE": "0"},
                               stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    place(hypr, lab, data / "state.json", focus=settings.condition == "foreground")
    sys.exit(lab.wait())


def apply_rules(hypr, rules: Path) -> None:
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
        hypr.request("eval hl.window_rule(" + chunk[:end + 1])


def place(hypr, lab: subprocess.Popen, state: Path, focus: bool) -> None:
    """BenchLab's window, once it has written its state, at ``FRAME``, until Hyprland says it's there; focused when
    ``focus``."""
    deadline = time.monotonic() + PLACE_S
    while time.monotonic() < deadline and lab.poll() is None:
        windows = hypr.by_pid(lab.pid) if state.exists() else []
        if not windows:
            time.sleep(0.2)
            continue
        window = windows[0]
        if [*window.get("at", ()), *window.get("size", ())] == list(FRAME):
            if focus:
                hypr.focus(window["address"])
            return
        hypr.place(window["address"], FRAME)
        time.sleep(0.5)


def module(path: Path):
    """trycua's module at ``path``, under a name of its own."""
    spec = importlib.util.spec_from_file_location(f"trycua_hyprland_{path.stem}", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


if __name__ == "__main__":
    main(BenchLab().settings)
