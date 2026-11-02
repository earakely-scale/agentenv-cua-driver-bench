"""The trials of the bench's GUI-only tasks, trycua's Bench v2, each in both of trycua's conditions: prompted as
trycua's runner prompts them, with the task's brief (a CDB task's with its workspace, a BenchLab task's rendered from
the run's seed), in the background their background brief, and the time and turns they tell the agent, and with their
system prompt for a Linux desktop, a browser task's allowing its localhost site, all checked against the fetched task
pack; with the sentinel in that condition and BenchLab in the task's mode with the run's seed, claude-code with no
built-in tools but Skill and Read, the sentinel armed just around the prompt within the task's time and turns; its
grade, whatever became of the agent: in a container of its own with no network, on the trial's snapshot, and the
trajectory's half outside; and the whole of Bench v2 in trycua's schedule."""
import ast
import importlib.util
import json
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"
TRIALS = {"cdb-g02": "cdb-s02", "cdb-g03": "cdb-s03", "cdb-g04": "cdb-s04"}
LABS = ("MB-09", "MB-10", "MB-11", "IR-01", "IR-02", "IR-03", "IR-04")
RUNS = (1, 2, 3, 4, 5)
CONDITIONS = ("background", "foreground")
EVERY = (*TRIALS, *(f"{probe.lower()}-r{run}" for probe in LABS for run in RUNS))


def _trial(name, condition):
    return {step["id"]: step for step in json.loads((ROOT / "tasks" / f"{name}-{condition}.json").read_text())}


@pytest.fixture
def trycua():
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    return _module(PACK / "scoring" / "bench_v2.py")


@pytest.mark.parametrize("probe", TRIALS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_trial_is_prompted_as_trycuas_runner_prompts_it(trycua, probe, condition):
    task = TRIALS[probe]
    brief = (PACK / "taskpack/tasks/shared" / task / "brief.md").read_text().replace(
        "configured `cua` MCP server", "configured computer-use MCP server").strip()
    limits = json.loads((PACK / "probes" / probe.upper() / "task.json").read_text())
    trial = _trial(probe, condition)

    assert trial["task"]["prompt"] == _prompt(trycua, f"{brief}\n\nYour workspace directory is `/home/user/{task}`.",
                                              condition, limits)
    assert trial["agent"]["system_prompt"] == _system(limits)
    assert (trial["task"]["timeout_seconds"], trial["task"]["max_turns"]) == (limits["timeout_s"], limits["max_turns"])


@pytest.mark.parametrize("probe", LABS)
@pytest.mark.parametrize("run", RUNS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_benchlab_trial_is_seeded_and_prompted_as_trycuas_runner_does_it(trycua, probe, run, condition):
    seed = _module(PACK / "runner" / "bench_core.py").probe_seed(probe, run - 1)
    limits = json.loads((PACK / "probes" / probe / "task.json").read_text())
    brief = _module(PACK / "probes" / probe / "render_brief.py").render(seed)
    trial = _trial(f"{probe.lower()}-r{run}", condition)

    assert trial["env"]["env_params"]["app_settings"]["benchlab"] == {
        "mode": limits["app_args"][limits["app_args"].index("--mode") + 1], "seed": seed}
    assert trial["task"]["prompt"] == _prompt(trycua, brief, condition, limits)
    assert trial["agent"]["system_prompt"] == _system(limits)
    assert (trial["task"]["timeout_seconds"], trial["task"]["max_turns"]) == (limits["timeout_s"], limits["max_turns"])
    assert trial["grade"]["command"] == f"python3 /grade/grade.py {probe} {seed}"


def test_trycuas_runner_prompts_with_the_brief_in_its_condition_and_tells_the_time_and_turns(trycua):
    runner = (PACK / "runner" / "run_bench.py").read_text()

    assert 'prompt = (v2.brief_for(brief.strip(), condition) if bench_v2 else brief.strip()) + "\\n"' in runner
    assert 'prompt += f"\\nYou have about {timeout_s // 60} minutes and at most {max_turns} turns.\\n"' in runner
    assert 'p.add_argument("--tell-budget", action=argparse.BooleanOptionalAction, default=True)' in runner


@pytest.mark.parametrize("name", EVERY)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_trial_arms_the_sentinel_in_its_condition_just_around_the_agent_and_grades_it(name, condition):
    trial = _trial(name, condition)
    env = f"desktop-{TRIALS[name].removeprefix('cdb-')}" if name in TRIALS else "desktop-benchlab"

    assert trial["env"]["env_id"] == env
    assert trial["env"]["env_params"]["app_settings"]["bench-sentinel"] == {"condition": condition}
    assert set(trial["env"]["env_params"]["app_settings"]) == ({"bench-sentinel"} if name in TRIALS
                                                               else {"bench-sentinel", "benchlab"})
    assert trial["agent"]["env_ids"] == [env] and trial["agent"]["builtin_tools"] == {"only": ["Skill", "Read"]}
    assert {trial[step]["env_id"] for step in ("record", "arm", "disarm", "snapshot", "gui_only")} == {env}
    assert (trial["arm"]["args"], trial["disarm"]["args"]) == ({"action": "arm", "condition": condition},
                                                               {"action": "disarm"})
    assert (trial["task"]["depends_on"], trial["disarm"]["depends_on"], trial["snapshot"]["depends_on"]) == (
        ["arm"], ["task"], ["disarm"])
    assert trial["task"]["fail_task_on_error"] is False and trial["disarm"]["fail_task_on_error"] is False


@pytest.mark.parametrize("name", EVERY)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_trial_is_graded_in_a_sandbox_of_its_own_with_no_network_and_its_trajectory_outside(name, condition):
    trial = _trial(name, condition)
    container = {"sandbox_name": "grader", "container_name": "grade"}

    assert trial["box"]["network"] == "none" and trial["box"]["docker_context_artifact_id"] == "grader"
    assert {key: trial["pack"][key] for key in (*container, "artifact_id")} == {**container, "artifact_id": "taskpack"}
    assert {key: trial["trial"][key] for key in (*container, "artifact_from_step_id")} == {
        **container, "artifact_from_step_id": "snapshot"}
    assert trial["snapshot"]["env_id"] == trial["env"]["env_id"]
    assert trial["grade"]["type"] == "run_container_unit_tests_verifier"
    assert {key: trial["grade"][key] for key in (*container, "reward_path")} == {**container,
                                                                                "reward_path": "/grade/reward.txt"}
    assert trial["grade"]["command"].split()[:2] == ["python3", "/grade/grade.py"]
    assert (trial["gui_only"]["type"], trial["gui_only"]["file_artifact_id"], trial["gui_only"]["prompt_id"]) == (
        "env_outcome_verifier", "gui_only", "task")


def test_bench_v2_is_each_task_five_runs_in_each_condition_in_trycuas_schedule(trycua):
    """trycua's schedule: the v2 tasks in order, runs 1 to 3, then runs 4 and 5, a whole run in one condition. A CDB
    task's runs are one task file, its seed unused; the eval runs each task file once, and a condition's eval its half."""
    trials = (ROOT / "evals" / "bench-v2-trials.txt").read_text().split()
    expected = [f"{task.lower()}-{condition}" if task.startswith("CDB-") else f"{task.lower()}-r{run}-{condition}"
                for condition in ("foreground", "background") for runs in ((1, 2, 3), (4, 5))
                for task in trycua.V2_TASKS for run in runs]

    assert trials == expected and len(trials) == 100
    assert all((ROOT / "tasks" / f"{name}.json").is_file() for name in trials)
    assert tomllib.loads((ROOT / "evals" / "bench-v2.toml").read_text())["tasks"] == list(dict.fromkeys(trials))
    for condition in ("foreground", "background"):
        assert tomllib.loads((ROOT / "evals" / f"{condition}.toml").read_text())["tasks"] == [
            name for name in dict.fromkeys(trials) if name.endswith(f"-{condition}")]


def _prompt(v2, brief, condition, limits):
    """The prompt as trycua's runner builds it: the brief in its condition, then the time and turns, which it tells by
    default."""
    return (v2.brief_for(brief.strip(), condition) + "\n"
            + f"\nYou have about {limits['timeout_s'] // 60} minutes and at most {limits['max_turns']} turns.\n")


def _system(limits):
    runner = ast.parse((PACK / "runner" / "claude_arms.py").read_text())
    [macos] = [ast.literal_eval(node.value) for node in runner.body if isinstance(node, ast.Assign)
               and any(getattr(target, "id", None) == "MACOS_SYSTEM_PROMPT" for target in node.targets)]
    system = macos.replace("a macOS desktop", "a Linux desktop")
    if limits.get("browser"):
        system = system.replace("Do not use the network.", "Do not use the internet; the task's localhost site is allowed.")
    return system


def _module(path):
    spec = importlib.util.spec_from_file_location(f"trycua_{path.parent.name}_{path.stem}".replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
