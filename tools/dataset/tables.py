"""tables.py BENCH DATASET: the dataset's tables from its runs/ folders and the bench's committed trial tasks.

tasks/tasks.parquet (one row per trial task), results/trials.parquet (one row per graded trial, with the upstream driver
version its run ran, the harness errors it was re-run for and whether the board counts it, as the Space's config.json
says and at each OS and driver's newest version alone), results/board.parquet (the trials the board counts, in the few
columns the dataset viewer opens on, each with its replay in the Space),
results/calls.parquet (one row per tool call, keyed by os, run and trial_id as trials are), and
results/missing.parquet (one row per trial
whose re-runs were spent, so the run it belongs to is incomplete)."""
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

import pandas as pd

CRITERIA = ("key_focus", "window_raised", "typing", "pointer", "clipboard", "space", "dialog", "activation")
STEM = re.compile(r"^(?:(?P<os>macos)-)?(?:(?P<driver>agent-desktop|macos-harness|codex-computer-use|aside)-)?"
                  r"(?P<task>(?:cdb-g|mb-|ir-)\d\d)(?:-r(?P<run>\d))?-(?P<condition>foreground|background)$")
#: The driver of a trial that names none, the bench's first arm.
DRIVER = "cua-driver"
SPACE = f"https://huggingface.co/spaces/{os.environ.get('HF_REPO') or 'earakely-scale/CuaDriverBench-AgentEnv'}"
#: Each run's upstream driver version where its manifest doesn't record one (tools/dataset/driver_versions.py).
KNOWN_VERSIONS = Path(__file__).with_name("driver_versions.json")


def main():
    bench, dataset = Path(sys.argv[1]), Path(sys.argv[2])
    trials = sorted(p.parent for p in dataset.glob("runs/*/*/*/trial.json"))
    tasks = [task_row(bench, path) for path in sorted(bench.glob("tasks/*.json")) if STEM.match(path.stem)]
    titles = {task["task"]: task["title"] for task in tasks}
    cfg = json.loads((bench / "tools" / "space" / "config.json").read_text())
    (dataset / "tasks").mkdir(exist_ok=True)
    (dataset / "results").mkdir(exist_ok=True)
    pd.DataFrame(tasks).to_parquet(dataset / "tasks" / "tasks.parquet", index=False)
    known = json.loads(KNOWN_VERSIONS.read_text()) if KNOWN_VERSIONS.exists() else {}
    rows, calls = [], []
    for folder in trials:
        row, trial_calls = trial_row(dataset, folder, titles, cfg, known)
        rows.append(row)
        calls.extend(trial_calls)
    newest = {}
    for row in rows:
        key = (row["os"], row["driver"])
        if row["on_board"] and row["driver_version"] and version_key(row["driver_version"]) > version_key(newest.get(key)):
            newest[key] = row["driver_version"]
    for row in rows:
        current = newest.get((row["os"], row["driver"]))
        row["on_board"] = row["on_board"] and (not current or row["driver_version"] == current)
    missing = [missing_row(folder) for folder in sorted(p.parent for p in dataset.glob("runs/*/*/*/missing.json"))]
    pd.DataFrame(rows).to_parquet(dataset / "results" / "trials.parquet", index=False)
    board = sorted((board_row(row, cfg) for row in rows if row["on_board"]),
                   key=lambda r: (r["os"], r["driver"], r["model"], r["task"], r["condition"], r["run"] or 0))
    pd.DataFrame(board).to_parquet(dataset / "results" / "board.parquet", index=False)
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


def version_key(version):
    """``version`` as numbers to order by, 0.47.10 after 0.47.4; an unknown one before every known."""
    return tuple(int(n) for n in re.findall(r"\d+", version)) if version else ()


def driver_version(folder, os_name, driver, known):
    """The upstream version of ``driver`` the run of the trial in ``folder`` ran: its run manifest's, else ``known``'s."""
    manifest = folder.parent / "manifest.json"
    computers = (json.loads(manifest.read_text()).get("computers") or {}) if manifest.exists() else {}
    return next((c["driver_version"] for c in computers.values() if c.get("driver") == driver and c.get("driver_version")),
                known.get(f"{os_name}/{folder.parent.name}"))


def trial_row(dataset, folder, titles, cfg, known=None):
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
        "driver_version": driver_version(folder, facts["os"], facts.get("driver", DRIVER), known or {}),
        "task": facts["task"],
        "probe": facts["probe"],
        "title": titles.get(facts["task"]),
        "condition": facts["condition"],
        "model": facts["model"],
        "harness": facts["harness"],
        "harness_version": facts["harness_version"],
        "effort": facts.get("effort"),
        "reward": facts["reward"],
        "passed": facts.get("passed"),
        "on_board": f"{facts['os']}/{folder.parent.name}" not in (cfg.get("exclude_runs") or [])
                    and ((cfg.get("models") or {}).get(facts["model"]) or {}).get("board", True),
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


def board_row(row, cfg):
    """A trial as the dataset viewer opens on it: readable names, the grade's halves, what it took, and its replay."""
    lead = "" if row["driver"] == DRIVER else f"{row['driver']}/"
    replay = (f"{SPACE}#/{lead}{row['os']}/{row['task']}/{row['condition']}/{urllib.parse.quote(row['model'], safe='')}"
              f"/r{row['run_index']}")
    driver = cfg["drivers"].get(row["driver"]) or {}
    return {
        "os": (cfg["oses"].get(row["os"]) or {}).get("name", row["os"]),
        "driver": driver.get("label") or driver.get("name") or row["driver"],
        "driver_version": row["driver_version"],
        "model": ((cfg.get("models") or {}).get(row["model"]) or {}).get("name", row["model"]),
        "task": row["probe"],
        "title": row["title"],
        "condition": row["condition"],
        "run": row["run_index"],
        "passed": row["passed"],
        "task_done": row["task_passed"],
        "gui_only": row["gui_only"],
        "user_undisturbed": row["user_undisturbed"],
        "seconds": None if row["duration_s"] is None else round(row["duration_s"]),
        "model_calls": row["model_calls"],
        "cost_usd": row["cost_usd"],
        "replay": replay,
    }


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
