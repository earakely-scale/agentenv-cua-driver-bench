"""The app's launch on Windows: trycua's BenchLab as their runner starts it, their ``windows/benchlab.py`` run by
``BenchLab.exe``, the copy of pythonw.exe the install made beside the Python, in the mode, with the seed and in the
condition of the app's settings, without activating it in the background, at their frame for BenchLab on Windows,
writing its state and events afresh into the app's data folder; wxPython from the app's venv. Staying while BenchLab
runs."""
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

from app import DATA, BenchLab

HERE = Path(__file__).resolve().parent
LAB = Path(sys.base_prefix) / "BenchLab.exe"
#: trycua's frame for BenchLab on Linux and Windows: x, y, width, height.
FRAME = (40, 40, 760, 540)


def main(settings) -> None:
    data = Path.home() / DATA
    data.mkdir(exist_ok=True)
    for name in ("state.json", "events.jsonl"):
        (data / name).unlink(missing_ok=True)
    background = ["--no-activate"] if settings.condition == "background" else []
    with open(data / "lab.log", "ab") as log:
        lab = subprocess.Popen([str(LAB), str(HERE / "lab" / "windows" / "benchlab.py"), "--mode", settings.mode,
                                "--seed", str(settings.seed), "--state", str(data / "state.json"),
                                "--events", str(data / "events.jsonl"), "--frame", ",".join(map(str, FRAME)),
                                *background],
                               env={**os.environ, "PYTHONPATH": sysconfig.get_paths()["purelib"]},
                               stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    sys.exit(lab.wait())


if __name__ == "__main__":
    main(BenchLab().settings)
