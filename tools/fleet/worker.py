"""worker.py RUN SPECS: on a fleet VM, run each trial SPECS lists (lines of `task-file-stem|trial-name|run-index`) in
the bench's checkout with agent-env, re-running it when infrastructure cut it short, then export it and upload it to
the dataset at runs/OS/RUN/<name>, replacing what was there, OS being $RUN_OS (linux by default). A line with a fourth
field, a task instance id, exports and uploads that finished trial without running it. First it uploads the run's
manifest (manifest.py) to runs/OS/RUN/manifest.json, the model being $RUN_MODEL.

A trial infrastructure cut short is a harness error, never a score: a rate limit is re-run after a backoff, up to 6
times; an API 5xx or overload up to 3 times; a failed setup or health check (a step of SETUP_STEPS) up to 2 times, each
on a fresh deploy. Past that the trial is missing: its record goes to the dataset as <name>/missing.json, and a row
with a missing trial is incomplete. A graded trial's folder carries attempts.json, the harness errors it was re-run
for. Everything else (timeout, max turns, a wrong end state, a GUI-only violation) is a failed trial and counts.
Progress goes to ~/fleet/progress.jsonl, which a restart resumes from. A file ~/fleet/stop stops the worker before its
next trial, the one running left to finish."""
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi

import manifest

REPO = os.environ.get("HF_REPO") or "earakely-scale/CuaDriverBench-AgentEnv"
OS = os.environ.get("RUN_OS") or "linux"
HOME = Path.home()
BENCH = Path(os.environ.get("BENCH", HOME / "bench")).expanduser()
FLEET = HOME / "fleet"
OUT = FLEET / "out"
DB = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state") / "agent-env/document_store/local.db"
VENV = Path(os.environ.get("VENV", HOME / "venv")).expanduser()
AGENT_ENV = VENV / "bin/agent-env"
PYTHON = VENV / "bin/python"
SETUP_STEPS = ("env", "sandbox", "box", "pack", "agent", "skills", "record", "arm", "snapshot", "trial", "grade",
               "gui_only")
RATE = ("rate limit", "rate_limit", "api error: 429", "too many requests")
SERVER = ("overloaded", "api error: 5", "internal server error", "service unavailable", "bad gateway")
LIMITS = {"rate": 6, "server": 3, "setup": 2}
TRIAL_S, STOP_S = 3600, 120


def main():
    run, specs = sys.argv[1], Path(sys.argv[2])
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(REPO, repo_type="dataset", exist_ok=True)
    done = {json.loads(line)["name"] for line in _progress().read_text().splitlines() if line.strip()} \
        if _progress().exists() else set()
    lines = specs.read_text().split()
    _upload_manifest(api, run, lines)
    for line in lines:
        stem, name, index, *finished = line.split("|")
        if name in done:
            continue
        if (FLEET / "stop").exists():
            return
        _trial(api, run, stem, name, int(index), finished[0] if finished else None)
    _upload_manifest(api, run, lines)


def _trial(api, run, stem, name, index, finished):
    tries = {"rate": 0, "server": 0, "setup": 0}
    instance = finished and _instances(stem).get(finished)
    while not finished:
        before = _instances(stem)
        with open(FLEET / "logs" / f"{name}.log", "a") as log:
            code = _run([str(AGENT_ENV), "run", ".", "--task", stem], log)
        instance = max((d for i, d in _instances(stem).items() if i not in before),
                       key=lambda d: d.get("created_at_utc") or "", default=None)
        kind = failure(instance)
        if kind is None:
            break
        tries[kind] += 1
        if tries[kind] > LIMITS[kind]:
            return _missing(api, run, name, stem, index, instance, kind, tries, code)
        time.sleep(60 * tries[kind] if kind == "rate" else 10)
    export = subprocess.run([str(PYTHON), str(BENCH / "tools" / "dataset" / "export.py"), str(OUT),
                             f"{instance['instance_id']}|{name}|{index}"],
                            capture_output=True, text=True, env={**os.environ, "BENCH": str(BENCH)})
    if export.returncode != 0:
        return _record(name, stem, index, instance, "export_failed", error=export.stderr[-2000:], tries=tries)
    summary = json.loads(export.stdout.strip().splitlines()[-1])
    if summary["leaked"]:
        return _record(name, stem, index, instance, "withheld", leaked=summary["leaked"], tries=tries)
    (OUT / name / "attempts.json").write_text(json.dumps({"harness_errors": tries}))
    if error := _upload(api, run, name):
        return _record(name, stem, index, instance, "upload_failed", error=error, tries=tries)
    _record(name, stem, index, instance, "uploaded", summary=summary, tries=tries)


def _run(argv, log):
    """``argv`` run in the bench, logging to ``log``, stopped as GNU timeout stops it after TRIAL_S, which macOS lacks:
    SIGTERM, for agent-env to tear down what it deployed, then SIGKILL; its exit code, 124 when it was stopped."""
    process = subprocess.Popen(argv, cwd=BENCH, stdout=log, stderr=subprocess.STDOUT)
    try:
        return process.wait(TRIAL_S)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(STOP_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 124


def _missing(api, run, name, stem, index, instance, kind, tries, code):
    """A trial infrastructure cut short past its re-runs: missing, its record in the dataset beside the graded ones."""
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.iterdir():
        if stale.is_file():
            stale.unlink()
    record = {"name": name, "task_file": stem, "run_index": index, "os": OS, "status": "missing", "kind": kind,
              "harness_errors": tries, "instance": instance and instance["instance_id"], "exit": code}
    (folder / "missing.json").write_text(json.dumps(record, indent=1))
    error = _upload(api, run, name)
    _record(name, stem, index, instance, "missing", kind=kind, tries=tries, exit=code, upload_error=error)


def _upload(api, run, name):
    """Upload OUT/name to the run's folder for it, replacing what was there; the last error, or None."""
    for attempt in range(5):
        try:
            api.upload_folder(repo_id=REPO, repo_type="dataset", folder_path=str(OUT / name),
                              path_in_repo=f"runs/{OS}/{run}/{name}", commit_message=f"{run}: {name}",
                              delete_patterns="*")
            return None
        except Exception as error:
            if attempt == 4:
                return str(error)[:500]
            time.sleep(30 * (attempt + 1))


def _upload_manifest(api, run, lines):
    """The run's manifest, written and uploaded once a worker starts, and again once its trials are done, when it knows
    how the computers they booted were composed; every worker of a run writes the same pins."""
    OUT.mkdir(parents=True, exist_ok=True)
    built = manifest.build(BENCH, run, OS, os.environ.get("RUN_MODEL"), lines,
                           {"setup_steps": list(SETUP_STEPS), "reruns": LIMITS}, manifest.installed_drivers(),
                           state=DB.parents[2])
    (OUT / "manifest.json").write_text(json.dumps(built, indent=1))
    api.upload_file(path_or_fileobj=str(OUT / "manifest.json"), path_in_repo=f"runs/{OS}/{run}/manifest.json",
                    repo_id=REPO, repo_type="dataset", commit_message=f"{run}: manifest")


def failure(instance):
    """Why a trial must be run again, as trycua's gates count it: `rate`, `server` or `setup`; None when it counts."""
    if instance is None:
        return "setup"
    steps = {s["step_id"]: s["status"] for s in instance.get("completed_steps") or []}
    responses = instance["context"].get("prompt_responses") or []
    message = " ".join(str(r.get("error_message") or "") for r in responses).lower()
    if any(word in message for word in RATE):
        return "rate"
    if any(word in message for word in SERVER):
        return "server"
    if not responses or any(steps.get(step) != "success" for step in SETUP_STEPS):
        return "setup"
    return None


def _instances(stem):
    if not DB.exists():
        return {}
    con = sqlite3.connect(DB)
    try:
        rows = [json.loads(doc) for (doc,) in con.execute("select doc from docs_task_instances")]
    finally:
        con.close()
    return {d["instance_id"]: d for d in rows if d.get("task_id", "").endswith("/" + stem)}


def _record(name, stem, index, instance, status, **details):
    line = {"name": name, "stem": stem, "run_index": index, "status": status,
            "instance": instance and instance["instance_id"], "at": datetime.now(timezone.utc).isoformat(), **details}
    with open(_progress(), "a") as progress:
        progress.write(json.dumps(line) + "\n")


def _progress():
    return FLEET / "progress.jsonl"


if __name__ == "__main__":
    main()
