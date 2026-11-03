"""worker.py RUN SPECS: on a fleet VM, run each trial SPECS lists (lines of `task-file-stem|trial-name|run-index`) in
the bench's checkout with agent-env, retrying it as trycua's runner does, then export it and upload it to the dataset
at runs/linux/RUN/<name>, replacing what was there. A line with a fourth field, a task instance id, exports and uploads
that finished trial without running it.

trycua's gates: a trial cut short by a rate limit is retried after a backoff; an API 5xx or overload up to 3 times,
then the trial is excluded; a harness or setup failure once, then excluded. Everything else (timeout, max turns, a
wrong end state, a GUI-only violation) is a failed trial and counts. Progress goes to ~/fleet/progress.jsonl, which a
restart resumes from. A file ~/fleet/stop stops the worker before its next trial, the one running left to finish."""
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi

REPO = os.environ.get("HF_REPO") or "earakely-scale/CuaDriverBench-AgentEnv"
HOME = Path.home()
BENCH = Path(os.environ.get("BENCH", HOME / "bench")).expanduser()
FLEET = HOME / "fleet"
OUT = FLEET / "out"
DB = HOME / ".local/state/agent-env/document_store/local.db"
VENV = Path(os.environ.get("VENV", HOME / "venv")).expanduser()
AGENT_ENV = VENV / "bin/agent-env"
PYTHON = VENV / "bin/python"
SETUP_STEPS = ("env", "sandbox", "box", "pack", "agent", "skills", "record", "arm", "snapshot", "trial", "grade",
               "gui_only")
RATE = ("rate limit", "rate_limit", "api error: 429", "too many requests")
SERVER = ("overloaded", "api error: 5", "internal server error", "service unavailable", "bad gateway")
LIMITS = {"rate": 6, "server": 3, "setup": 1}


def main():
    run, specs = sys.argv[1], Path(sys.argv[2])
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(REPO, repo_type="dataset", exist_ok=True)
    done = {json.loads(line)["name"] for line in _progress().read_text().splitlines() if line.strip()} \
        if _progress().exists() else set()
    for line in specs.read_text().split():
        stem, name, index, *finished = line.split("|")
        if name in done:
            continue
        if (FLEET / "stop").exists():
            return
        _trial(api, run, stem, name, int(index), finished[0] if finished else None)


def _trial(api, run, stem, name, index, finished):
    tries = {"rate": 0, "server": 0, "setup": 0}
    instance = finished and _instances(stem).get(finished)
    while not finished:
        before = _instances(stem)
        with open(FLEET / "logs" / f"{name}.log", "a") as log:
            code = subprocess.run(["timeout", "3600", str(AGENT_ENV), "run", ".", "--task", stem], cwd=BENCH,
                                  stdout=log, stderr=subprocess.STDOUT).returncode
        instance = max((d for i, d in _instances(stem).items() if i not in before),
                       key=lambda d: d.get("created_at_utc") or "", default=None)
        kind = failure(instance)
        if kind is None:
            break
        tries[kind] += 1
        if tries[kind] > LIMITS[kind]:
            return _record(name, stem, index, instance, "excluded", kind=kind, tries=tries, exit=code)
        time.sleep(60 * tries[kind] if kind == "rate" else 10)
    export = subprocess.run([str(PYTHON), str(BENCH / "tools" / "dataset" / "export.py"), str(OUT),
                             f"{instance['instance_id']}|{name}|{index}"],
                            capture_output=True, text=True, env={**os.environ, "BENCH": str(BENCH)})
    if export.returncode != 0:
        return _record(name, stem, index, instance, "export_failed", error=export.stderr[-2000:], tries=tries)
    summary = json.loads(export.stdout.strip().splitlines()[-1])
    if summary["leaked"]:
        return _record(name, stem, index, instance, "withheld", leaked=summary["leaked"], tries=tries)
    for attempt in range(5):
        try:
            api.upload_folder(repo_id=REPO, repo_type="dataset", folder_path=str(OUT / name),
                              path_in_repo=f"runs/linux/{run}/{name}", commit_message=f"{run}: {name}",
                              delete_patterns="*")
            break
        except Exception as error:
            if attempt == 4:
                return _record(name, stem, index, instance, "upload_failed", error=str(error)[:500], tries=tries)
            time.sleep(30 * (attempt + 1))
    _record(name, stem, index, instance, "uploaded", summary=summary, tries=tries)


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
