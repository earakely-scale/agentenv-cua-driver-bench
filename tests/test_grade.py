"""The bench's grade in its container, offline, on a trial staged as the trial's snapshot is (each app's files under
``trial/<app>/``) and trycua's task pack as fetched: trycua's evaluator runs on the task's workspace, here the task's
untouched one, which fails, or one trycua's own tests solve; the sentinel's log must show the whole trial; GUI-only
fails on a violation the guard logged or DevTools opened while armed; the background condition adds trycua's A22
criteria, the foreground none; and a solved trial that left the user undisturbed in the GUI is a background
completion, with a reward of 1. A BenchLab trial is graded by trycua's evaluator for its probe on BenchLab's state and
events, with the run's seed: the interruption handled as trycua's own tests handle it passes, another answer fails, and
missing data or another seed's fails closed."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_sentinel import OTHER, Run, sentinel_module  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"
TASKS = PACK / "taskpack" / "tasks" / "shared"
TASK = TASKS / "cdb-s02"
NODE = pytest.mark.skipif(not shutil.which("node"), reason="trycua's cdb-s04 evaluator serves its site with node")
LAB = "IR-01"


@pytest.fixture
def grader():
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    spec = importlib.util.spec_from_file_location("bench_grade", ROOT / "artifacts" / "grader" / "grade.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _solved(scratch, task="cdb-s02"):
    """The task's workspace as trycua's own tests of their evaluator solve it."""
    name = task.replace("-", "_")
    spec = importlib.util.spec_from_file_location(f"trycua_test_{name}", TASKS / task / "tests" / f"test_{name}.py")
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    scratch.mkdir()
    workspace = tests.Workspace(scratch)
    workspace.complete()
    return workspace.root


def _staged(tmp_path, run, condition="background", solved=False, edit=None, devtools=(), task="cdb-s02"):
    """A trial's snapshot as load_artifact stages it in the grading container."""
    trial = tmp_path / "trial"
    workspace = trial / task / task
    if solved:
        shutil.copytree(_solved(tmp_path / "solving", task), workspace)
    else:
        subprocess.run([sys.executable, "reset/setup.py", "--workspace", str(workspace)], cwd=TASKS / task, check=True)
    return _sentinel(trial, run, condition, edit, devtools)


def _sentinel(trial, run, condition="background", edit=None, devtools=()):
    sentinel = trial / "bench-sentinel" / ".bench-sentinel"
    sentinel.mkdir(parents=True)
    lines = [json.loads(line) for line in run.lines]
    if condition is not None:
        lines[0]["condition"] = condition
    (sentinel / "sentinel.jsonl").write_text("".join(json.dumps(line) + "\n" for line in (edit or (lambda x: x))(lines)))
    if devtools:
        (sentinel / "devtools.jsonl").write_text("".join(json.dumps(
            {"ev": "devtools_opened", "t": t, "title": "Copperfield Mail"}) + "\n" for t in devtools))
    return trial


def _results(grader, tmp_path, run, task="cdb-s02", **staged):
    trial = _staged(tmp_path, run, task=task, **staged)
    return {result["id"]: result for result in grader.grade(task, trial, PACK, tmp_path)}


def test_an_untouched_workspace_fails_trycuas_evaluator_and_a_quiet_trial_holds_the_rest(grader, sentinel_module,
                                                                                         tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module).trial())

    assert results["task"]["result"] is False and results["task"]["checks"]["mail_preserved"] is True
    failed = [name for name, passed in results["task"]["checks"].items() if not passed]
    assert failed and all(results["task"]["check_details"][name] for name in failed)
    assert results["sentinel"]["result"] is True and results["gui_only"] == {**results["gui_only"], "result": True,
                                                                              "violations": []}
    assert results["user_undisturbed"]["result"] is True and results["user_undisturbed"]["unmeasured"] == []
    assert results["user_undisturbed"]["background_completion"] is False


@pytest.mark.parametrize("task", ["cdb-s02", "cdb-s03", pytest.param("cdb-s04", marks=NODE)])
def test_a_solved_trial_that_left_the_user_undisturbed_in_the_gui_is_a_background_completion(grader, sentinel_module,
                                                                                             tmp_path, task):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), task=task, solved=True)

    assert results["task"]["result"] is True and results["task"]["score"] == 1.0
    assert all(result["result"] for result in results.values())
    assert results["user_undisturbed"]["background_completion"] is True


def test_a_solved_trial_that_took_the_users_focus_is_not_a_background_completion(grader, sentinel_module, tmp_path):
    def steal(run):
        run.desktop.active_window = run.desktop.focus_window = OTHER
        run.sentinel.focus_changed(False)
        run.sentinel.changed("active", OTHER)

    results = _results(grader, tmp_path, Run(sentinel_module).trial(steal), solved=True)

    assert results["task"]["result"] is True and results["gui_only"]["result"] is True
    assert results["user_undisturbed"]["result"] is False
    assert {key for key, held in results["user_undisturbed"]["criteria"].items() if not held} == {
        "key_focus", "typing", "activation"}


def test_a_violation_the_guard_logged_fails_gui_only(grader, sentinel_module, tmp_path):
    run = Run(sentinel_module)
    run.trial(lambda run: run.processes.append((50, "xterm", 0)))

    assert _results(grader, tmp_path, run)["gui_only"]["violations"] == ["process:xterm"]


@pytest.mark.parametrize("after_arming_ms, violations", [(-1000, []), (500, ["devtools:Copperfield Mail"])],
                         ids=["before arming", "while armed"])
def test_an_electron_apps_devtools_opened_while_armed_fails_gui_only(grader, sentinel_module, tmp_path, after_arming_ms,
                                                                     violations):
    run = Run(sentinel_module).trial()
    armed = next(line["t"] for line in map(json.loads, run.lines) if line["ev"] == "armed")

    assert _results(grader, tmp_path, run, devtools=[armed + after_arming_ms])["gui_only"]["violations"] == violations


@pytest.mark.parametrize("edit, problem", [
    (lambda lines: [line for line in lines if line["ev"] != "disarmed"], "stopped before it was disarmed"),
    (lambda lines: [line for line in lines if line["ev"] != "armed" and not line["armed"]], "never armed"),
    (lambda lines: [*lines[:-2], {"ev": "sample_error", "t": lines[-2]["t"], "armed": True, "error": "BadAtom"},
                    *lines[-2:]], "a sample failed: BadAtom"),
], ids=["not disarmed", "never armed", "a sample failed"])
def test_a_log_that_doesnt_show_the_whole_trial_fails_the_grade(grader, sentinel_module, tmp_path, edit, problem):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), edit=edit)

    assert results["sentinel"]["result"] is False and any(problem in p for p in results["sentinel"]["problems"])
    assert results["gui_only"]["result"] is False and results["user_undisturbed"]["result"] is False


def test_a_sentinel_without_a_condition_fails_the_grade(grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module).trial(), condition=None)

    assert results["sentinel"]["problems"] == ["the sentinel's condition is None"]


def test_the_users_window_asked_to_close_disturbs_the_user(grader, sentinel_module, tmp_path):
    run = Run(sentinel_module).trial(lambda run: run.sentinel.emit("close_refused"))

    undisturbed = _results(grader, tmp_path, run)["user_undisturbed"]

    assert undisturbed["result"] is False and undisturbed["close_refused"] == 1


def test_the_foreground_has_no_a22_result(grader, sentinel_module, tmp_path):
    results = _results(grader, tmp_path, Run(sentinel_module, background=False).trial(), condition="foreground")

    assert set(results) == {"sentinel", "task", "gui_only"}


@pytest.mark.parametrize("solved, reward", [(True, "1\n"), (False, "0\n")], ids=["solved", "untouched"])
def test_the_grade_writes_its_results_and_a_reward_the_verifier_scores(grader, sentinel_module, tmp_path, monkeypatch,
                                                                       solved, reward):
    trial = _staged(tmp_path, Run(sentinel_module).trial(), solved=solved)
    monkeypatch.setattr(grader, "TRIAL", trial)
    monkeypatch.setattr(grader, "TRYCUA", PACK)
    monkeypatch.setattr(grader, "OUT", tmp_path)

    grader.main([])

    assert (tmp_path / "reward.txt").read_text() == reward
    assert json.loads((tmp_path / "result.json").read_text())["task"] == "cdb-s02"


def test_the_grading_image_has_the_node_cdb_s04_pins():
    dockerfile = (ROOT / "artifacts" / "grader" / "grader.Dockerfile").read_text()
    node = next(line for line in (ROOT / "envs" / "cdb-s04" / "bench_app.py").read_text().splitlines()
                if line.startswith("NODE = "))

    assert f"FROM node:{node.split(chr(34))[1].split('.')[0]}-bookworm@sha256:" in dockerfile


def _seed(run=1):
    return _module(PACK / "runner" / "bench_core.py").probe_seed(LAB, run - 1)


def _lab(tmp_path, run, seed, answer="deny", data=True):
    """A BenchLab trial's snapshot: IR-01's state and events as trycua's own tests write a run that answers its
    permission prompt with ``answer``, and the sentinel's log."""
    trial = tmp_path / "trial"
    if data:
        folder = trial / "benchlab" / ".benchlab"
        folder.mkdir(parents=True)
        interrupts = _module(PACK / "probes" / "tests" / "test_interrupts.py")
        interrupts.S.write_files(folder, *interrupts.irmodal_run(seed, answer=answer))
    return _sentinel(trial, run)


def _lab_results(grader, tmp_path, run, seed, graded_seed=None, **lab):
    trial = _lab(tmp_path, run, seed, **lab)
    return {result["id"]: result for result in grader.grade(LAB, trial, PACK, tmp_path, graded_seed or seed)}


def test_a_benchlab_trial_handled_as_trycuas_tests_handle_it_is_a_background_completion(grader, sentinel_module,
                                                                                       tmp_path):
    results = _lab_results(grader, tmp_path, Run(sentinel_module).trial(), _seed())

    assert results["task"]["result"] is True and results["task"]["score"] == 1.0
    assert {"permission_denied", "fields_submitted", "integrity"} <= set(results["task"]["checks"])
    assert set(results["task"]["check_details"]["permission_denied"]) == {"weight", "detail"}
    assert results["user_undisturbed"]["background_completion"] is True


@pytest.mark.parametrize("lab, graded_seed, failed", [
    ({"answer": "allow"}, None, "permission_denied"),
    ({"data": False}, None, "inputs_loadable"),
    ({}, 1, "integrity"),
], ids=["access granted", "no BenchLab data", "another seed"])
def test_a_benchlab_trial_fails_trycuas_evaluator_on_another_answer_missing_data_or_another_seed(
        grader, sentinel_module, tmp_path, lab, graded_seed, failed):
    task = _lab_results(grader, tmp_path, Run(sentinel_module).trial(), _seed(), graded_seed, **lab)["task"]

    assert task["result"] is False and task["checks"][failed] is False


def test_the_grade_of_a_benchlab_trial_takes_its_probe_and_seed(grader, sentinel_module, tmp_path, monkeypatch):
    trial = _lab(tmp_path, Run(sentinel_module).trial(), _seed())
    monkeypatch.setattr(grader, "TRIAL", trial)
    monkeypatch.setattr(grader, "TRYCUA", PACK)
    monkeypatch.setattr(grader, "OUT", tmp_path)

    grader.main([LAB, str(_seed())])

    assert (tmp_path / "reward.txt").read_text() == "1\n"
    assert json.loads((tmp_path / "result.json").read_text())["task"] == LAB


def _module(path):
    spec = importlib.util.spec_from_file_location(f"bench_test_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
