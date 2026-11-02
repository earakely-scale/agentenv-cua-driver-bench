"""The fleet's plan and its workers' gates, offline: Bench v2's 100 trials split into workers on one computer each,
each trial named with its run; and a finished trial counted, or run again for a rate limit, an API error or a failed
setup, as trycua's runner does."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SETUP = ("env", "sandbox", "box", "pack", "agent", "skills", "record", "arm", "snapshot", "trial", "grade", "gui_only")


def _module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plan():
    return _module(ROOT / "tools" / "fleet" / "plan.py")


@pytest.fixture
def worker():
    pytest.importorskip("huggingface_hub")
    return _module(ROOT / "tools" / "fleet" / "worker.py")


def test_bench_v2_splits_into_workers_of_one_computer_each_with_each_trial_named_for_its_run(plan):
    stems = (ROOT / "evals" / "bench-v2-trials.txt").read_text().split()

    workers = plan.split(ROOT, stems, 10)

    assert [env for env, _ in workers] == ["desktop-s02", "desktop-s03", "desktop-s04"] + ["desktop-benchlab"] * 7
    assert all(len(specs) == 10 for _, specs in workers)
    names = [line.split("|")[1] for _, specs in workers for line in specs]
    assert len(set(names)) == 100
    assert workers[0][1][:4] == [f"cdb-g02-foreground|cdb-g02-r{run}-foreground|{run}" for run in (1, 2, 3, 4)]
    assert "mb-09-r4-background|mb-09-r4-background|4" in [line for _, specs in workers for line in specs]


def _instance(error=None, failed=(), responses=True):
    return {"completed_steps": [{"step_id": step, "status": "failure" if step in failed else "success"}
                                for step in SETUP],
            "context": {"prompt_responses": [{"error_message": error}] if responses else []}}


@pytest.mark.parametrize("instance, kind", [
    (_instance(), None),
    (_instance("claude CLI exited with code 1: Reached maximum number of turns (45)"), None),
    (_instance("claude CLI timed out after 360s"), None),
    (_instance("API Error: 429 Too Many Requests"), "rate"),
    (_instance("API Error: 529 overloaded_error"), "server"),
    (_instance("API Error: 500 Internal server error"), "server"),
    (_instance(failed=("grade",)), "setup"),
    (_instance(responses=False), "setup"),
    (None, "setup"),
], ids=["passed or failed", "max turns", "timed out", "rate limit", "overloaded", "5xx", "grade broke",
        "agent never ran", "no instance"])
def test_a_trial_counts_unless_a_rate_limit_an_api_error_or_its_setup_cut_it_short(worker, instance, kind):
    assert worker.failure(instance) == kind
