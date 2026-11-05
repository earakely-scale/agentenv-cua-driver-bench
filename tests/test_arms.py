"""The macOS arms beside cua-driver's: agent-desktop's and macos-harness's computers and trials are cua-driver's twins
but for the driver and the env ids, agent-desktop's foreground trials with its server headed; their trial lists are the
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
def test_an_arms_trial_is_cua_drivers_on_its_computer_agent_desktop_headed_in_the_foreground(arm, stem):
    twin = _swapped(json.loads((ROOT / "tasks" / f"{stem}.json").read_text()), arm)
    trial = json.loads((ROOT / "tasks" / f"macos-{arm}-{stem.removeprefix('macos-')}.json").read_text())
    env = next(step for step in trial if step["id"] == "env")
    headed = env["env_params"].pop("driver_settings", None)

    assert trial == twin
    assert headed == ({"headed": True} if arm == "agent-desktop" and stem.endswith("-foreground") else None)


@pytest.mark.parametrize("arm", ARMS)
def test_an_arms_trial_lists_are_cua_drivers_and_its_benchlab_list_leaves_out_the_cdb_tasks(arm):
    twins = (ROOT / "evals" / "macos-bench-v2-trials.txt").read_text().split()
    every = (ROOT / "evals" / f"macos-{arm}-bench-v2-trials.txt").read_text().split()
    benchlab = (ROOT / "evals" / f"macos-{arm}-benchlab-trials.txt").read_text().split()

    assert every == [f"macos-{arm}-{stem.removeprefix('macos-')}" for stem in twins]
    assert benchlab == [stem for stem in every if "-cdb-" not in stem] and len(benchlab) == 70


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
    task = tables.task_row(ROOT, ROOT / "tasks" / "macos-agent-desktop-ir-01-r1-foreground.json")
    assert (task["driver"], task["computer"], task["os"]) == ("agent-desktop", "desktop-benchlab-macos-agent-desktop",
                                                             "macos")
