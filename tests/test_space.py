"""The replay Space's catalog and figures per driver, offline: a trial's driver, cua-driver when its trial.json names
none; a missing trial's from its task file; the board, the replay keys and the trial order per driver; each OS and
model that several drivers ran compared over the tasks all of them ran in both conditions; the card's tables with
their drivers; the results figures of cua-driver's rows alone, and a drivers figure's panel per comparison; the
other drivers' calls as the replay's lane says them; and a gallery clip's moment, span and callouts."""
import importlib
import json
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPACE = ROOT / "tools" / "space"
SONNET, HAIKU = "anthropic/claude-sonnet-5-5", "anthropic/claude-haiku-5-5"
CONFIG = {"models": {HAIKU: {"name": "Claude Haiku 5.5"}, SONNET: {"name": "Claude Sonnet 5.5"}},
          "drivers": {"cua-driver": {"name": "cua-driver", "detail": "trycua's cua-driver 0.38.0, its tools", "slot": 2},
                      "agent-desktop": {"name": "agent-desktop", "detail": "Vercel's agent-desktop 1.2.0, its tools",
                                        "slot": 6}},
          "oses": {"linux": {"name": "Linux"}, "macos": {"name": "macOS"}},
          "conditions": {"foreground": {"name": "Foreground", "short": "agent owns the desktop"},
                         "background": {"name": "Background", "short": "a user is typing"}},
          "title": "T", "links": {}, "screen": [1920, 1080], "user_frame": [0, 0, 10, 10], "user_script": "x"}


@pytest.fixture
def space(monkeypatch):
    monkeypatch.syspath_prepend(str(SPACE))
    return lambda name: importlib.import_module(f"cdbviz.{name}")


def _meta(driver, task, condition, run_index, passed, score, os="macos", model=SONNET):
    run = f"{driver}-{model.rsplit('/', 1)[-1]}-{os}"
    return {"uid": f"{os}--{run}--{task}-r{run_index}-{condition}", "id": f"{task}-r{run_index}-{condition}",
            "os": os, "driver": driver, "task": task, "probe": task.upper(), "condition": condition, "model": model,
            "model_name": CONFIG["models"][model]["name"], "run": run, "run_index": run_index,
            "started_at": f"2026-11-05T0{run_index}:00:00Z", "passed": passed, "grade": {"task": {"score": score}},
            "cost": None}


def _catalog(space, metas, cfg=CONFIG):
    return space("catalog").build(metas, cfg, None, {m["uid"]: {} for m in metas})


def _cells(driver, results, os="macos", model=SONNET):
    """A run per (task, condition, passed, score) result."""
    return [_meta(driver, task, cond, k, passed, score, os, model)
            for task, cond, outcomes in results for k, (passed, score) in enumerate(outcomes, 1)]


def test_a_trial_names_its_driver_and_one_that_names_none_ran_on_cua_driver(space, tmp_path):
    trials = space("trials")
    for run, driver in (("sonnet-5-5-2026-11-05", None), ("agent-desktop-sonnet-5-5-2026-11-05", "agent-desktop")):
        folder = tmp_path / "runs" / "macos" / run / "ir-01-r2-foreground"
        folder.mkdir(parents=True)
        facts = {"trial_id": folder.name, "task": "ir-01", "condition": "foreground", "os": "macos", "model": SONNET,
                 "run_index": 2, "started_at": "2026-11-05T01:00:00Z", **({"driver": driver} if driver else {})}
        (folder / "trial.json").write_text(json.dumps(facts))
        (folder / "timeline.json").write_text("{}")

    loaded = {t["meta"]["run"]: t["meta"] for t in (trials.load(f, CONFIG, tmp_path) for f in trials.discover(tmp_path))}

    assert {run: m["driver"] for run, m in loaded.items()} == {
        "sonnet-5-5-2026-11-05": "cua-driver", "agent-desktop-sonnet-5-5-2026-11-05": "agent-desktop"}
    assert len({m["uid"] for m in loaded.values()}) == 2


def test_a_missing_trial_takes_its_driver_and_task_from_its_task_file(space, tmp_path):
    for run, stem in (("agent-desktop-haiku-5-5-2026-11-05", "macos-agent-desktop-ir-04-r5-background"),
                      ("haiku-5-5-2026-11-05", "macos-ir-04-r5-background"), ("haiku-5-5-2026-11-02", "cdb-g02-foreground")):
        folder = tmp_path / "runs" / ("linux" if stem.startswith("cdb") else "macos") / run / "lost"
        folder.mkdir(parents=True)
        (folder / "missing.json").write_text(json.dumps({"name": "lost", "task_file": stem, "os": folder.parts[-3]}))

    found = {(x["run"], x["driver"], x["task"], x["condition"]) for x in space("trials").discover_missing(tmp_path)}

    assert found == {("agent-desktop-haiku-5-5-2026-11-05", "agent-desktop", "ir-04", "background"),
                     ("haiku-5-5-2026-11-05", "cua-driver", "ir-04", "background"),
                     ("haiku-5-5-2026-11-02", "cua-driver", "cdb-g02", "foreground")}


def test_the_board_the_replay_keys_and_the_trial_order_are_per_driver(space):
    metas = [_meta(driver, "ir-01", "background", k, k == 1, 1.0) for driver in ("agent-desktop", "cua-driver")
             for k in (1, 2)]
    cat = _catalog(space, metas)

    rows = {(r["driver"], r["condition"]): (r["passed"], r["n_trials"]) for r in cat["board"]}
    assert rows == {("cua-driver", "background"): (1, 2), ("agent-desktop", "background"): (1, 2)}
    assert [(t["driver"], t["key"], t["of"]) for t in cat["trials"]] == [
        ("cua-driver", "r1", 2), ("cua-driver", "r2", 2), ("agent-desktop", "r1", 2), ("agent-desktop", "r2", 2)]
    assert cat["driver"] == "cua-driver"


def test_the_catalog_lists_its_drivers_in_config_order_and_a_driver_config_lacks_takes_a_colour_of_its_own(space):
    metas = [_meta(driver, "ir-01", "foreground", 1, True, 1.0) for driver in ("new-arm", "agent-desktop", "cua-driver")]

    drivers = _catalog(space, metas)["drivers"]

    assert [(d["id"], d["slot"]) for d in drivers] == [("cua-driver", 2), ("agent-desktop", 6), ("new-arm", 0)]
    assert drivers[0]["detail"] == CONFIG["drivers"]["cua-driver"]["detail"]


def test_a_comparison_holds_the_os_and_model_and_counts_only_the_tasks_every_driver_ran_in_both_conditions(space):
    both = lambda task, fg, bg: [(task, "foreground", fg), (task, "background", bg)]
    metas = (_cells("cua-driver", both("ir-01", [(True, 1.0)] * 2, [(False, 0.5)] * 2)
                    + both("mb-09", [(True, 1.0)] * 2, [(True, 1.0), (False, 0.2)]))
             + _cells("agent-desktop", both("ir-01", [(True, 1.0)] * 2, [(True, 1.0)] * 2)
                      + [("mb-09", "foreground", [(True, 1.0)] * 2)])
             + _cells("cua-driver", both("ir-01", [(True, 1.0)], [(True, 1.0)]), model=HAIKU)
             + _cells("cua-driver", both("ir-01", [(True, 1.0)], [(True, 1.0)]), os="linux")
             + _cells("agent-desktop", both("ir-01", [(True, 1.0)], [(True, 1.0)]), os="linux"))

    comparisons = _catalog(space, metas)["comparisons"]

    assert [(c["os"], c["model"], c["tasks"], c["of"]) for c in comparisons] == [
        ("linux", SONNET, ["ir-01"], 1), ("macos", SONNET, ["ir-01"], 2)]
    macos = {d["id"]: d for d in comparisons[1]["drivers"]}
    assert list(macos) == ["cua-driver", "agent-desktop"]
    assert (macos["cua-driver"]["background"]["passed"], macos["cua-driver"]["background"]["n"]) == (0, 2)
    assert macos["agent-desktop"]["background"]["pass"] == 1.0 and macos["cua-driver"]["background"]["score"] == 0.5


def test_a_task_the_config_runs_in_the_foreground_alone_counts_there_and_is_said_to(space):
    catalog = space("catalog")
    cfg = {**CONFIG, "tasks": {"mb-10": {"probe": "MB-10", "conditions": ["foreground"]}}}
    metas = [m for driver in ("cua-driver", "agent-desktop") for m in _cells(driver, [
        ("ir-01", "foreground", [(True, 1.0)]), ("ir-01", "background", [(False, 0.5)]),
        ("mb-10", "foreground", [(True, 1.0)])])]
    cat = _catalog(space, metas, cfg)

    rows = {(r["driver"], r["condition"]): (r["passed"], r["n_trials"], set(r["tasks"])) for r in cat["board"]}
    [comparison] = cat["comparisons"]
    cua = comparison["drivers"][0]

    assert rows[("cua-driver", "foreground")] == (2, 2, {"ir-01", "mb-10"})
    assert rows[("cua-driver", "background")] == (0, 1, {"ir-01"})
    assert set(comparison["tasks"]) == {"ir-01", "mb-10"}
    assert (cua["foreground"]["n"], cua["background"]["n"], cua["background"]["score"]) == (2, 1, 0.5)
    assert "MB-10 runs in the foreground only." in catalog.results_md(cat)
    assert "(MB-10 runs in the foreground only)" in catalog.drivers_md(cat)
    assert {t["id"]: t["conditions"] for t in cat["tasks"]} == {"ir-01": ["foreground", "background"],
                                                                "mb-10": ["foreground"]}
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    [panel] = space("figures").driver_specs(cat)["drivers-full-pass"]["panels"]
    assert [s["values"] for s in panel["series"]] == [[1.0, 0.0], [1.0, 0.0]]


def test_a_driver_that_runs_in_the_foreground_alone_is_compared_there_and_not_run_in_the_background(space):
    catalog = space("catalog")
    codex = {"name": "Codex Computer Use", "detail": "OpenAI's Codex Computer Use", "slot": 4}
    cfg = {**CONFIG, "drivers": {**CONFIG["drivers"], "codex-computer-use": codex}}
    metas = (_cells("cua-driver", [("ir-01", "foreground", [(True, 1.0)] * 2), ("ir-01", "background", [(False, 0.5)] * 2)])
             + _cells("agent-desktop", [("ir-01", "foreground", [(False, 0.5)] * 2),
                                        ("ir-01", "background", [(True, 1.0)] * 2)])
             + _cells("codex-computer-use", [("ir-01", "foreground", [(True, 1.0), (False, 0.25)])]))
    metas = [{**m, "cost": 0.1} for m in metas]
    cat = _catalog(space, metas, cfg)

    [comparison] = cat["comparisons"]
    drivers = {d["id"]: d for d in comparison["drivers"]}
    table = catalog.drivers_md(cat)

    assert list(drivers) == ["cua-driver", "agent-desktop", "codex-computer-use"]
    assert "background" not in drivers["codex-computer-use"]
    assert (drivers["codex-computer-use"]["foreground"]["passed"], drivers["codex-computer-use"]["foreground"]["n"]) == (1, 2)
    assert "| macOS | Claude Sonnet 5.5 | Codex Computer Use | 50% (1/2) | 63% | not run | not run | 2 |" in table
    assert "| macOS | Claude Sonnet 5.5 | agent-desktop | 0% (0/2) | 50% | **100% (2/2)** | **100%** | 4 |" in table
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    figures = space("figures")
    [panel] = figures.driver_specs(cat)["drivers-full-pass"]["panels"]
    assert [s["values"] for s in panel["series"]] == [[1.0, 0.0], [0.0, 1.0], [0.5, None]]
    panels = {p["cond"]: [q["name"] for q in p["points"]] for p in figures.pareto_spec(cat)["panels"] if p["kind"] == "drivers"}
    assert panels == {"foreground": ["cua-driver", "agent-desktop", "Codex Computer Use"],
                      "background": ["cua-driver", "agent-desktop"]}


def test_the_card_tables_name_each_rows_driver_and_bold_a_models_best_driver(space):
    catalog = space("catalog")
    metas = (_cells("cua-driver", [("ir-01", "foreground", [(True, 1.0)] * 2), ("ir-01", "background", [(False, 0.5)] * 2)])
             + _cells("agent-desktop", [("ir-01", "foreground", [(True, 1.0)] * 2),
                                        ("ir-01", "background", [(True, 1.0), (False, 0.5)])]))
    cat = _catalog(space, metas)

    results = catalog.results_md(cat)
    drivers = catalog.drivers_md(cat)

    assert results.splitlines()[0].startswith("| OS | Model | Driver | Condition |")
    assert [line.split(" | ")[2] for line in results.splitlines()[2:6]] == ["cua-driver"] * 2 + ["agent-desktop"] * 2
    assert "| macOS | Claude Sonnet 5.5 | cua-driver | 100% (2/2) | 100% | 0% (0/2) | 50% | 4 |" in drivers
    assert "| macOS | Claude Sonnet 5.5 | agent-desktop | 100% (2/2) | 100% | **50% (1/2)** | **75%** | 4 |" in drivers
    assert "Claude Sonnet 5.5 on macOS, IR-01." in drivers and "- **agent-desktop**: Vercel's agent-desktop" in drivers
    assert catalog.drivers_md(_catalog(space, metas[:4])) == ""


def test_the_results_figures_are_of_cua_drivers_rows_and_a_drivers_figure_has_a_panel_per_comparison(space):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    figures = space("figures")
    metas = (_cells("cua-driver", [("ir-01", "foreground", [(True, 1.0)]), ("ir-01", "background", [(False, 0.4)])])
             + _cells("agent-desktop", [("ir-01", "foreground", [(False, 0.6)]), ("ir-01", "background", [(True, 1.0)])])
             + _cells("cua-driver", [("ir-01", "foreground", [(True, 1.0)]), ("ir-01", "background", [(True, 1.0)])],
                      model=HAIKU))
    labelled = {**CONFIG["drivers"]["agent-desktop"], "name": "Vercel Labs (agent-desktop)", "label": "agent-desktop"}
    cat = _catalog(space, metas, {**CONFIG, "drivers": {**CONFIG["drivers"], "agent-desktop": labelled}})

    results = figures.specs(cat)
    drivers = figures.driver_specs(cat)

    [panel] = results["task-score"]["panels"]
    assert {s["name"]: s["values"] for s in panel["series"]} == {"Claude Haiku 5.5": [1.0, 1.0],
                                                                 "Claude Sonnet 5.5": [1.0, 0.4]}
    assert "all through cua-driver" in results["full-pass"]["subtitle"]
    [panel] = drivers["drivers-full-pass"]["panels"]
    assert panel["label"] == "Claude Sonnet 5.5 on macOS" and panel["note"] == "1 task · IR-01"
    assert [(s["name"], s["slot"], s["values"]) for s in panel["series"]] == [
        ("cua-driver", 2, [1.0, 0.0]), ("agent-desktop", 6, [0.0, 1.0])]
    svg = figures.figure(drivers["drivers-full-pass"], "dark", True)
    assert "agent-desktop" in svg and figures.SERIES["dark"][6] in svg
    assert "Vercel Labs (agent-desktop)" in space("catalog").drivers_md(cat)


def test_a_span_of_tasks_names_each_task_and_three_or_more_in_a_row_as_a_range(space):
    ranges = space("catalog").ranges

    assert ranges(["G02", "G03", "G04", "MB-09", "MB-10", "IR-01"]) == "G02–G04, MB-09, MB-10, IR-01"


def test_another_drivers_calls_read_in_the_lane_as_steps_on_elements_points_and_text(space):
    trials = space("trials")

    def said(tool, inp):
        d = trials.describe({"tool": tool, "input": inp}, "", trials.Desk({"screen": [1920, 1080]}))
        return d["verb"], d["obj"], d["where"]

    assert said("desktop_click", {"ref_id": "@s1q3:e14"}) == ("Click", "element e14", None)
    assert said("desktop_snapshot", {"app": "BenchLab", "include_bounds": True}) == ("Read window", "", "BenchLab")
    assert said("desktop_drag", {"from": "@s1q3:e5", "to_xy": "250,192"}) == ("Drag", "from element e5 to (250, 192)",
                                                                             None)
    assert said("desktop_batch", {"commands_json": '[{"command": "hover", "args": {"xy": "160,180"}}]'}) == (
        "Hover", "at (160, 180)", None)
    assert said("macos_harness", {"commands": [["click", "--app", "BenchLab", "--element_index", "1"],
                                               ["get_app_state", "--app", "BenchLab"]]}) == (
        "Run 2 steps", "click element 1 → read window", "BenchLab")
    assert said("macos_harness", {"commands": [["drag", "--help"]]})[:2] == ("Read help", "drag")
    assert said("js", {"code": 'let app = await cua.getApp("BenchLab"); await app.setValue(2, "Jonas"); '
                               "await app.click(5);"}) == (
        "Run 3 steps", "read window → set value “Jonas” → +1 more", "BenchLab")
    assert said("js", {"code": "await app.drag([80,161],[80,114]); await app.pressKey('Tab')"}) == (
        "Run 2 steps", "drag from (80, 161) to (80, 114) → press Tab", None)
    assert said("js", {"code": "nodeRepl.write(1)"}) == ("Run JavaScript", "", None)
    assert said("repl", {"code": 'const app = await computer.getApp("BenchLab"); await app.setValue(2, "Jonas");'}) == (
        "Run 2 steps", "read window → set value “Jonas”", "BenchLab")
    assert said("repl", {"code": "console.log(1)"}) == ("Run JavaScript", "", None)
    assert [trials.kind_of("js", {"code": code}) for code in (
        "await app.getAXState({disableDiffing: true})", "await app.click([102, 78])")] == ["look", "act"]
    assert [trials.kind_of("repl", {"code": code}) for code in (
        "await app.getAXState()", "await app.click(5)")] == ["look", "act"]
    assert [trials.kind_of(tool, inp) for tool, inp in (
        ("desktop_screenshot", {}), ("macos_harness", {"commands": [["get_app_state", "--app", "BenchLab"]]}),
        ("desktop_wait", {"ms": 800}), ("desktop_drag", {}), ("click", {}))] == ["look", "look", "wait", "act", "act"]


def test_why_two_drivers_differ_keeps_each_points_examples_to_the_trials_the_catalog_holds(space):
    metas = _cells("cua-driver", [("ir-01", "background", [(True, 1.0)])]) + _cells(
        "agent-desktop", [("ir-01", "background", [(False, 0.5)])])
    held, gone = metas[0]["uid"], "macos--cua-driver-sonnet-5-5-macos--ir-01-r9-background"
    why = {"os": "macos", "drivers": ["cua-driver", "agent-desktop"], "title": "Why", "lead": "",
           "points": [{"head": "A.", "text": "a", "examples": [held, gone]}, {"head": "B.", "text": "b"}]}

    cat = _catalog(space, metas, {**CONFIG, "driver_why": [why]})

    assert [p["examples"] for p in cat["driver_why"][0]["points"]] == [[held], []]
    assert _catalog(space, metas)["driver_why"] == []


def test_the_configs_account_of_two_drivers_names_drivers_and_an_os_it_has_and_says_each_point_with_examples():
    cfg = json.loads((SPACE / "config.json").read_text())
    for why in cfg["driver_why"]:
        assert why["os"] in cfg["oses"] and set(why["drivers"]) <= set(cfg["drivers"]) and why["title"] and why["lead"]
        assert all(p["head"] and p["text"] and p["examples"] for p in why["points"])
        assert all(u.split("--")[0] == why["os"] and u.count("--") == 2 for p in why["points"] for u in p["examples"])


def test_a_run_the_config_excludes_is_named_as_its_os_and_run(space):
    assert space("trials").run_of(Path("/d/runs/macos/cua-driver-sonnet-5-5-2026-11-05/ir-01-r1-foreground"), Path("/d")) == (
        "macos/cua-driver-sonnet-5-5-2026-11-05")
    cfg = json.loads((SPACE / "config.json").read_text())
    assert all(run.count("/") == 1 and run.split("/")[0] in cfg["oses"] for run in cfg["exclude_runs"])


def test_a_pairs_panels_show_one_region_of_the_screen_holding_every_window_at_its_aspect(space):
    pair = space("pair")

    class Fake:
        def __init__(self, condition, wins, frame=None):
            self.scene = type("S", (), {"sw": 1920, "sh": 1080, "calls": [{"win": w, "kind": "act"} for w in wins],
                                        "user": {"frame": frame} if frame else None})()
            self.m, self.cfg = {"condition": condition}, {"user_frame": [420, 340, 900, 520]}
            self.boxes = lambda: pair.Panel.boxes(self)

    x, y, w, h = pair.view(Fake("foreground", [[65, 81, 760, 568]]), Fake("background", [[65, 81, 760, 568]], [420, 340, 900, 520]))

    assert abs(w / h - 16 / 9) < 1e-6 and x <= 65 - 56 + 1 and y <= 81 and x + w >= 1320 and y + h >= 860
    assert x >= 0 and y >= 0 and x + w <= 1920 and y + h <= 1080
    assert pair.view(Fake("foreground", [])) == (0, 0, 1920, 1080)


def _trial(task, condition, k, *, passed=False, score=0.0, gui=True, user=True, ending="Replied DONE", errors=(),
           criteria=None, model=SONNET, driver="cua-driver", os="linux", first_disturbance=None):
    """A loaded trial as build.py holds it, its meta and its web timeline, graded as told."""
    meta = _meta(driver, task, condition, k, passed, score, os, model)
    broken = criteria or ([] if user else ["key_focus"])
    meta["grade"] = {"task": {"result": score == 1.0, "score": score},
                     "gui_only": {"result": gui, "violations": [] if gui else ["mcp__desktop-s04__launch_app:arguments"]},
                     "user_undisturbed": {"result": user, "criteria": {c: c not in broken for c in ("key_focus",
                                                                                                    "window_raised")}}
                     if condition == "background" else None}
    meta.update(ending=ending, duration=100.0)
    calls = [{"t0": 10.0 + i, "tool": "launch_app" if not gui else "click", "err": e} for i, e in enumerate(errors)]
    events = [{"t": first_disturbance, "c": "key_focus"}] if first_disturbance is not None else []
    return {"meta": meta, "web": {"calls": calls, "armed": [2.0, 90.0], "duration": 100.0,
                                  "user": {"events": events} if condition == "background" else None}}


REFUSAL = "Background delivery is not available: the requested target has no focus-free input backend"
LINUX_DIALOG = {**CONFIG, "caveats": [{"os": "linux", "condition": "background", "tasks": ["ir-01"], "mark": "‡",
                                        "short": "Not passable on Linux", "passable": False}]}


WINDOWS_DIALOG = {**CONFIG, "caveats": [{"os": "windows", "condition": "background", "tasks": ["ir-01"], "mark": "†",
                                          "short": "A dialog takes the keyboard on Windows", "dialog": True}]}


def test_a_dialog_caveat_counts_the_disturbance_as_the_dialogs_without_calling_the_task_unpassable(space):
    failures, figures = space("failures"), space("figures")
    loaded = [_trial("ir-01", "background", 1, score=1.0, user=False, os="windows"),
              _trial("ir-02", "background", 1, score=1.0, user=False, os="windows")]
    cat = _catalog(space, [t["meta"] for t in loaded], WINDOWS_DIALOG)

    got = failures.build(loaded, cat)

    assert [got["by_trial"][t["meta"]["uid"]] for t in loaded] == ["dialog", "disturbed"]
    assert figures.unpassable(cat) == ""


def test_a_failed_trial_counts_under_the_gravest_way_it_failed(space):
    failures = space("failures")
    loaded = [
        _trial("ir-02", "background", 1, passed=True, score=1.0),
        _trial("cdb-g04", "background", 1, gui=False, user=False, ending="Replied BLOCKED: no log", errors=[REFUSAL]),
        _trial("ir-01", "background", 1, score=1.0, user=False),
        _trial("ir-02", "background", 2, score=1.0, user=False, ending="Hit the 45-turn limit"),
        _trial("mb-09", "background", 1, ending="Replied BLOCKED: no drag", errors=[REFUSAL]),
        _trial("mb-09", "background", 2, ending="Replied BLOCKED: no screenshot"),
        _trial("mb-09", "foreground", 1, ending="Replied BLOCKED: no screenshot", errors=[REFUSAL]),
        _trial("cdb-g02", "foreground", 1, score=0.6, ending="Hit the 45-turn limit"),
        _trial("cdb-g03", "foreground", 1, score=0.4, ending="Ran out of time"),
        _trial("ir-04", "foreground", 1, score=0.5),
    ]
    cat = _catalog(space, [t["meta"] for t in loaded], LINUX_DIALOG)

    got = failures.build(loaded, cat)

    assert [got["by_trial"][t["meta"]["uid"]] for t in loaded] == [
        "pass", "left_gui", "dialog", "disturbed", "no_background", "blocked", "blocked", "out_of_turns",
        "out_of_turns", "wrong"]
    assert [m["id"] for m in got["modes"]] == ["pass", "wrong", "out_of_turns", "blocked", "no_background", "dialog",
                                               "disturbed", "left_gui"]


def test_a_modes_examples_are_sonnets_first_then_those_that_show_it_soonest_across_setups(space):
    failures = space("failures")
    loaded = [_trial("ir-01", "background", 1, score=1.0, user=False, first_disturbance=60.0, os="macos"),
              _trial("ir-02", "background", 1, score=1.0, user=False, first_disturbance=5.0, os="macos", model=HAIKU),
              _trial("ir-02", "background", 2, score=1.0, user=False, first_disturbance=30.0, os="macos"),
              _trial("ir-02", "background", 3, score=1.0, user=False, first_disturbance=8.0, os="macos",
                     driver="agent-desktop"),
              _trial("ir-01", "background", 2, score=1.0, user=False, first_disturbance=4.0, os="macos")]
    cat = _catalog(space, [t["meta"] for t in loaded])

    [first, second, third] = failures.build(loaded, cat)["examples"]["disturbed"]

    uid = lambda t: t["meta"]["uid"]
    assert (first, second, third) == (uid(loaded[4]), uid(loaded[3]), uid(loaded[2]))
    assert failures.shown_at(loaded[4], "disturbed") == 2.0


def test_the_failure_figures_stack_each_setups_outcomes_and_grid_the_criteria_its_background_broke(space):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    failures, figures = space("failures"), space("figures")
    loaded = [_trial("ir-02", "foreground", 1, passed=True, score=1.0, os="macos"),
              _trial("ir-02", "background", 1, passed=True, score=1.0, os="macos"),
              _trial("ir-01", "background", 1, score=1.0, user=False, criteria=["key_focus", "window_raised"],
                     os="macos"),
              _trial("ir-01", "background", 2, score=1.0, user=False, os="macos", driver="agent-desktop"),
              _trial("ir-02", "foreground", 1, score=0.5, os="macos", driver="agent-desktop",
                     ending="Hit the 45-turn limit")]
    cat = _catalog(space, [t["meta"] for t in loaded],
                   {**CONFIG, "criteria": {"key_focus": ["Focus", "keeps keyboard focus", "lost keyboard focus"],
                                           "window_raised": ["On top", "stays on top", "a window was raised"]}})
    cat["failures"] = failures.build(loaded, cat)

    specs = figures.failure_specs(cat)
    bars, grid = specs["failure-modes"], specs["disturbances"]

    assert [m["id"] for m in bars["modes"]] == ["pass", "out_of_turns", "disturbed"]
    assert [(g["label"], [r["label"] for r in g["rows"]]) for g in bars["panels"]] == [
        ("macOS · cua-driver", ["Claude Sonnet 5.5"]), ("macOS · agent-desktop", ["Claude Sonnet 5.5"])]
    assert bars["panels"][0]["rows"][0]["bars"]["background"] == [("pass", 1), ("out_of_turns", 0), ("disturbed", 1)]
    assert [c["id"] for c in grid["columns"]] == ["any", "key_focus", "window_raised"]
    assert [r["cells"] for g in grid["panels"] for r in g["rows"]] == [[0.5, 0.5, 0.5], [1.0, 1.0, 0.0]]
    assert figures.write_all(cat, [])["failure_figures"] == ["failure-modes", "disturbances"]
    svg = figures.bars(bars, "dark", True)
    assert "Disturbed the user" in svg and figures.tone("dark", 3, 1) in svg
    assert "| macOS | cua-driver | Claude Sonnet 5.5 | 1 · 1 | 0 · 0 | 0 · 1 | 1 · 2 |" in failures.markdown(cat)


def test_the_grid_counts_each_tasks_passing_runs_per_model_off_where_the_bench_doesnt_run_it_none_before_it_ran(space):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    cfg = {**CONFIG, "tasks": {"mb-10": {"probe": "MB-10", "conditions": ["foreground"]}},
           "caveats": [{"os": "linux", "condition": "background", "tasks": ["ir-01"], "mark": "‡",
                        "short": "Not passable on Linux"}]}
    metas = [{**m, "harness": "claude-code"} for m in _cells("cua-driver", [
        ("ir-01", "foreground", [(True, 1.0)] * 2), ("ir-01", "background", [(False, 1.0)] * 2),
        ("ir-02", "foreground", [(True, 1.0), (False, 0.5)]), ("ir-02", "background", [(True, 1.0)] * 2),
        ("mb-10", "foreground", [(True, 1.0)] * 2)], os="linux")] + [{**m, "harness": "claude-code"} for m in _cells(
        "cua-driver", [("ir-01", "foreground", [(True, 1.0)]), ("ir-01", "background", [(False, 1.0)]),
                       ("ir-02", "background", [(True, 1.0)])], os="linux", model=HAIKU)]

    spec = space("figures").tasks_spec(_catalog(space, metas, cfg))

    fg, bg = spec["panels"]
    assert [c["id"] for c in spec["cols"]] == [HAIKU, SONNET] and spec["full"] == 2
    assert (fg["cells"][("ir-02", SONNET)]["passed"], fg["cells"][("ir-02", SONNET)]["n"]) == (1, 2)
    assert bg["cells"][("mb-10", SONNET)] == "off" and fg["cells"][("ir-02", HAIKU)] is None
    assert list(bg["marks"]) == ["ir-01"] and not fg["marks"]
    assert spec["notes"][:2] == [
        "With the user typing on Linux, every model passes IR-02 and no other task: all 3 of its trials, against none "
        "of the other 3.", "The marked rows can't pass there: IR-01 (‡ not passable on Linux)."]


def test_a_models_column_is_headed_by_its_family_and_its_variant(space):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    heads = space("figures").heads

    assert heads(["Claude Haiku 5.5", "Claude Opus 5.5", "GPT-6 Luna", "GPT-6.1 Terra", "GPT-6.1 Sol"]) == [
        ("Claude 5.5", "Haiku"), ("Claude 5.5", "Opus"), ("GPT-6", "Luna"), ("GPT-6.1", "Terra"), ("GPT-6.1", "Sol")]


def test_the_frontier_holds_the_points_no_cheaper_one_matches_and_a_point_counts_the_trials_every_point_ran(space):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    figures = space("figures")
    points = [{"name": name, "cost": cost, "share": share} for name, cost, share in (
        ("luna", 0.02, 0.34), ("haiku", 0.07, 0.43), ("terra", 0.10, 0.39), ("sol", 0.18, 0.43), ("sonnet", 0.56, 0.52),
        ("opus", 0.82, 0.48))]
    metas = ([{**m, "cost": 0.5} for m in _cells("cua-driver", [
        ("ir-01", "foreground", [(True, 1.0), (False, 0.0)]), ("ir-02", "foreground", [(True, 1.0)] * 2)], os="linux")]
             + [{**m, "cost": 0.1} for m in _cells("cua-driver", [("ir-01", "foreground", [(True, 1.0)] * 2)],
                                                    os="linux", model=HAIKU)])

    tallied = figures.tally(_catalog(space, metas), "linux", [("cua-driver", SONNET, "S", 1), ("cua-driver", HAIKU, "H", 0)])

    assert [p["name"] for p in figures.frontier(points)] == ["luna", "haiku", "sonnet"]
    assert [(p["name"], p["n"], p["passed"], p["cost"]) for p in tallied] == [("S", 2, 1, 0.5), ("H", 2, 2, 0.1)]


def test_an_os_gap_holds_the_model_and_the_bench_driver_over_the_tasks_every_os_ran_in_both_conditions(space):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    both = lambda task, fg, bg: [(task, "foreground", fg), (task, "background", bg)]
    metas = (_cells("cua-driver", both("ir-01", [(True, 1.0)] * 2, [(False, 0.5)] * 2)
                    + both("mb-09", [(True, 1.0)] * 2, [(False, 0.5)] * 2), os="linux")
             + _cells("cua-driver", both("ir-01", [(True, 1.0)] * 2, [(True, 1.0)] * 2), os="macos")
             + _cells("agent-desktop", both("ir-01", [(False, 0.0)], [(False, 0.0)]), os="linux"))

    [gap] = space("figures").os_gaps(_catalog(space, metas))

    assert (gap["model"], gap["tasks"]) == (SONNET, ["ir-01"])
    assert {o["id"]: (o["foreground"]["pass"], o["background"]["pass"]) for o in gap["oses"]} == {
        "linux": (1.0, 0.0), "macos": (1.0, 1.0)}


def test_each_other_os_where_two_models_ran_gets_a_passes_grid_of_its_own(space):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    metas = [{**m, "cost": 0.1, "harness": "claude-code"} for os_ in ("linux", "macos") for model in (SONNET, HAIKU)
             for m in _cells("cua-driver", [("ir-01", "foreground", [(True, 1.0)]),
                                            ("ir-01", "background", [(True, 1.0)])], os=os_, model=model)]

    specs = space("figures").compare_specs(_catalog(space, metas))

    assert [key for key in specs if key.startswith("models-tasks")] == ["models-tasks", "models-tasks-macos"]
    assert specs["models-tasks"]["subtitle"].startswith("Linux")
    assert specs["models-tasks-macos"]["subtitle"].startswith("macOS")


def test_the_comparison_figures_are_written_with_their_notes_and_one_without_data_is_left_out(space, tmp_path):
    for package in ("fontTools", "PIL", "brotli"):
        pytest.importorskip(package)
    metas = [{**m, "cost": cost, "harness": "claude-code"} for model, cost in ((SONNET, 0.5), (HAIKU, 0.1)) for m in _cells(
        "cua-driver", [("ir-01", "foreground", [(True, 1.0)] * 2), ("ir-01", "background", [(False, 1.0), (True, 1.0)])],
        os="linux", model=model)]

    cat = _catalog(space, metas)
    cat["failures"] = {"modes": [], "by_trial": {}, "examples": {}}

    written = space("figures").write_all(cat, [tmp_path])

    assert written["compare_figures"] == ["models-tasks", "pareto"] and set(written["compare_notes"]) == {
        "models-tasks", "pareto"}
    assert all((tmp_path / f"{key}{variant}.svg").exists() for key in written["compare_figures"]
               for variant in ("", "-dark", "-phone", "-phone-dark"))
    assert "Claude Haiku 5.5 (50% at $0.10), is the whole frontier" in written["compare_notes"]["pareto"][1]


def _calls(*rows):
    keys = ("i", "t0", "tool", "verb", "obj", "kind", "err", "pt")
    return [dict(zip(keys, row)) for row in rows]


def test_a_clip_plays_its_modes_moment_or_the_whole_run_sped_up(space):
    pytest.importorskip("PIL")
    clip = space("clip")
    refused = "Background delivery is not available: the target has no focus-free input backend"
    events = [{"t": 9.0, "c": "typing"}, {"t": 12.0, "c": "window_raised"}, {"t": 11.5, "c": "key_focus"}]
    calls = _calls((0, 5.0, "click", "Click", "", "act", refused, None), (1, 8.0, "click", "Click", "", "act", refused, [3, 4]),
                   (2, 20.0, "launch_app", "Launch app", "", "act", None, None))
    sc = types.SimpleNamespace(start=2.0, end=60.0, user={"events": events}, calls=calls)
    m = {"grade": {"gui_only": {"violations": ["mcp__desktop-s04__launch_app:launch_path"]}}}

    assert [clip.moment(sc, m, mode) for mode in ("focus", "raise", "dialog", "refused", "gui", "turns")] == [
        11.5, 12.0, 11.5, 8.0, 20.0, None]
    assert clip.window(sc, m, {"mode": "focus"}) == (8.5, 16.0, 1, 11.5)
    assert clip.window(sc, m, {"mode": "focus", "at": 3.0}) == (2.0, 7.5, 1, 3.0)
    assert clip.window(sc, m, {"mode": "refused"}) == (6.0, 22.0, 2, 8.0)
    assert clip.window(sc, m, {"mode": "turns"}) == (2.0, 60.0, 10, None)


def test_a_clips_callouts_name_each_new_kind_of_disturbance_the_modes_first_and_each_failed_driver_call(space, tmp_path):
    pytest.importorskip("PIL")
    clip = space("clip")
    (tmp_path / "timeline.json").write_text(json.dumps({"calls": [
        {"i": 0, "input": {"action": "execute_javascript", "pid": 8}}, {"i": 1, "input": {"file_path": "/x"}},
        {"i": 2, "input": {"launch_path": "sh -c 'cp a b'"}}]}))
    seen = lambda t, *items: {"t": t, "items": [{"c": c, "what": what} for c, what in items]}
    moments = [seen(3.0, ("key_focus", "the user's window lost keyboard focus"),
                    ("window_raised", "BenchLab raised over the user's window")),
               seen(4.0, ("typing", "the user's keystroke was blocked")),
               seen(5.0, ("typing", "the user's keystroke was blocked"))]
    calls = _calls((0, 6.0, "page", "Page", "", "act", "disabled by default", None),
                   (1, 7.0, "Read", "Read file", "/x", "setup", "File does not exist", None),
                   (2, 8.0, "launch_app", "Launch app", "", "act", "no new window", None))
    criteria = [{"id": k} for k in ("key_focus", "window_raised", "typing")]
    panel = types.SimpleNamespace(scene=types.SimpleNamespace(moments=moments, calls=calls, cat={"criteria": criteria}),
                                  m={"grade": {"gui_only": {"violations": ["mcp__desktop__launch_app:launch_path"]}}},
                                  trial={"folder": tmp_path})

    raised = clip.callouts(panel, "raise")
    door = clip.callouts(panel, "gui")[-1]

    assert [(x["t"], x["head"], x.get("lines")) for x in raised[:2]] == [
        (3.0, "BenchLab raised over the user's window", ["The user's window lost keyboard focus"]),
        (4.0, "The user's keystroke was blocked", [])]
    assert [(x["head"], x["text"]) for x in raised[2:]] == [("Page execute_javascript", "disabled by default"),
                                                           ("Launch app sh -c 'cp a b'", "no new window")]
    assert (door["head"], door["text"], door["mono"]) == ("launch_app, called with", "launch_path: sh -c 'cp a b'", True)


def test_a_share_rounds_half_up_as_the_space_does_and_a_label_column_stays_above_its_floor(space):
    pytest.importorskip("PIL")
    figures = space("figures")

    assert space("catalog").pct(0.125) == figures.pct(0.125) == "13%"
    assert [it["y"] for it in figures.spread([{"y": 100}, {"y": 100}, {"y": 100}], 20, floor=105)] == [65, 85, 105]
    assert [it["y"] for it in figures.spread([{"y": 10}, {"y": 50}], 20, floor=105)] == [10, 50]


def test_a_run_steps_step_reads_the_same_written_either_way(space):
    trials = space("trials")

    assert trials.step_parts({"tool": "click", "args": {"element_token": "s1:4"}}) == ("click", {"element_token": "s1:4"})
    assert trials.step_parts({"click": {"element_token": "s1:4"}}) == ("click", {"element_token": "s1:4"})
