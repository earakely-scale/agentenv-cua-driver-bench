"""The bench's sentinel as a computer app beside a task's: the user's window, which logs all that disturbs that user while
an agent works, on Linux our port (``sentinel.py``), on macOS trycua's BenchSentinel.app, built from their Swift sources
at the pinned commit (``files.json``, ``build-macos.sh``) and run beside their GUI-only guard (``sentinel_macos.py``), on
Windows their wxPython port, run as their runner runs it from ``BenchSentinel.exe``, a copy of the Python's pythonw.exe
beside it, and beside their GUI-only guard on Windows (``install-windows.ps1``, ``sentinel_windows.py``).
Its data is its log, ``~/.bench-sentinel/sentinel.jsonl``, which a reset starts afresh; a task arms it around the agent
with the ``sentinel`` artifact's run_code steps, as trycua's runner does."""
import json
from pathlib import Path
from typing import Literal

from agentenv_protocol.computer import (ComputerAppEnvironment, Download, Launch, Packages, Ready, RunScript,
                                        computer_app, install, install_step, linux, ready_check, windows)
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]},
            {"os": {"type": "macos", "display": ["aqua"]}, "arch": ["arm64"]},
            {"os": {"type": "windows", "display": ["dwm"]}, "arch": ["amd64"]}]
LOG_FOLDER = ".bench-sentinel"
PINNED = json.loads((HERE / "files.json").read_text(encoding="utf-8"))
#: Microsoft's Visual C++ runtime, which wxPython's DLLs need and a trimmed Windows lacks, at its versioned URL.
VC_REDIST = Download(url="https://download.visualstudio.microsoft.com/download/pr/990c720a-46ce-4dc7-87b9-c2eb615d34b9/"
                         "CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe",
                     sha256="cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b", to="vc_redist.x64.exe")


class MacOS(BaseModel):
    """How a macOS computer installs the app, as agent-env's ``[install.macos]`` takes it."""

    downloads: list[Download]
    run: list[RunScript]


@computer_app(supports=SUPPORTS)
@linux(packages=Packages(apt=["python3-tk", "fonts-dejavu-core", "wmctrl", "xclip"]), python="requirements.txt",
       paths=[LOG_FOLDER],
       launch=Launch(at="boot", command=["venv/bin/python", "sentinel.py"], window={"class": "Benchsentinel"},
                     ready=Ready(window=True)))
@install("macos", MacOS(downloads=[Download(url=f["url"], sha256=f["sha256"], to=f["path"]) for f in PINNED["macos"]],
                        run=[RunScript(script="build-macos.sh", scope="session")]),
         paths=[LOG_FOLDER], launch=Launch(at="boot", command=["venv/bin/python", "sentinel_macos.py"]))
@windows(downloads=[*(Download(url=f["url"], sha256=f["sha256"], to=f"lab/{f['path']}") for f in PINNED["windows"]),
                    VC_REDIST],
         python="requirements-windows.txt", run=[RunScript(script="install-windows.ps1")], paths=[LOG_FOLDER],
         launch=Launch(at="boot", command=["venv/Scripts/python.exe", "sentinel_windows.py"],
                       window={"instance": "benchsentinel.exe"}, ready=Ready(window=True)))
class BenchSentinel(ComputerAppEnvironment):
    class Settings(BaseModel):
        #: trycua's two conditions: ``background``, the user's "User activity" window, which types; ``foreground``,
        #: the "Bench Sentinel" witness.
        condition: Literal["foreground", "background"] = "foreground"

    @install_step(scope="session", os="linux")
    def log_folder(self) -> None:
        (Path.home() / LOG_FOLDER).mkdir(exist_ok=True)

    @ready_check(os=["macos", "windows"])
    def started(self) -> bool:
        """BenchSentinel's log begun: its start line written on macOS, its ready line on Windows."""
        try:
            first = (Path.home() / LOG_FOLDER / "sentinel.jsonl").read_text().splitlines()[0]
            return json.loads(first)["ev"] in ("start", "ready")
        except (FileNotFoundError, IndexError, ValueError, KeyError):
            return False
