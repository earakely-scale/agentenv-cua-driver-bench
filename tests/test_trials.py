"""The trials of the bench's GUI-only tasks, each in both of trycua's conditions: prompted as trycua's runner prompts
them, with the task's brief, its workspace and, in the background, their background brief, and with their system
prompt for a Linux desktop, all checked against the fetched task pack; with the sentinel in that condition,
claude-code with no built-in tools but Skill and Read, the sentinel armed just around the prompt within the task's time and
turns; and its grade, whatever became of the agent: in a container of its own with no network, on the trial's snapshot,
and the trajectory's half outside."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "artifacts" / "taskpack"
TRIALS = {"cdb-g02": "cdb-s02", "cdb-g03": "cdb-s03", "cdb-g04": "cdb-s04"}
CONDITIONS = ("background", "foreground")


def _trial(probe, condition):
    return {step["id"]: step for step in json.loads((ROOT / "tasks" / f"{probe}-{condition}.json").read_text())}


@pytest.fixture
def trycua():
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    spec = importlib.util.spec_from_file_location("trycua_bench_v2", PACK / "scoring" / "bench_v2.py")
    bench_v2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench_v2)
    return bench_v2


@pytest.mark.parametrize("probe", TRIALS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_trial_is_prompted_as_trycuas_runner_prompts_it(trycua, probe, condition):
    task = TRIALS[probe]
    brief = (PACK / "taskpack/tasks/shared" / task / "brief.md").read_text().replace(
        "configured `cua` MCP server", "configured computer-use MCP server").strip()
    expected = trycua.brief_for(f"{brief}\n\nYour workspace directory is `/home/user/{task}`.", condition)
    runner = ast.parse((PACK / "runner" / "claude_arms.py").read_text())
    [system] = [ast.literal_eval(node.value) for node in runner.body if isinstance(node, ast.Assign)
                and any(getattr(target, "id", None) == "SYSTEM_PROMPT" for target in node.targets)]
    limits = json.loads((PACK / "probes" / probe.upper() / "task.json").read_text())
    trial = _trial(probe, condition)

    assert trial["task"]["prompt"] == expected
    assert trial["agent"]["system_prompt"] == system.replace("a macOS desktop", "a Linux desktop")
    assert (trial["task"]["timeout_seconds"], trial["task"]["max_turns"]) == (limits["timeout_s"], limits["max_turns"])


@pytest.mark.parametrize("probe", TRIALS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_trial_arms_the_sentinel_in_its_condition_just_around_the_agent_and_grades_it(probe, condition):
    trial = _trial(probe, condition)
    env = f"desktop-{TRIALS[probe].removeprefix('cdb-')}"

    assert trial["env"]["env_id"] == env
    assert trial["env"]["env_params"] == {"app_settings": {"bench-sentinel": {"condition": condition}}}
    assert trial["agent"]["env_ids"] == [env] and trial["agent"]["builtin_tools"] == {"only": ["Skill", "Read"]}
    assert (trial["arm"]["args"], trial["disarm"]["args"]) == ({"action": "arm", "condition": condition},
                                                               {"action": "disarm"})
    assert (trial["task"]["depends_on"], trial["disarm"]["depends_on"], trial["snapshot"]["depends_on"]) == (
        ["arm"], ["task"], ["disarm"])
    assert trial["task"]["fail_task_on_error"] is False and trial["disarm"]["fail_task_on_error"] is False


@pytest.mark.parametrize("probe", TRIALS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_trial_is_graded_in_a_sandbox_of_its_own_with_no_network_and_its_trajectory_outside(probe, condition):
    trial = _trial(probe, condition)
    container = {"sandbox_name": "grader", "container_name": "grade"}

    assert trial["box"]["network"] == "none" and trial["box"]["docker_context_artifact_id"] == "grader"
    assert {key: trial["pack"][key] for key in (*container, "artifact_id")} == {**container, "artifact_id": "taskpack"}
    assert {key: trial["trial"][key] for key in (*container, "artifact_from_step_id")} == {
        **container, "artifact_from_step_id": "snapshot"}
    assert trial["snapshot"]["env_id"] == trial["env"]["env_id"]
    assert trial["grade"]["type"] == "run_container_unit_tests_verifier"
    assert {key: trial["grade"][key] for key in (*container, "command", "reward_path")} == {
        **container, "command": "python3 /grade/grade.py", "reward_path": "/grade/reward.txt"}
    assert (trial["gui_only"]["type"], trial["gui_only"]["file_artifact_id"], trial["gui_only"]["prompt_id"]) == (
        "env_outcome_verifier", "gui_only", "task")
