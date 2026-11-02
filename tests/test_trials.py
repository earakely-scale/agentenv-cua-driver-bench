"""The trials ``python tools/taskpack.py tasks`` writes from the fetched task pack: each GUI-only task in both of
trycua's conditions, prompted as trycua's runner prompts it and within its time and turns, with the sentinel in that
condition, claude-code with only the computer env's tools and trycua's system prompt for Linux, the sentinel armed just
around the prompt, and the grade, which runs whatever became of the agent; git-ignored, since they hold trycua's
text."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import taskpack  # noqa: E402

PACK = ROOT / "artifacts" / "taskpack"


@pytest.fixture
def trials(tmp_path):
    if not (PACK / "MANIFEST.sha256").exists():
        pytest.skip("the task pack isn't fetched: python tools/taskpack.py")
    taskpack.tasks(taskpack.read_lock(), folder=tmp_path)
    return lambda name: {step["id"]: step for step in json.loads((tmp_path / f"{name}.json").read_text())}


def test_a_background_trial_prompts_as_trycua_and_arms_the_user_window_just_around_the_agent(trials):
    trial = trials("cdb-g02-background")
    brief = (PACK / "taskpack/tasks/shared/cdb-s02/brief.md").read_text().strip()

    assert trial["env"]["env_id"] == "desktop-s02"
    assert trial["env"]["env_params"] == {"app_settings": {"bench-sentinel": {"condition": "background"}}}
    assert trial["agent"]["builtin_tools"] == {"only": ["Skill"]}
    assert trial["task"]["prompt"].startswith(brief) and "`/home/user/cdb-s02`" in trial["task"]["prompt"]
    assert '"User activity"' in trial["task"]["prompt"] and trial["task"]["timeout_seconds"] == 360
    assert "a Linux desktop" in trial["agent"]["system_prompt"] and "macOS" not in trial["agent"]["system_prompt"]
    assert (trial["arm"]["args"], trial["disarm"]["args"]) == (
        {"action": "arm", "condition": "background"}, {"action": "disarm"})
    assert (trial["task"]["max_turns"], trial["task"]["fail_task_on_error"], trial["disarm"]["fail_task_on_error"]) == (
        45, False, False)
    assert (trial["task"]["depends_on"], trial["disarm"]["depends_on"], trial["grade"]["depends_on"]) == (
        ["arm"], ["task"], ["disarm"])
    assert (trial["grade"]["file_artifact_id"], trial["grade"]["prompt_id"]) == ("grade", "task")


def test_each_gui_only_task_has_a_trial_in_each_condition(trials):
    for probe, env in (("cdb-g02", "desktop-s02"), ("cdb-g03", "desktop-s03"), ("cdb-g04", "desktop-s04")):
        foreground = trials(f"{probe}-foreground")
        assert foreground["env"]["env_id"] == env
        assert foreground["env"]["env_params"]["app_settings"]["bench-sentinel"]["condition"] == "foreground"
        assert "User activity" not in foreground["task"]["prompt"]


def test_the_trials_are_git_ignored():
    ignored = subprocess.run(["git", "check-ignore", "tasks/cdb-g02-background.json", "tasks/cdb-g04-foreground.json"],
                             cwd=ROOT, capture_output=True, text=True)

    assert ignored.stdout.split() == ["tasks/cdb-g02-background.json", "tasks/cdb-g04-foreground.json"]
