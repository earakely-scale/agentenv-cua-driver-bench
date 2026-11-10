"""The trials of the bench's GUI-only tasks, trycua's Bench v2, each in both of trycua's conditions: prompted as
trycua's runner prompts them, with the task's brief (a CDB task's with its workspace, a BenchLab task's rendered from
the run's seed), in the background their background brief, and the time and turns they tell the agent, and with their
system prompt for a Linux desktop, a browser task's allowing its localhost site, all checked against the fetched task
pack; on macOS the same but on its macOS computers with their system prompt as it is; on Windows the same on its
Windows computers with their system prompt for a Windows desktop, a CDB task's workspace at the Windows home and a
BenchLab brief as their Windows runner words it, BenchLab in the trial's condition too; on Omarchy BenchLab's trials
alone, on its Omarchy computer with their system prompt for a Linux desktop, a brief as their Hyprland runner words it
and BenchLab in the trial's condition too; with the sentinel in that condition and BenchLab in the
task's mode with the run's seed, claude-code with no built-in tools but Skill and Read, the sentinel armed just
around the prompt within the task's time and turns; its grade, whatever became of the agent: in a container of its
own with no network, on the trial's snapshot, and the trajectory's half outside; and the whole of Bench v2 in
trycua's schedule, MB-10 and MB-11 in the foreground alone; on Omarchy its BenchLab trials in that order."""
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
#: The tasks run in the foreground alone: a real hover and a native tooltip need the pointer, in the background the
#: user's.
FOREGROUND_ONLY = ("MB-10", "MB-11")
LAB_TRIALS = tuple(f"{probe.lower()}-r{run}" for probe in LABS for run in RUNS)
LAB_CELLS = tuple((probe, run, condition) for probe in LABS for run in RUNS for condition in CONDITIONS
                  if not (condition == "background" and probe in FOREGROUND_ONLY))
EVERY = tuple((name, os, condition) for os in ("linux", "macos", "windows", "omarchy")
              for name in (LAB_TRIALS if os == "omarchy" else (*TRIALS, *LAB_TRIALS))
              for condition in CONDITIONS if not (condition == "background" and name[:5].upper() in FOREGROUND_ONLY))
#: Where each OS's computer keeps a task's workspace, its session user's home, and how a path there is joined.
HOMES = {"linux": "/home/user", "macos": "/Users/lume", "windows": "C:\\Users\\user"}
SEPARATORS = {"windows": "\\"}
OSES = ("linux", "macos", "windows")
#: The OSes of BenchLab's trials: every OS's, and Omarchy's, which has BenchLab's trials alone.
LAB_OSES = (*OSES, "omarchy")
#: How trycua's Windows and Hyprland runners word a BenchLab brief, which says Mac on every other OS.
PLATFORM_WORDS = {"windows": ("on your Mac", "on this Windows PC"), "omarchy": ("on your Mac", "on this Linux computer")}
#: Where the BenchLab app reads the trial's condition.
LAB_CONDITION = ("windows", "omarchy")


def _trial(name, condition, os="linux"):
    prefix = "" if os == "linux" else f"{os}-"
    return {step["id"]: step for step in json.loads((ROOT / "tasks" / f"{prefix}{name}-{condition}.json").read_text())}


@pytest.fixture
def trycua():
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    return _module(PACK / "scoring" / "bench_v2.py")


@pytest.mark.parametrize("os", OSES)
@pytest.mark.parametrize("probe", TRIALS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_each_trial_is_prompted_as_trycuas_runner_prompts_it(trycua, probe, condition, os):
    task = TRIALS[probe]
    brief = (PACK / "taskpack/tasks/shared" / task / "brief.md").read_text().replace(
        "configured `cua` MCP server", "configured computer-use MCP server").strip()
    limits = json.loads((PACK / "probes" / probe.upper() / "task.json").read_text())
    trial = _trial(probe, condition, os)

    assert trial["task"]["prompt"] == _prompt(
        trycua, f"{brief}\n\nYour workspace directory is `{HOMES[os]}{SEPARATORS.get(os, '/')}{task}`.", condition,
        limits)
    assert trial["agent"]["system_prompt"] == _system(limits, os)
    assert (trial["task"]["timeout_seconds"], trial["task"]["max_turns"]) == (limits["timeout_s"], limits["max_turns"])


@pytest.mark.parametrize("os", LAB_OSES)
@pytest.mark.parametrize(("probe", "run", "condition"), LAB_CELLS)
def test_each_benchlab_trial_is_seeded_and_prompted_as_trycuas_runner_does_it(trycua, probe, run, condition, os):
    seed = _module(PACK / "runner" / "bench_core.py").probe_seed(probe, run - 1)
    limits = json.loads((PACK / "probes" / probe / "task.json").read_text())
    brief = _module(PACK / "probes" / probe / "render_brief.py").render(seed)
    brief = brief.replace(*PLATFORM_WORDS[os]) if os in PLATFORM_WORDS else brief
    trial = _trial(f"{probe.lower()}-r{run}", condition, os)

    assert trial["env"]["env_params"]["app_settings"]["benchlab"] == {
        "mode": limits["app_args"][limits["app_args"].index("--mode") + 1], "seed": seed,
        **({"condition": condition} if os in LAB_CONDITION else {})}
    assert trial["task"]["prompt"] == _prompt(trycua, brief, condition, limits)
    assert trial["agent"]["system_prompt"] == _system(limits, os)
    assert (trial["task"]["timeout_seconds"], trial["task"]["max_turns"]) == (limits["timeout_s"], limits["max_turns"])
    assert trial["grade"]["command"] == f"python3 /grade/grade.py {probe} {seed}"


def test_omarchys_brief_is_worded_as_trycuas_hyprland_runner_words_it():
    session = ast.parse((PACK / "launch" / "hyprland_session.py").read_text())
    [words] = [ast.literal_eval(node.value) for node in session.body if isinstance(node, ast.Assign)
               and any(getattr(target, "id", None) == "PLATFORM_WORDS" for target in node.targets)]

    assert PLATFORM_WORDS["omarchy"] == words


def test_trycuas_runner_prompts_with_the_brief_in_its_condition_and_tells_the_time_and_turns(trycua):
    runner = (PACK / "runner" / "run_bench.py").read_text()

    assert 'prompt = (v2.brief_for(brief.strip(), condition) if bench_v2 else brief.strip()) + "\\n"' in runner
    assert 'prompt += f"\\nYou have about {timeout_s // 60} minutes and at most {max_turns} turns.\\n"' in runner
    assert 'p.add_argument("--tell-budget", action=argparse.BooleanOptionalAction, default=True)' in runner


@pytest.mark.parametrize(("name", "os", "condition"), EVERY)
def test_each_trial_arms_the_sentinel_in_its_condition_just_around_the_agent_and_grades_it(name, os, condition):
    trial = _trial(name, condition, os)
    env = f"desktop-{TRIALS[name].removeprefix('cdb-')}" if name in TRIALS else "desktop-benchlab"
    env = env if os == "linux" else f"{env}-{os}"

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


@pytest.mark.parametrize(("name", "os", "condition"), EVERY)
def test_each_trial_is_graded_in_a_sandbox_of_its_own_with_no_network_and_its_trajectory_outside(name, os, condition):
    trial = _trial(name, condition, os)
    container = {"sandbox_name": "grader", "container_name": "grade"}

    assert trial["box"]["network"] == "none" and trial["box"]["docker_context_artifact_id"] == "grader"
    assert trial["sandbox"].get("sandbox_type") == ("local" if os == "macos" else None)
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


def test_bench_v2_is_each_task_five_runs_in_each_of_its_conditions_in_trycuas_schedule(trycua):
    """trycua's schedule: the v2 tasks in order, runs 1 to 3, then runs 4 and 5, a whole run in one condition, MB-10
    and MB-11 in the foreground alone, with no background task file. A CDB task's runs are one task file, its seed
    unused; the eval runs each task file once, and a condition's eval its half. On macOS and on Windows, the same
    trials in the same order, and on Windows its BenchLab trials alone too; on Omarchy its BenchLab trials alone."""
    trials = (ROOT / "evals" / "bench-v2-trials.txt").read_text().split()
    expected = [f"{task.lower()}-{condition}" if task.startswith("CDB-") else f"{task.lower()}-r{run}-{condition}"
                for condition in ("foreground", "background") for runs in ((1, 2, 3), (4, 5))
                for task in trycua.V2_TASKS for run in runs
                if not (condition == "background" and task in FOREGROUND_ONLY)]

    assert trials == expected and len(trials) == 90
    assert not [p.name for p in (ROOT / "tasks").glob("*-background.json")
                if any(f"-{task.lower()}-r" in f"-{p.stem}" for task in FOREGROUND_ONLY)]
    assert all((ROOT / "tasks" / f"{name}.json").is_file() for name in trials)
    assert tomllib.loads((ROOT / "evals" / "bench-v2.toml").read_text())["tasks"] == list(dict.fromkeys(trials))
    for condition in ("foreground", "background"):
        assert tomllib.loads((ROOT / "evals" / f"{condition}.toml").read_text())["tasks"] == [
            name for name in dict.fromkeys(trials) if name.endswith(f"-{condition}")]
    assert (ROOT / "evals" / "codex-bench-v2-trials.txt").read_text().split() == [f"codex-{name}" for name in trials]
    macos = (ROOT / "evals" / "macos-bench-v2-trials.txt").read_text().split()
    assert macos == [f"macos-{name}" for name in trials]
    assert all((ROOT / "tasks" / f"{name}.json").is_file() for name in macos)
    assert tomllib.loads((ROOT / "evals" / "macos-bench-v2.toml").read_text())["tasks"] == list(dict.fromkeys(macos))
    windows = (ROOT / "evals" / "windows-bench-v2-trials.txt").read_text().split()
    assert windows == [f"windows-{name}" for name in trials]
    assert all((ROOT / "tasks" / f"{name}.json").is_file() for name in windows)
    assert tomllib.loads((ROOT / "evals" / "windows-bench-v2.toml").read_text())["tasks"] == list(dict.fromkeys(windows))
    assert (ROOT / "evals" / "windows-benchlab-trials.txt").read_text().split() == [
        name for name in windows if not name.startswith("windows-cdb-")]
    omarchy = (ROOT / "evals" / "omarchy-benchlab-trials.txt").read_text().split()
    assert omarchy == [f"omarchy-{name}" for name in trials if not name.startswith("cdb-")]
    assert all((ROOT / "tasks" / f"{name}.json").is_file() for name in omarchy)
    assert {path.stem for path in (ROOT / "tasks").glob("omarchy-*-r?-*.json")} == set(omarchy)


@pytest.mark.parametrize("path", sorted((ROOT / "tasks").glob("codex-*.json")), ids=lambda path: path.stem)
def test_each_codex_trial_is_its_linux_twin_with_codex_as_the_agent_its_own_tools_off_at_medium_effort(path):
    """GPT runs on Codex, the agent `codex` ships: the trial is its Linux twin's but for the agent, whose own tools
    (shell, patch, web search, sub-agents) are off, leaving the computer env's, and the effort it asks for."""
    codex = {step["id"]: step for step in json.loads(path.read_text())}
    twin = {step["id"]: step for step in json.loads(path.with_name(path.name.removeprefix("codex-")).read_text())}
    agent = twin["agent"]

    assert list(codex) == list(twin)
    assert {k: v for k, v in codex.items() if k not in ("agent", "task")} == {
        k: v for k, v in twin.items() if k not in ("agent", "task")}
    assert codex["agent"] == {"id": "agent", "type": "deploy_agent", "a2a_agent_id": "codex",
                              "env_ids": agent["env_ids"], "builtin_tools": {"disable": "*"},
                              "system_prompt": agent["system_prompt"], "depends_on": agent["depends_on"]}
    assert codex["task"] == {**twin["task"], "effort": "medium"}


def test_every_linux_trial_has_its_codex_twin():
    trials = set((ROOT / "evals" / "bench-v2-trials.txt").read_text().split())
    agent_desktop = (ROOT / "evals" / "agent-desktop-bench-v2-trials.txt").read_text().split()

    linux = {path.stem for path in (ROOT / "tasks").glob("codex-*.json")
             if not path.stem.startswith(("codex-macos-", "codex-windows-"))}

    assert linux == {f"codex-{name}" for name in trials | set(agent_desktop)}
    assert (ROOT / "evals" / "codex-agent-desktop-bench-v2-trials.txt").read_text().split() == [
        f"codex-{name}" for name in agent_desktop]


def test_every_windows_trial_has_its_codex_twin_and_their_lists_are_its():
    windows = (ROOT / "evals" / "windows-bench-v2-trials.txt").read_text().split()
    twins = {path.stem for path in (ROOT / "tasks").glob("codex-windows-*.json")
             if not path.stem.startswith("codex-windows-codex-computer-use-")}

    assert twins == {f"codex-{name}" for name in windows}
    for kind in ("bench-v2", "benchlab"):
        assert (ROOT / "evals" / f"codex-windows-{kind}-trials.txt").read_text().split() == [
            f"codex-{name}" for name in (ROOT / "evals" / f"windows-{kind}-trials.txt").read_text().split()]


def _prompt(v2, brief, condition, limits):
    """The prompt as trycua's runner builds it: the brief in its condition, then the time and turns, which it tells by
    default."""
    return (v2.brief_for(brief.strip(), condition) + "\n"
            + f"\nYou have about {limits['timeout_s'] // 60} minutes and at most {limits['max_turns']} turns.\n")


def _system(limits, os="linux"):
    runner = ast.parse((PACK / "runner" / "claude_arms.py").read_text())
    [macos] = [ast.literal_eval(node.value) for node in runner.body if isinstance(node, ast.Assign)
               and any(getattr(target, "id", None) == "MACOS_SYSTEM_PROMPT" for target in node.targets)]
    system = {"linux": macos.replace("a macOS desktop", "a Linux desktop"),
              "omarchy": macos.replace("a macOS desktop", "a Linux desktop"),
              "windows": macos.replace("a macOS desktop", "a Windows desktop")}.get(os, macos)
    if limits.get("browser"):
        system = system.replace("Do not use the network.", "Do not use the internet; the task's localhost site is allowed.")
    return system


def _module(path):
    spec = importlib.util.spec_from_file_location(f"trycua_{path.parent.name}_{path.stem}".replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
