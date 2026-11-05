"""The macOS arms beside cua-driver's: agent-desktop's and macos-harness's computers and trials are cua-driver's twins
but for the driver and the env ids, the computer/v1 tools hidden from the agent so it runs on the arm's own, and
agent-desktop's foreground trials with its server headed; their trial lists are the
twins'; a trial is named as its twin, its driver in the dataset; and the GUI-only check judges agent-desktop's launch
as cua-driver's launch_app."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARMS = ("agent-desktop", "macos-harness")
ENVS = ("desktop-benchlab-macos", "desktop-s02-macos", "desktop-s03-macos", "desktop-s04-macos")
STEMS = list(dict.fromkeys((ROOT / "evals" / "macos-bench-v2-trials.txt").read_text().split()))
#: Every computer/v1 tool a driver can serve, its required ones and the pointer and keyboard groups: an arm's agent
#: runs on the arm's own tools, these hidden from it, while the grader and the recordings still use them.
COMPUTER_TOOLS = ["computer_click", "computer_drag", "computer_key", "computer_keyboard_down", "computer_keyboard_up",
                  "computer_pointer_down", "computer_pointer_list", "computer_pointer_move", "computer_pointer_position",
                  "computer_pointer_up", "computer_screenshot", "computer_scroll", "computer_type", "computer_wait"]


def _module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _swapped(value, arm):
    if isinstance(value, dict):
        return {k: _swapped(v, arm) for k, v in value.items()}
    if isinstance(value, list):
        return [_swapped(v, arm) for v in value]
    return f"{value}-{arm}" if value in ENVS else value


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("env", ENVS)
def test_an_arms_computer_is_cua_drivers_but_for_its_driver(arm, env):
    twin = (ROOT / "envs" / env / "env.toml").read_text()

    assert (ROOT / "envs" / f"{env}-{arm}" / "env.toml").read_text() == twin.replace(
        'driver = "cua-driver"', f'driver = "{arm}"')


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("stem", STEMS)
def test_an_arms_trial_is_cua_drivers_on_its_computer_on_its_own_tools_agent_desktop_headed_in_the_foreground(arm,
                                                                                                             stem):
    twin = _swapped(json.loads((ROOT / "tasks" / f"{stem}.json").read_text()), arm)
    trial = json.loads((ROOT / "tasks" / f"macos-{arm}-{stem.removeprefix('macos-')}.json").read_text())
    env = next(step for step in trial if step["id"] == "env")
    headed = env["env_params"].pop("driver_settings", None)
    hidden = trial.pop(next(n for n, step in enumerate(trial) if step["id"] == "arm_tools"))
    agent = next(step for step in trial if step["id"] == "agent")
    waits = agent["depends_on"]
    agent["depends_on"] = ["env"]

    assert trial == twin
    assert headed == ({"headed": True} if arm == "agent-desktop" and stem.endswith("-foreground") else None)
    assert hidden == {"id": "arm_tools", "type": "modify_env_tool_access", "env_id": env["env_id"], "action": "disable",
                      "role": "default", "tools": COMPUTER_TOOLS, "depends_on": ["env"]}
    assert waits == ["env", "arm_tools"]


@pytest.mark.parametrize("arm", ARMS)
def test_an_arms_trial_lists_are_cua_drivers_and_its_benchlab_list_leaves_out_the_cdb_tasks(arm):
    twins = (ROOT / "evals" / "macos-bench-v2-trials.txt").read_text().split()
    every = (ROOT / "evals" / f"macos-{arm}-bench-v2-trials.txt").read_text().split()
    benchlab = (ROOT / "evals" / f"macos-{arm}-benchlab-trials.txt").read_text().split()

    assert every == [f"macos-{arm}-{stem.removeprefix('macos-')}" for stem in twins]
    assert benchlab == [stem for stem in every if "-cdb-" not in stem] and len(benchlab) == 60


def test_an_arms_trial_is_named_as_its_twin_and_its_driver_reaches_the_dataset():
    plan = _module(ROOT / "tools" / "fleet" / "plan.py")
    tables = _module(ROOT / "tools" / "dataset" / "tables.py")
    export = _module(ROOT / "tools" / "dataset" / "export.py")
    stems = ["macos-agent-desktop-ir-01-r2-background", "macos-macos-harness-cdb-g02-foreground",
             "macos-macos-harness-cdb-g02-foreground", "macos-ir-01-r2-background"]

    named = [line for _, specs in plan.split(ROOT, stems, 10) for line in specs]
    assert [line.split("|")[1] for line in named] == ["ir-01-r2-background", "cdb-g02-r1-foreground",
                                                      "cdb-g02-r2-foreground", "ir-01-r2-background"]
    assert [tables.STEM.match(stem)["driver"] for stem in stems] == ["agent-desktop", "macos-harness",
                                                                     "macos-harness", None]
    assert export.STEM.match("macos-agent-desktop-mb-10-r3-foreground").group("task", "driver") == (
        "mb-10", "agent-desktop")
    assert [line.split("|")[1] for line in plan.split(ROOT, ["macos-cua-driver-mb-10-r3-foreground"], 10)[0][1]] == [
        "mb-10-r3-foreground"]
    assert export.STEM.match("macos-cua-driver-mb-10-r3-foreground").group("task", "driver") == ("mb-10", "cua-driver")
    assert not tables.STEM.match("macos-cua-driver-mb-10-r3-foreground")
    task = tables.task_row(ROOT, ROOT / "tasks" / "macos-agent-desktop-ir-01-r1-foreground.json")
    assert (task["driver"], task["computer"], task["os"]) == ("agent-desktop", "desktop-benchlab-macos-agent-desktop",
                                                             "macos")


@pytest.mark.parametrize("stem", STEMS)
def test_cua_drivers_trial_on_its_own_tools_is_its_twin_with_the_computer_tools_hidden(stem):
    twin = json.loads((ROOT / "tasks" / f"{stem}.json").read_text())
    trial = json.loads((ROOT / "tasks" / f"macos-cua-driver-{stem.removeprefix('macos-')}.json").read_text())
    hidden = trial.pop(next(n for n, step in enumerate(trial) if step["id"] == "arm_tools"))
    agent = next(step for step in trial if step["id"] == "agent")
    waits = agent["depends_on"]
    agent["depends_on"] = ["env"]

    assert trial == twin and waits == ["env", "arm_tools"]
    assert hidden == {"id": "arm_tools", "type": "modify_env_tool_access", "env_id": next(
        step for step in twin if step["id"] == "env")["env_id"], "action": "disable", "role": "default",
        "tools": COMPUTER_TOOLS, "depends_on": ["env"]}
    assert (ROOT / "evals" / "macos-cua-driver-bench-v2-trials.txt").read_text().split() == [
        f"macos-cua-driver-{s.removeprefix('macos-')}" for s in (ROOT / "evals" / "macos-bench-v2-trials.txt").read_text().split()]
