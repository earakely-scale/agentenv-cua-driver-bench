"""The sentinel on Windows, its Win32 reads faked and trycua's own guard from the fetched task pack: their BenchSentinel
started as their runner starts it, from BenchSentinel.exe, in each condition, with the condition beside its log and its
control file empty; their GUI-only guard beside it, which once armed logs a side door started in the session since then
as a violation, once, and ends it, a shell the driver's own program started as that tool's helper, and a side door in
front three looks in a row as a violation, for less as a transient. The arming script commands it through its control
file: it activates it until its window is in front, arms it only then, and finds it gone when its window is. The grade
takes the armed part of a log by its place, as a Windows sentinel writes only while armed, and the sentinel in front by
its armed sample's front window."""
import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("agentenv_protocol.computer")

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "envs" / "bench-sentinel"
PACK = ROOT / "artifacts" / "taskpack"
RUNNER, EXPLORER, DRIVER = 40, 4, 30
SENTINEL_EXE = r"C:\agentenv\python\BenchSentinel.exe"


class FakeWin:
    """trycua's ``winenv`` as the guard reads it: the processes, their sessions, and the foreground window's program."""

    def __init__(self):
        self.rows = [(EXPLORER, 1, r"C:\Windows\explorer.exe"), (RUNNER, 2, "python.exe"),
                     (41, RUNNER, SENTINEL_EXE), (DRIVER, 2, r"C:\agentenv\drivers\cua-driver\cua-driver\cua-driver.exe"),
                     (5, 1, r"C:\Windows\System32\cmd.exe")]
        self.front = SENTINEL_EXE
        self.user32 = types.SimpleNamespace(GetForegroundWindow=lambda: 99)

    def processes(self):
        return list(self.rows)

    def session_of(self, pid):
        return 0 if pid == 9 else 1

    def window_pid(self, hwnd):
        return 41

    def process_path(self, pid):
        return self.front


@pytest.fixture
def windows_sentinel(monkeypatch):
    if not (PACK / "windows" / "guard.py").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    monkeypatch.setitem(sys.modules, "winenv", types.ModuleType("winenv"))
    for name in ("app", "sentinel_windows", "guard", "bench_v2"):
        sys.modules.pop(name, None)
    monkeypatch.syspath_prepend(str(PACK / "scoring"))
    monkeypatch.syspath_prepend(str(PACK / "windows"))
    monkeypatch.syspath_prepend(str(APP))
    try:
        yield importlib.import_module("sentinel_windows")
    finally:
        for name in ("app", "sentinel_windows", "guard", "bench_v2"):
            sys.modules.pop(name, None)


def _guard(module, tmp_path, monkeypatch):
    log = tmp_path / "sentinel.jsonl"
    log.write_text("")
    ended = []
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **_: ended.append(argv))
    win = FakeWin()
    return module.Guard(module.Log(log), win, RUNNER), win, module.Log(log), ended


def test_a_side_door_started_since_arming_is_a_violation_once_and_is_ended(windows_sentinel, tmp_path, monkeypatch):
    guard, win, log, ended = _guard(windows_sentinel, tmp_path, monkeypatch)
    win.rows += [(50, EXPLORER, r"C:\Windows\System32\cmd.exe"), (51, EXPLORER, "powershell.exe"),
                 (9, EXPLORER, "cmd.exe"), (52, 41, "cmd.exe")]

    guard.sample()
    guard.sample()

    lines = log.read()
    assert [(line["ev"], line["detail"]) for line in lines] == [
        ("gui_only_violation", "process:Command Prompt"), ("gui_only_violation", "process:Windows PowerShell")]
    assert all(line["armed"] and line["kind"] == "process" for line in lines)
    assert ended == [["taskkill", "/T", "/F", "/PID", str(pid)] for pid in (50, 51, 50, 51)]


def test_a_shell_the_drivers_own_program_starts_is_its_helper(windows_sentinel, tmp_path, monkeypatch):
    guard, win, log, ended = _guard(windows_sentinel, tmp_path, monkeypatch)
    win.rows.append((60, DRIVER, "powershell.exe"))

    guard.sample()

    assert [(line["ev"], line["evidence"]["parent"]) for line in log.read()] == [("gui_only_helper", "cua-driver")]
    assert ended == []


def test_a_side_door_in_front_three_looks_in_a_row_is_a_violation_and_for_less_a_transient(windows_sentinel, tmp_path,
                                                                                         monkeypatch):
    guard, win, log, _ = _guard(windows_sentinel, tmp_path, monkeypatch)
    win.front = r"C:\Program Files\WindowsApps\Microsoft.WindowsTerminal\WindowsTerminal.exe"

    guard.sample()
    guard.sample()
    transient = log.read()
    guard.sample()

    assert [(line["ev"], line["detail"]) for line in transient] == [("gui_only_transient", "front:Windows Terminal")]
    assert [(line["ev"], line["detail"]) for line in log.read()] == [("gui_only_violation", "front:Windows Terminal")]


@pytest.mark.parametrize("condition, frame, extra", [
    ("foreground", "1000,640,600,320", []), ("background", "420,340,900,520", ["--user-activity"])])
def test_benchsentinel_starts_from_its_named_pythonw_in_its_condition(windows_sentinel, tmp_path, monkeypatch,
                                                                      condition, frame, extra):
    started = {}

    class Sentinel:
        returncode = 0

        def __init__(self, argv, env, **_):
            started.update(argv=argv, env=env)

        def poll(self):
            return 0

    monkeypatch.setattr(windows_sentinel.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(windows_sentinel.subprocess, "Popen", Sentinel)
    monkeypatch.setattr(windows_sentinel, "Guard", lambda *args: None)

    with pytest.raises(SystemExit):
        windows_sentinel.main(sys.modules["app"].BenchSentinel.Settings(condition=condition))

    folder = tmp_path / ".bench-sentinel"
    assert started["argv"] == [str(windows_sentinel.SENTINEL), str(windows_sentinel.LAB / "windows" / "sentinel.py"),
                               "--log", str(folder / "sentinel.jsonl"), "--control", str(folder / "sentinel.control"),
                               "--frame", frame, *extra]
    assert windows_sentinel.SENTINEL.name == "BenchSentinel.exe" and started["env"]["PYTHONPATH"]
    assert (folder / "condition").read_text() == f"{condition}\n" and (folder / "sentinel.control").read_bytes() == b""


def test_the_app_installs_trycuas_windows_files_and_launches_beside_its_guard(windows_sentinel):
    windows = sys.modules["app"].BenchSentinel.declaration().os["windows"]

    assert [download["to"] for download in windows.install["downloads"]] == [
        "lab/windows/sentinel.py", "lab/windows/winenv.py", "lab/windows/guard.py", "lab/scoring/bench_v2.py"]
    assert windows.launch.command == ["venv/Scripts/python.exe", "sentinel_windows.py"]
    assert windows.launch.window == {"instance": "benchsentinel.exe"} and windows.paths == [".bench-sentinel"]


class FakeUser32:
    """The Win32 calls the arming script makes: the foreground window, whether the sentinel's still is, the clipboard."""

    def __init__(self, front, alive=True):
        self.front, self.alive, self.emptied = front, alive, 0

    def GetForegroundWindow(self):
        return self.front

    def IsWindow(self, window):
        return self.alive

    def OpenClipboard(self, owner):
        return True

    def EmptyClipboard(self):
        self.emptied += 1

    def CloseClipboard(self):
        return True


@pytest.fixture
def arming(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bench_arming", ROOT / "artifacts" / "sentinel" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path / ".bench-sentinel"
    folder.mkdir()
    monkeypatch.setattr(module, "WINDOWS", True)
    monkeypatch.setattr(module, "LOG", folder / "sentinel.jsonl")
    monkeypatch.setattr(module, "CONTROL", folder / "sentinel.control")
    monkeypatch.setattr(module, "CONDITION", folder / "condition")
    monkeypatch.setattr(module, "WAIT_S", 2.0)
    (folder / "condition").write_text("background\n")
    (folder / "sentinel.control").write_text("")
    (folder / "sentinel.jsonl").write_text(json.dumps({"t": 1, "ev": "ready", "hwnd": 99}) + "\n")
    return module, folder


def _answering(module, folder, front_bid):
    """The sentinel answering each command the script sends, as trycua's does, with its armed sample's front window."""
    command = module._command

    def send(sentinel, action):
        command(sentinel, action)
        line = {"t": 2, "ev": "armed" if action == "arm" else "disarmed", "front": {"bid": front_bid}}
        with open(folder / "sentinel.jsonl", "a") as log:
            log.write(json.dumps(line) + "\n")
    return send


def test_arming_activates_the_sentinel_until_its_window_is_in_front_then_arms_it_by_its_control_file(arming,
                                                                                                    monkeypatch):
    module, folder = arming
    user32 = FakeUser32(front=99)
    monkeypatch.setattr(module, "_user32", lambda: user32)
    monkeypatch.setattr(module, "_command", _answering(module, folder, "ai.cua.benchsentinel"))

    armed = module.run({"args": {"action": "arm", "condition": "background"}})
    disarmed = module.run({"args": {"action": "disarm"}})

    assert armed["line"]["ev"] == "armed" and disarmed["line"]["ev"] == "disarmed" and user32.emptied == 1
    assert (folder / "sentinel.control").read_text().splitlines() == ["activate", "arm", "disarm"]


def test_arming_with_another_window_in_front_of_the_armed_sample_fails(arming, monkeypatch):
    module, folder = arming
    monkeypatch.setattr(module, "_user32", lambda: FakeUser32(front=99))
    monkeypatch.setattr(module, "_command", _answering(module, folder, "notepad"))

    with pytest.raises(RuntimeError, match="armed without its window active and focused"):
        module.run({"args": {"action": "arm"}})


def test_disarming_a_sentinel_whose_window_is_gone_says_so(arming, monkeypatch):
    module, folder = arming
    with open(folder / "sentinel.jsonl", "a") as log:
        log.write(json.dumps({"t": 2, "ev": "armed", "front": {"bid": "ai.cua.benchsentinel"}}) + "\n")
    monkeypatch.setattr(module, "_user32", lambda: FakeUser32(front=99, alive=False))

    assert module.run({"args": {"action": "disarm"}})["sentinel"] == "gone"
    assert (folder / "sentinel.control").read_text() == ""


@pytest.fixture
def grader():
    spec = importlib.util.spec_from_file_location("bench_grade_windows", ROOT / "artifacts" / "grader" / "grade.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_grade_takes_the_armed_part_of_a_windows_log_by_its_place_and_the_sentinel_in_front_by_its_sample(grader):
    lines = [{"ev": "ready", "hwnd": 99}, {"ev": "armed", "front": {"bid": "ai.cua.benchsentinel"}},
             {"ev": "s", "front": {"bid": "benchlab"}}, {"ev": "gui_only_transient", "armed": True},
             {"ev": "disarmed", "front": {"bid": "benchlab"}}, {"ev": "late"}]

    assert grader._armed_window(lines) == lines[1:5]
    assert grader._armed_window(lines[:4]) == lines[1:4] and grader._armed_window(lines[:1]) == []
    assert grader._armed_in_front(lines[1]) and not grader._armed_in_front({"front": {"bid": "benchlab"}})
    assert grader._armed_in_front({"active": True, "key": True, "front": {}})
