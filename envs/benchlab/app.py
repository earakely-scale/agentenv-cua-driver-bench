"""trycua's BenchLab as a computer app: the window of the bench's precision and interruption tasks, MB-09 to MB-11 and
IR-01 to IR-04, their Linux port, a GTK app with one mode per task, here in the mode and with the seed its settings give
(``lab.py``). Its install brings their two files at the pinned commit (``files.json``, by URL and sha256, under
``lab/``). Its data is ``~/.benchlab``, the state and the events BenchLab writes, which trycua's evaluator for the task
grades."""
import json
from pathlib import Path
from typing import Literal

from agentenv_protocol.computer import (ComputerAppEnvironment, Download, Launch, Packages, Ready, computer_app,
                                        install_step, linux)
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]}]
DATA = ".benchlab"
FILES = json.loads((HERE / "files.json").read_text(encoding="utf-8"))["files"]


@computer_app(supports=SUPPORTS)
@linux(packages=Packages(apt=["python3-gi", "gir1.2-gtk-3.0", "fonts-dejavu-core", "xdotool"]),
       downloads=[Download(url=f["url"], sha256=f["sha256"], to=f"lab/{f['path']}") for f in FILES], paths=[DATA],
       launch=Launch(at="boot", command=["venv/bin/python", "lab.py"], window={"class": "BenchLab"},
                     ready=Ready(window=True)))
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
