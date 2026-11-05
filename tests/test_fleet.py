"""The fleet's plan, its workers' gates and its runs' manifests, offline: Bench v2's 100 trials split into workers on
one computer each, each trial named with its run; a finished trial counted, or run again for a rate limit, an API
error or a failed setup, and recorded as missing once its re-runs are spent; and a run's manifest pinning each input
that changes a score."""
import importlib.util
import json
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
def worker(monkeypatch):
    pytest.importorskip("huggingface_hub")
    monkeypatch.syspath_prepend(str(ROOT / "tools" / "fleet"))
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


@pytest.fixture
def manifest():
    return _module(ROOT / "tools" / "fleet" / "manifest.py")


def test_a_runs_manifest_pins_the_task_pack_computers_drivers_tool_lists_image_host_seeds_and_re_run_policy(
        manifest, tmp_path, monkeypatch):
    driver = tmp_path / "cua-driver"
    driver.mkdir()
    (driver / "mcp.json").write_text('{"tools": []}')
    (driver / "mcp-macos.json").write_text('{"tools": ["macos"]}')
    specs = ["cdb-g02-foreground|cdb-g02-r1-foreground|1", "mb-09-r4-background|mb-09-r4-background|4"]
    policy = {"setup_steps": list(SETUP), "reruns": {"rate": 6, "server": 3, "setup": 2}}
    image = {"image": "agentenv-macos-bench", "macos_build": "25F84"}
    monkeypatch.setattr(manifest, "_version", lambda name: "0.9.1412")
    monkeypatch.setattr(manifest, "_ec2", lambda item: "mac2-m2.metal")
    monkeypatch.setattr(manifest, "_checkout_commit", lambda name: "2d4ad6fe")

    store = tmp_path / "state" / "agent-env" / "document_store"
    store.mkdir(parents=True)
    base = {"id": "@local/agentenv-framework/computers/macos-26", "version": 1}
    built_at = {"status": "ready", "image": "local:agentenv-computer-72b0", "key": "sha256:72b0",
                "built_at": "2026-11-05T00:14:08+00:00", "probe": {"checks": {"passed": 49, "failed": 1}}}
    envs = [{"id": f"@local/~/{ROOT.name}/desktop-s02", "version": version, "computer": base,
             "metadata": {"composed": {"vm_bundle": {"arm64": {**built_at, "image": image_name}}}}}
            for version, image_name in ((1, "local:agentenv-computer-0ld0"), (2, "local:agentenv-computer-72b0"))]
    with manifest.sqlite3.connect(store / "local.db") as db:
        db.execute("create table docs_envs (doc text)")
        db.execute("create table docs_artifacts (doc text)")
        db.executemany("insert into docs_envs values (?)", [(json.dumps(env),) for env in envs])
        db.execute("insert into docs_artifacts values (?)", (json.dumps(
            {**base, "type": "computer", "forms": {"vm_bundle": {"image": "ghcr.io/trycua/macos:26@sha256:7cb2"}}}),))
    monkeypatch.setattr(manifest.Path, "home", lambda: ROOT.parent)

    built = manifest.build(ROOT, "run-1", "macos", "anthropic/claude-sonnet-5-5", specs, policy, tmp_path, image,
                           tmp_path / "state")

    lock = manifest.tomllib.loads((ROOT / "taskpack.lock.toml").read_text())
    assert built["task_pack"] == {"repo": "trycua/cua", "commit": lock["commit"], "sha256": lock["sha256"]}
    assert (built["os"], built["trials"], built["model"]) == ("macos", 2, "anthropic/claude-sonnet-5-5")
    assert built["tasks"] == ["cdb-g02-foreground", "mb-09-r4-background"]
    assert built["conditions"] == ["background", "foreground"]
    assert built["limits"] == [{"max_turns": 45, "timeout_s": 360}] and built["health_checks"] == policy
    s02 = built["computers"]["desktop-s02"]
    assert (s02["computer"], s02["driver"], s02["display"]) == ("ubuntu-24.04", "cua-driver",
                                                                {"width": 1920, "height": 1080})
    assert s02["tool_list_sha256"] == manifest.hashlib.sha256(b'{"tools": ["macos"]}').hexdigest()
    assert built["framework"]["commit"] == "2d4ad6fe"
    assert s02["composed"] == {"vm_bundle/arm64": {
        "image": "local:agentenv-computer-72b0", "key": "sha256:72b0", "built_at": "2026-11-05T00:14:08+00:00",
        "base": "ghcr.io/trycua/macos:26@sha256:7cb2", "probe": {"passed": 49, "failed": 1}}}
    assert built["computers"]["desktop-benchlab"]["composed"] is None
    assert built["bench"]["commit"] == manifest.subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                                               capture_output=True, text=True).stdout.strip()
    assert built["seeds"] == {"mb-09-r4-background": {"benchlab": 539937}}
    assert (built["image"], built["host"]["instance_type"]) == (image, "mac2-m2.metal")

    monkeypatch.setattr(manifest, "_version", lambda name: "0.9.1411")
    with pytest.raises(SystemExit, match="needs 0.9.1412 or later"):
        manifest.build(ROOT, "run-1", "macos", "anthropic/claude-sonnet-5-5", specs, policy, tmp_path)


def test_a_trial_whose_re_runs_are_spent_is_missing_and_its_record_reaches_the_dataset(worker, tmp_path, monkeypatch):
    uploaded = []
    monkeypatch.setattr(worker, "OUT", tmp_path / "out")
    monkeypatch.setattr(worker, "FLEET", tmp_path)
    monkeypatch.setattr(worker, "OS", "macos")
    api = type("Api", (), {"upload_folder": lambda self, **kw: uploaded.append(kw)})()
    (tmp_path / "out" / "cdb-g02-r1-foreground").mkdir(parents=True)
    (tmp_path / "out" / "cdb-g02-r1-foreground" / "trial.json").write_text("{}")

    worker._missing(api, "run-1", "cdb-g02-r1-foreground", "cdb-g02-foreground", 1, {"instance_id": "i-1"}, "setup",
                    {"rate": 0, "server": 0, "setup": 3}, 1)

    folder = tmp_path / "out" / "cdb-g02-r1-foreground"
    assert [p.name for p in folder.iterdir()] == ["missing.json"]
    record = json.loads((folder / "missing.json").read_text())
    assert (record["status"], record["kind"], record["harness_errors"]["setup"]) == ("missing", "setup", 3)
    assert uploaded[0]["path_in_repo"] == "runs/macos/run-1/cdb-g02-r1-foreground"
    progress = json.loads((tmp_path / "progress.jsonl").read_text())
    assert (progress["status"], progress["upload_error"]) == ("missing", None)


def test_setup_and_health_check_failures_are_re_run_twice_before_a_trial_is_missing(worker):
    assert worker.LIMITS == {"rate": 6, "server": 3, "setup": 2}
