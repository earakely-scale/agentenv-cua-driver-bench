"""The bench task apps, read as a computer reads them at put: each declares the task's files at the lock's commit, its
runtimes, packages, workspace and launch; the files every app shares are the same in each; and the launcher's commands
and lock cleanup. BenchLab's app declares trycua's two files at the lock's commit, its data and launch and their modes,
and starts BenchLab as their runner does."""
import ast
import importlib
import json
import os
import plistlib
import shutil
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import get_args

import pytest

pytest.importorskip("agentenv_protocol.computer")

from agentenv_protocol.computer._load import load_class  # noqa: E402
from agentenv_protocol.computer.app import ComputerAppEnvironment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TASKS = {"cdb-s02": "CdbS02", "cdb-s03": "CdbS03", "cdb-s04": "CdbS04"}
SHARED = ("bench_app.py", "install.sh", "install-macos.sh", "devtools_hook.js", "requirements-macos.txt")


def _declared(task):
    for name in ("app", "bench_app"):
        sys.modules.pop(name, None)
    return load_class(ROOT / "envs" / task / "app.py", TASKS[task], ComputerAppEnvironment)


@pytest.fixture
def bench_app():
    sys.modules.pop("bench_app", None)
    sys.path.insert(0, str(ROOT / "envs" / "cdb-s02"))
    try:
        yield importlib.import_module("bench_app")
    finally:
        sys.path.remove(str(ROOT / "envs" / "cdb-s02"))
        sys.modules.pop("bench_app", None)


def test_the_files_every_task_app_shares_are_the_same_in_each():
    for name in SHARED:
        assert len({(ROOT / "envs" / task / name).read_bytes() for task in TASKS}) == 1, name


@pytest.mark.parametrize("task", TASKS)
def test_a_task_app_lists_its_tasks_files_at_the_locks_commit(task):
    commit = tomllib.loads((ROOT / "taskpack.lock.toml").read_text())["commit"]
    listed = json.loads((ROOT / "envs" / task / "files.json").read_text())

    assert listed["commit"] == commit
    assert {f["path"].split("/")[0] for f in listed["files"]} <= {"apps", "fixture", "reset", "platform", "brief.md",
                                                                  "task.cuabench.json"}
    assert "platform/launch.linux.json" in {f["path"] for f in listed["files"]}
    for f in listed["files"]:
        assert f["url"].startswith(f"https://raw.githubusercontent.com/trycua/cua/{commit}/libs/cua-driver-bench/"
                                   f"taskpack/tasks/shared/{task}/")
        assert not f["path"].startswith(("tests/", "evaluator/", "tools/"))
        assert not (f["path"].startswith("apps/") and "/tests/" in f["path"])


@pytest.mark.parametrize("task", TASKS)
def test_a_task_app_declares_its_files_runtimes_workspace_and_launch(task):
    declared = _declared(task).declaration()
    linux = declared.os["linux"]
    files = json.loads((ROOT / "envs" / task / "files.json").read_text())["files"]

    tos = [download["to"] for download in linux.install["downloads"]]
    assert tos[:len(files)] == [f"task/{f['path']}" for f in files]
    assert sorted(tos[len(files):]) == sorted(
        ["runtime/electron-amd64.zip", "runtime/electron-arm64.zip",
         *(["runtime/node-amd64.tar.xz", "runtime/node-arm64.tar.xz", "runtime/chromium-amd64.zip",
            "runtime/chromium-arm64.zip"] if task == "cdb-s04" else [])])
    apt = linux.install["packages"]["apt"]
    assert ("gnucash" in apt) == (task == "cdb-s03") and ("libreoffice-calc" in apt) == (task != "cdb-s04")
    assert ("fonts-liberation" in apt) == (task == "cdb-s04")
    assert linux.paths == [task]
    assert linux.launch.command == ["venv/bin/python", "bench_app.py"] and linux.launch.at == "boot"
    assert [step.name for step in declared.install_steps] == ["workspace", "browser", "browser_policies",
                                                              "electron_apps"]
    assert [check.name for check in declared.ready_checks] == ["windows"]

    macos = declared.os["macos"]
    tos = [download["to"] for download in macos.install["downloads"]]
    assert "task/platform/launch.macos.json" in tos[:len(files)]
    assert sorted(tos[len(files):]) == sorted(["runtime/electron-arm64.zip", *{
        "cdb-s02": ["runtime/LibreOffice.dmg"], "cdb-s03": ["runtime/LibreOffice.dmg", "runtime/Gnucash.dmg"],
        "cdb-s04": ["runtime/node-arm64.tar.xz", "runtime/chromium-arm64.zip"]}[task]])
    assert macos.install["run"] == [{"script": "install-macos.sh", "scope": "session"}]
    assert macos.install["python"] == "requirements-macos.txt"
    assert macos.install["grants"] == [{"executable": "venv/bin/python", "services": ["accessibility"]}]
    assert macos.paths == [task] and macos.launch.command == ["venv/bin/python", "bench_app.py"]
    assert macos.launch.ready is None


def test_the_launcher_runs_the_apps_runtimes_in_place_of_npx_and_node_with_electrons_devtools_hooked(
        bench_app, tmp_path, monkeypatch):
    monkeypatch.setattr(bench_app, "MACOS", False)
    values = {"${bundle}": "/opt/b/task", "${workspace}": "/home/user/cdb-s02", "${workspace_uri}": "file:///x",
              "${python}": "/py"}
    electron = {"id": "mail", "command": ["npx", "electron", ".", "--surface=mail", "--workspace=${workspace}"],
                "window": {"title": "Copperfield Mail"}}
    node = {"id": "archive", "command": ["node", "server.js"]}
    calc = {"id": "calc", "command": ["libreoffice", "--calc", "${workspace}/planning/a.ods"]}
    browser = {"id": "browser", "command": ["google-chrome", "--no-first-run", "--user-data-dir=${workspace}/.runtime/b",
                                            "--new-window", "http://127.0.0.1:4184/"]}

    assert bench_app._command(electron, values) == [
        str(bench_app.HERE / "runtime/electron/electron"), ".", "--surface=mail", "--workspace=/home/user/cdb-s02",
        "--no-sandbox", "--user-data-dir=/home/user/cdb-s02/.runtime/electron-mail"]
    assert bench_app._command(node, values) == [str(bench_app.HERE / "runtime/node/bin/node"), "server.js"]
    assert bench_app._command(calc, values) == ["libreoffice", "--calc", "/home/user/cdb-s02/planning/a.ods"]
    assert bench_app._command(browser, values) == [
        str(bench_app.HERE / "runtime/chromium/chrome"), "--no-sandbox", "--disable-dev-shm-usage",
        "--class=BenchChromium", "--no-first-run", "--user-data-dir=/home/user/cdb-s02/.runtime/b", "--new-window",
        "http://127.0.0.1:4184/"]
    assert bench_app._sub("${unknown}/x", values) == "${unknown}/x"
    assert bench_app._hooked(bench_app._command(electron, values)) == {
        "NODE_OPTIONS": f"--require={bench_app.HERE / 'devtools_hook.js'}"}
    assert bench_app._hooked(bench_app._command(browser, values)) == bench_app._hooked(bench_app._command(calc, values)) == {}

    monkeypatch.setattr(bench_app, "MACOS", True)
    chrome = {"id": "browser", "command": [bench_app.MAC_CHROME, "--no-first-run", "http://127.0.0.1:4184/"]}
    assert bench_app._command(electron, values) == [
        str(bench_app.HERE / "runtime/apps/Copperfield Mail.app/Contents/MacOS/Electron"), ".", "--surface=mail",
        "--workspace=/home/user/cdb-s02", "--user-data-dir=/home/user/cdb-s02/.runtime/electron-mail",
        "--use-mock-keychain"]
    assert bench_app._command(chrome, values) == [str(bench_app.MAC_CHROMIUM), "--no-first-run", "http://127.0.0.1:4184/"]
    assert bench_app.MAC_CHROMIUM.relative_to(bench_app.HERE).as_posix() == (
        "runtime/chromium/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
    assert bench_app._hooked(bench_app._command(electron, values)) == {
        "NODE_OPTIONS": f"--require={bench_app.HERE / 'devtools_hook.js'}"}


def test_on_macos_the_launcher_finds_and_places_windows_through_the_accessibility_api(bench_app, monkeypatch):
    frames = {"mail": (20, 30, 900, 680), "calc": (0, 0, 800, 600)}
    moved = []
    monkeypatch.setattr(bench_app, "MACOS", True)
    monkeypatch.setattr(bench_app, "_shown", lambda: [("7:70", "Copperfield Mail", "mail"),
                                                      ("9:90", "lighthouse-replan.ods - LibreOffice Calc", "calc")])
    monkeypatch.setattr(bench_app, "_frame", frames.__getitem__)
    monkeypatch.setattr(bench_app, "_set_frame", lambda element, bounds: moved.append((element, bounds)))
    bounds = {"x": 380, "y": 160, "width": 1180, "height": 780}

    assert bench_app._search({"title": "Copperfield Mail"}) == ["7:70"] and bench_app._search({"title": "Mail"}) == []
    assert bench_app._search({"title_contains": "lighthouse-replan"}) == ["9:90"]
    assert bench_app._at("7:70", {"x": 20, "y": 30, "width": 900, "height": 680}) and not bench_app._at("9:90", bounds)
    assert not bench_app._at("8:80", bounds)
    bench_app._move("9:90", bounds)
    assert moved == [("calc", bounds)]


def test_a_browser_install_unpacks_chromium_with_its_execute_bits_and_writes_the_policies(bench_app, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    bench_app.install_browser(runtime, tmp_path / "policies")
    assert not (tmp_path / "policies").exists()
    with zipfile.ZipFile(runtime / "chromium-amd64.zip", "w") as archive:
        executable = zipfile.ZipInfo("chrome-linux64/chrome")
        executable.external_attr = 0o100755 << 16
        archive.writestr(executable, "#!/bin/sh\n")

    bench_app.install_browser(runtime, tmp_path / "policies")

    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == [
        "policies/agentenv-bench.json", "runtime/chromium/chrome"]
    assert os.access(runtime / "chromium/chrome", os.X_OK)
    policies = json.loads((tmp_path / "policies/agentenv-bench.json").read_text())
    assert policies["BrowserSignin"] == 0 and not policies["CommandLineFlagSecurityWarningsEnabled"]
    assert policies["DeveloperToolsAvailability"] == 2


def test_the_launcher_matches_a_whole_title_or_part_of_one_literally(bench_app):
    assert bench_app._title({"title": "Copperfield Mail"}) == "^Copperfield Mail$"
    assert bench_app._title({"title_contains": "a.b (1)"}) == r"a\.b \(1\)"


def test_a_window_two_matches_hold_belongs_to_the_more_specific(bench_app, monkeypatch):
    shown = {"Ledger Lantern Mail": ["7"], "kestrel-wharf-reconciliation": ["1"], "kestrel-wharf": ["1", "2"]}
    monkeypatch.setattr(bench_app, "_search", lambda window: shown[window.get("title") or window["title_contains"]])
    windows = [{"title": "Ledger Lantern Mail"}, {"title_contains": "kestrel-wharf-reconciliation"},
               {"title_contains": "kestrel-wharf"}]

    assert bench_app.claimed(windows) == [["7"], ["1"], ["2"]]
    shown["kestrel-wharf"] = ["1"]
    assert bench_app.claimed(windows) == [["7"], ["1"], []]


def test_a_tip_setting_takes_its_keys_place_in_a_keyfile_and_keeps_the_rest(bench_app, tmp_path):
    keyfile = tmp_path / "glib-2.0" / "settings" / "keyfile"
    section, line = "[org/gnucash/GnuCash/dialogs/tip-of-the-day]", "show-at-startup=false"

    bench_app._setting(keyfile, section, line)
    assert keyfile.read_text() == f"{section}\n{line}\n"
    keyfile.write_text(f"[org/gnucash/GnuCash/general]\nprefs-version=5005\n\n{section}\nshow-at-startup=true\n"
                       "current-tip=1\n\n[org/gnucash/GnuCash/history]\nfile0='/b'\n")
    bench_app._setting(keyfile, section, line)
    assert keyfile.read_text() == ("[org/gnucash/GnuCash/general]\nprefs-version=5005\n\n"
                                   f"{section}\n{line}\ncurrent-tip=1\n\n[org/gnucash/GnuCash/history]\nfile0='/b'\n")
    keyfile.write_text("[org/gnucash/GnuCash/general]\nprefs-version=5005\n")
    bench_app._setting(keyfile, section, line)
    assert keyfile.read_text() == f"[org/gnucash/GnuCash/general]\nprefs-version=5005\n\n{section}\n{line}\n"


def test_libreoffice_starts_without_its_tip_in_a_new_profile_and_in_one_it_wrote(bench_app, tmp_path):
    profile = tmp_path / "lo"
    command = ["libreoffice", "--calc", f"-env:UserInstallation={profile.as_uri()}", "/w/a.ods"]
    xcu = profile / "user" / "registrymodifications.xcu"

    bench_app._quiet(command, {})
    assert '<prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false</value>' in xcu.read_text()
    xcu.write_text('<?xml version="1.0"?>\n<oor:items xmlns:oor="http://openoffice.org/2001/registry">\n'
                   '<item oor:path="/a"><prop oor:name="b"><value>1</value></prop></item>\n</oor:items>\n')
    bench_app._quiet(command, {})
    text = xcu.read_text()
    assert '<prop oor:name="b">' in text and text.count("ShowTipOfTheDay") == 1 and text.endswith("</oor:items>\n")


def test_a_launch_removes_the_locks_stopped_apps_left_and_nothing_else(bench_app, tmp_path):
    for name in ("planning/.~lock.replan.ods#", "book/k.gnucash.LCK", "book/k.gnucash.LNK", "book/k.gnucash",
                 "planning/replan.ods", "mail/messages.json"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")

    bench_app._unlock(tmp_path)

    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == [
        "book/k.gnucash", "mail/messages.json", "planning/replan.ods"]


@pytest.fixture
def lab():
    for name in ("app", "lab"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(ROOT / "envs" / "benchlab"))
    try:
        yield importlib.import_module("lab")
    finally:
        sys.path.remove(str(ROOT / "envs" / "benchlab"))
        for name in ("app", "lab"):
            sys.modules.pop(name, None)


def test_benchlab_declares_trycuas_files_at_the_locks_commit_its_data_and_launch_and_their_modes(lab):
    app = sys.modules["app"]
    linux = app.BenchLab.declaration().os["linux"]
    commit = tomllib.loads((ROOT / "taskpack.lock.toml").read_text())["commit"]
    listed = json.loads((ROOT / "envs" / "benchlab" / "files.json").read_text())

    assert listed["commit"] == commit
    assert [download["to"] for download in linux.install["downloads"]] == [
        "lab/linux/benchlab.py", "lab/probes/_common/benchlab_common.py"]
    assert all(f["url"].startswith(f"https://raw.githubusercontent.com/trycua/cua/{commit}/") for f in listed["files"])
    assert {"python3-gi", "gir1.2-gtk-3.0", "xdotool"} <= set(linux.install["packages"]["apt"])
    assert linux.paths == [app.DATA] == [".benchlab"]
    assert linux.launch.command == ["venv/bin/python", "lab.py"] and linux.launch.window == {"class": "BenchLab"}
    pack = ROOT / "artifacts" / "taskpack" / "linux" / "benchlab.py"
    if pack.exists():
        [modes] = [ast.literal_eval(node.value) for node in ast.parse(pack.read_text()).body
                   if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "MODES"]
        assert get_args(app.BenchLab.Settings.model_fields["mode"].annotation) == modes
    assert app.BenchLab.Settings().model_dump() == {"mode": "hover", "seed": 1, "condition": "foreground"}
    windows = app.BenchLab.declaration().os["windows"]
    assert [download["to"] for download in windows.install["downloads"]] == [
        "lab/windows/benchlab.py", "lab/probes/_common/benchlab_common.py", "vc_redist.x64.exe"]
    assert all(f["url"].startswith(f"https://raw.githubusercontent.com/trycua/cua/{commit}/") for f in listed["windows"])
    assert windows.install["python"] == "requirements-windows.txt" and windows.paths == [".benchlab"]
    assert [run["script"] for run in windows.install["run"]] == ["install-windows.ps1"]
    assert windows.launch.command == ["venv/Scripts/python.exe", "lab_windows.py"]
    assert windows.launch.window == {"instance": "benchlab.exe"}


def test_benchlab_starts_as_trycuas_runner_starts_it_with_a_throwaway_home(lab, monkeypatch, tmp_path):
    started = {}

    class Lab:
        pid = 7

        def __init__(self, argv, env, **_):
            started.update(argv=argv, home=env["HOME"])

        def wait(self):
            return 0

    monkeypatch.setattr(lab.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lab.subprocess, "Popen", Lab)
    monkeypatch.setattr(lab, "_place", lambda process: None)
    settings = sys.modules["app"].BenchLab.Settings(mode="irmodal", seed=517139)

    with pytest.raises(SystemExit):
        lab.main(settings)

    data = tmp_path / ".benchlab"
    assert started["argv"] == ["/usr/bin/python3", str(lab.LAB), "--mode", "irmodal", "--seed", "517139",
                               "--state", str(data / "state.json"), "--events", str(data / "events.jsonl")]
    assert data.is_dir() and started["home"] != str(tmp_path)


@pytest.mark.parametrize("condition, activates", [("foreground", True), ("background", False)])
def test_on_windows_benchlab_starts_from_its_named_pythonw_as_trycuas_runner_starts_it(lab, monkeypatch, tmp_path,
                                                                                      condition, activates):
    sys.path.insert(0, str(ROOT / "envs" / "benchlab"))
    try:
        lab_windows = importlib.import_module("lab_windows")
    finally:
        sys.path.remove(str(ROOT / "envs" / "benchlab"))
        sys.modules.pop("lab_windows", None)
    started = {}

    class Lab:
        def __init__(self, argv, env, **_):
            started.update(argv=argv, env=env)

        def wait(self):
            return 0

    monkeypatch.setattr(lab_windows.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lab_windows.subprocess, "Popen", Lab)
    settings = sys.modules["app"].BenchLab.Settings(mode="irmodal", seed=517139, condition=condition)

    with pytest.raises(SystemExit):
        lab_windows.main(settings)

    data = tmp_path / ".benchlab"
    assert started["argv"] == [
        str(lab_windows.LAB), str(lab_windows.HERE / "lab" / "windows" / "benchlab.py"), "--mode", "irmodal",
        "--seed", "517139", "--state", str(data / "state.json"), "--events", str(data / "events.jsonl"),
        "--frame", "40,40,760,540", *([] if activates else ["--no-activate"])]
    assert lab_windows.LAB.name == "BenchLab.exe" and started["env"]["PYTHONPATH"]


def test_on_macos_each_electron_app_gets_a_bundle_of_its_own_name_and_identifier(bench_app, tmp_path, monkeypatch):
    source = tmp_path / "runtime" / "electron" / "Electron.app" / "Contents"
    (source / "MacOS").mkdir(parents=True)
    (source / "MacOS" / "Electron").write_text("electron")
    (source / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "Electron", "CFBundleExecutable": "Electron",
                                                        "CFBundleIdentifier": "com.github.Electron"}))
    ran = []
    monkeypatch.setattr(bench_app, "MAC_ELECTRON", source / "MacOS" / "Electron")
    monkeypatch.setattr(bench_app, "MAC_APPS", tmp_path / "runtime" / "apps")
    monkeypatch.setattr(bench_app, "_spec", lambda: {"apps": [
        {"id": "mail", "command": ["npx", "electron", "."], "window": {"title": "Copperfield Mail"}},
        {"id": "calc", "command": ["soffice"], "window": {"title_contains": "replan"}}]})

    def run(argv, **kwargs):
        ran.append(argv[0])
        if argv[0] == "cp":
            shutil.copytree(argv[-2], argv[-1])
    monkeypatch.setattr(bench_app.subprocess, "run", run)
    bench_app.BenchTaskApp.electron_apps(None)

    info = plistlib.loads((tmp_path / "runtime/apps/Copperfield Mail.app/Contents/Info.plist").read_bytes())
    assert (info["CFBundleName"], info["CFBundleDisplayName"], info["CFBundleIdentifier"], info["CFBundleExecutable"]) == (
        "Copperfield Mail", "Copperfield Mail", "dev.agentenv.bench.mail", "Electron")
    assert ran == ["cp", "codesign"] and sorted(p.name for p in (tmp_path / "runtime/apps").iterdir()) == [
        "Copperfield Mail.app"]
