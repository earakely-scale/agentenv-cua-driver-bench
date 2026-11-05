"""plan.py TRIALS OUT PER_WORKER: split the trial list (`evals/bench-v2-trials.txt`: one task-file stem per line, a G
task's stem once per run) into worker spec files OUT/worker-NN.txt of at most PER_WORKER trials, each worker on one
computer so that it builds one, in the list's order, and the whole run's lines into OUT/run.txt, which each worker's
manifest pins. A trial's name is its stem with its run: cdb-g02-background's third line is cdb-g02-r3-background; a
stem that names its run keeps it. A macOS trial's name is its Linux twin's, the OS being its run's folder
(runs/macos/RUN), and so is an arm's: macos-agent-desktop-ir-01-r1-foreground is ir-01-r1-foreground, its driver in
its run's trials."""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RUN = re.compile(r"-r(\d)-(foreground|background)$")
#: A macOS trial's OS and its driver, an arm's or cua-driver's on its own tools, which its name leaves to its run's
#: folder.
PREFIX = re.compile(r"^macos-(?:agent-desktop-|macos-harness-|cua-driver-)?")


def main():
    trials, out, per = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    workers = split(ROOT, trials.read_text().split(), per)
    for n, (env, specs) in enumerate(workers, 1):
        (out / f"worker-{n:02d}.txt").write_text("\n".join(specs) + "\n")
        print(f"worker-{n:02d}", env, len(specs))
    (out / "run.txt").write_text("".join(f"{line}\n" for _, specs in workers for line in specs))


def split(bench, stems, per):
    """Each worker's computer and its `stem|name|run` lines."""
    seen, groups = defaultdict(int), defaultdict(list)
    for stem in stems:
        seen[stem] += 1
        named = RUN.search(stem)
        index = int(named[1]) if named else seen[stem]
        name = PREFIX.sub("", stem if named else re.sub(r"-(foreground|background)$", rf"-r{index}-\1", stem))
        env = next(s for s in json.loads((bench / "tasks" / f"{stem}.json").read_text()) if s["id"] == "env")["env_id"]
        groups[env].append(f"{stem}|{name}|{index}")
    return [(env, specs[start:start + per]) for env, specs in groups.items() for start in range(0, len(specs), per)]


if __name__ == "__main__":
    main()
