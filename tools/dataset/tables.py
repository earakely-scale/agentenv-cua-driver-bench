"""tables.py BENCH DATASET: the dataset's tables from its runs/ folders and the bench's committed trial tasks.

tasks/tasks.parquet (one row per trial task), results/trials.parquet (one row per graded trial, with the harness errors
it was re-run for), results/calls.parquet (one row per tool call, keyed by os, run and trial_id as trials are), and
results/missing.parquet (one row per trial
whose re-runs were spent, so the run it belongs to is incomplete)."""
import json
import re
import sys
from pathlib import Path

import pandas as pd

CRITERIA = ("key_focus", "window_raised", "typing", "pointer", "clipboard", "space", "dialog", "activation")
STEM = re.compile(r"^(?:(?P<os>macos)-)?(?:(?P<driver>agent-desktop|macos-harness)-)?(?P<task>(?:cdb-g|mb-|ir-)\d\d)"
                  r"(?:-r(?P<run>\d))?-(?P<condition>foreground|background)$")
#: The driver of a trial that names none, the bench's first arm.
DRIVER = "cua-driver"


def main():
    bench, dataset = Path(sys.argv[1]), Path(sys.argv[2])
    trials = sorted(p.parent for p in dataset.glob("runs/*/*/*/trial.json"))
    tasks = [task_row(bench, path) for path in sorted(bench.glob("tasks/*.json")) if STEM.match(path.stem)]
    titles = {task["task"]: task["title"] for task in tasks}
    off = unscored(bench)
    (dataset / "tasks").mkdir(exist_ok=True)
    (dataset / "results").mkdir(exist_ok=True)
    pd.DataFrame(tasks).to_parquet(dataset / "tasks" / "tasks.parquet", index=False)
    rows, calls = [], []
    for folder in trials:
        row, trial_calls = trial_row(dataset, folder, titles, off)
        rows.append(row)
        calls.extend(trial_calls)
    missing = [missing_row(folder) for folder in sorted(p.parent for p in dataset.glob("runs/*/*/*/missing.json"))]
    pd.DataFrame(rows).to_parquet(dataset / "results" / "trials.parquet", index=False)
    pd.DataFrame(calls).to_parquet(dataset / "results" / "calls.parquet", index=False)
    pd.DataFrame(missing, columns=MISSING).to_parquet(dataset / "results" / "missing.parquet", index=False)
    print(len(rows), "trials,", len(calls), "calls,", len(missing), "missing")


def task_row(bench, path):
    steps = {step["id"]: step for step in json.loads(path.read_text())}
    match = STEM.match(path.stem)
    task = match["task"]
    probe = task.upper() if not task.startswith("cdb") else "CDB-" + task.split("-")[1].upper()
    prompt = steps["task"]["prompt"]
    title = (prompt.splitlines()[0].removeprefix("# ").strip() if prompt.startswith("# ")
             else json.loads((bench / "artifacts" / "taskpack" / "probes" / probe / "task.json").read_text())["title"])
    settings = steps["env"].get("env_params", {}).get("app_settings", {})
    return {
        "task_file": path.stem,
        "task": task,
        "probe": probe,
        "title": title,
        "condition": match["condition"],
        "run_index": int(match["run"]) if match["run"] else None,
        "seed": (settings.get("benchlab") or {}).get("seed"),
        "os": match["os"] or "linux",
        "driver": match["driver"] or DRIVER,
        "computer": steps["env"]["env_id"],
        "prompt": steps["task"]["prompt"],
        "system_prompt": steps["agent"]["system_prompt"],
        "builtin_tools": json.dumps(steps["agent"].get("builtin_tools")),
        "max_turns": steps["task"].get("max_turns"),
        "timeout_s": steps["task"].get("timeout_seconds"),
        "task_json": path.read_text(),
    }


def unscored(bench):
    """The OS, condition and tasks of each cell the Space's config doesn't score, its trials kept but in no total."""
    caveats = json.loads((bench / "tools" / "space" / "config.json").read_text()).get("caveats") or []
    return [(cv.get("os"), cv["condition"], set(cv["tasks"])) for cv in caveats if cv.get("unscored")]


def trial_row(dataset, folder, titles, off):
    facts = json.loads((folder / "trial.json").read_text())
    timeline = json.loads((folder / "timeline.json").read_text())
    grade = facts.get("grade") or {}
    task, gui, user = grade.get("task") or {}, grade.get("gui_only") or {}, grade.get("user_undisturbed") or {}
    trajectory_check = facts.get("gui_only_trajectory") or {}
    rel = folder.relative_to(dataset).as_posix()
    row = {
        "trial_id": facts["trial_id"],
        "run": folder.parent.name,
        "os": facts["os"],
        "driver": facts.get("driver", DRIVER),
        "task": facts["task"],
        "probe": facts["probe"],
        "title": titles.get(facts["task"]),
        "condition": facts["condition"],
        "model": facts["model"],
        "harness": facts["harness"],
        "harness_version": facts["harness_version"],
        "reward": facts["reward"],
        "passed": facts.get("passed"),
        "scored": not any(os_ in (None, facts["os"]) and condition == facts["condition"] and facts["task"] in tasks
                          for os_, condition, tasks in off),
        "run_index": facts.get("run_index"),
        "seed": facts.get("seed"),
        "task_file": facts.get("task_file"),
        "task_passed": task.get("result"),
        "task_score": task.get("score"),
        "task_checks": json.dumps(task.get("checks")),
        "gui_only": bool(gui.get("result")) and bool(trajectory_check.get("result", True)),
        "gui_only_violations": json.dumps(sorted(set(gui.get("violations") or [])
                                                 | set(trajectory_check.get("violations") or []))),
        "user_undisturbed": user.get("result") if user else None,
        **{f"a22_{key}": (user.get("criteria") or {}).get(key) if user else None for key in CRITERIA},
        "sentinel_ok": (grade.get("sentinel") or {}).get("result"),
        "agent_error": facts.get("agent_error"),
        "cost_usd": facts.get("cost_usd"),
        "cost_usd_reported": facts.get("cost_usd_reported"),
        "model_calls": facts.get("model_calls"),
        "num_turns": facts.get("num_turns"),
        "tool_calls": facts.get("tool_calls"),
        "tool_errors": facts.get("tool_errors"),
        "duration_s": facts.get("duration_s"),
        "agent_window_s": (timeline["disarmed_at"] - timeline["armed_at"])
        if timeline.get("disarmed_at") is not None else None,
        "harness_errors": _harness_errors(folder),
        "started_at": facts["started_at"],
        "recording": f"{rel}/recording.mp4",
        "trajectory": f"{rel}/trajectory.json",
        "timeline": f"{rel}/timeline.json",
        "sentinel_log": f"{rel}/sentinel.jsonl",
        "workspace": f"{rel}/workspace",
    }
    calls = [{"os": facts["os"], "run": folder.parent.name, "trial_id": facts["trial_id"], "i": c["i"], "turn": c["turn"], "t0": c["t0"], "t1": c["t1"],
              "tool": c["tool"], "server": c["server"], "input": json.dumps(c["input"]), "error": c["error"],
              "result": c["result"], "image": c["image"]} for c in timeline["calls"]]
    return row, calls


MISSING = ("run", "os", "name", "task_file", "run_index", "kind", "harness_errors")


def missing_row(folder):
    """A trial infrastructure cut short past its re-runs, from the record the fleet's worker uploads for it."""
    record = json.loads((folder / "missing.json").read_text())
    return {"run": folder.parent.name, "os": record["os"], "name": record["name"], "task_file": record["task_file"],
            "run_index": record["run_index"], "kind": record["kind"],
            "harness_errors": sum(record["harness_errors"].values())}


def _harness_errors(folder):
    """How many times infrastructure cut the trial short before this run of it, 0 when its folder doesn't say."""
    attempts = folder / "attempts.json"
    return sum(json.loads(attempts.read_text())["harness_errors"].values()) if attempts.exists() else 0


if __name__ == "__main__":
    main()
