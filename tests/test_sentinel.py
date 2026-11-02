"""The bench's sentinel on a fake desktop, scored by trycua's own summarizer and A22 criteria from the fetched task pack:
a quiet armed window holds all eight criteria, each disturbance trips its own, and what macOS wouldn't count (a window
above on another desktop, minimized, or a dock) trips none. The GUI-only guard's violations while armed: a terminal in
front 1.5 s, a terminal's program, a new program on a pseudo-terminal. Also its app's declaration and its conditions."""
import importlib
import json
import sys
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("Xlib")
pytest.importorskip("tkinter")
pytest.importorskip("agentenv_protocol.computer")

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "envs" / "bench-sentinel"
SCORING = ROOT / "artifacts" / "taskpack" / "scoring"
OWN, OTHER, DIALOG, DOCK = 0x1600003, 0x2200007, 0x3400002, 0x1000001


@pytest.fixture
def sentinel_module():
    for name in ("app", "sentinel"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(APP))
    try:
        yield importlib.import_module("sentinel")
    finally:
        sys.path.remove(str(APP))
        for name in ("app", "sentinel"):
            sys.modules.pop(name, None)


@pytest.fixture
def scoring():
    if not (SCORING / "summarize_sentinel.py").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    sys.path.insert(0, str(SCORING))
    try:
        yield importlib.import_module("summarize_sentinel"), importlib.import_module("bench_v2")
    finally:
        sys.path.remove(str(SCORING))


class FakeDesktop:
    """A desktop of the sentinel's window, another app's, and what a test adds, as the sentinel reads it."""

    def __init__(self):
        self.apps = {OWN: ("Benchsentinel", 100), OTHER: ("Mail", 200), DIALOG: ("Confirm", 300),
                     DOCK: ("Panel", 400)}
        self.kinds = {DOCK: "_NET_WM_WINDOW_TYPE_DOCK", DIALOG: "_NET_WM_WINDOW_TYPE_DIALOG"}
        self.stack = [OTHER, OWN]
        self.desktops = {OWN: 0, OTHER: 0, DIALOG: 0, DOCK: 0xFFFFFFFF}
        self.transients, self.minimized, self.titles = {}, set(), {}
        self.active_window = self.focus_window = OWN
        self.at, self.current = [500, 400], 0

    def own(self, window):
        return window == OWN

    def main(self):
        return OWN

    def pointer(self):
        return list(self.at)

    def active(self):
        return self.active_window

    def focus(self):
        return self.focus_window

    def current_desktop(self):
        return self.current

    def window_desktop(self, window):
        return self.desktops.get(window)

    def clients(self):
        return tuple(self.stack)

    def stacking(self):
        return list(self.stack)

    def app(self, window):
        return self.apps[window]

    def kind(self, window):
        return self.kinds.get(window)

    def hidden(self, window):
        return window in self.minimized

    def transient_for(self, window):
        return self.transients.get(window)

    def title(self, window):
        return self.titles.get(window, "")


class Field:
    def __init__(self):
        self.value, self.has_focus = "", True

    def text(self):
        return self.value

    def focused(self):
        return self.has_focus

    def append(self, text):
        self.value += text


class Run:
    """A sentinel on the fake desktop with a clock of its own: armed, a few seconds of samples and typing, something
    done, a few more, disarmed."""

    def __init__(self, sentinel_module, background=True):
        self.desktop, self.field, self.lines, self.now = FakeDesktop(), Field() if background else None, [], 1.7e9
        self.processes = [(1, "supervisord", 0)]
        self.sentinel = sentinel_module.Sentinel(self.desktop, self.field, self.lines.append, lambda: self.now,
                                                 lambda: list(self.processes))

    def seconds(self, n):
        for tick in range(n * 20):
            self.now += 0.05
            self.sentinel.tick()
            if tick % 20 == 19:
                self.sentinel.type_tick()

    def trial(self, act=lambda run: None):
        self.sentinel.emit("start", pid=100, bid="ai.cua.benchsentinel")
        self.seconds(1)
        self.sentinel.toggle()
        self.seconds(2)
        act(self)
        self.seconds(2)
        self.sentinel.toggle()
        return self

    def criteria(self, scoring, tmp_path):
        summarize, v2 = scoring
        log = tmp_path / "sentinel.jsonl"
        log.write_text("".join(line + "\n" for line in self.lines))
        summary = summarize.summarize(str(log))
        assert summary["available"]
        return {key for key, held in v2.multiplayer_criteria(summary).items() if held is False}, summary


def _steal(run):
    run.desktop.active_window = run.desktop.focus_window = OTHER
    run.desktop.stack = [OWN, OTHER]
    run.sentinel.focus_changed(False)
    run.sentinel.changed("active", OTHER)


def _dialog(run):
    run.desktop.transients[DIALOG] = OWN
    run.desktop.stack.append(DIALOG)


def _pointer(run):
    run.desktop.at = [520, 400]


def _desktop(run):
    run.desktop.current = 1
    run.sentinel.changed("desktop")


@pytest.mark.parametrize("act, disturbed", [
    (lambda run: None, set()),
    (_steal, {"key_focus", "window_raised", "typing", "activation"}),
    (lambda run: run.desktop.stack.reverse(), {"window_raised"}),
    (_pointer, {"pointer"}),
    (lambda run: run.sentinel.changed("clipboard"), {"clipboard"}),
    (_desktop, {"space"}),
    (_dialog, {"dialog", "window_raised"}),
    (lambda run: run.sentinel.key("q", 24, synthetic=True), {"typing"}),
    (lambda run: run.sentinel.button(1, True, [5, 5], synthetic=False), {"typing"}),
    (lambda run: run.sentinel.button(5, True, [5, 5], synthetic=False), {"typing"}),
    (lambda run: setattr(run.field, "value", run.field.value + "x"), {"typing"}),
], ids=["quiet", "focus stolen", "raised", "pointer", "clipboard", "desktop", "dialog", "key", "click", "scroll",
        "text changed"])
def test_each_disturbance_trips_its_own_criteria_as_trycua_scores_them(sentinel_module, scoring, tmp_path, act,
                                                                        disturbed):
    found, summary = Run(sentinel_module).trial(act).criteria(scoring, tmp_path)

    assert found == disturbed
    assert summary["user_activity"]["typed"] >= 2 and summary["front_changed_to"] == (["Mail"] if act is _steal else [])


@pytest.mark.parametrize("above", [
    lambda run: (run.desktop.minimized.add(OTHER), run.desktop.stack.reverse()),
    lambda run: (run.desktop.desktops.update({OTHER: 1}), run.desktop.stack.reverse()),
    lambda run: run.desktop.stack.append(DOCK),
], ids=["minimized", "on another desktop", "a dock"])
def test_what_macos_shows_no_window_for_is_not_raised_over_the_user(sentinel_module, scoring, tmp_path, above):
    found, _ = Run(sentinel_module).trial(above).criteria(scoring, tmp_path)

    assert found == set()


def test_the_witness_neither_types_nor_measures_typing(sentinel_module, scoring, tmp_path):
    run = Run(sentinel_module, background=False).trial()
    summarize, v2 = scoring
    log = tmp_path / "sentinel.jsonl"
    log.write_text("".join(line + "\n" for line in run.lines))

    criteria = v2.multiplayer_criteria(summarize.summarize(str(log)))

    assert criteria.pop("typing") is None and all(criteria.values())
    assert not any(json.loads(line)["ev"].startswith("user_") for line in run.lines)


def test_a_log_line_is_trycuas(sentinel_module):
    run = Run(sentinel_module).trial(_steal)
    lines = [json.loads(line) for line in run.lines]
    sample = next(line for line in lines if line["ev"] == "s" and line["armed"])

    assert {"ev", "t", "armed", "mouse", "front", "active", "key", "clip", "onspace", "sheet", "above_n"} <= set(sample)
    assert sample["front"] == {"bid": "ai.cua.benchsentinel", "pid": sample["front"]["pid"]}
    assert [line["ev"] for line in lines if line["ev"] in ("armed", "user_text", "disarmed")] == [
        "armed", "user_text", "disarmed"]
    assert {"didResignKey", "didResignActive", "front", "user_blocked", "user_type"} <= {line["ev"] for line in lines}


def test_a_desktop_notice_without_a_new_desktop_is_no_switch(sentinel_module):
    run = Run(sentinel_module)
    run.sentinel.changed("desktop")
    run.desktop.current = 1
    run.sentinel.changed("desktop")

    assert [json.loads(line)["onspace"] for line in run.lines if json.loads(line)["ev"] == "space"] == [False]


def _guarded(run):
    return [(line["ev"], line["detail"]) for line in map(json.loads, run.lines) if line["ev"].startswith("gui_only")]


def _terminal_in_front(seconds):
    def act(run):
        run.desktop.apps[OTHER] = ("Xfce4-terminal", 200)
        run.desktop.active_window = OTHER
        run.seconds(seconds)
        run.desktop.active_window = OWN
    return act


def test_a_terminal_in_front_three_guard_samples_in_a_row_is_a_violation(sentinel_module):
    assert _guarded(Run(sentinel_module).trial(_terminal_in_front(2))) == [
        ("gui_only_transient", "front:xfce4-terminal"), ("gui_only_violation", "front:xfce4-terminal")]


def test_libreoffices_macro_editor_in_front_is_a_violation(sentinel_module):
    def editor(run):
        run.desktop.titles[OTHER] = "My Macros & Dialogs.Standard — LibreOffice Basic"
        run.desktop.active_window = OTHER
        run.seconds(2)

    assert _guarded(Run(sentinel_module).trial(editor))[-1] == ("gui_only_violation", "front:libreoffice-macros")


def test_a_terminal_in_front_for_less_is_only_transient(sentinel_module):
    assert _guarded(Run(sentinel_module).trial(_terminal_in_front(1))) == [
        ("gui_only_transient", "front:xfce4-terminal")]


def test_a_terminals_program_or_a_new_program_on_a_terminal_is_a_violation_once(sentinel_module):
    run = Run(sentinel_module)
    run.processes.append((40, "bash", 34816))

    run.trial(lambda run: run.processes.extend([(50, "xterm", 0), (51, "python3", 34817)]))

    assert _guarded(run) == [("gui_only_violation", "process:xterm"), ("gui_only_violation", "terminal:session")]
    violation = next(json.loads(line) for line in run.lines if "terminal:session" in line)
    assert violation["evidence"]["pid"] == 51 and violation["armed"]


def test_the_guard_watches_only_while_armed(sentinel_module):
    run = Run(sentinel_module)
    run.processes.append((50, "xterm", 0))
    run.seconds(2)

    assert _guarded(run) == []


def test_the_app_launches_the_sentinel_at_boot_and_keeps_its_log_as_data(sentinel_module):
    app = sys.modules["app"]
    declared = app.BenchSentinel.declaration().os["linux"]

    assert declared.launch.command == ["venv/bin/python", "sentinel.py"]
    assert declared.launch.window == {"class": sentinel_module.WM_CLASS} and declared.launch.ready.window
    assert declared.paths == [".bench-sentinel"] and sentinel_module.LOG.parent.name == ".bench-sentinel"
    assert {"python3-tk", "wmctrl", "xclip"} <= set(declared.install["packages"]["apt"])
    assert app.BenchSentinel.Settings().condition == "foreground"
    assert app.BenchSentinel.Settings(condition="background").condition == "background"
    with pytest.raises(ValueError):
        app.BenchSentinel.Settings(condition="sideways")


def test_each_task_computer_has_the_sentinel():
    for task, app in (("s02", "cdb-s02"), ("s03", "cdb-s03"), ("s04", "cdb-s04"), ("benchlab", "benchlab")):
        env = tomllib.loads((ROOT / "envs" / f"desktop-{task}" / "env.toml").read_text())
        assert env["apps"] == [app, "bench-sentinel"]
