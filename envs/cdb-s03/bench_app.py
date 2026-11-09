"""What every bench task's app shares, the same file in each task app's folder. Its install brings the task's own files
(``files.json``: each at trycua's pinned commit, by URL and sha256, under ``task/``) and the runtimes they run on, and
builds the task's workspace in the session user's home with the task's ``reset/setup.py``, checked by its
``reset/verify.py``. Run as a script, it is the app's launch: it opens the task's windows as the task's
``platform/launch.linux.json`` says, on that workspace, and stays while they run, so stopping the app stops them all. On
macOS it follows the task's ``platform/launch.macos.json`` with the macOS builds of the same apps, and finds and places
the windows through the Accessibility API, which the app's own interpreter is granted, whichever driver the computer
has. On Windows it follows ``platform/launch.windows.json``, finds and places the windows through Win32, and builds the
workspace as its server starts, as the session user: Windows composes as its admin, so no install step runs as that
user there."""
from __future__ import annotations

import ctypes
import json
import os
import plistlib
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from agentenv_protocol.computer import (ComputerAppEnvironment, Download, Launch, Packages, Ready, RunScript,
                                        install_step, ready_check)
from pydantic import BaseModel

if sys.platform == "darwin":
    import objc
    from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateApplication,
                                     AXUIElementSetAttributeValue, AXUIElementSetMessagingTimeout, AXValueCreate,
                                     AXValueGetValue, kAXPositionAttribute, kAXSizeAttribute, kAXTitleAttribute,
                                     kAXValueCGPointType, kAXValueCGSizeType, kAXWindowsAttribute)
    from Quartz import (CGPoint, CGSize, CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowLayer,
                        kCGWindowListExcludeDesktopElements, kCGWindowListOptionOnScreenOnly, kCGWindowNumber,
                        kCGWindowOwnerPID)

    #: The Accessibility API's call for the window server's number of a window, private, as yabai and Hammerspoon
    #: call it: what ties a window the API names to one the window server shows.
    _WINDOW_NUMBER = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")[
        "_AXUIElementGetWindow"]
    _WINDOW_NUMBER.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]

if sys.platform == "win32":
    import winreg
    from ctypes import wintypes

    _user32, _dwmapi = ctypes.WinDLL("user32"), ctypes.WinDLL("dwmapi")
    _ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_ENUM, wintypes.LPARAM]
    for _call, _args in (("IsWindowVisible", [wintypes.HWND]), ("GetWindowTextLengthW", [wintypes.HWND]),
                         ("GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
                         ("GetWindowRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
                         ("ShowWindow", [wintypes.HWND, ctypes.c_int]),
                         ("SetWindowPos", [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT])):
        getattr(_user32, _call).argtypes = _args
    _dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    #: DWMWA_CLOAKED: a window another virtual desktop or the shell keeps hidden while it reports itself visible.
    _CLOAKED = 14
    #: ShowWindow's SW_RESTORE, and SetWindowPos's SWP_NOZORDER | SWP_NOACTIVATE: placed, as it stands, unfocused.
    _RESTORE, _PLACE = 9, 0x0004 | 0x0010

HERE = Path(__file__).resolve().parent
TASK = HERE / "task"
RUNTIME = HERE / "runtime"
#: Loaded into each of the task's Electron apps before its own main script: it logs each opening of their DevTools,
#: docked in the app's own window where the guard can't see it, for the bench's grade.
DEVTOOLS_HOOK = HERE / "devtools_hook.js"
SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]},
            {"os": {"type": "macos", "display": ["aqua"]}, "arch": ["arm64"]},
            {"os": {"type": "windows", "display": ["dwm"]}, "arch": ["amd64"]}]
MACOS = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"
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
#: The Windows builds for amd64: Electron's, Node's and Chrome for Testing's at the versions above, and the LibreOffice
#: and GnuCash the task's Windows descriptor runs from Program Files, from their installers, at the macOS versions.
WIN_ELECTRON_SHA256 = "ce7eedcef94de0d12b9ba54d5244f5a323c00e17b5cdea2ef0e4f440e1a74c4c"
WIN_NODE_SHA256 = "cbc74b5e0982c9dbb41525fd8fb5dcd32fbee237863f7829072f4639a1ce5f20"
WIN_CHROMIUM_SHA256 = "220021ecfdad08c116fc71a153e65e3861ba841c531afc4f7acc7bd5d44b41db"
LIBREOFFICE_MSI = ("https://downloadarchive.documentfoundation.org/libreoffice/old/25.8.7.3/win/x86_64/"
                   "LibreOffice_25.8.7.3_Win_x86-64.msi",
                   "ecdb65e76f5e91dc198b8c8dce5b5d6e1eb12fea6023553e52b591afd10b619d")
GNUCASH_SETUP = ("https://github.com/Gnucash/gnucash/releases/download/5.17/gnucash-5.17.setup.exe",
                 "a3e8049755e536f647640762a483ebe1b6c79cc50cc81a746fa64a404e98d271")
#: Where Chrome for Testing reads managed policies on Windows, under HKEY_LOCAL_MACHINE.
WIN_POLICIES = r"SOFTWARE\Policies\Google\Chrome for Testing"
WIN_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
#: Each console program the app starts on Windows gets no console window, which would stand in front of the task's.
_NO_WINDOW = 0x08000000
MAC_ELECTRON = RUNTIME / "electron" / "Electron.app" / "Contents" / "MacOS" / "Electron"
#: Where each of the task's Electron apps gets a bundle of its own on macOS: a clone of Electron.app under the app's name
#: and an identifier of its own, as an Electron app ships, so a driver that names apps tells them apart.
MAC_APPS = RUNTIME / "apps"
MAC_APP_ID = "dev.agentenv.bench"
MAC_CHROMIUM = (RUNTIME / "chromium" / "Google Chrome for Testing.app" / "Contents" / "MacOS"
                / "Google Chrome for Testing")
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
#: What the app's interpreter needs on macOS to find and place the windows, and the permission it's granted for it.
MAC_REQUIREMENTS = "requirements-macos.txt"
MAC_GRANTS = [{"executable": "venv/bin/python", "services": ["accessibility"]}]
#: How long an app may take to answer the Accessibility API before it's passed over for that look.
_AX_TIMEOUT_S = 2.0
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

    python: str
    downloads: list[Download]
    run: list[RunScript]
    grants: list[dict]


def macos(*, workspace: str, calc: bool = False, gnucash: bool = False, node: bool = False,
          browser: bool = False) -> dict:
    """The ``@install("macos", ...)`` of a task's app: the task's files, Electron, and what else its macOS descriptor
    runs (LibreOffice, GnuCash, Node, Chrome for Testing), PyObjC with Accessibility for its interpreter, its
    ``workspace`` folder of the home as its data, and a launch that's ready once each of its windows shows
    (``windows``)."""
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
    return dict(spec=MacOS(python=MAC_REQUIREMENTS, downloads=downloads,
                           run=[RunScript(script="install-macos.sh", scope="session")], grants=MAC_GRANTS),
                paths=[workspace], launch=Launch(at="boot", command=["venv/bin/python", "bench_app.py"]))


def windows(*, workspace: str, first_window: str, calc: bool = False, gnucash: bool = False, node: bool = False,
            browser: bool = False) -> dict:
    """The ``@windows(...)`` of a task's app: the task's files, Electron, and what else its Windows descriptor runs
    (LibreOffice, GnuCash, Node, Chrome for Testing), installed by ``install-windows.ps1``, its ``workspace`` folder of
    the home as its data, and a launch that's ready once ``first_window`` shows, after which its ``windows`` check waits
    for the rest."""
    files = json.loads((HERE / "files.json").read_text(encoding="utf-8"))["files"]
    downloads = [Download(url=f["url"], sha256=f["sha256"], to=f"task/{f['path']}") for f in files]
    downloads.append(Download(url=f"https://github.com/electron/electron/releases/download/v{ELECTRON}/"
                                  f"electron-v{ELECTRON}-win32-x64.zip",
                              sha256=WIN_ELECTRON_SHA256, to="runtime/electron.zip"))
    if node:
        downloads.append(Download(url=f"https://nodejs.org/dist/v{NODE}/node-v{NODE}-win-x64.zip",
                                  sha256=WIN_NODE_SHA256, to="runtime/node.zip"))
    if browser:
        downloads.append(Download(url=f"https://storage.googleapis.com/chrome-for-testing-public/{CHROMIUM}/"
                                      "win64/chrome-win64.zip",
                                  sha256=WIN_CHROMIUM_SHA256, to="runtime/chromium.zip"))
    for wanted, (url, sha256), name in ((calc, LIBREOFFICE_MSI, "LibreOffice.msi"),
                                        (gnucash, GNUCASH_SETUP, "gnucash-setup.exe")):
        if wanted:
            downloads.append(Download(url=url, sha256=sha256, to=f"runtime/{name}"))
    return dict(downloads=downloads, run=[RunScript(script="install-windows.ps1")], paths=[workspace],
                launch=Launch(at="boot", command=["venv/Scripts/python.exe", "bench_app.py"],
                              window={"title": first_window}, ready=Ready(window=True, timeout_s=_LAUNCH_TIMEOUT_S)))


class BenchTaskApp(ComputerAppEnvironment):
    """A bench task's app: its install builds the workspace, which must check out byte for byte, and it's ready once
    each of the task's windows shows. On Windows its server builds the workspace when it starts, unless it's there,
    before it keeps the app's paths as installed."""

    def __init__(self) -> None:
        super().__init__()
        if WINDOWS and not Path(_values(_spec())["${workspace}"]).exists():
            build_workspace()

    @install_step(scope="session", os=["linux", "macos"])
    def workspace(self) -> None:
        build_workspace()

    @install_step(scope="system", os="linux")
    def browser(self) -> None:
        install_browser(RUNTIME, POLICY_DIR)

    @install_step(scope="system", os="windows")
    def browser_policies_windows(self) -> None:
        """Where the task has a browser, ``POLICIES`` as Chrome for Testing's machine policies in the registry: a
        number or a boolean as a DWORD, anything else as JSON, as Chrome reads a dictionary or a list policy there."""
        if (RUNTIME / "chromium").exists():
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, WIN_POLICIES, 0, winreg.KEY_WRITE) as key:
                for name, value in POLICIES.items():
                    if isinstance(value, (bool, int)):
                        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))
                    else:
                        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, json.dumps(value))

    @install_step(scope="system", os="macos")
    def browser_policies(self) -> None:
        """Where the task has a browser, ``POLICIES`` as Chrome for Testing's managed preferences."""
        if (RUNTIME / "chromium").exists():
            MAC_POLICIES.parent.mkdir(parents=True, exist_ok=True)
            MAC_POLICIES.write_bytes(plistlib.dumps(POLICIES))

    @install_step(scope="session", os="macos")
    def electron_apps(self) -> None:
        """Each of the task's Electron apps as a bundle of its own, signed ad hoc, as its Info.plist changed."""
        for app in _spec()["apps"]:
            if app["command"][:2] == ["npx", "electron"]:
                bundle, name = _bundle(app), app["window"]["title"]
                bundle.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["cp", "-cR", str(MAC_ELECTRON.parents[2]), str(bundle)], check=True)
                info = bundle / "Contents" / "Info.plist"
                info.write_bytes(plistlib.dumps({**plistlib.loads(info.read_bytes()), "CFBundleName": name,
                                                 "CFBundleDisplayName": name,
                                                 "CFBundleIdentifier": f"{MAC_APP_ID}.{app['id']}"}))
                subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @ready_check(os=["linux", "macos", "windows"])
    def windows(self) -> bool:
        return all(claimed([app["window"] for app in _spec()["apps"] if "window" in app]))


def build_workspace() -> None:
    """The task's workspace, as its ``reset/setup.py`` builds it, checked by its ``reset/verify.py``."""
    spec = _spec()
    values = _values(spec)
    for step in ("setup", "verify"):
        subprocess.run([_sub(arg, values) for arg in spec["semantics"]["reset"][step]], cwd=TASK, check=True,
                       creationflags=_NO_WINDOW if WINDOWS else 0)


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
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                            creationflags=_NO_WINDOW if WINDOWS else 0))
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
    name = "macos" if MACOS else "windows" if WINDOWS else "linux"
    return json.loads((TASK / "platform" / f"launch.{name}.json").read_text(encoding="utf-8"))


def _values(spec: dict) -> dict[str, str]:
    workspace = Path(spec["workspace_root"].replace("${HOME}", str(Path.home())).replace("${USERPROFILE}",
                                                                                         str(Path.home())))
    return {"${bundle}": str(TASK), "${workspace}": str(workspace), "${workspace_uri}": workspace.as_uri(),
            "${python}": sys.executable}


def _sub(text: str, values: dict[str, str]) -> str:
    return re.sub(r"\$\{\w+\}", lambda match: values.get(match.group(0), match.group(0)), text)


def _command(app: dict, values: dict[str, str]) -> list[str]:
    """The app's command as the task gives it, with Electron, Node and Chromium this app installed in place of ``npx
    electron``, ``node`` and ``google-chrome``. Electron and Chromium run without Chromium's sandbox, which a container
    can't give them, Electron with its own profile under the workspace's runtime folder and Chromium without /dev/shm,
    which no computer sizes, and with its own window class. On macOS Electron runs sandboxed from the app's own bundle,
    on Chromium's mock keychain, since a bundle signed ad hoc would ask for the keychain item another app made, and
    Chrome for Testing in place of Google Chrome."""
    argv = [_sub(arg, values) for arg in app["command"]]
    if WINDOWS:
        profile = Path(values["${workspace}"]) / ".runtime" / f"electron-{app['id']}"
        if argv[0] in ("npx", "npx.cmd") and argv[1:2] == ["electron"]:
            return [str(RUNTIME / "electron" / "electron.exe"), *argv[2:], f"--user-data-dir={profile}"]
        if argv[0] == "node":
            return [str(RUNTIME / "node" / "node.exe"), *argv[1:]]
        if argv[0] == WIN_CHROME:
            return [str(RUNTIME / "chromium" / "chrome.exe"), *argv[1:]]
        return argv
    if argv[:2] == ["npx", "electron"] and MACOS:
        profile = Path(values["${workspace}"]) / ".runtime" / f"electron-{app['id']}"
        return [str(_bundle(app) / "Contents" / "MacOS" / "Electron"), *argv[2:], f"--user-data-dir={profile}",
                "--use-mock-keychain"]
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


def _bundle(app: dict) -> Path:
    return MAC_APPS / f"{app['window']['title']}.app"


def _hooked(command: list[str]) -> dict[str, str]:
    """For an Electron app, the environment that loads the DevTools hook into it."""
    if MACOS:
        electron = MAC_APPS in Path(command[0]).parents and Path(command[0]).name == "Electron"
    else:
        electron = command[0] == str(RUNTIME / "electron" / ("electron.exe" if WINDOWS else "electron"))
    return {"NODE_OPTIONS": f"--require={DEVTOOLS_HOOK.as_posix()}"} if electron else {}


def _quiet(command: list[str], env: dict[str, str]) -> None:
    """A first run's tip of the day off, GnuCash's and LibreOffice's, in the settings each keeps in the runtime folder
    the task gives it, where a reset leaves none."""
    if command[0] == "gnucash":
        _setting(Path(env["XDG_CONFIG_HOME"]) / "glib-2.0" / "settings" / "keyfile",
                 "[org/gnucash/GnuCash/dialogs/tip-of-the-day]", "show-at-startup=false")
    if WINDOWS and Path(command[0]).name == "gnucash.exe":
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              r"Software\GSettings\org\gnucash\GnuCash\dialogs\tip-of-the-day") as key:
            winreg.SetValueEx(key, "show-at-startup", 0, winreg.REG_SZ, "false")
    profile = next((arg.split("=", 1)[1] for arg in command if arg.startswith("-env:UserInstallation=")), None)
    if Path(command[0]).stem in ("libreoffice", "soffice", "scalc") and profile:
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
    """The ids of the shown windows ``window`` matches: X's, on macOS ``<pid>:<window number>``, or on Windows its
    handle."""
    if MACOS or WINDOWS:
        return [wid for wid, title, _ in (_shown() if MACOS else _win_shown())
                if (title == window["title"] if "title" in window else window["title_contains"] in title)]
    return subprocess.run(["xdotool", "search", "--onlyvisible", "--name", _title(window)],
                          capture_output=True, text=True).stdout.split()


def _shown() -> list[tuple[str, str, object]]:
    """The windows on screen on macOS, each its id, ``<pid>:<window number>``, its title and its element: those the
    window server shows, each found and named through the Accessibility API."""
    on_screen = {(info[kCGWindowOwnerPID], info[kCGWindowNumber]) for info in CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID)
        if info.get(kCGWindowLayer) == 0}
    found = []
    for pid in sorted({pid for pid, _ in on_screen}):
        app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, _AX_TIMEOUT_S)
        error, windows = AXUIElementCopyAttributeValue(app, kAXWindowsAttribute, None)
        for element in windows if not error and windows else ():
            number = ctypes.c_uint32()
            if _WINDOW_NUMBER(objc.pyobjc_id(element), ctypes.byref(number)) or (pid, number.value) not in on_screen:
                continue
            error, title = AXUIElementCopyAttributeValue(element, kAXTitleAttribute, None)
            found.append((f"{pid}:{number.value}", "" if error else str(title or ""), element))
    return found


def _win_shown() -> list[tuple[str, str, None]]:
    """The top-level windows Windows shows, each its handle and title: visible, titled, and not cloaked."""
    found = []

    def take(hwnd, _):
        length = _user32.GetWindowTextLengthW(hwnd)
        cloaked = wintypes.DWORD()
        _dwmapi.DwmGetWindowAttribute(hwnd, _CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if _user32.IsWindowVisible(hwnd) and length and not cloaked.value:
            title = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, title, length + 1)
            found.append((str(hwnd), title.value, None))
        return True

    _user32.EnumWindows(_ENUM(take), 0)
    return found


def _frame(element: object) -> tuple[int, int, int, int]:
    """A macOS window's place and size, as the Accessibility API gives them."""
    found = []
    for attribute, kind in ((kAXPositionAttribute, kAXValueCGPointType), (kAXSizeAttribute, kAXValueCGSizeType)):
        error, value = AXUIElementCopyAttributeValue(element, attribute, None)
        ok, struct = (False, None) if error else AXValueGetValue(value, kind, None)
        if not ok:
            raise ValueError(f"the window has no {attribute}")
        found.append(struct)
    point, size = found
    return int(point.x), int(point.y), int(size.width), int(size.height)


def _set_frame(element: object, bounds: dict) -> None:
    AXUIElementSetAttributeValue(element, kAXPositionAttribute,
                                 AXValueCreate(kAXValueCGPointType, CGPoint(bounds["x"], bounds["y"])))
    AXUIElementSetAttributeValue(element, kAXSizeAttribute,
                                 AXValueCreate(kAXValueCGSizeType, CGSize(bounds["width"], bounds["height"])))


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
    if WINDOWS:
        _user32.ShowWindow(int(wid), _RESTORE)
        _user32.SetWindowPos(int(wid), None, bounds["x"], bounds["y"], bounds["width"], bounds["height"], _PLACE)
        return
    if MACOS:
        for element in [element for shown, _, element in _shown() if shown == wid]:
            _set_frame(element, bounds)
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
            x, y, width, height = next(_frame(element) for shown, _, element in _shown() if shown == wid)
        elif WINDOWS:
            rect = wintypes.RECT()
            if not _user32.GetWindowRect(int(wid), ctypes.byref(rect)):
                return False
            x, y, width, height = rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        else:
            geometry = dict(line.split("=", 1) for line in subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", wid], capture_output=True, text=True).stdout.split())
            x, y, width, height = (int(geometry[key]) for key in ("X", "Y", "WIDTH", "HEIGHT"))
    except (KeyError, ValueError, StopIteration):
        return False
    return (abs(width - bounds["width"]) <= 8 and abs(height - bounds["height"]) <= 8
            and abs(x - bounds["x"]) <= 40 and abs(y - bounds["y"]) <= 60)


if __name__ == "__main__":
    launch()
