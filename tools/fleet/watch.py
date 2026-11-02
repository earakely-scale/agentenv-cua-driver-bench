"""watch.py INSTANCES_FILE [--once]: every 3 minutes, each worker's state (its `fleet` unit, its trials by status,
how many passed, the trial running); exits when every worker's unit has stopped, printing their progress lines."""
import json
import sys
import time
from pathlib import Path

from common import ssm

PEEK = """echo "unit=$(systemctl is-active fleet)"
cat ~/fleet/progress.jsonl 2>/dev/null
echo "running=$(ls -t ~/fleet/logs 2>/dev/null | head -1)"
"""


def main():
    instances = Path(sys.argv[1]).read_text().split()
    while True:
        states = {i: _peek(i) for i in instances}
        active = 0
        for instance, text in states.items():
            lines = text.splitlines()
            unit = next((l.split("=", 1)[1] for l in lines if l.startswith("unit=")), "?")
            progress = [json.loads(l) for l in lines if l.startswith("{")]
            running = next((l.split("=", 1)[1] for l in lines if l.startswith("running=")), "")
            counts = {}
            for p in progress:
                counts[p["status"]] = counts.get(p["status"], 0) + 1
            passed = sum(1 for p in progress if (p.get("summary") or {}).get("passed"))
            active += unit in ("active", "activating")
            print(f"{instance} {unit:9} {counts} passed={passed} last={running}", flush=True)
        if not active or "--once" in sys.argv:
            for instance, text in states.items():
                print("==", instance)
                print("\n".join(l[:400] for l in text.splitlines() if l.startswith("{")))
            return
        print("---", time.strftime("%H:%M:%S"), flush=True)
        time.sleep(180)


def _peek(instance):
    try:
        return ssm(instance, PEEK, timeout=90)
    except (Exception, SystemExit) as error:
        return f"unit=unreachable {type(error).__name__}"


if __name__ == "__main__":
    main()
