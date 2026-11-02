"""The bench's grade of a trial, in its grading container, on the trial's snapshot as ``load_artifact`` stages it
(each app's files under ``/grade/trial/<app>/``, by their path in the home) and trycua's task pack
(``/grade/trycua``): their evaluator for the task on the task's workspace, or for a BenchLab task (``grade.py PROBE
SEED``) on BenchLab's state and events with the trial's seed, as their runner gives it, their A22 criteria on the
sentinel's log,
and the GUI-only guard's violations, with each Electron app's DevTools openings, while the sentinel was armed. The
files the agent left are parsed only here, never where the trial runs. Writes ``/grade/result.json`` and
``/grade/reward.txt``, 1 when every result holds, else 0; the trajectory's half of GUI-only is ``gui_only``'s verifier.

Its results: ``sentinel``, its log shows the whole trial (a condition, armed, disarmed, no sample lost); ``task``,
trycua's evaluator passed; ``gui_only``, no violation the guard logged and no DevTools opened; and in the background
condition ``user_undisturbed``, all eight A22 criteria measured and held and the user's window not asked to close."""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TRIAL = Path("/grade/trial")
TRYCUA = Path("/grade/trycua")
OUT = Path("/grade")
SENTINEL = Path("bench-sentinel/.bench-sentinel")
LAB = Path("benchlab/.benchlab")
TASKS = ("cdb-s02", "cdb-s03", "cdb-s04")


def main():
    if len(sys.argv) == 3:
        task, seed = sys.argv[1], int(sys.argv[2])
    else:
        [task], seed = [path.name for path in TRIAL.iterdir() if path.name in TASKS], None
    with tempfile.TemporaryDirectory() as scratch:
        results = grade(task, TRIAL, TRYCUA, Path(scratch), seed)
    (OUT / "result.json").write_text(json.dumps({"task": task, "results": results}, indent=1) + "\n")
    (OUT / "reward.txt").write_text("1\n" if all(result["result"] for result in results) else "0\n")


def grade(task, trial, trycua, scratch, seed=None):
    """The results of a trial of ``task``, a CDB task or with ``seed`` a BenchLab probe, from its snapshot ``trial``,
    with trycua's task pack ``trycua``."""
    evaluation = (_lab(trycua / "probes" / task, trial / LAB, seed, scratch) if seed is not None
                  else _evaluate(trycua / "taskpack" / "tasks" / "shared" / task, trial / task / task, scratch))
    summarize, v2 = (_module(trycua / "scoring" / f"{name}.py") for name in ("summarize_sentinel", "bench_v2"))
    log = trial / SENTINEL / "sentinel.jsonl"
    lines = _lines(log)
    start = max((i for i, line in enumerate(lines) if line["ev"] == "start"), default=0)
    lines = lines[start:]
    summary = summarize.summarize(str(log))
    condition = next((line.get("condition") for line in reversed(lines) if line["ev"] == "start"), None)
    window = [line for line in lines if line["armed"] or line["ev"] == "disarmed"]
    armed = next((line for line in window if line["ev"] == "armed"), {})
    problems = _problems(window, condition)
    violations = sorted({line["detail"] for line in window if line["ev"] == "gui_only_violation"}
                        | _devtools(trial / SENTINEL / "devtools.jsonl", window))
    gui_only = not violations and not problems
    multiplayer = v2.multiplayer_score(summary, bool(summary["available"] and armed.get("active") and armed.get("key")),
                                       bool(evaluation.get("passed")) and gui_only, condition)
    closes = sum(line["ev"] == "close_refused" for line in window)
    results = [
        {"id": "sentinel", "result": not problems, "problems": problems,
         "description": "the sentinel's log shows the whole trial"},
        {"id": "task", "result": evaluation.get("passed") is True, "score": evaluation.get("score"),
         "description": f"trycua's evaluator for {task}",
         "checks": {name: check.get("passed")
                    for name, check in (evaluation.get("detail") or evaluation).get("checks", {}).items()}},
        {"id": "gui_only", "result": gui_only, "violations": violations,
         "transient": sorted({line["detail"] for line in window if line["ev"] == "gui_only_transient"}),
         "description": "no way out of the GUI the guard saw, and no DevTools opened"},
    ]
    if condition == "background":
        undisturbed = multiplayer["user_undisturbed"] is True and not closes and not problems
        results.append({"id": "user_undisturbed", "result": undisturbed, "criteria": multiplayer["criteria"],
                        "unmeasured": multiplayer["unmeasured"], "close_refused": closes,
                        "background_completion": bool(multiplayer["background_completion"]) and undisturbed,
                        "description": "trycua's A22: the user could have kept working, undisturbed"})
    return results


def _problems(window, condition):
    """What keeps the sentinel's log from showing the whole trial: no condition, never armed, not disarmed (it stopped
    while armed), or samples that failed while armed."""
    problems = [] if condition in ("background", "foreground") else [f"the sentinel's condition is {condition!r}"]
    if not any(line["ev"] == "armed" for line in window):
        problems.append("the sentinel was never armed")
    elif not any(line["ev"] == "disarmed" for line in window):
        problems.append("the sentinel stopped before it was disarmed")
    errors = sorted({line.get("error") for line in window if line["ev"] == "sample_error"})
    return problems + [f"a sample failed: {error}" for error in errors[:5]]


def _devtools(log, window):
    """Each opening of an Electron app's DevTools while the sentinel was armed, as the app's hook logged it."""
    if not window or not log.exists():
        return set()
    start, end = window[0]["t"], next((line["t"] for line in window if line["ev"] == "disarmed"), float("inf"))
    return {f"devtools:{line.get('title')}" for line in _lines(log) if start <= line["t"] <= end}


def _evaluate(task, workspace, scratch):
    """trycua's evaluator for the task folder ``task`` on ``workspace``: its JSON result."""
    result = scratch / "result.json"
    (scratch / "artifacts").mkdir(exist_ok=True)
    subprocess.run([sys.executable, "evaluator/evaluate.py", "--workspace", str(workspace), "--artifacts",
                    str(scratch / "artifacts"), "--result", str(result), "--agent-exit-code", "0"], cwd=task,
                   check=True, timeout=300)
    return json.loads(result.read_text())


def _lab(probe, data, seed, scratch):
    """trycua's evaluator for the BenchLab task ``probe`` on BenchLab's state and events in ``data``, with the trial's
    ``seed``: its JSON result, which says why when they're missing."""
    result = scratch / "result.json"
    subprocess.run([sys.executable, str(probe / "evaluate.py"), "--seed", str(seed), "--state",
                    str(data / "state.json"), "--events", str(data / "events.jsonl"), "--result", str(result)],
                   check=True, timeout=300)
    return json.loads(result.read_text())


def _module(path):
    spec = importlib.util.spec_from_file_location(f"trycua_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lines(log):
    """A JSONL log's whole lines; a torn last line is left out."""
    return [json.loads(raw) for raw in log.read_text().splitlines() if raw.strip().endswith("}")] if log.exists() else []


if __name__ == "__main__":
    main()
