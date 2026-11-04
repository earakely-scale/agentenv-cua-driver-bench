"""manifest.py BENCH RUN OS MODEL SPECS [--image FILE]: the manifest of a run, written beside its trials as
runs/OS/RUN/manifest.json: every input that changes a score, pinned. That is the task pack and grader (trycua's commit
and sha256), the framework installed, the model and agent, each computer with its driver and the sha256 of that
driver's tool list, the image the computers boot (FILE, the JSON identity the image records, such as a macOS image's
/etc/agentenv/image.json), the host, the limits, conditions and seeds the trials run under, and the policy that
re-runs a trial infrastructure cut short. It refuses a framework older than FRAMEWORK_FLOOR."""
import argparse
import hashlib
import json
import platform
import re
import tomllib
import urllib.request
from datetime import datetime, timezone
from importlib import metadata, util
from pathlib import Path

CONDITION = re.compile(r"-(foreground|background)$")
#: The oldest agentenv-framework whose verifiers are handed the graded prompt's trajectory, which gui_only reads.
FRAMEWORK_FLOOR = (0, 9, 1412)


def build(bench: Path, run: str, os_type: str, model: str, specs: list[str], policy: dict,
          drivers: Path | None, image: dict | None = None) -> dict:
    """The manifest of ``run`` on ``os_type``: ``specs`` are its `stem|name|run` lines, ``policy`` the worker's setup
    steps and re-run limits, ``drivers`` the installed framework's driver folders (each with its mcp.json), ``image``
    the identity of the image the computers boot, where it records one."""
    framework = {name: _version(name) for name in ("agentenv-framework", "agentenv-framework-protocol")}
    _require_floor(framework["agentenv-framework"])
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
        "framework": framework,
        "model": model,
        "agents": sorted({steps["agent"].get("a2a_agent_id") or "default" for steps in tasks.values()}),
        "builtin_tools": _distinct(steps["agent"].get("builtin_tools") for steps in tasks.values()),
        "computers": {env: _computer(bench, env, drivers) for env in envs},
        "image": image,
        "host": {"platform": platform.platform(), "instance_type": _ec2("instance-type")},
        "limits": _distinct({"max_turns": steps["task"].get("max_turns"),
                             "timeout_s": steps["task"].get("timeout_seconds")} for steps in tasks.values()),
        "conditions": sorted({CONDITION.search(stem)[1] for stem in stems if CONDITION.search(stem)}),
        "tasks": stems,
        "seeds": {stem: seeds for stem, steps in tasks.items() if (seeds := _seeds(steps["env"]))},
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


def _seeds(env_step: dict) -> dict:
    """Each app's seed, of the apps the env step seeds."""
    settings = env_step.get("env_params", {}).get("app_settings") or {}
    return {app: config["seed"] for app, config in settings.items() if isinstance(config, dict) and "seed" in config}


def _require_floor(version: str | None) -> None:
    found = re.match(r"(\d+)\.(\d+)\.(\d+)", version or "")
    if not found or tuple(map(int, found.groups())) < FRAMEWORK_FLOOR:
        raise SystemExit(f"agentenv-framework {version or 'is not installed'}: the bench needs "
                         f"{'.'.join(map(str, FRAMEWORK_FLOOR))} or later, whose verifiers get the graded trajectory")


def _ec2(item: str) -> str | None:
    """``item`` of this host's EC2 instance metadata, or None off EC2."""
    base = "http://169.254.169.254/latest"
    try:
        put = urllib.request.Request(f"{base}/api/token", method="PUT",
                                     headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        token = urllib.request.urlopen(put, timeout=1).read().decode()
        get = urllib.request.Request(f"{base}/meta-data/{item}", headers={"X-aws-ec2-metadata-token": token})
        return urllib.request.urlopen(get, timeout=1).read().decode()
    except OSError:
        return None


def _distinct(values) -> list:
    """Each value once, in a fixed order."""
    return [json.loads(value) for value in sorted({json.dumps(value, sort_keys=True) for value in values})]


def _version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("bench", "run", "os_type", "model", "specs"):
        parser.add_argument(name)
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(Path(args.bench), args.run, args.os_type, args.model, Path(args.specs).read_text().split(),
                           {}, installed_drivers(), json.loads(args.image.read_text()) if args.image else None),
                     indent=1))
