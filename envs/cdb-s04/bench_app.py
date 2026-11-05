"""What every bench task's app shares, the same file in each task app's folder. Its install brings the task's own files
(``files.json``: each at trycua's pinned commit, by URL and sha256, under ``task/``) and the runtimes they run on, and
builds the task's workspace in the session user's home with the task's ``reset/setup.py``, checked by its
``reset/verify.py``. Run as a script, it is the app's launch: it opens the task's windows as the task's
``platform/launch.linux.json`` says, on that workspace, and stays while they run, so stopping the app stops them all. On
macOS it follows the task's ``platform/launch.macos.json`` with the macOS builds of the same apps, and finds and places
the windows through the computer's cua-driver daemon, as trycua's runner does through its own."""
from __future__ import annotations

import json
import os
import plistlib
import re
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from agentenv_protocol.computer import (ComputerAppEnvironment, Download, Launch, Packages, Ready, RunScript,
                                        install_step, ready_check)
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
TASK = HERE / "task"
RUNTIME = HERE / "runtime"
#: Loaded into each of the task's Electron apps before its own main script: it logs each opening of their DevTools,
#: docked in the app's own window where the guard can't see it, for the bench's grade.
DEVTOOLS_HOOK = HERE / "devtools_hook.js"
SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]},
            {"os": {"type": "macos", "display": ["aqua"]}, "arch": ["arm64"]}]
MACOS = sys.platform == "darwin"
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
               "libxss1", "xdotool", "wmctrl", "unzip", "xz-utils", "librsvg2-common", "adwaita-icon-theme",
               "shared-mime-info"]
#: Chrome for Testing, at the build agentenv's chromium app pins, for a task's browser in place of google-chrome: its
#: archive and sha256 by arch, what it links against beyond DESKTOP_APT, a font for the pages it shows, and its window
#: class, its own, so its windows are never taken for another app's Chromium.
CHROMIUM = "156.0.8078.4"
CHROMIUM_ARCHIVES = {"amd64": ("linux64/chrome-linux64.zip",
                               "43fd31766c7533a02dda2ded5ad50c2f861cd5400be7509c0abad71129f79d79"),
                     "arm64": ("linux-arm64/chrome-linux-arm64.zip",
                               "910a12fff6170202195f72ef3d353801c7063d301ab80b1f51b77d791fda60ce")}
BROWSER_APT = ["fonts-liberation", "libatspi2.0-0t64", "libglib2.0-0t64", "libvulkan1", "libx11-6", "libxcb1",
               "libxext6"]
BROWSER_CLASS = "BenchChromium"
#: Where Chrome for Testing reads managed policies, and those that keep a fresh profile free of first-run tabs,
#: sign-in, sync, prompts and the warning bar its container flags would show, and keep its DevTools, a way out of the
#: GUI the bench's guard can't see, shut.
POLICY_DIR = Path("/etc/opt/chrome_for_testing/policies/managed")
POLICIES = {
    "BrowserSignin": 0,
    "SyncDisabled": True,
    "PromotionalTabsEnabled": False,
    "DefaultBrowserSettingEnabled": False,
    "MetricsReportingEnabled": False,
    "PasswordManagerEnabled": False,
    "AutofillSettings": [{"url_pattern": "*", "blocked_types": ["all"]}],
    "TranslateEnabled": False,
    "ComponentUpdatesEnabled": False,
    "DefaultGeolocationSetting": 2,
    "DefaultNotificationsSetting": 2,
    "CommandLineFlagSecurityWarningsEnabled": False,
    "DeveloperToolsAvailability": 2,
}
CALC_APT = ["libreoffice-calc", "libreoffice-gtk3"]
GNUCASH_APT = ["gnucash", "python3-gi"]
#: The macOS builds for Apple silicon: Electron's, Node's and Chrome for Testing's at the versions above, and the
#: LibreOffice and GnuCash the task's macOS descriptor runs from /Applications, out of their disk images.
MAC_ELECTRON_SHA256 = "01bb5d8756d220002ed5f8dccfb5a01391c4b919667af7156257cf5252e3e8ae"
MAC_NODE_SHA256 = "037650d0839f457747396f052073fb48333d31bf5abd3c98b74da20d89ebb1ad"
MAC_CHROMIUM_SHA256 = "987d2f8499c87d21676f78178550cfcbfb1bb53786821e2cff46c5a7e99b58be"
LIBREOFFICE_DMG = ("https://downloadarchive.documentfoundation.org/libreoffice/old/25.8.7.3/mac/aarch64/"
                   "LibreOffice_25.8.7.3_MacOS_aarch64.dmg",
                   "e7556aa61e282f89578ebaf35afdb09c94dcf9d6ee7c137004377bee81a6e900")
GNUCASH_DMG = ("https://github.com/Gnucash/gnucash/releases/download/5.17/Gnucash-Arm-5.17-1.dmg",
               "adbc91d6d69a297c1c599ad2849303a06c01310130d355473c0700f80dd2eb32")
#: Where Chrome for Testing reads managed policies on macOS.
MAC_POLICIES = Path("/Library/Managed Preferences/com.google.chrome.for.testing.plist")
MAC_ELECTRON = RUNTIME / "electron" / "Electron.app" / "Contents" / "MacOS" / "Electron"
MAC_CHROMIUM = (RUNTIME / "chromium" / "Google Chrome for Testing.app" / "Contents" / "MacOS"
                / "Google Chrome for Testing")
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
#: cua-driver's daemon in a macOS computer, its socket.
CUA_DRIVER = Path("/tmp/agentenv-cua-driver.sock")
_SESSION = uuid.uuid4().hex
_LAUNCH_TIMEOUT_S = 180
_PLACE_TIMEOUT_S = 90


def install(*, workspace: str, first_window: str, apt: list[str] = (), node: bool = False,
            browser: bool = False) -> dict:
    """The ``@linux(...)`` of a task's app: the task's files and runtimes (Node and Chromium where the task needs them),
    the packages its windows need beside ``DESKTOP_APT``, its ``workspace`` folder of the home as its data, which a
    reset puts back as ``setup.py`` built it, and a launch that's ready once ``first_window`` shows, after which its
    ``windows`` check waits for the rest."""
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
    if browser:
        downloads += [Download(url=f"https://storage.googleapis.com/chrome-for-testing-public/{CHROMIUM}/{path}",
                               sha256=sha256, to=f"runtime/chromium-{arch}.zip", arch=arch)
                      for arch, (path, sha256) in CHROMIUM_ARCHIVES.items()]
        apt = [*apt, *BROWSER_APT]
    return dict(packages=Packages(apt=sorted({*DESKTOP_APT, *apt})), downloads=downloads,
                run=[RunScript(script="install.sh")], paths=[workspace],
                launch=Launch(at="boot", command=["venv/bin/python", "bench_app.py"], window={"title": first_window},
                              ready=Ready(window=True, timeout_s=_LAUNCH_TIMEOUT_S)))


class MacOS(BaseModel):
    """How a macOS computer installs the app, as agent-env's ``[install.macos]`` takes it."""

    downloads: list[Download]
    run: list[RunScript]


def macos(*, workspace: str, calc: bool = False, gnucash: bool = False, node: bool = False,
          browser: bool = False) -> dict:
    """The ``@install("macos", ...)`` of a task's app: the task's files, Electron, and what else its macOS descriptor
    runs (LibreOffice, GnuCash, Node, Chrome for Testing), its ``workspace`` folder of the home as its data, and a
    launch that's ready once each of its windows shows (``windows``)."""
    files = json.loads((HERE / "files.json").read_text(encoding="utf-8"))["files"]
    downloads = [Download(url=f["url"], sha256=f["sha256"], to=f"task/{f['path']}") for f in files]
    downloads.append(Download(url=f"https://github.com/electron/electron/releases/download/v{ELECTRON}/"
                                  f"electron-v{ELECTRON}-darwin-arm64.zip",
                              sha256=MAC_ELECTRON_SHA256, to="runtime/electron-arm64.zip"))
    if node:
        downloads.append(Download(url=f"https://nodejs.org/dist/v{NODE}/node-v{NODE}-darwin-arm64.tar.xz",
                                  sha256=MAC_NODE_SHA256, to="runtime/node-arm64.tar.xz"))
    if browser:
        downloads.append(Download(url=f"https://storage.googleapis.com/chrome-for-testing-public/{CHROMIUM}/"
                                      "mac-arm64/chrome-mac-arm64.zip",
                                  sha256=MAC_CHROMIUM_SHA256, to="runtime/chromium-arm64.zip"))
    for wanted, (url, sha256), name in ((calc, LIBREOFFICE_DMG, "LibreOffice"), (gnucash, GNUCASH_DMG, "Gnucash")):
        if wanted:
            downloads.append(Download(url=url, sha256=sha256, to=f"runtime/{name}.dmg"))
    return dict(spec=MacOS(downloads=downloads, run=[RunScript(script="install-macos.sh", scope="session")]),
                paths=[workspace], launch=Launch(at="boot", command=["venv/bin/python", "bench_app.py"]))


class BenchTaskApp(ComputerAppEnvironment):
    """A bench task's app: its install builds the workspace, which must check out byte for byte, and it's ready once
    each of the task's windows shows."""

    @install_step(scope="session", os=["linux", "macos"])
    def workspace(self) -> None:
        spec = _spec()
        values = _values(spec)
        for step in ("setup", "verify"):
            subprocess.run([_sub(arg, values) for arg in spec["semantics"]["reset"][step]], cwd=TASK, check=True)

    @install_step(scope="system", os="linux")
    def browser(self) -> None:
        install_browser(RUNTIME, POLICY_DIR)

    @install_step(scope="system", os="macos")
    def browser_policies(self) -> None:
        """Where the task has a browser, ``POLICIES`` as Chrome for Testing's managed preferences."""
        if (RUNTIME / "chromium").exists():
            MAC_POLICIES.parent.mkdir(parents=True, exist_ok=True)
            MAC_POLICIES.write_bytes(plistlib.dumps(POLICIES))

    @ready_check(os=["linux", "macos"])
    def windows(self) -> bool:
        return all(claimed([app["window"] for app in _spec()["apps"] if "window" in app]))


def install_browser(runtime: Path, policies: Path) -> None:
    """Where the task has a browser, Chromium's archive unpacked to ``runtime/chromium``, with unzip, which keeps its
    execute bits, and ``POLICIES`` written to ``policies``."""
    for archive in runtime.glob("chromium-*.zip"):
        unpacked = runtime / "chromium-unpacked"
        subprocess.run(["unzip", "-q", str(archive), "-d", str(unpacked)], check=True)
        [top] = unpacked.iterdir()
        top.rename(runtime / "chromium")
        unpacked.rmdir()
        archive.unlink()
        policies.mkdir(parents=True, exist_ok=True)
        (policies / "agentenv-bench.json").write_text(json.dumps(POLICIES, indent=1) + "\n", encoding="utf-8")


def launch() -> None:
    """Open the task's windows on its workspace, each placed as the bench places it, and stay while any runs."""
    spec = _spec()
    values = _values(spec)
    workspace = Path(values["${workspace}"])
    _unlock(workspace)
    logs = workspace / ".runtime" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    running = []
    for app in spec["apps"]:
        env = {**{key: value for key, value in os.environ.items() if key not in app.get("unset_env", [])},
               **{key: _sub(value, values) for key, value in app.get("env", {}).items()}}
        command = _command(app, values)
        env.update(_hooked(command))
        _quiet(command, env)
        with open(logs / f"{app['id']}.log", "wb") as log:
            running.append(subprocess.Popen(command, cwd=_sub(app.get("cwd", "${bundle}"), values), env=env,
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT))
        if ready := app.get("ready"):
            _wait_for(ready["url"], ready["timeout_seconds"])
    _place([app["window"] for app in spec["apps"] if "window" in app])
    while any(process.poll() is None for process in running):
        time.sleep(1)


def _unlock(workspace: Path) -> None:
    """Remove the locks a stopped app left, LibreOffice's and GnuCash's, which would keep it from opening its file
    again: a launch only runs with every one of the task's apps stopped."""
    for path in workspace.rglob("*"):
        if path.is_file() and (re.fullmatch(r"\.~lock\..*#", path.name) or path.suffix in (".LCK", ".LNK")):
            path.unlink(missing_ok=True)


def _spec() -> dict:
    return json.loads((TASK / "platform" / f"launch.{'macos' if MACOS else 'linux'}.json").read_text(encoding="utf-8"))


def _values(spec: dict) -> dict[str, str]:
    workspace = Path(spec["workspace_root"].replace("${HOME}", str(Path.home())))
    return {"${bundle}": str(TASK), "${workspace}": str(workspace), "${workspace_uri}": workspace.as_uri(),
            "${python}": sys.executable}


def _sub(text: str, values: dict[str, str]) -> str:
    return re.sub(r"\$\{\w+\}", lambda match: values.get(match.group(0), match.group(0)), text)


def _command(app: dict, values: dict[str, str]) -> list[str]:
    """The app's command as the task gives it, with Electron, Node and Chromium this app installed in place of ``npx
    electron``, ``node`` and ``google-chrome``. Electron and Chromium run without Chromium's sandbox, which a container
    can't give them, Electron with its own profile under the workspace's runtime folder and Chromium without /dev/shm,
    which no computer sizes, and with its own window class. On macOS Electron and Chrome for Testing run sandboxed, in
    place of ``npx electron`` and Google Chrome."""
    argv = [_sub(arg, values) for arg in app["command"]]
    if argv[:2] == ["npx", "electron"] and MACOS:
        profile = Path(values["${workspace}"]) / ".runtime" / f"electron-{app['id']}"
        return [str(MAC_ELECTRON), *argv[2:], f"--user-data-dir={profile}"]
    if argv[0] == MAC_CHROME:
        return [str(MAC_CHROMIUM), *argv[1:]]
    if argv[:2] == ["npx", "electron"]:
        profile = Path(values["${workspace}"]) / ".runtime" / f"electron-{app['id']}"
        return [str(RUNTIME / "electron" / "electron"), *argv[2:], "--no-sandbox", f"--user-data-dir={profile}"]
    if argv[0] == "node":
        return [str(RUNTIME / "node" / "bin" / "node"), *argv[1:]]
    if argv[0] == "google-chrome":
        return [str(RUNTIME / "chromium" / "chrome"), "--no-sandbox", "--disable-dev-shm-usage",
                f"--class={BROWSER_CLASS}", *argv[1:]]
    return argv


def _hooked(command: list[str]) -> dict[str, str]:
    """For an Electron app, the environment that loads the DevTools hook into it."""
    electron = MAC_ELECTRON if MACOS else RUNTIME / "electron" / "electron"
    return {"NODE_OPTIONS": f"--require={DEVTOOLS_HOOK}"} if command[0] == str(electron) else {}


def _quiet(command: list[str], env: dict[str, str]) -> None:
    """A first run's tip of the day off, GnuCash's and LibreOffice's, in the settings each keeps in the runtime folder
    the task gives it, where a reset leaves none."""
    if command[0] == "gnucash":
        _setting(Path(env["XDG_CONFIG_HOME"]) / "glib-2.0" / "settings" / "keyfile",
                 "[org/gnucash/GnuCash/dialogs/tip-of-the-day]", "show-at-startup=false")
    profile = next((arg.split("=", 1)[1] for arg in command if arg.startswith("-env:UserInstallation=")), None)
    if Path(command[0]).name in ("libreoffice", "soffice") and profile:
        path = Path(urllib.request.url2pathname(profile.removeprefix("file://"))) / "user" / "registrymodifications.xcu"
        tip = ('<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="ShowTipOfTheDay" oor:op="fuse">'
               "<value>false</value></prop></item>")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<oor:items xmlns:oor="http://openoffice.org/2001/'
                            'registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/'
                            f'XMLSchema-instance">\n{tip}\n</oor:items>\n', encoding="utf-8")
        elif "ShowTipOfTheDay" not in (text := path.read_text(encoding="utf-8")):
            path.write_text(text.replace("</oor:items>", f"{tip}\n</oor:items>"), encoding="utf-8")


def _setting(keyfile: Path, section: str, line: str) -> None:
    """``line`` in ``section`` of a GLib keyfile, in place of the same key's there."""
    keyfile.parent.mkdir(parents=True, exist_ok=True)
    text = keyfile.read_text(encoding="utf-8") if keyfile.exists() else ""
    key = line.split("=", 1)[0]
    if section not in text:
        text = f"{text.rstrip()}\n\n{section}\n{line}\n".lstrip()
    else:
        head, _, rest = text.partition(section)
        body, sep, tail = rest.partition("\n[")
        body = "\n".join(entry for entry in body.split("\n") if not entry.startswith(f"{key}="))
        text = f"{head}{section}\n{line}{body}{sep}{tail}"
    keyfile.write_text(text, encoding="utf-8")


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


def claimed(windows: list[dict]) -> list[list[str]]:
    """The ids of the shown windows each of ``windows`` matches, a window matched by more than one belonging to the
    most specific: a whole title first, then the longest part of one. GnuCash's "kestrel-wharf" also matches Calc's
    "kestrel-wharf-reconciliation.ods" window, which Calc's longer match holds."""
    order = sorted(range(len(windows)), key=lambda i: ("title" not in windows[i],
                                                       -len(windows[i].get("title_contains", ""))))
    taken: set[str] = set()
    found: list[list[str]] = [[] for _ in windows]
    for i in order:
        found[i] = [wid for wid in _search(windows[i]) if wid not in taken]
        taken.update(found[i])
    return found


def _search(window: dict) -> list[str]:
    """The ids of the shown windows ``window`` matches: X's, or on macOS cua-driver's, as ``<pid>:<window id>``."""
    if MACOS:
        return [f"{shown['pid']}:{shown['window_id']}" for shown in _driver("list_windows").get("windows", [])
                if (shown.get("title") == window["title"] if "title" in window
                    else window["title_contains"] in (shown.get("title") or ""))]
    return subprocess.run(["xdotool", "search", "--onlyvisible", "--name", _title(window)],
                          capture_output=True, text=True).stdout.split()


def _driver(tool: str, **args) -> dict:
    """cua-driver's ``tool`` called on the computer's daemon, as trycua's runner calls its own; its structured
    result."""
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(30)
        connection.connect(str(CUA_DRIVER))
        connection.sendall((json.dumps({"method": "call", "name": tool, "args": args, "session_id": _SESSION}) + "\n")
                           .encode())
        reply = json.loads(connection.makefile("rb").readline())
    if not reply.get("ok") or reply["result"].get("isError"):
        raise RuntimeError(f"cua-driver {tool}: {reply.get('error') or reply['result'].get('content')}")
    return reply["result"].get("structuredContent") or {}


def _place(windows: list[dict]) -> None:
    """Move each window to the bench's bounds, again until it stays there three looks in a row, since an app may resize
    itself once it's shown, as LibreOffice maximizes; a window that doesn't show is left to the app's readiness."""
    deadline, held = time.monotonic() + _PLACE_TIMEOUT_S, [0] * len(windows)
    while time.monotonic() < deadline:
        for i, (window, ids) in enumerate(zip(windows, claimed(windows))):
            if not (bounds := window.get("bounds")) or not ids:
                continue
            if _at(ids[0], bounds):
                held[i] += 1
            else:
                held[i] = 0
                _move(ids[0], bounds)
        if all(held[i] >= 3 for i, window in enumerate(windows) if window.get("bounds")):
            return
        time.sleep(1)


def _move(wid: str, bounds: dict) -> None:
    if MACOS:
        pid, window_id = map(int, wid.split(":"))
        try:
            _driver("set_window_frame", pid=pid, window_id=window_id, x=bounds["x"], y=bounds["y"],
                    width=bounds["width"], height=bounds["height"])
        except RuntimeError:
            pass
        return
    subprocess.run(["wmctrl", "-ir", f"0x{int(wid):x}", "-b", "remove,maximized_vert,maximized_horz"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["xdotool", "windowsize", wid, str(bounds["width"]), str(bounds["height"]),
                    "windowmove", wid, str(bounds["x"]), str(bounds["y"])],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _at(wid: str, bounds: dict) -> bool:
    """Whether the window has the bounds' size, and its frame their place, give or take the window manager's frame."""
    try:
        if MACOS:
            pid, window_id = map(int, wid.split(":"))
            frame = next(shown["bounds"] for shown in _driver("list_windows").get("windows", [])
                         if (shown["pid"], shown["window_id"]) == (pid, window_id))
            x, y, width, height = (int(frame[key]) for key in ("x", "y", "width", "height"))
        else:
            geometry = dict(line.split("=", 1) for line in subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", wid], capture_output=True, text=True).stdout.split())
            x, y, width, height = (int(geometry[key]) for key in ("X", "Y", "WIDTH", "HEIGHT"))
    except (KeyError, ValueError, StopIteration, RuntimeError):
        return False
    return (abs(width - bounds["width"]) <= 8 and abs(height - bounds["height"]) <= 8
            and abs(x - bounds["x"]) <= 40 and abs(y - bounds["y"]) <= 60)


if __name__ == "__main__":
    launch()
