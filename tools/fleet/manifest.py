"""manifest.py BENCH RUN OS MODEL SPECS: the manifest of a run, written beside its trials as runs/OS/RUN/manifest.json:
every input that changes a score, pinned. That is the task pack and grader (trycua's commit and sha256), the framework
installed, the model and agent, each computer with its driver and the sha256 of that driver's tool list, the limits
and conditions the trials run under, and the policy that re-runs a trial infrastructure cut short."""
import hashlib
import json
import re
import sys
import tomllib
from datetime import datetime, timezone
from importlib import metadata, util
from pathlib import Path

CONDITION = re.compile(r"-(foreground|background)$")


def build(bench: Path, run: str, os_type: str, model: str, specs: list[str], policy: dict,
          drivers: Path | None) -> dict:
    """The manifest of ``run`` on ``os_type``: ``specs`` are its `stem|name|run` lines, ``policy`` the worker's setup
    steps and re-run limits, ``drivers`` the installed framework's driver folders (each with its mcp.json)."""
    lock = tomllib.loads((bench / "taskpack.lock.toml").read_text())
    stems = sorted({line.split("|")[0] for line in specs})
    tasks = {stem: {step["id"]: step for step in json.loads((bench / "tasks" / f"{stem}.json").read_text())}
             for stem in stems}
    envs = sorted({steps["env"]["env_id"] for steps in tasks.values()})
    return {
        "run": run,
        "os": os_type,
        "trials": len(specs),
        "task_pack": {"repo": lock["repo"], "commit": lock["commit"], "sha256": lock["sha256"]},
        "framework": {name: _version(name) for name in ("agentenv-framework", "agentenv-framework-protocol")},
        "model": model,
        "agents": sorted({steps["agent"].get("a2a_agent_id") or "default" for steps in tasks.values()}),
        "builtin_tools": _distinct(steps["agent"].get("builtin_tools") for steps in tasks.values()),
        "computers": {env: _computer(bench, env, drivers) for env in envs},
        "limits": _distinct({"max_turns": steps["task"].get("max_turns"),
                             "timeout_s": steps["task"].get("timeout_seconds")} for steps in tasks.values()),
        "conditions": sorted({CONDITION.search(stem)[1] for stem in stems if CONDITION.search(stem)}),
        "tasks": stems,
        "health_checks": policy,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }


def installed_drivers() -> Path | None:
    """The installed framework's driver folders, where each driver's pinned tool list is."""
    spec = util.find_spec("agent_env")
    return Path(spec.origin).parent / "drivers" / "envs" if spec and spec.origin else None


def _computer(bench: Path, env: str, drivers: Path | None) -> dict:
    spec = tomllib.loads((bench / "envs" / env / "env.toml").read_text())
    tools = drivers / spec["driver"] / "mcp.json" if drivers else None
    return {"computer": spec.get("computer"), "driver": spec.get("driver"), "display": spec.get("display"),
            "apps": spec.get("apps", []),
            "tool_list_sha256": hashlib.sha256(tools.read_bytes()).hexdigest() if tools and tools.is_file() else None}


def _distinct(values) -> list:
    """Each value once, in a fixed order."""
    return [json.loads(value) for value in sorted({json.dumps(value, sort_keys=True) for value in values})]


def _version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


if __name__ == "__main__":
    bench, run, os_type, model, specs = sys.argv[1:6]
    print(json.dumps(build(Path(bench), run, os_type, model, Path(specs).read_text().split(), {},
                           installed_drivers()), indent=1))
