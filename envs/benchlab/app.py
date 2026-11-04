"""trycua's BenchLab as a computer app: the window of the bench's precision and interruption tasks, MB-09 to MB-11 and
IR-01 to IR-04, with one mode per task, here in the mode and with the seed its settings give. On Linux it's their port,
a GTK app (``lab.py``), whose two files its install brings at the pinned commit (``files.json``, by URL and sha256,
under ``lab/``); on macOS their app itself, BenchLab.app, built from their Swift sources at that commit
(``build-macos.sh``, ``lab_macos.py``), ready once it has written its state. Its data is ``~/.benchlab``, the state and
the events BenchLab writes, which trycua's evaluator for the task grades."""
import json
from pathlib import Path
from typing import Literal

from agentenv_protocol.computer import (ComputerAppEnvironment, Download, Launch, Packages, Ready, RunScript,
                                        computer_app, install, install_step, linux, ready_check)
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]},
            {"os": {"type": "macos", "display": ["aqua"]}, "arch": ["arm64"]}]
DATA = ".benchlab"
PINNED = json.loads((HERE / "files.json").read_text(encoding="utf-8"))
FILES = PINNED["files"]


class MacOS(BaseModel):
    """How a macOS computer installs the app, as agent-env's ``[install.macos]`` takes it."""

    downloads: list[Download]
    run: list[RunScript]


@computer_app(supports=SUPPORTS)
@linux(packages=Packages(apt=["python3-gi", "gir1.2-gtk-3.0", "fonts-dejavu-core", "xdotool"]),
       downloads=[Download(url=f["url"], sha256=f["sha256"], to=f"lab/{f['path']}") for f in FILES], paths=[DATA],
       launch=Launch(at="boot", command=["venv/bin/python", "lab.py"], window={"class": "BenchLab"},
                     ready=Ready(window=True)))
@install("macos", MacOS(downloads=[Download(url=f["url"], sha256=f["sha256"], to=f"lab/{f['path']}")
                                   for f in PINNED["macos"]],
                        run=[RunScript(script="build-macos.sh", scope="session")]),
         paths=[DATA], launch=Launch(at="boot", command=["venv/bin/python", "lab_macos.py"]))
class BenchLab(ComputerAppEnvironment):
    class Settings(BaseModel):
        #: The task's BenchLab mode: MB-09 listdrag, MB-10 hover, MB-11 tooltip, IR-01 irmodal, IR-02 irbanner, IR-03
        #: irunsaved, IR-04 irconsent. trycua's preflight window, hover with seed 1, when a task gives none.
        mode: Literal["listdrag", "hover", "tooltip", "irmodal", "irbanner", "irunsaved", "irconsent"] = "hover"
        #: The trial's seed, trycua's ``probe_seed(task, run_index)``, from which BenchLab draws the task's values.
        seed: int = 1

    @install_step(scope="session", os="linux")
    def data_folder(self) -> None:
        (Path.home() / DATA).mkdir(exist_ok=True)

    @ready_check(os="macos")
    def state_written(self) -> bool:
        """trycua's runner's readiness of BenchLab.app: its state file written."""
        return (Path.home() / DATA / "state.json").is_file()
