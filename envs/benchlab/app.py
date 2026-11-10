"""trycua's BenchLab as a computer app: the window of the bench's precision and interruption tasks, MB-09 to MB-11 and
IR-01 to IR-04, with one mode per task, here in the mode and with the seed its settings give. On Linux it's their port,
a GTK app (``lab.py``), whose two files its install brings at the pinned commit (``files.json``, by URL and sha256,
under ``lab/``); on macOS their app itself, BenchLab.app, built from their Swift sources at that commit
(``build-macos.sh``, ``lab_macos.py``); on Windows their wxPython port, run as their runner runs it from ``BenchLab.exe``,
a copy of the Python's pythonw.exe beside it (``install-windows.ps1``, ``lab_windows.py``); on Omarchy their Linux port
again, on Wayland, placed and focused through Hyprland's IPC as their Hyprland runner does (``lab_hyprland.py``), with
their Hyprland files beside it. On macOS, Windows and Omarchy it's ready once it has written its state. Its data is ``~/.benchlab``, the state and the events BenchLab writes, which
trycua's evaluator for the task grades."""
import importlib.util
import json
from pathlib import Path
from typing import Literal

from agentenv_protocol.computer import (ComputerAppEnvironment, Download, Launch, Packages, Ready, RunScript,
                                        computer_app, install, install_step, linux, ready_check, windows)
from hyprland_ipc import patient
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]},
            {"os": {"type": "macos", "display": ["aqua"]}, "arch": ["arm64"]},
            {"os": {"type": "windows", "display": ["dwm"]}, "arch": ["amd64"]},
            {"os": {"type": "linux", "distribution": ["omarchy"], "display": ["wayland"]}, "arch": ["amd64"]}]
DATA = ".benchlab"
#: trycua's frame for BenchLab on Linux and Windows: x, y, width, height.
FRAME = (40, 40, 760, 540)
PINNED = json.loads((HERE / "files.json").read_text(encoding="utf-8"))
FILES = PINNED["files"]
#: Microsoft's Visual C++ runtime, which wxPython's DLLs need and a trimmed Windows lacks, at its versioned URL.
VC_REDIST = Download(url="https://download.visualstudio.microsoft.com/download/pr/990c720a-46ce-4dc7-87b9-c2eb615d34b9/"
                         "CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe",
                     sha256="cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b", to="vc_redist.x64.exe")


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
@windows(downloads=[*(Download(url=f["url"], sha256=f["sha256"], to=f"lab/{f['path']}") for f in PINNED["windows"]),
                    VC_REDIST],
         python="requirements-windows.txt", run=[RunScript(script="install-windows.ps1")], paths=[DATA],
         launch=Launch(at="boot", command=["venv/Scripts/python.exe", "lab_windows.py"],
                       window={"instance": "benchlab.exe"}, ready=Ready(window=True)))
@linux(distribution="omarchy",
       downloads=[Download(url=f["url"], sha256=f["sha256"], to=f"lab/{f['path']}") for f in PINNED["omarchy"]],
       paths=[DATA],
       launch=Launch(at="boot", command=["venv/bin/python", "lab_hyprland.py"], window={"class": "BenchLab"},
                     ready=Ready(window=True)))
class BenchLab(ComputerAppEnvironment):
    class Settings(BaseModel):
        #: The task's BenchLab mode: MB-09 listdrag, MB-10 hover, MB-11 tooltip, IR-01 irmodal, IR-02 irbanner, IR-03
        #: irunsaved, IR-04 irconsent. trycua's preflight window, hover with seed 1, when a task gives none.
        mode: Literal["listdrag", "hover", "tooltip", "irmodal", "irbanner", "irunsaved", "irconsent"] = "hover"
        #: The trial's seed, trycua's ``probe_seed(task, run_index)``, from which BenchLab draws the task's values.
        seed: int = 1
        #: The trial's condition, which only Windows and Omarchy read: there trycua's runners start BenchLab without
        #: activating it in the background, and on Hyprland focus it in the foreground.
        condition: Literal["foreground", "background"] = "foreground"

    @install_step(scope="session", os="linux")
    def data_folder(self) -> None:
        (Path.home() / DATA).mkdir(exist_ok=True)

    @ready_check(os=["macos", "windows", "linux/omarchy"])
    def state_written(self) -> bool:
        """trycua's runner's readiness of BenchLab: its state file written."""
        return (Path.home() / DATA / "state.json").is_file()

    @ready_check(os="linux/omarchy")
    def placed(self) -> bool:
        """On Hyprland, BenchLab's window at ``FRAME``, as trycua's runner places it before it goes on."""
        spec = importlib.util.spec_from_file_location("trycua_hyprland_hypr", HERE / "lab" / "hyprland" / "hypr.py")
        hypr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hypr)
        return any(window.get("class") == "BenchLab" and [*window.get("at", ()), *window.get("size", ())] == list(FRAME)
                   for window in patient(hypr).clients())
