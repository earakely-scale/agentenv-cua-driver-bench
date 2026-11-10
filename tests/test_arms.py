"""The arms beside cua-driver's, agent-desktop's, macos-harness's and codex-computer-use's on macOS, agent-desktop's
on Linux and Windows, and codex-computer-use's on Windows in the foreground: their computers and trials are cua-driver's twins but for the driver and the env ids, the computer/v1 tools
hidden from the agent so it runs on the arm's own, agent-desktop's foreground trials with its server headed, and
codex-computer-use's with Codex let act on the task's apps alone; their trial lists are the twins'; a trial is named as
its twin, its driver in the dataset; and the GUI-only check judges agent-desktop's launch as cua-driver's
launch_app."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARMS = ("agent-desktop", "macos-harness", "codex-computer-use")
ENVS = ("desktop-benchlab-macos", "desktop-s02-macos", "desktop-s03-macos", "desktop-s04-macos")
STEMS = list(dict.fromkeys((ROOT / "evals" / "macos-bench-v2-trials.txt").read_text().split()))
LINUX_ENVS = ("desktop-benchlab", "desktop-s02", "desktop-s03", "desktop-s04")
LINUX_STEMS = list(dict.fromkeys((ROOT / "evals" / "bench-v2-trials.txt").read_text().split()))
WINDOWS_ENVS = ("desktop-benchlab-windows", "desktop-s02-windows", "desktop-s03-windows", "desktop-s04-windows")
WINDOWS_STEMS = list(dict.fromkeys((ROOT / "evals" / "windows-bench-v2-trials.txt").read_text().split()))
#: Each arm and its twin's trials: macOS's for every arm, Linux's and Windows' for agent-desktop, and Windows' foreground
#: ones for codex-computer-use, which OpenAI runs on Windows only on the active desktop.
ARM_STEMS = [(arm, stem) for arm in ARMS for stem in STEMS] + [("agent-desktop", stem) for stem in LINUX_STEMS] + [
    ("agent-desktop", stem) for stem in WINDOWS_STEMS] + [
    ("codex-computer-use", stem) for stem in WINDOWS_STEMS if stem.endswith("-foreground")]
#: Every computer/v1 tool a driver can serve, its required ones and the pointer and keyboard groups: an arm's agent
#: runs on the arm's own tools, these hidden from it, while the grader and the recordings still use them.
#: The apps codex-computer-use's arm lets Codex act on in each computer, as macOS names them, and on Windows as Codex
#: shows them, since there an app's request names the program it runs from: the task's own, never the sentinel, the
#: user's window.
CODEX_APPS = {"desktop-benchlab-macos": ["BenchLab"],
              "desktop-s02-macos": ["Copperfield Mail", "Signal Quay Chat", "Daymark Calendar", "LibreOffice"],
              "desktop-s03-macos": ["Ledger Lantern Mail", "LibreOffice", "GnuCash"],
              "desktop-s04-macos": ["Rillwatch Cases", "Margin Lantern Manual", "Google Chrome for Testing"],
              "desktop-benchlab-windows": ["BenchLab"], "desktop-s02-windows": None, "desktop-s03-windows": None,
              "desktop-s04-windows": None}
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
    return f"{value}-{arm}" if value in ENVS + LINUX_ENVS + WINDOWS_ENVS else value


def _arm_stem(arm, stem):
    """The arm's trial of cua-driver's ``stem``, its OS's prefix first on macOS and Windows."""
    for prefix in ("macos-", "windows-"):
        if stem.startswith(prefix):
            return f"{prefix}{arm}-{stem.removeprefix(prefix)}"
    return f"{arm}-{stem}"


@pytest.mark.parametrize("arm, env", [(arm, env) for arm in ARMS for env in ENVS]
                         + [("agent-desktop", env) for env in LINUX_ENVS + WINDOWS_ENVS]
                         + [("codex-computer-use", env) for env in WINDOWS_ENVS])
def test_an_arms_computer_is_cua_drivers_but_for_its_driver(arm, env):
    twin = (ROOT / "envs" / env / "env.toml").read_text()

    assert (ROOT / "envs" / f"{env}-{arm}" / "env.toml").read_text() == twin.replace(
        'driver = "cua-driver"', f'driver = "{arm}"')


@pytest.mark.parametrize("arm, stem", ARM_STEMS)
def test_an_arms_trial_is_cua_drivers_on_its_computer_on_its_own_tools_with_its_drivers_settings(arm, stem):
    twin = _swapped(json.loads((ROOT / "tasks" / f"{stem}.json").read_text()), arm)
    trial = json.loads((ROOT / "tasks" / f"{_arm_stem(arm, stem)}.json").read_text())
    env = next(step for step in trial if step["id"] == "env")
    settings = env["env_params"].pop("driver_settings", None)
    hidden = trial.pop(next(n for n, step in enumerate(trial) if step["id"] == "arm_tools"))
    agent = next(step for step in trial if step["id"] == "agent")
    waits = agent["depends_on"]
    agent["depends_on"] = ["env"]

    assert trial == twin
    assert settings == _settings(arm, stem, env["env_id"].removesuffix(f"-{arm}"))
    assert hidden == {"id": "arm_tools", "type": "modify_env_tool_access", "env_id": env["env_id"], "action": "disable",
                      "role": "default", "tools": COMPUTER_TOOLS, "depends_on": ["env"]}
    assert waits == ["env", "arm_tools"]


def _settings(arm, stem, computer):
    """The driver settings an arm's trial deploys with: agent-desktop's server headed in the foreground, and Codex let
    act on the task's apps alone."""
    if arm == "codex-computer-use":
        return {"allowed_apps": CODEX_APPS[computer]}
    return {"headed": True} if arm == "agent-desktop" and stem.endswith("-foreground") else None


@pytest.mark.parametrize("arm", ARMS)
def test_an_arms_trial_lists_are_cua_drivers_and_its_benchlab_list_leaves_out_the_cdb_tasks(arm):
    twins = (ROOT / "evals" / "macos-bench-v2-trials.txt").read_text().split()
    every = (ROOT / "evals" / f"macos-{arm}-bench-v2-trials.txt").read_text().split()
    benchlab = (ROOT / "evals" / f"macos-{arm}-benchlab-trials.txt").read_text().split()

    assert every == [f"macos-{arm}-{stem.removeprefix('macos-')}" for stem in twins]
    assert benchlab == [stem for stem in every if "-cdb-" not in stem] and len(benchlab) == 60


def test_agent_desktops_linux_trial_list_is_cua_drivers():
    twins = (ROOT / "evals" / "bench-v2-trials.txt").read_text().split()

    assert (ROOT / "evals" / "agent-desktop-bench-v2-trials.txt").read_text().split() == [
        f"agent-desktop-{stem}" for stem in twins]


@pytest.mark.parametrize("kind", ["bench-v2", "benchlab"])
def test_agent_desktops_windows_trial_lists_are_cua_drivers(kind):
    twins = (ROOT / "evals" / f"windows-{kind}-trials.txt").read_text().split()

    assert (ROOT / "evals" / f"windows-agent-desktop-{kind}-trials.txt").read_text().split() == [
        f"windows-agent-desktop-{stem.removeprefix('windows-')}" for stem in twins]


@pytest.mark.parametrize("kind", ["bench-v2", "benchlab"])
def test_codex_computer_uses_windows_trial_lists_are_cua_drivers_foreground_ones_and_its_codex_clis_theirs(kind):
    twins = (ROOT / "evals" / f"windows-{kind}-trials.txt").read_text().split()
    every = (ROOT / "evals" / f"windows-codex-computer-use-{kind}-trials.txt").read_text().split()

    assert every == [f"windows-codex-computer-use-{stem.removeprefix('windows-')}" for stem in twins
                     if stem.endswith("-foreground")]
    assert (ROOT / "evals" / f"codex-windows-codex-computer-use-{kind}-trials.txt").read_text().split() == [
        f"codex-{stem}" for stem in every]


def test_an_arms_trial_is_named_as_its_twin_and_its_driver_reaches_the_dataset():
    plan = _module(ROOT / "tools" / "fleet" / "plan.py")
    tables = _module(ROOT / "tools" / "dataset" / "tables.py")
    export = _module(ROOT / "tools" / "dataset" / "export.py")
    stems = ["macos-agent-desktop-ir-01-r2-background", "macos-macos-harness-cdb-g02-foreground",
             "macos-macos-harness-cdb-g02-foreground", "macos-ir-01-r2-background", "agent-desktop-cdb-g03-foreground",
             "macos-codex-computer-use-mb-09-r4-foreground", "windows-agent-desktop-ir-02-r3-background"]

    named = [line for _, specs in plan.split(ROOT, stems, 10) for line in specs]
    assert [line.split("|")[1] for line in named] == ["ir-01-r2-background", "cdb-g02-r1-foreground",
                                                      "cdb-g02-r2-foreground", "ir-01-r2-background",
                                                      "cdb-g03-r1-foreground", "mb-09-r4-foreground",
                                                      "ir-02-r3-background"]
    assert [tables.STEM.match(stem)["driver"] for stem in stems[:-1]] == ["agent-desktop", "macos-harness",
                                                                          "macos-harness", None, "agent-desktop",
                                                                          "codex-computer-use"]
    assert export.STEM.match("windows-agent-desktop-ir-02-r3-background").group("task", "driver") == (
        "ir-02", "agent-desktop")
    for stem in ("windows-codex-computer-use-mb-09-r4-foreground", "codex-windows-codex-computer-use-mb-09-r4-foreground"):
        assert [line.split("|")[1] for line in plan.split(ROOT, [stem], 10)[0][1]] == ["mb-09-r4-foreground"]
        assert export.STEM.match(stem).group("task", "driver") == ("mb-09", "codex-computer-use")
    assert export.STEM.match("macos-agent-desktop-mb-10-r3-foreground").group("task", "driver") == (
        "mb-10", "agent-desktop")
    assert export.STEM.match("macos-codex-computer-use-cdb-g04-background").group("task", "driver") == (
        "cdb-g04", "codex-computer-use")
    assert [line.split("|")[1] for line in plan.split(ROOT, ["macos-cua-driver-mb-10-r3-foreground"], 10)[0][1]] == [
        "mb-10-r3-foreground"]
    assert export.STEM.match("macos-cua-driver-mb-10-r3-foreground").group("task", "driver") == ("mb-10", "cua-driver")
    assert not tables.STEM.match("macos-cua-driver-mb-10-r3-foreground")
    task = tables.task_row(ROOT, ROOT / "tasks" / "macos-agent-desktop-ir-01-r1-foreground.json")
    assert (task["driver"], task["computer"], task["os"]) == ("agent-desktop", "desktop-benchlab-macos-agent-desktop",
                                                             "macos")
    task = tables.task_row(ROOT, ROOT / "tasks" / "agent-desktop-ir-01-r1-foreground.json")
    assert (task["driver"], task["computer"], task["os"]) == ("agent-desktop", "desktop-benchlab-agent-desktop", "linux")


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


#: The macOS arms OpenAI's Codex CLI also runs, GPT through each driver as it ships, and the Windows one.
CODEX_ARMS = ("codex-computer-use", "cua-driver")
CODEX_STEMS = [stem for arm in CODEX_ARMS
               for stem in dict.fromkeys((ROOT / "evals" / f"macos-{arm}-bench-v2-trials.txt").read_text().split())] + list(
    dict.fromkeys((ROOT / "evals" / "windows-codex-computer-use-bench-v2-trials.txt").read_text().split()))


@pytest.mark.parametrize("stem", CODEX_STEMS)
def test_a_macos_or_windows_codex_cli_trial_is_its_claude_code_twin_but_for_the_agent_and_its_effort(stem):
    """As on Linux, the Codex CLI trials are Claude Code's but for the agent, its own tools all off, and the effort."""
    twin = json.loads((ROOT / "tasks" / f"{stem}.json").read_text())
    trial = json.loads((ROOT / "tasks" / f"codex-{stem}.json").read_text())
    agent, task = (next(step for step in trial if step["id"] == key) for key in ("agent", "task"))

    assert (agent.pop("a2a_agent_id"), agent.pop("builtin_tools"), task.pop("effort")) == ("codex", {"disable": "*"},
                                                                                           "medium")
    assert trial == [{k: v for k, v in step.items() if not (step["id"] == "agent" and k == "builtin_tools")}
                     for step in twin]


@pytest.mark.parametrize("arm", CODEX_ARMS)
def test_codex_clis_macos_trial_lists_are_claude_codes_and_its_trials_are_named_as_theirs(arm):
    plan = _module(ROOT / "tools" / "fleet" / "plan.py")
    export = _module(ROOT / "tools" / "dataset" / "export.py")
    tables = _module(ROOT / "tools" / "dataset" / "tables.py")
    for kind in ("bench-v2", "benchlab"):
        twins = (ROOT / "evals" / f"macos-{arm}-{kind}-trials.txt").read_text().split()
        assert (ROOT / "evals" / f"codex-macos-{arm}-{kind}-trials.txt").read_text().split() == [
            f"codex-{stem}" for stem in twins]
    stem = f"codex-macos-{arm}-ir-01-r2-background"

    assert [line.split("|")[1] for line in plan.split(ROOT, [stem], 10)[0][1]] == ["ir-01-r2-background"]
    assert export.STEM.match(stem).group("task", "driver") == ("ir-01", arm)
    assert not tables.STEM.match(stem)
