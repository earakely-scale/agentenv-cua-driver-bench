"""The bench's sentinel as a computer app beside a task's: the user's window, which logs all that disturbs that user while
an agent works (``sentinel.py``). Its data is its log, ``~/.bench-sentinel/sentinel.jsonl``, which a reset starts
afresh; a task arms it around the agent with the ``sentinel`` artifact's run_code steps, as trycua's runner does."""
from pathlib import Path
from typing import Literal

from agentenv_protocol.computer import (ComputerAppEnvironment, Launch, Packages, Ready, computer_app, install_step,
                                        linux)
from pydantic import BaseModel

SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]}]
LOG_FOLDER = ".bench-sentinel"


@computer_app(supports=SUPPORTS)
@linux(packages=Packages(apt=["python3-tk", "fonts-dejavu-core", "wmctrl", "xclip"]), python="requirements.txt",
       paths=[LOG_FOLDER],
       launch=Launch(at="boot", command=["venv/bin/python", "sentinel.py"], window={"class": "BenchSentinel"},
                     ready=Ready(window=True)))
class BenchSentinel(ComputerAppEnvironment):
    class Settings(BaseModel):
        #: trycua's two conditions: ``background``, the user's "User activity" window, which types; ``foreground``,
        #: the "Bench Sentinel" witness.
        condition: Literal["foreground", "background"] = "foreground"

    @install_step(scope="session", os="linux")
    def log_folder(self) -> None:
        (Path.home() / LOG_FOLDER).mkdir(exist_ok=True)
