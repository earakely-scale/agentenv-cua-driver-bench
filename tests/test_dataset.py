"""The dataset's exporter and tables, offline: a trial's cost at list price from the tokens its trajectory reports (a
flat price from the totals, a tiered one call by call, the calls' own counts when the run was cut off before Claude
Code's result), its timeline on the recording's clock, and the rows the tables take from a trial folder and a task
file."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"
START = 1_793_628_000.0


def _module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def export():
    return _module(ROOT / "tools" / "dataset" / "export.py")


@pytest.fixture
def tables():
    pytest.importorskip("pandas")
    return _module(ROOT / "tools" / "dataset" / "tables.py")


def _call(message_id, model, prompt_tokens, output_tokens, cached=0):
    return {"type": "assistant", "message": {"id": message_id, "model": model, "content": [], "usage": {
        "input_tokens": prompt_tokens - cached, "cache_read_input_tokens": cached, "output_tokens": output_tokens}}}


def _stamp(seconds):
    return datetime.fromtimestamp(START + seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def test_a_flat_priced_trial_costs_its_token_totals_at_list_price(export):
    usage = {"anthropic/claude-sonnet-5-5": {"canonicalModel": "claude-sonnet-5-5", "inputTokens": 90,
                                             "outputTokens": 18926, "cacheReadInputTokens": 4780149,
                                             "cacheCreationInputTokens": 222025}}

    assert export.cost(usage, []) == 1.7005
    assert export.cost({"some/model": {"canonicalModel": "unpriced", "inputTokens": 1}}, []) is None


def test_haiku_is_priced_call_by_call_at_its_prompts_tier_with_the_totals_output_spread_over_the_calls(export):
    events = [_call("a", "claude-haiku-5-5", 50_000, 100, cached=49_000),
              _call("b", "claude-haiku-5-5", 150_000, 100, cached=149_000)]
    usage = {"anthropic/claude-haiku-5-5": {"canonicalModel": "claude-haiku-5-5", "outputTokens": 400}}

    small = (1_000 * 0.10 + 49_000 * 0.01 + 200 * 0.50) / 1e6
    large = (1_000 * 0.50 + 149_000 * 0.05 + 200 * 2.50) / 1e6
    assert export.cost(usage, events) == round(small + large, 4)


def test_a_run_cut_off_before_its_result_is_priced_from_its_calls_each_counted_once(export):
    events = [_call("a", "claude-sonnet-5-5", 10_000, 50), _call("a", "claude-sonnet-5-5", 10_000, 50),
              _call("b", "claude-sonnet-5-5", 20_000, 70, cached=18_000)]

    totals = export.from_calls(events)

    assert totals == {"claude-sonnet-5-5": {"canonicalModel": "claude-sonnet-5-5", "inputTokens": 12_000,
                                            "outputTokens": 120, "cacheReadInputTokens": 18_000,
                                            "cacheCreationInputTokens": 0}}
    assert export.cost(totals, events) == round((12_000 * 2 + 18_000 * 0.2 + 120 * 10) / 1e6, 4)


def test_the_timeline_puts_calls_text_and_the_users_lane_on_the_recordings_clock(export):
    use = {"type": "tool_use", "id": "t1", "name": "mcp__desktop-s02__click", "input": {"element_token": "s1:4"}}
    events = [{"type": "system", "subtype": "init"},
              {"type": "assistant", "timestamp": _stamp(10),
               "message": {"id": "m1", "content": [use, {"type": "text", "text": "Opening the mail."}]}},
              {"type": "user", "timestamp": _stamp(12), "message": {"content": [
                  {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                   "content": [{"type": "text", "text": "Background delivery is not available"}]}]}}]
    sentinel = [{"ev": "armed", "t": (START + 5) * 1000, "armed": True},
                *({"ev": "s", "t": (START + 5 + i / 20) * 1000, "armed": True, "active": True, "key": True,
                   "front": {"bid": "ai.cua.benchsentinel"}, "above_n": 0, "mouse": [1, 2]} for i in range(25)),
                {"ev": "didResignKey", "t": (START + 11) * 1000, "armed": True}]
    scripts = {"arm": {"line": {"t": (START + 5) * 1000}}, "disarm": {"line": {"t": (START + 20) * 1000}}}

    timeline = export.timeline(events, sentinel, START, START + 30, scripts)

    call = timeline["calls"][0]
    assert (call["tool"], call["server"], call["t0"], call["t1"], call["error"]) == ("click", "desktop-s02", 10, 12,
                                                                                  True)
    assert call["result"] == "Background delivery is not available" and call["turn"] == 1
    assert timeline["texts"] == [{"t": 10, "turn": 1, "text": "Opening the mail."}]
    assert [e["ev"] for e in timeline["user"]] == ["armed", "didResignKey"] and timeline["user"][1]["t"] == 11
    assert len(timeline["samples"]) == 3 and (timeline["armed_at"], timeline["disarmed_at"]) == (5, 20)


def test_a_trials_row_holds_every_half_of_its_grade_and_where_its_files_are(tables, tmp_path):
    folder = tmp_path / "runs" / "linux" / "haiku-5-5-2026-11-02" / "ir-02-r3-background"
    folder.mkdir(parents=True)
    criteria = dict.fromkeys(tables.CRITERIA, True)
    facts = {"trial_id": folder.name, "os": "linux", "task": "ir-02", "probe": "IR-02", "condition": "background",
             "model": "anthropic/claude-haiku-5-5", "harness": "claude-code", "harness_version": "2.1.280",
             "reward": 1.0, "passed": True, "run_index": 3, "seed": 1, "started_at": "2026-11-02T17:00:00Z",
             "grade": {"task": {"result": True, "score": 1.0, "checks": {"no_restart": True}},
                       "gui_only": {"result": True, "violations": []}, "sentinel": {"result": True},
                       "user_undisturbed": {"result": True, "criteria": criteria}},
             "gui_only_trajectory": {"result": True, "violations": []}}
    (folder / "trial.json").write_text(json.dumps(facts))
    (folder / "timeline.json").write_text(json.dumps({"armed_at": 5.0, "disarmed_at": 30.0, "calls": [
        {"i": 0, "turn": 1, "t0": 6.0, "t1": 7.0, "tool": "click", "server": "desktop-benchlab", "input": {},
         "error": False, "result": "ok", "image": False}]}))

    row, calls = tables.trial_row(tmp_path, folder, {"ir-02": "Set two fields and press Apply"})

    assert (row["run"], row["passed"], row["gui_only"], row["user_undisturbed"], row["a22_pointer"]) == (
        "haiku-5-5-2026-11-02", True, True, True, True)
    assert row["agent_window_s"] == 25.0 and row["recording"].endswith("ir-02-r3-background/recording.mp4")
    assert [(c["trial_id"], c["tool"]) for c in calls] == [(folder.name, "click")]


def test_a_trial_re_run_for_harness_errors_says_so_and_one_whose_re_runs_were_spent_is_a_missing_row(tables, tmp_path):
    run = tmp_path / "runs" / "macos" / "sonnet-5-5-2026-11-09"
    graded, missing = run / "ir-02-r1-background", run / "ir-02-r2-background"
    graded.mkdir(parents=True)
    missing.mkdir()
    (graded / "attempts.json").write_text(json.dumps({"harness_errors": {"rate": 1, "server": 0, "setup": 1}}))
    (missing / "missing.json").write_text(json.dumps({
        "name": missing.name, "task_file": "ir-02-r2-background", "run_index": 2, "os": "macos", "status": "missing",
        "kind": "setup", "harness_errors": {"rate": 0, "server": 0, "setup": 3}, "instance": "i-2", "exit": 1}))

    assert tables._harness_errors(graded) == 2 and tables._harness_errors(missing) == 0
    assert tables.missing_row(missing) == {"run": "sonnet-5-5-2026-11-09", "os": "macos", "name": missing.name,
                                           "task_file": "ir-02-r2-background", "run_index": 2, "kind": "setup",
                                           "harness_errors": 3}


def test_a_task_files_row_takes_its_title_from_its_brief_or_trycuas_probe(tables):
    g02 = tables.task_row(ROOT, ROOT / "tasks" / "cdb-g02-background.json")

    assert (g02["probe"], g02["title"], g02["condition"], g02["run_index"]) == (
        "CDB-G02", "Lighthouse program schedule replan", "background", None)
    if not (PACK / "probes" / "MB-09" / "task.json").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    mb09 = tables.task_row(ROOT, ROOT / "tasks" / "mb-09-r2-foreground.json")
    assert (mb09["probe"], mb09["run_index"], mb09["seed"] is not None) == ("MB-09", 2, True)
    assert mb09["title"] == json.loads((PACK / "probes" / "MB-09" / "task.json").read_text())["title"]
