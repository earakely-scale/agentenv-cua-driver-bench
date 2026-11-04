"""The app's launch on macOS: trycua's BenchLab.app as their runner starts it, its executable in the mode and with the
seed of the app's settings, with a throwaway home and their runner's clean environment, writing its state and events
afresh into the app's data folder and its output beside them; it places its own window. Staying while BenchLab
runs."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app import DATA, BenchLab

HERE = Path(__file__).resolve().parent
LAB = HERE / "apps" / "BenchLab.app" / "Contents" / "MacOS" / "BenchLab"


def main(settings) -> None:
    data = Path.home() / DATA
    data.mkdir(exist_ok=True)
    for name in ("state.json", "events.jsonl"):
        (data / name).unlink(missing_ok=True)
    with open(data / "lab.log", "ab") as log:
        lab = subprocess.Popen([str(LAB), "--mode", settings.mode, "--seed", str(settings.seed),
                                "--state", str(data / "state.json"), "--events", str(data / "events.jsonl")],
                               env=clean_env(), stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    sys.exit(lab.wait())


def clean_env() -> dict[str, str]:
    """trycua's runner's environment for a bench app on macOS, in a home of its own."""
    home = Path(tempfile.mkdtemp(prefix="benchlab-home-"))
    (home / "tmp").mkdir()
    return {"HOME": str(home), "TMPDIR": str(home / "tmp"), "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "USER": os.environ.get("USER", ""), "LANG": "en_US.UTF-8", "CUA_DRIVER_RS_TELEMETRY_ENABLED": "false",
            "DO_NOT_TRACK": "1"}


if __name__ == "__main__":
    main(BenchLab().settings)
