"""What every bench task's app shares, the same file in each task app's folder. Its install brings the task's own files
(``files.json``: each at trycua's pinned commit, by URL and sha256, under ``task/``) and the runtimes they run on, and
builds the task's workspace in the session user's home with the task's ``reset/setup.py``, checked by its
``reset/verify.py``. Run as a script, it is the app's launch: it opens the task's windows as the task's
``platform/launch.linux.json`` says, on that workspace, and stays while they run, so stopping the app stops them all."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from agentenv_protocol.computer import (ComputerAppEnvironment, Download, Launch, Packages, Ready, RunScript,
                                        install_step, ready_check)

HERE = Path(__file__).resolve().parent
TASK = HERE / "task"
SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]}]
_ARCHES = {"amd64": "x64", "arm64": "arm64"}

ELECTRON = "43.8.1"
ELECTRON_SHA256 = {"amd64": "7e11ff34c837de9ffcdfad2a73be1905704a6c17eb6baf5763428f20e4975a79",
                   "arm64": "9b26d2a0a526ba136d5d6a3b3fa6365c00c982480afff0aac291e2adf1641369"}
NODE = "22.23.4"
NODE_SHA256 = {"amd64": "1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce",
               "arm64": "6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b"}

#: What Electron links against that the base computer lacks, and what the launcher and the windows' icons need.
DESKTOP_APT = ["libasound2t64", "libatk-bridge2.0-0t64", "libatk1.0-0t64", "libcairo2", "libcups2t64", "libdbus-1-3",
               "libdrm2", "libexpat1", "libgbm1", "libgtk-3-0t64", "libnspr4", "libnss3", "libpango-1.0-0",
               "libxcomposite1", "libxdamage1", "libxfixes3", "libxkbcommon0", "libxrandr2", "libxshmfence1",
               "libxss1", "xdotool", "unzip", "xz-utils", "librsvg2-common", "adwaita-icon-theme", "shared-mime-info"]
CALC_APT = ["libreoffice-calc", "libreoffice-gtk3"]
GNUCASH_APT = ["gnucash", "python3-gi"]
_LAUNCH_TIMEOUT_S = 180
_PLACE_TIMEOUT_S = 90


def install(*, workspace: str, first_window: str, apt: list[str] = (), node: bool = False) -> dict:
    """The ``@linux(...)`` of a task's app: the task's files and runtimes, the packages its windows need beside
    ``DESKTOP_APT``, its ``workspace`` folder of the home as its data, which a reset puts back as ``setup.py`` built
    it, and a launch that's ready once ``first_window`` shows, after which its ``windows`` check waits for the rest."""
    files = json.loads((HERE / "files.json").read_text(encoding="utf-8"))["files"]
    downloads = [Download(url=f["url"], sha256=f["sha256"], to=f"task/{f['path']}") for f in files]
    downloads += [Download(url=f"https://github.com/electron/electron/releases/download/v{ELECTRON}/"
                               f"electron-v{ELECTRON}-linux-{_ARCHES[arch]}.zip",
                           sha256=sha256, to=f"runtime/electron-{arch}.zip", arch=arch)
                  for arch, sha256 in ELECTRON_SHA256.items()]
    if node:
        downloads += [Download(url=f"https://nodejs.org/dist/v{NODE}/node-v{NODE}-linux-{_ARCHES[arch]}.tar.xz",
                               sha256=sha256, to=f"runtime/node-{arch}.tar.xz", arch=arch)
                      for arch, sha256 in NODE_SHA256.items()]
    return dict(packages=Packages(apt=sorted({*DESKTOP_APT, *apt})), downloads=downloads,
                run=[RunScript(script="install.sh")], paths=[workspace],
                launch=Launch(at="boot", command=["venv/bin/python", "bench_app.py"], window={"title": first_window},
                              ready=Ready(window=True, timeout_s=_LAUNCH_TIMEOUT_S)))


class BenchTaskApp(ComputerAppEnvironment):
    """A bench task's app: its install builds the workspace, which must check out byte for byte, and it's ready once
    each of the task's windows shows."""

    @install_step(scope="session", os="linux")
    def workspace(self) -> None:
        spec = _spec()
        values = _values(spec)
        for step in ("setup", "verify"):
            subprocess.run([_sub(arg, values) for arg in spec["semantics"]["reset"][step]], cwd=TASK, check=True)

    @ready_check(os="linux")
    def windows(self) -> bool:
        return all(_shown(app["window"]) for app in _opened(_spec()) if "window" in app)


def launch() -> None:
    """Open the task's windows on its workspace, each placed as the bench places it, and stay while any runs."""
    spec = _spec()
    values = _values(spec)
    workspace = Path(values["${workspace}"])
    _unlock(workspace)
    logs = workspace / ".runtime" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    running = []
    for app in _opened(spec):
        env = {**{key: value for key, value in os.environ.items() if key not in app.get("unset_env", [])},
               **{key: _sub(value, values) for key, value in app.get("env", {}).items()}}
        if app["id"] == "gnucash":
            _quiet_gnucash(env)
        with open(logs / f"{app['id']}.log", "wb") as log:
            running.append(subprocess.Popen(_command(app, values), cwd=_sub(app.get("cwd", "${bundle}"), values),
                                            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT))
        if ready := app.get("ready"):
            _wait_for(ready["url"], ready["timeout_seconds"])
    for app in _opened(spec):
        if "window" in app:
            _place(app["window"])
    while any(process.poll() is None for process in running):
        time.sleep(1)


def _unlock(workspace: Path) -> None:
    """Remove the locks a stopped app left, LibreOffice's and GnuCash's, which would keep it from opening its file
    again: a launch only runs with every one of the task's apps stopped."""
    for path in workspace.rglob("*"):
        if path.is_file() and (re.fullmatch(r"\.~lock\..*#", path.name) or path.suffix in (".LCK", ".LNK")):
            path.unlink(missing_ok=True)


def _spec() -> dict:
    return json.loads((TASK / "platform" / "launch.linux.json").read_text(encoding="utf-8"))


def _opened(spec: dict) -> list[dict]:
    """The task's apps this computer opens: all but a browser, which waits until the computer has one."""
    return [app for app in spec["apps"] if app["kind"] != "browser"]


def _values(spec: dict) -> dict[str, str]:
    workspace = Path(spec["workspace_root"].replace("${HOME}", str(Path.home())))
    return {"${bundle}": str(TASK), "${workspace}": str(workspace), "${workspace_uri}": workspace.as_uri(),
            "${python}": sys.executable}


def _sub(text: str, values: dict[str, str]) -> str:
    return re.sub(r"\$\{\w+\}", lambda match: values.get(match.group(0), match.group(0)), text)


def _command(app: dict, values: dict[str, str]) -> list[str]:
    """The app's command as the task gives it, with Electron and Node this app installed in place of ``npx electron``
    and ``node``. Electron runs without Chromium's sandbox, which a container can't give it, and with its own profile
    under the workspace's runtime folder."""
    argv = [_sub(arg, values) for arg in app["command"]]
    if argv[:2] == ["npx", "electron"]:
        profile = Path(values["${workspace}"]) / ".runtime" / f"electron-{app['id']}"
        return [str(HERE / "runtime" / "electron" / "electron"), *argv[2:], "--no-sandbox", f"--user-data-dir={profile}"]
    if argv[0] == "node":
        return [str(HERE / "runtime" / "node" / "bin" / "node"), *argv[1:]]
    return argv


def _quiet_gnucash(env: dict[str, str]) -> None:
    """GnuCash's tip of the day off, in the settings file its keyfile backend reads from the runtime folder the task
    gives it."""
    keyfile = Path(env["XDG_CONFIG_HOME"]) / "glib-2.0" / "settings" / "keyfile"
    keyfile.parent.mkdir(parents=True, exist_ok=True)
    keyfile.write_text("[org/gnucash/GnuCash/dialogs/totd]\nshow-at-startup=false\n", encoding="utf-8")


def _wait_for(url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            if time.monotonic() > deadline:
                raise SystemExit(f"{url} didn't answer within {timeout_s} s")
            time.sleep(0.5)


def _title(window: dict) -> str:
    """An xdotool --name pattern for the window's title: the whole of ``title``, or one holding ``title_contains``."""
    return f"^{_literal(window['title'])}$" if "title" in window else _literal(window["title_contains"])


def _literal(text: str) -> str:
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", text)


def _shown(window: dict) -> bool:
    return subprocess.run(["xdotool", "search", "--onlyvisible", "--name", _title(window)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _place(window: dict) -> None:
    """Move the window to the bench's bounds once it shows; one that doesn't show is left to the app's readiness."""
    if not (bounds := window.get("bounds")):
        return
    try:
        subprocess.run(["xdotool", "search", "--sync", "--onlyvisible", "--name", _title(window),
                        "windowsize", str(bounds["width"]), str(bounds["height"]),
                        "windowmove", str(bounds["x"]), str(bounds["y"])],
                       timeout=_PLACE_TIMEOUT_S, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass


if __name__ == "__main__":
    launch()
