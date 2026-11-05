"""The replay Space's catalog and figures per driver, offline: a trial's driver, cua-driver when its trial.json names
none; a missing trial's from its task file; the board, the replay keys and the trial order per driver; each OS and
model that several drivers ran compared over the tasks all of them ran in both conditions; the card's tables with
their drivers; the results figures of cua-driver's rows alone, and a drivers figure's panel per comparison; and the
other drivers' calls as the replay's lane says them."""
import importlib
import json
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
            "started_at": f"2026-11-05T0{run_index}:00:00Z", "passed": passed, "grade": {"task": {"score": score}}}


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


def test_a_task_the_config_doesnt_score_in_the_background_counts_in_the_foreground_alone(space):
    catalog = space("catalog")
    cfg = {**CONFIG, "caveats": [{"os": None, "condition": "background", "tasks": ["mb-10"], "mark": "¶",
                                  "short": "Not scored", "reason": "Why.", "unscored": True}]}
    metas = [m for driver in ("cua-driver", "agent-desktop") for m in _cells(driver, [
        ("ir-01", "foreground", [(True, 1.0)]), ("ir-01", "background", [(False, 0.5)]),
        ("mb-10", "foreground", [(True, 1.0)]), ("mb-10", "background", [(False, 0.0)])])]
    cat = _catalog(space, metas, cfg)

    rows = {(r["driver"], r["condition"]): (r["passed"], r["n_trials"], set(r["tasks"])) for r in cat["board"]}
    [comparison] = cat["comparisons"]
    cua = comparison["drivers"][0]

    assert rows[("cua-driver", "foreground")] == (2, 2, {"ir-01", "mb-10"})
    assert rows[("cua-driver", "background")] == (0, 1, {"ir-01"})
    assert set(comparison["tasks"]) == {"ir-01", "mb-10"}
    assert (cua["foreground"]["n"], cua["background"]["n"], cua["background"]["score"]) == (2, 1, 0.5)
    assert "not scored¶" in catalog.results_md(cat) and "¶ Not scored: Why." in catalog.results_md(cat)
    assert catalog.unscored(cfg, "linux", "background", "mb-10") and not catalog.unscored(cfg, "macos", "foreground", "mb-10")


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
    cat = _catalog(space, metas)

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
    assert [trials.kind_of(tool, inp) for tool, inp in (
        ("desktop_screenshot", {}), ("macos_harness", {"commands": [["get_app_state", "--app", "BenchLab"]]}),
        ("desktop_wait", {"ms": 800}), ("desktop_drag", {}), ("click", {}))] == ["look", "look", "wait", "act", "act"]


def test_a_run_the_config_excludes_is_named_as_its_os_and_run(space):
    assert space("trials").run_of(Path("/d/runs/macos/cua-driver-sonnet-5-5-2026-11-05/ir-01-r1-foreground"), Path("/d")) == (
        "macos/cua-driver-sonnet-5-5-2026-11-05")
    assert all(run.startswith("macos/") for run in json.loads((SPACE / "config.json").read_text())["exclude_runs"])
