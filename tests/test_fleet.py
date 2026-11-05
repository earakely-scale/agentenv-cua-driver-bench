"""The fleet's plan, its workers' gates and its runs' manifests, offline: Bench v2's 90 trials split into workers on
one computer each, each trial named with its run; a finished trial counted, or run again for a rate limit, an API
error or a failed setup, and recorded as missing once its re-runs are spent; and a run's manifest pinning each input
that changes a score."""
import hashlib
import importlib.util
import json
import sys
import types
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

    assert [env for env, _ in workers] == ["desktop-s02", "desktop-s03", "desktop-s04"] + ["desktop-benchlab"] * 6
    assert all(len(specs) == 10 for _, specs in workers)
    names = [line.split("|")[1] for _, specs in workers for line in specs]
    assert len(set(names)) == 90
    assert workers[0][1][:4] == [f"cdb-g02-foreground|cdb-g02-r{run}-foreground|{run}" for run in (1, 2, 3, 4)]
    assert "mb-09-r4-background|mb-09-r4-background|4" in [line for _, specs in workers for line in specs]


def test_a_plan_writes_each_workers_trials_and_the_whole_runs_for_its_manifest(plan, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(plan.sys, "argv", ["plan.py", str(ROOT / "evals" / "macos-bench-v2-trials.txt"), str(tmp_path),
                                           "24"])

    plan.main()

    workers = sorted(tmp_path.glob("worker-*.txt"))
    assert (tmp_path / "run.txt").read_text().split() == [line for f in workers for line in f.read_text().split()]
    assert len((tmp_path / "run.txt").read_text().split()) == 90


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
    platform_ = {"os": "macos", "version": "26.5.2", "arch": "arm64", "display": "aqua"}
    built_at = {"status": "ready", "image": "local:agentenv-computer-72b0", "key": "sha256:72b0",
                "built_at": "2026-11-05T00:14:08+00:00", "probe": {"checks": {"passed": 49, "failed": 1}},
                "card": {"capabilities": {"extensions": [{"params": {"platform": platform_}}]}}}
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

    harness = {"name": "claude-code", "versions": ["2.1.314"], "effort": None}
    built = manifest.build(ROOT, "run-1", "macos", "anthropic/claude-sonnet-5-5", specs, policy, tmp_path, image,
                           tmp_path / "state", harness)

    lock = manifest.tomllib.loads((ROOT / "taskpack.lock.toml").read_text())
    assert built["task_pack"] == {"repo": "trycua/cua", "commit": lock["commit"], "sha256": lock["sha256"]}
    assert (built["os"], built["trials"], built["model"]) == ("macos", 2, "anthropic/claude-sonnet-5-5")
    assert built["tasks"] == ["cdb-g02-foreground", "mb-09-r4-background"]
    assert built["conditions"] == ["background", "foreground"]
    assert built["limits"] == [{"max_turns": 45, "timeout_s": 360}] and built["health_checks"] == policy
    s02 = built["computers"]["desktop-s02"]
    assert (s02["computer"], s02["driver"], s02["display"]) == ("ubuntu-24.04", "cua-driver",
                                                                {"width": 1920, "height": 1080})
    assert s02["tool_list"] == "mcp-macos.json"
    assert s02["tool_list_sha256"] == manifest.hashlib.sha256(b'{"tools": ["macos"]}').hexdigest()
    assert built["framework"]["commit"] == "2d4ad6fe"
    assert s02["composed"] == {"vm_bundle/arm64": {
        "image": "local:agentenv-computer-72b0", "key": "sha256:72b0", "built_at": "2026-11-05T00:14:08+00:00",
        "base": "ghcr.io/trycua/macos:26@sha256:7cb2", "probe": {"passed": 49, "failed": 1}, "platform": platform_}}
    assert built["harness"] == harness
    assert built["computers"]["desktop-benchlab"]["composed"] is None
    assert built["bench"]["commit"] == manifest.subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                                               capture_output=True, text=True).stdout.strip()
    assert built["seeds"] == {"mb-09-r4-background": {"benchlab": 539937}}
    assert (built["image"], built["host"]["instance_type"]) == (image, "mac2-m2.metal")

    monkeypatch.setattr(manifest, "_version", lambda name: "0.9.1411")
    with pytest.raises(SystemExit, match="needs 0.9.1412 or later"):
        manifest.build(ROOT, "run-1", "macos", "anthropic/claude-sonnet-5-5", specs, policy, tmp_path)


def test_on_an_ec2_mac_the_host_type_is_read_through_apples_curl_which_local_network_privacy_lets_through(
        manifest, monkeypatch):
    def unreachable(*args, **kwargs):
        raise OSError("No route to host")
    calls = []

    def curl(argv, **kwargs):
        calls.append(argv)
        return manifest.subprocess.CompletedProcess(argv, 0, "token" if "PUT" in argv else "mac2-m2.metal", "")
    monkeypatch.setattr(manifest.urllib.request, "urlopen", unreachable)
    monkeypatch.setattr(manifest.subprocess, "run", curl)
    monkeypatch.setattr(manifest.platform, "system", lambda: "Linux")
    assert manifest._ec2("instance-type") is None and not calls

    monkeypatch.setattr(manifest.platform, "system", lambda: "Darwin")
    assert manifest._ec2("instance-type") == "mac2-m2.metal"
    assert [argv[0] for argv in calls] == ["/usr/bin/curl", "/usr/bin/curl"]
    assert calls[1][-2:] == ["X-aws-ec2-metadata-token: token", "http://169.254.169.254/latest/meta-data/instance-type"]


def test_a_workers_manifest_pins_the_whole_run_and_keeps_what_other_workers_uploaded(worker, tmp_path, monkeypatch):
    uploaded = []
    monkeypatch.setattr(worker, "OUT", tmp_path / "out")
    monkeypatch.setattr(worker, "FLEET", tmp_path)
    monkeypatch.setattr(worker, "BENCH", ROOT)
    monkeypatch.setattr(worker, "OS", "macos")
    monkeypatch.setattr(worker, "DB", tmp_path / "state" / "agent-env" / "document_store" / "local.db")
    monkeypatch.setattr(worker.manifest, "_version", lambda name: "0.9.1443")
    run = ["macos-mb-09-r1-foreground|mb-09-r1-foreground|1", "macos-cdb-g02-background|cdb-g02-r1-background|1"]
    (tmp_path / "run-specs.txt").write_text("\n".join(run) + "\n")
    (tmp_path / "out" / "mb-09-r1-foreground").mkdir(parents=True)
    (tmp_path / "out" / "mb-09-r1-foreground" / "trial.json").write_text('{"harness_version": "2.1.314"}')
    theirs = {"vm_bundle/arm64": {"image": "local:agentenv-computer-372a"}}
    monkeypatch.setattr(worker, "_uploaded", lambda run: {
        "computers": {"desktop-s02-macos": {"composed": theirs}}, "harness": {"versions": ["2.1.300"]}})
    api = type("Api", (), {"upload_file": lambda self, **kw: uploaded.append(kw)})()

    worker._upload_manifest(api, "run-1", ["mb-09-r1-foreground"])

    written = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert written["trials"] == 2 and set(written["computers"]) == {"desktop-benchlab-macos", "desktop-s02-macos"}
    assert written["computers"]["desktop-s02-macos"]["composed"] == theirs
    assert written["harness"] == {"name": "claude-code", "versions": ["2.1.300", "2.1.314"], "effort": None}
    assert uploaded[0]["path_in_repo"] == "runs/macos/run-1/manifest.json"


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


@pytest.fixture
def board(monkeypatch):
    """board.py with a stand-in for common, whose ssm records each script and answers from ``board.common.replies``:
    by instance, a reply, a function of the script, or an exception to raise."""
    common = types.ModuleType("common")
    common.ROOT, common.scripts, common.replies = ROOT, [], {}

    def ssm(instance, script, timeout=300, os_type="linux"):
        common.scripts.append((instance, script))
        reply = common.replies[instance]
        if isinstance(reply, BaseException):
            raise reply
        return reply(script) if callable(reply) else reply
    common.ssm = ssm
    monkeypatch.setitem(sys.modules, "common", common)
    monkeypatch.syspath_prepend(str(ROOT / "tools" / "fleet"))
    loaded = _module(ROOT / "tools" / "fleet" / "board.py")
    loaded.common = common
    return loaded


def _worker(board, run, computer, n):
    return board.Worker(f"{run}/{computer}", run, "m", computer, [f"{computer}-stem|t{i}|1" for i in range(n)])


def test_a_board_keeps_each_computers_workers_on_one_host_and_splits_a_computer_only_past_a_hosts_share(board):
    workers = [_worker(board, "sonnet", "lab", 20), _worker(board, "haiku", "lab", 20),
               *(_worker(board, "sonnet", computer, 10) for computer in ("s02", "s03", "s04"))]
    hosts = board.assign(workers, [board.Host("b4", "i-4"), board.Host("b5", "i-5")])

    assert {h.name: [w.id for w in h.workers] for h in hosts} == {
        "b4": ["sonnet/lab", "haiku/lab"], "b5": ["sonnet/s02", "sonnet/s03", "sonnet/s04"]}
    labs = [_worker(board, run, "lab", 35) for run in ("a", "b", "c", "d")]
    split = board.assign([*labs, _worker(board, "e", "s02", 10)], [board.Host("b4", "i-4"), board.Host("b5", "i-5")])
    assert [([w.id for w in h.workers], h.load) for h in split] == [(["a/lab", "b/lab", "e/s02"], 80),
                                                                    (["c/lab", "d/lab"], 70)]


def test_a_boards_runs_are_planned_as_plan_py_plans_them_each_worker_one_computer(board):
    workers, runs = board.planned({"per": 35, "run": [
        {"name": "mh", "model": "m", "trials": "evals/macos-macos-harness-benchlab-trials.txt"}]})

    assert [(w.id, w.computer, len(w.specs)) for w in workers] == [
        ("mh/01", "desktop-benchlab-macos-macos-harness", 35), ("mh/02", "desktop-benchlab-macos-macos-harness", 25)]
    assert runs["mh"] == workers[0].specs + workers[1].specs and len(runs["mh"]) == 60


def _peek(running, digest="", ended=0, framework=None, failed=0):
    return (f"running={int(running)}\ndigest={digest}\nended={ended}\nfailed={failed}\n"
            + (f"framework={framework}\n" if framework else "") + "log=last line\n")


def _runner(board, tmp_path, monkeypatch, hosts, started=None, **settings):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        out = started.pop(0) if started else "started"
        return types.SimpleNamespace(returncode=0, stdout=out + "\n", stderr="")
    monkeypatch.setattr(board.subprocess, "run", run)
    monkeypatch.setattr(board.time, "time", lambda: 1000.0)
    runner = board.Runner({"os": "macos", **settings}, hosts, tmp_path, tmp_path / "b.state.json", tmp_path / "b.log")
    return runner, calls


def test_a_host_runs_its_workers_one_after_another_and_never_starts_one_twice(board, tmp_path, monkeypatch):
    first, second = _worker(board, "r", "lab", 2), _worker(board, "r", "s02", 1)
    host = board.Host("b4", "i-4", workers=[first, second])
    runner, calls = _runner(board, tmp_path, monkeypatch, [host])
    replies = board.common.replies

    replies["i-4"] = _peek(False)
    runner.poll(host)
    replies["i-4"] = _peek(True, first.digest, 1)
    runner.poll(host)
    again = board.Runner(runner.board, [host], tmp_path, runner.state_path, runner.log)
    again.poll(host)
    replies["i-4"] = _peek(False, first.digest, 2)
    again.poll(host)

    assert [argv[2:5] for argv in calls] == [["i-4", "r", "m"], ["i-4", "r", "m"]]
    assert [a[-1] for a in calls] == ["--fresh", "--fresh"] and calls[1][5].endswith("r--s02.txt")
    state = json.loads((tmp_path / "b.state.json").read_text())
    assert (state["r/lab"]["status"], state["r/s02"]["status"]) == ("done", "started")
    assert "b4 ended r/lab: 2 trials; last line" in (tmp_path / "b.log").read_text()


def test_an_unreachable_host_and_a_failed_start_drop_nothing_and_a_short_worker_resumes_then_fails(
        board, tmp_path, monkeypatch):
    worker = _worker(board, "r", "lab", 3)
    host = board.Host("b4", "i-4", workers=[worker])
    runner, calls = _runner(board, tmp_path, monkeypatch, [host], started=["Error: SSM throttled", "started"])
    replies = board.common.replies

    replies["i-4"] = SystemExit("i-4: Failed: could not connect")
    runner.poll(host)
    replies["i-4"] = _peek(False)
    runner.poll(host)
    runner.poll(host)
    for ended in (1, 2, 2):
        replies["i-4"] = _peek(False, worker.digest, ended)
        runner.poll(host)

    log = (tmp_path / "b.log").read_text()
    assert "b4 couldn't be asked: i-4: Failed: could not connect" in log
    assert "b4 couldn't start r/lab: ['Error: SSM throttled']; trying again" in log
    assert [a[-1] for a in calls] == ["--fresh", "--fresh", "macos", "macos"]
    assert json.loads((tmp_path / "b.state.json").read_text())["r/lab"]["status"] == "failed"
    assert "b4 r/lab failed: 2 of 3 trials" in log


def test_a_worker_whose_trials_failed_their_export_exports_just_those_again_from_their_task_instances(
        board, tmp_path, monkeypatch):
    worker = _worker(board, "r", "lab", 2)
    host = board.Host("b4", "i-4", workers=[worker])
    runner, calls = _runner(board, tmp_path, monkeypatch, [host])
    progress = "\n".join(json.dumps(record) for record in (
        {"name": "t0", "stem": "lab-stem", "run_index": 1, "status": "uploaded", "instance": "inst-0"},
        {"name": "t1", "stem": "lab-stem", "run_index": 1, "status": "export_failed", "instance": "inst-1"}))
    again = hashlib.sha256(b"lab-stem|t1|1|inst-1\n").hexdigest()
    replies = board.common.replies

    replies["i-4"] = _peek(False)
    runner.poll(host)
    replies["i-4"] = lambda script: progress if script.startswith("cat ") else _peek(False, worker.digest, 2, failed=1)
    runner.poll(host)
    replies["i-4"] = _peek(True, again, 0)
    runner.poll(host)
    replies["i-4"] = _peek(False, again, 1)
    runner.poll(host)

    assert len(calls) == 2 and calls[1][5].endswith("r--lab--reexport-1.txt") and calls[1][-1] == "--fresh"
    assert (tmp_path / "r--lab--reexport-1.txt").read_text() == "lab-stem|t1|1|inst-1\n"
    assert json.loads((tmp_path / "b.state.json").read_text())["r/lab"]["status"] == "done"
    log = (tmp_path / "b.log").read_text()
    assert "b4 r/lab: 1 trial not uploaded; exporting it again (1/2)" in log and "b4 ended r/lab: 1 trials;" in log


def test_an_idle_host_moves_to_its_framework_pin_before_its_next_worker(board, tmp_path, monkeypatch):
    worker = _worker(board, "r", "lab", 1)
    host = board.Host("b4", "i-4", framework="e1afb200", workers=[worker])
    runner, calls = _runner(board, tmp_path, monkeypatch, [host], venv="~/b1/venv-ae", framework_checkout="~/b1/ae")
    pinned = "e1afb200aaaabbbbccccddddeeeeffff00001111"
    board.common.replies["i-4"] = lambda script: (pinned + "\n" if "git checkout" in script
                                                  else _peek(False, framework="bc0c9d67" + "0" * 32))

    runner.poll(host)
    board.common.replies["i-4"] = _peek(False, framework=pinned)
    runner.poll(host)

    assert any("git checkout -q -f e1afb200" in script for _, script in board.common.scripts)
    assert host.framework == pinned and len(calls) == 1
    assert "b4 pinned to e1afb200aaaa" in (tmp_path / "b.log").read_text()
