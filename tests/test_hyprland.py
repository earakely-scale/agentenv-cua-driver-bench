"""The bench on Omarchy, Hyprland's IPC faked and trycua's own Hyprland files from the fetched task pack: BenchLab and
the sentinel install trycua's Hyprland port at the lock's commit and start as their Hyprland runner starts them, after
their window rules, sent as their runner sends them, at their runner's frames; their GUI-only guard beside the sentinel,
which once armed logs a terminal started since then as a violation, once, and ends it, one cua-driver's own program
started as that tool's helper, a terminal's window or one of Omarchy's launchers in front three looks in a row as a
violation
and for less as a transient. The arming script activates the sentinel until its window is the active window on top,
then arms it; the grade takes a Hyprland log's armed part by its place and the sentinel in front by its armed sample;
and the sentinel's self-check asks for disturbances trycua's oracle causes and criteria trycua's A22 scores."""
import ast
import importlib
import importlib.util
import json
import signal
import sys
import tomllib
import types
from pathlib import Path

import pytest

pytest.importorskip("agentenv_protocol.computer")

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"
SESSION = PACK / "launch" / "hyprland_session.py"
RUNNER, DRIVER, HYPRLAND = 40, 30, 2
OWN = "0xsentinel"


@pytest.fixture(autouse=True)
def _pack():
    if not (PACK / "hyprland" / "guard.py").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")


def _constant(path, name):
    [value] = [ast.literal_eval(node.value) for node in ast.parse(path.read_text()).body
               if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == name for target in node.targets)]
    return value


def _trycuas_rules():
    """The requests trycua's Hyprland runner's ``apply_rules`` sends for their ``bench.lua``."""
    [function] = [node for node in ast.parse(SESSION.read_text()).body
                  if isinstance(node, ast.FunctionDef) and node.name == "apply_rules"]
    scope = {"RULES": PACK / "hyprland" / "bench.lua"}
    exec(compile(ast.Module([function], []), str(SESSION), "exec"), scope)
    sent = []
    scope["apply_rules"](types.SimpleNamespace(request=sent.append))
    return sent


class FakeHypr:
    """trycua's ``hypr`` as the launchers, the guard and the arming script read it."""

    def __init__(self):
        self.sent, self.placed, self.focused, self.at = [], [], [], {}
        self.active, self.layers, self.top = {"class": "BenchSentinel", "address": OWN}, {}, OWN

    def request(self, command):
        self.sent.append(command)

    def by_pid(self, pid):
        return [{"address": "0xlab", "at": self.at.get("at", [0, 0]), "size": self.at.get("size", [800, 600])}]

    def place(self, address, frame):
        self.placed.append((address, frame))
        self.at = {"at": list(frame[:2]), "size": list(frame[2:])}

    def focus(self, address):
        self.focused.append(address)

    def active_window(self):
        return dict(self.active)

    def clients(self):
        return [{"address": "0xlab"}, {"address": self.top}]

    def query(self, what):
        return {"layers": self.layers}[what]


# BenchLab


@pytest.fixture
def lab_hyprland(monkeypatch):
    for name in ("app", "lab_hyprland"):
        sys.modules.pop(name, None)
    monkeypatch.syspath_prepend(str(ROOT / "envs" / "benchlab"))
    try:
        yield importlib.import_module("lab_hyprland")
    finally:
        for name in ("app", "lab_hyprland"):
            sys.modules.pop(name, None)


def test_benchlab_installs_trycuas_hyprland_port_at_the_locks_commit_and_launches_on_wayland(lab_hyprland):
    app = sys.modules["app"]
    omarchy = app.BenchLab.declaration().os["linux/omarchy"]
    commit = tomllib.loads((ROOT / "taskpack.lock.toml").read_text())["commit"]
    listed = json.loads((ROOT / "envs" / "benchlab" / "files.json").read_text())["omarchy"]

    assert [download["to"] for download in omarchy.install["downloads"]] == [
        "lab/linux/benchlab.py", "lab/probes/_common/benchlab_common.py", "lab/hyprland/hypr.py",
        "lab/hyprland/bench.lua"]
    assert all(f["url"].startswith(f"https://raw.githubusercontent.com/trycua/cua/{commit}/") for f in listed)
    assert not omarchy.install.get("packages") and omarchy.paths == [".benchlab"]
    assert omarchy.launch.command == ["venv/bin/python", "lab_hyprland.py"]
    assert omarchy.launch.window == {"class": "BenchLab"} and omarchy.launch.ready.window is True
    checks = {check.name: check.os for check in app.BenchLab.declaration().ready_checks}
    assert "linux/omarchy" in checks["state_written"] and checks["placed"] == ["linux/omarchy"]


def test_benchlabs_frame_is_trycuas_hyprland_runners(lab_hyprland):
    assert lab_hyprland.FRAME == sys.modules["app"].FRAME == _constant(SESSION, "LAB_FRAME")


@pytest.mark.parametrize("condition, focused", [("foreground", ["0xlab"]), ("background", [])])
def test_benchlab_starts_as_trycuas_hyprland_runner_starts_it_placed_after_their_rules(lab_hyprland, monkeypatch,
                                                                                    tmp_path, condition, focused):
    hypr, started = FakeHypr(), {}
    data = tmp_path / ".benchlab"
    data.mkdir()
    (data / "events.jsonl").write_text("stale\n")

    class Lab:
        pid = 7

        def __init__(self, argv, env, **_):
            started.update(argv=argv, env=env, rules=list(hypr.sent))
            (data / "state.json").write_text("{}")

        def poll(self):
            return None

        def wait(self):
            return 0

    monkeypatch.setattr(lab_hyprland, "module", lambda path: hypr)
    monkeypatch.setattr(lab_hyprland, "RULES", PACK / "hyprland" / "bench.lua")
    monkeypatch.setattr(lab_hyprland.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lab_hyprland.subprocess, "Popen", Lab)
    monkeypatch.setattr(lab_hyprland.time, "sleep", lambda s: None)
    settings = sys.modules["app"].BenchLab.Settings(mode="irmodal", seed=517139, condition=condition)

    with pytest.raises(SystemExit):
        lab_hyprland.main(settings)

    assert started["argv"] == ["/usr/bin/python3", str(lab_hyprland.LAB / "linux" / "benchlab.py"), "--mode",
                               "irmodal", "--seed", "517139", "--state", str(data / "state.json"), "--events",
                               str(data / "events.jsonl")]
    assert (started["env"]["GDK_BACKEND"], started["env"]["NO_AT_BRIDGE"]) == ("wayland", "0")
    assert started["rules"] == _trycuas_rules() and len(started["rules"]) == 3
    assert hypr.placed == [("0xlab", (40, 40, 760, 540))] and hypr.focused == focused
    assert not (data / "events.jsonl").exists()


# The sentinel


@pytest.fixture
def sentinel_hyprland(monkeypatch):
    names = ("app", "sentinel_hyprland", "guard", "bench_v2", "hypr")
    for name in names:
        sys.modules.pop(name, None)
    monkeypatch.syspath_prepend(str(PACK / "scoring"))
    monkeypatch.syspath_prepend(str(PACK / "hyprland"))
    monkeypatch.syspath_prepend(str(ROOT / "envs" / "bench-sentinel"))
    try:
        yield importlib.import_module("sentinel_hyprland")
    finally:
        for name in names:
            sys.modules.pop(name, None)


def test_the_sentinel_installs_trycuas_hyprland_port_and_launches_beside_its_guard(sentinel_hyprland):
    app = sys.modules["app"]
    omarchy = app.BenchSentinel.declaration().os["linux/omarchy"]

    assert [download["to"] for download in omarchy.install["downloads"]] == [
        "lab/hyprland/sentinel.py", "lab/hyprland/hypr.py", "lab/hyprland/guard.py", "lab/hyprland/bench.lua",
        "lab/scoring/bench_v2.py"]
    assert not omarchy.install.get("packages") and omarchy.paths == [".bench-sentinel"]
    assert omarchy.launch.command == ["venv/bin/python", "sentinel_hyprland.py"]
    assert omarchy.launch.window == {"class": "BenchSentinel"}
    assert "started" in {check.name for check in app.BenchSentinel.declaration().ready_checks
                         if "linux/omarchy" in (check.os or [])}
    assert sentinel_hyprland.WITNESS_FRAME == _constant(SESSION, "WITNESS_FRAME")


@pytest.mark.parametrize("condition, frame, extra", [
    ("foreground", "1000,640,600,320", []), ("background", "420,340,900,520", ["--user-activity"])])
def test_benchsentinel_starts_as_trycuas_hyprland_runner_starts_it_in_its_condition(sentinel_hyprland, tmp_path,
                                                                                    monkeypatch, condition, frame,
                                                                                    extra):
    hypr, started = FakeHypr(), {}

    class Sentinel:
        returncode = 0

        def __init__(self, argv, env, **_):
            started.update(argv=argv, env=env, rules=list(hypr.sent))

        def poll(self):
            return 0

    monkeypatch.setattr(sentinel_hyprland, "H", hypr)
    monkeypatch.setattr(sentinel_hyprland, "RULES", PACK / "hyprland" / "bench.lua")
    monkeypatch.setattr(sentinel_hyprland.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sentinel_hyprland.subprocess, "Popen", Sentinel)
    monkeypatch.setattr(sentinel_hyprland, "Guard", lambda *args: None)

    with pytest.raises(SystemExit):
        sentinel_hyprland.main(sys.modules["app"].BenchSentinel.Settings(condition=condition))

    folder = tmp_path / ".bench-sentinel"
    assert started["argv"] == ["/usr/bin/python3", str(sentinel_hyprland.LAB / "hyprland" / "sentinel.py"),
                               "--log", str(folder / "sentinel.jsonl"), "--control", str(folder / "sentinel.control"),
                               "--frame", frame, *extra]
    assert started["env"]["GDK_BACKEND"] == "wayland" and started["rules"] == _trycuas_rules()
    assert (folder / "condition").read_text() == f"{condition}\n" and (folder / "sentinel.control").read_bytes() == b""


def _guard(module, tmp_path, monkeypatch, rows):
    log = tmp_path / "sentinel.jsonl"
    log.write_text("")
    killed, hypr = [], FakeHypr()
    monkeypatch.setattr(module.G, "process_rows", lambda: list(rows))
    monkeypatch.setattr(module, "H", hypr)
    monkeypatch.setattr(module, "_kill", killed.append)
    return module.Guard(module.Log(log), RUNNER), hypr, module.Log(log), killed


BASE = [(1, 0, "systemd"), (HYPRLAND, 1, "Hyprland"), (RUNNER, 1, "python"), (41, RUNNER, "python3"),
        (DRIVER, 1, "cua-driver"), (5, HYPRLAND, "alacritty")]


def test_a_terminal_started_since_arming_is_a_violation_once_and_is_ended(sentinel_hyprland, tmp_path, monkeypatch):
    rows = list(BASE)
    guard, _, log, killed = _guard(sentinel_hyprland, tmp_path, monkeypatch, rows)
    rows += [(50, HYPRLAND, "alacritty"), (51, HYPRLAND, "foot"), (52, 41, "kitty"), (53, HYPRLAND, "nautilus")]

    guard.sample()
    guard.sample()

    lines = log.read()
    assert [(line["ev"], line["detail"]) for line in lines] == [
        ("gui_only_violation", "process:Alacritty"), ("gui_only_violation", "process:foot")]
    assert all(line["armed"] and line["kind"] == "process" for line in lines)
    assert killed == [50, 51, 50, 51]


def test_a_terminal_the_drivers_own_program_starts_is_its_helper(sentinel_hyprland, tmp_path, monkeypatch):
    rows = list(BASE)
    guard, _, log, killed = _guard(sentinel_hyprland, tmp_path, monkeypatch, rows)
    rows.append((60, DRIVER, "foot"))

    guard.sample()

    assert [(line["ev"], line["evidence"]["parent"]) for line in log.read()] == [("gui_only_helper", "cua-driver")]
    assert killed == []


@pytest.mark.parametrize("front, layers, detail", [
    ({"class": "Alacritty"}, {}, "front:Alacritty"),
    ({"class": "org.omarchy.btop"}, {}, "front:Omarchy TUI"),
    ({"class": "BenchLab"}, {"DP-1": {"levels": {"2": [{"namespace": "omarchy-menu"}]}}}, "front:omarchy-menu"),
    ({"class": "BenchLab"}, {"DP-1": {"levels": {"3": [{"namespace": "omarchy-dock-apps"}]}}}, "front:omarchy-apps"),
], ids=["a terminal", "an Omarchy TUI", "Omarchy's menu", "Omarchy's Apps panel"])
def test_a_side_door_in_front_three_looks_in_a_row_is_a_violation_and_for_less_a_transient(sentinel_hyprland, tmp_path,
                                                                                         monkeypatch, front, layers,
                                                                                         detail):
    guard, hypr, log, _ = _guard(sentinel_hyprland, tmp_path, monkeypatch, BASE)
    hypr.active, hypr.layers = front, layers

    guard.sample()
    guard.sample()
    transient = log.read()
    guard.sample()

    assert [(line["ev"], line["detail"]) for line in transient] == [("gui_only_transient", detail)]
    assert [(line["ev"], line["detail"]) for line in log.read()] == [("gui_only_violation", detail)]


def test_benchlab_or_a_layer_of_another_namespace_in_front_is_no_side_door(sentinel_hyprland, tmp_path, monkeypatch):
    guard, hypr, log, _ = _guard(sentinel_hyprland, tmp_path, monkeypatch, BASE)
    hypr.active = {"class": "BenchLab"}
    hypr.layers = {"DP-1": {"levels": {"2": [{"namespace": "omarchy-bar"}], "0": [{"namespace": "omarchy-menu"}]}}}

    for _ in range(4):
        guard.sample()

    assert log.read() == []


# Arming, grading and the self-checks


@pytest.fixture
def arming(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bench_arming_hyprland", ROOT / "artifacts" / "sentinel" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path / ".bench-sentinel"
    folder.mkdir()
    for name, value in (("HYPRLAND", True), ("WINDOWS", False), ("MACOS", False), ("LOG", folder / "sentinel.jsonl"),
                        ("CONTROL", folder / "sentinel.control"), ("CONDITION", folder / "condition"),
                        ("WAIT_S", 2.0)):
        monkeypatch.setattr(module, name, value)
    (folder / "condition").write_text("background\n")
    (folder / "sentinel.jsonl").write_text(json.dumps({"t": 1, "ev": "ready", "address": OWN, "pid": 77}) + "\n")
    return module, folder


def test_arming_on_hyprland_empties_the_clipboard_and_activates_the_sentinel_until_its_window_is_on_top(arming,
                                                                                                    monkeypatch):
    module, folder = arming
    hypr, signals, ran = FakeHypr(), [], []
    hypr.active, hypr.top = {"address": "0xlab"}, "0xlab"

    def kill(pid, sig):
        signals.append((pid, sig))
        if sig == signal.SIGUSR1:
            hypr.active, hypr.top = {"address": OWN}, OWN
        if sig == signal.SIGUSR2:
            with open(folder / "sentinel.jsonl", "a") as log:
                log.write(json.dumps({"t": 2, "ev": "armed", "front": {"bid": "ai.cua.benchsentinel"}}) + "\n")

    monkeypatch.setattr(module, "_module", lambda path: hypr)
    monkeypatch.setattr(module.os, "kill", kill)
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **_: ran.append(argv))

    armed = module.run({"args": {"action": "arm", "condition": "background"}})

    assert armed["line"]["ev"] == "armed" and ran == [["wl-copy", "--clear"]]
    assert signals == [(77, signal.SIGUSR1), (77, signal.SIGUSR2)]


def test_the_grade_takes_a_hyprland_logs_armed_part_by_its_place_and_the_sentinel_in_front_by_its_sample():
    spec = importlib.util.spec_from_file_location("bench_grade_hyprland", ROOT / "artifacts" / "grader" / "grade.py")
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    lines = [{"ev": "ready", "address": OWN, "pid": 77}, {"ev": "armed", "front": {"bid": "ai.cua.benchsentinel"}},
             {"ev": "s", "front": {"bid": "BenchLab"}}, {"ev": "disarmed", "front": {"bid": "BenchLab"}}]

    assert grader._armed_window(lines) == lines[1:]
    assert grader._armed_in_front(lines[1]) and not grader._armed_in_front(lines[2])


def test_the_benchlab_check_reads_a_hyprland_sample_as_focused_by_its_front_window(monkeypatch):
    monkeypatch.syspath_prepend(str(PACK / "probes" / "_common"))
    spec = importlib.util.spec_from_file_location("bench_check_benchlab", ROOT / "artifacts" / "check_benchlab" /
                                                  "run.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)

    assert check._focused({"ev": "s", "front": {"bid": "ai.cua.benchsentinel"}})
    assert not check._focused({"ev": "s", "front": {"bid": "BenchLab"}})
    assert check._focused({"ev": "s", "key": True, "active": True}) and not check._focused(
        {"ev": "s", "key": False, "active": True})


def test_the_sentinel_check_asks_for_disturbances_trycuas_oracle_causes_and_criteria_their_a22_scores(monkeypatch,
                                                                                                    tmp_path):
    (tmp_path / "bench").symlink_to(PACK)
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ("bench_v2", "hypr", "summarize_sentinel"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    spec = importlib.util.spec_from_file_location("bench_check_sentinel_hyprland",
                                                  ROOT / "artifacts" / "check_sentinel_hyprland" / "run.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    oracle = (PACK / "hyprland" / "oracle.py").read_text()
    criteria = set(check.bench_v2.multiplayer_criteria({}))

    for kind, must in check.DISTURBANCES:
        assert f'kind in ("{kind}", "all")' in oracle or f'kind == "{kind}"' in oracle
        assert must <= criteria
    assert check.WITNESS_FRAME == _constant(SESSION, "WITNESS_FRAME")
