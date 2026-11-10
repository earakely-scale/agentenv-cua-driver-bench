"""board.py BOARD.toml [--plan]: run a board, several runs over a fleet of hosts, from one command. BOARD names the
runs (each a run name, a model and a trial list, as plan.py takes it) and the hosts (each an instance, and on a Mac the
framework commit its checkout is pinned to and the agent-env state its computers are kept in). The board's workers are
planned as plan.py plans them, at most `per` trials each, one computer per worker, and each computer's workers go to
one host, the busiest computers first to the least loaded host, so a host composes only the computers it runs; a
computer is split over hosts only where one host would carry more than its share. Each host runs its workers one after
another, through start.py; the board asks and starts its hosts concurrently.

It's restart-safe: what it started is kept in BOARD.state.json, and each poll reads what each host runs, by its
worker's trials' digest, so nothing starts twice. A host that can't be asked is passed over for that poll; a start that
fails is tried again; a worker that ended with trials left resumes, up to `RESUMES` times, then counts as failed; one
whose trials all ended but some failed their export or upload exports and uploads just those again, from their
finished task instances, as many times. A host's framework is checked out and installed at its pin only while it runs
nothing. With `keep`, each host's bench runs as its checkout is, a branch say, rather than moved to origin/main.
`--plan` prints the plan and starts nothing. What happens goes to BOARD.log."""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import plan
from common import ROOT, ssm

POLL_S = 60
#: How long a started worker may take to show on its host before its start counts as failed.
START_S = 600
#: How many times a worker that ended with trials left is resumed before it counts as failed.
RESUMES = 2
#: How far over its share of the board's trials a host takes another of a computer's workers before the computer is
#: split onto the least loaded host.
SLACK = 1.25
#: How many hosts the board asks, and starts workers on, at once.
CONCURRENT = 16


@dataclass
class Worker:
    id: str
    run: str
    model: str
    computer: str
    specs: list[str]
    settings: list[str] = field(default_factory=list)

    @property
    def digest(self) -> str:
        return hashlib.sha256(("\n".join(self.specs) + "\n").encode()).hexdigest()


@dataclass
class Host:
    name: str
    instance: str
    framework: str | None = None
    state: str | None = None
    workers: list[Worker] = field(default_factory=list)

    @property
    def load(self) -> int:
        return sum(len(w.specs) for w in self.workers)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    board = tomllib.loads(args.board.read_text())
    if any(h.get("framework") for h in board["host"]) and not {"framework_checkout", "venv"} <= board.keys():
        raise SystemExit("a host pins a framework, so the board names its checkout and venv (framework_checkout, venv)")
    workers, run_specs = planned(board)
    hosts = assign(workers, [Host(h["name"], h["instance"], h.get("framework"), h.get("state"))
                             for h in board["host"]])
    if args.plan:
        for host in hosts:
            computers = sorted({w.computer for w in host.workers})
            print(f"{host.name} ({host.instance}): {host.load} trials, composes {computers}")
            for w in host.workers:
                print(f"  {w.id}: {len(w.specs)} trials")
        return
    work = args.board.with_suffix(".board")
    work.mkdir(exist_ok=True)
    for name, lines in run_specs.items():
        (work / f"{name}.run.txt").write_text("\n".join(lines) + "\n")
    for w in workers:
        (work / f"{w.id.replace('/', '--')}.txt").write_text("\n".join(w.specs) + "\n")
    Runner(board, hosts, work, args.board.with_suffix(".state.json"), args.board.with_suffix(".log")).run()


def planned(board: dict) -> tuple[list[Worker], dict[str, list[str]]]:
    """The board's workers, each run's planned as plan.py plans a trial list, and each run's lines, which its
    workers' manifest pins."""
    workers, runs = [], {}
    for run in board["run"]:
        stems = (ROOT / run["trials"]).read_text().split()
        split = plan.split(ROOT, stems, board.get("per", 35))
        runs[run["name"]] = [line for _, specs in split for line in specs]
        for n, (computer, specs) in enumerate(split, 1):
            settings = [line.format(computer=computer) for line in run.get("set", [])]
            workers.append(Worker(f"{run['name']}/{n:02d}", run["name"], run["model"], computer, specs, settings))
    return workers, runs


def assign(workers: list[Worker], hosts: list[Host]) -> list[Host]:
    """Each worker given a host, a computer's workers to the host that already composes it unless that host would carry
    more than ``SLACK`` times its share, else to the least loaded host; the computers with the most trials first, and
    on each host its computers' workers together, in the board's order."""
    share = sum(len(w.specs) for w in workers) / len(hosts)
    by_computer: dict[str, list[Worker]] = {}
    for w in workers:
        by_computer.setdefault(w.computer, []).append(w)
    for computer in sorted(by_computer, key=lambda c: -sum(len(w.specs) for w in by_computer[c])):
        for w in by_computer[computer]:
            holding = [h for h in hosts if any(x.computer == computer for x in h.workers)]
            host = min(holding, key=lambda h: h.load) if holding else None
            if host is None or host.load + len(w.specs) > SLACK * share:
                host = min(hosts, key=lambda h: h.load)
            host.workers.append(w)
    order = {w.id: n for n, w in enumerate(workers)}
    for host in hosts:
        first = {}
        for w in host.workers:
            first.setdefault(w.computer, order[w.id])
        host.workers.sort(key=lambda w: (first[w.computer], order[w.id]))
    return hosts


#: What a host runs: whether a worker runs, its trials' digest, how many of them have ended and how many of those failed
#: their export or upload, the head of the framework checkout when one is named, and the job log's last line.
PEEK = """pgrep -f tools/fleet/worker.py >/dev/null && echo running=1 || echo running=0
echo "digest=$(shasum -a 256 ~/fleet/specs.txt 2>/dev/null | cut -c1-64)"
echo "ended=$(cat ~/fleet/progress.jsonl 2>/dev/null | wc -l | tr -d ' ')"
echo "failed=$(grep -cE '"status": "(export|upload)_failed"' ~/fleet/progress.jsonl 2>/dev/null)"
{framework}echo "log=$(tail -1 ~/fleet/job.log 2>/dev/null | cut -c1-200)"
"""


class Runner:
    def __init__(self, board: dict, hosts: list[Host], work: Path, state_path: Path, log: Path):
        self.board, self.hosts, self.work, self.state_path, self.log = board, hosts, work, state_path, log
        self.os = board.get("os", "macos")
        self.state = json.loads(state_path.read_text()) if state_path.exists() else {}
        self.lock = threading.Lock()

    def run(self) -> None:
        with ThreadPoolExecutor(max_workers=min(CONCURRENT, len(self.hosts))) as pool:
            while not all(self._finished(h) for h in self.hosts):
                list(pool.map(self._poll, self.hosts))
                time.sleep(POLL_S)
        self.say("board done: " + ", ".join(f"{w}: {s['status']}" for w, s in sorted(self.state.items())))

    def _poll(self, host: Host) -> None:
        with self.lock:
            self.poll(host)

    @contextmanager
    def _unlocked(self):
        """The board's lock let go while a host is asked or a worker started, the slow part of a poll, so other hosts'
        polls go on meanwhile; a poll outside run() holds no lock."""
        held = self.lock.locked()
        if held:
            self.lock.release()
        try:
            yield
        finally:
            if held:
                self.lock.acquire()

    def poll(self, host: Host) -> None:
        """One look at ``host``: what it runs recorded, and its next worker started when it runs nothing."""
        seen = self.peek(host)
        if seen is None:
            return
        current = next((w for w in host.workers if self.state.get(w.id, {}).get("status") == "started"), None)
        if current is not None:
            record = self.state[current.id]
            mine = seen["digest"] == record.get("digest", current.digest)
            if seen["running"] and mine:
                record["seen"] = True
                return self.save()
            if not record.get("seen") and not mine and time.time() - record["at"] < START_S:
                return
            if mine and seen["ended"] >= record.get("trials", len(current.specs)):
                if seen["failed"] and record.get("reexports", 0) < RESUMES:
                    return self.reexport(host, current)
                record["status"] = "failed" if seen["failed"] else "done"
                lost = f", {seen['failed']} not uploaded" if seen["failed"] else ""
                self.say(f"{host.name} ended {current.id}: {seen['ended']} trials{lost}; {seen['log']}")
            elif record.get("resumes", 0) < RESUMES and (record.get("seen") or mine):
                record["resumes"] = record.get("resumes", 0) + 1
                self.say(f"{host.name} {current.id} ended with {seen['ended']} of {record.get('trials', len(current.specs))} "
                         f"trials; resuming ({record['resumes']}/{RESUMES}); {seen['log']}")
                return self.start(host, current, fresh=False, specs=Path(record["specs"]) if record.get("specs") else None)
            else:
                record["status"] = "failed"
                self.say(f"{host.name} {current.id} failed: {seen['ended']} of {len(current.specs)} trials; "
                         f"{seen['log']}")
            self.save()
        if seen["running"]:
            return
        following = next((w for w in host.workers if self.state.get(w.id, {}).get("status", "pending") == "pending"),
                         None)
        if following is None:
            return
        if host.framework and seen.get("framework") != host.framework:
            return self.pin(host)
        self.start(host, following, fresh=True)

    def peek(self, host: Host) -> dict | None:
        framework = (f'echo "framework=$(git -C {self.board["framework_checkout"]} rev-parse HEAD 2>/dev/null)"\n'
                     if host.framework else "")
        try:
            with self._unlocked():
                out = ssm(host.instance, PEEK.format(framework=framework), timeout=90, os_type=self.os)
        except (Exception, SystemExit) as error:
            self.say(f"{host.name} couldn't be asked: {error}"[:300])
            return None
        seen = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        if "running" not in seen:
            return None
        return {"running": seen["running"] == "1", "digest": seen.get("digest", ""),
                "ended": int(seen.get("ended") or 0), "failed": int(seen.get("failed") or 0),
                "framework": seen.get("framework") or None,
                "log": seen.get("log", "")}

    def pin(self, host: Host) -> None:
        """``host``'s framework checkout moved to its pin and installed, while it runs nothing."""
        checkout, venv = self.board["framework_checkout"], self.board["venv"]
        ref = shlex.quote(host.framework)
        try:
            with self._unlocked():
                out = ssm(host.instance, f"""export PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH
cd {checkout} && git fetch -q origin && git checkout -q -f {ref}
git rev-parse HEAD
uv pip install -q --python {venv}/bin/python -e ./packages/agentenv-protocol -e '.[dev]' 2>&1 | tail -1""",
                          timeout=900, os_type=self.os)
        except (Exception, SystemExit) as error:
            return self.say(f"{host.name} couldn't be pinned to {host.framework}: {error}"[:300])
        head = (out.split() or [""])[0]
        if not head.startswith(host.framework) and head != host.framework:
            return self.say(f"{host.name}: {host.framework} isn't a commit its checkout has: HEAD {head[:12]}")
        host.framework = head
        self.say(f"{host.name} pinned to {head[:12]}")

    def reexport(self, host: Host, worker: Worker) -> None:
        """``worker``'s trials that failed their export or upload exported and uploaded again on ``host``, from the task
        instances they finished on, without running them."""
        try:
            with self._unlocked():
                out = ssm(host.instance, "cat ~/fleet/progress.jsonl", timeout=90, os_type=self.os)
        except (Exception, SystemExit) as error:
            return self.say(f"{host.name} couldn't read {worker.id}'s progress: {error}"[:300])
        records = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
        lines = [f"{r['stem']}|{r['name']}|{r['run_index']}|{r['instance']}" for r in records
                 if r.get("status") in ("export_failed", "upload_failed") and r.get("instance")]
        record = self.state[worker.id]
        record["reexports"] = record.get("reexports", 0) + 1
        specs = self.work / f"{worker.id.replace('/', '--')}--reexport-{record['reexports']}.txt"
        specs.write_text("\n".join(lines) + "\n")
        one = len(lines) == 1
        self.say(f"{host.name} {worker.id}: {len(lines)} trial{'' if one else 's'} not uploaded; exporting "
                 f"{'it' if one else 'them'} again ({record['reexports']}/{RESUMES})")
        self.start(host, worker, fresh=True, specs=specs)

    def start(self, host: Host, worker: Worker, *, fresh: bool, specs: Path | None = None) -> None:
        env = {**os.environ, **{name: value for name, value in (("FLEET_VENV", self.board.get("venv")),
                                                                  ("FLEET_BENCH", self.board.get("bench")),
                                                                  ("FLEET_STATE", host.state)) if value}}
        path = specs or self.work / f"{worker.id.replace('/', '--')}.txt"
        lines = specs.read_text().splitlines() if specs else worker.specs
        argv = [sys.executable, str(Path(__file__).with_name("start.py")), host.instance, worker.run, worker.model,
                str(path), "--run-specs",
                str(self.work / f"{worker.run}.run.txt"), "--os", self.os]
        if taskpack := self.board.get("taskpack"):
            argv += ["--taskpack", str(ROOT / taskpack)]
        if self.board.get("keep"):
            argv.append("--keep")
        if fresh:
            argv.append("--fresh")
        for line in worker.settings:
            argv += ["--set", line]
        with self._unlocked():
            done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, env=env)
        said = (done.stdout + done.stderr).strip().splitlines()
        if done.returncode or not said or said[-1] != "started":
            return self.say(f"{host.name} couldn't start {worker.id}: {said[-1:] or done.returncode}; trying again")
        record = self.state.setdefault(worker.id, {})
        record.update(status="started", at=time.time(), seen=False, host=host.name, trials=len(lines),
                      specs=str(specs) if specs else None,
                      digest=hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest())
        self.say(f"{host.name} {'started' if fresh else 'resumed'} {worker.id} ({len(lines)} trials, {worker.computer})")
        self.save()

    def _finished(self, host: Host) -> bool:
        return all(self.state.get(w.id, {}).get("status") in ("done", "failed") for w in host.workers)

    def save(self) -> None:
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state, indent=1, sort_keys=True))
        temp.replace(self.state_path)

    def say(self, text: str) -> None:
        with self.log.open("a") as out:
            out.write(f"{time.strftime('%H:%M:%S', time.gmtime())}Z {text}\n")


if __name__ == "__main__":
    main()
