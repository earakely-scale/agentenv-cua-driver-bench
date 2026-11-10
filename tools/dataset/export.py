"""export.py OUT INSTANCE|NAME|RUN...: each finished trial in this machine's agent-env store as a folder OUT/NAME of
what the dataset publishes, its task file read from the bench's checkout at $BENCH (default ~/bench).

trial.json (the facts), trajectory.json (claude-code's stream-json, or codex-cli's exec events, as recorded),
sentinel.jsonl and devtools.jsonl (from the trial's snapshot), grade.json (both verifications), workspace/ (the task
app's final files), recording.mp4 (the segments joined) with manifest.json, and timeline.json (calls, texts and the
user's lane on the recording's clock)."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
from datetime import datetime
from importlib import metadata, util
from pathlib import Path

STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "agent-env"
DB = STATE / "document_store" / "local.db"
KEY = re.compile(r"sk-[A-Za-z0-9_\-]{12,}")
PRICES = {"claude-sonnet-4-5": (3.0, 15.0, 0.30), "claude-sonnet-5-5": (2.0, 10.0, 0.20),
          "claude-opus-5-5": (4.0, 20.0, 0.40), "gpt-6-luna": (0.10, 0.50, 0.01), "gpt-6.1-terra": (1.0, 5.0, 0.05),
          "gpt-6.1-sol": (2.0, 10.0, 0.10), "gpt-6-astra": (10.0, 50.0, 1.0)}
TIERED = {"claude-haiku-5-5": (100_000, (0.10, 0.50, 0.01), (0.50, 2.50, 0.05))}
BENCH = Path(os.environ.get("BENCH", Path.home() / "bench"))
STEM = re.compile(r"^(?:codex-)?(?:macos-|windows-|omarchy-)?(?:(?P<driver>agent-desktop|macos-harness|codex-computer-use|cua-driver)-)?(?P<task>(?:cdb-g|mb-|ir-)\d\d)(?:-r\d)?"
                  r"-(?P<condition>foreground|background)$")


def main():
    out = Path(sys.argv[1])
    con = sqlite3.connect(DB)
    rows = con.execute("select doc from docs_task_instances")
    instances = {d["instance_id"]: d for d in (json.loads(doc) for (doc,) in rows)}
    artifacts = {}
    for (doc,) in con.execute("select doc from docs_artifacts"):
        d = json.loads(doc)
        artifacts[(d["id"], d["version"])] = d
    for spec in sys.argv[2:]:
        instance_id, name, run = spec.split("|")
        export(instances[instance_id], artifacts, out, name, int(run))


def export(instance, artifacts, out, name, run_index):
    ctx, md = instance["context"], instance["context"]["metadata"]
    stem = named(instance["task_id"])
    task, condition, driver = STEM.match(stem).group("task", "condition", "driver")
    steps = {s["id"]: s for s in json.loads((BENCH / "tasks" / f"{stem}.json").read_text())}
    env_step = steps["env"]
    seed = (env_step.get("env_params", {}).get("app_settings", {}).get("benchlab") or {}).get("seed")
    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    response = ctx["prompt_responses"][-1]
    recorded = json.loads(_path(response["agent_trajectory_object_url"]).read_text())
    (folder / "trajectory.json").write_text(json.dumps(recorded, indent=1))
    codex = bool(recorded) and recorded[0].get("type") == "thread.started"
    events = from_codex(recorded, response.get("model")) if codex else recorded

    snapshot = md.get("env_snapshotted_universes", {}).get("snapshot")
    workspace_app = None
    if snapshot:
        for (aid, version), doc in artifacts.items():
            if not aid.startswith(snapshot["id"] + "-") or doc.get("type") != "environment":
                continue
            app = doc["environment_name"]
            for rel, ref in doc.get("file_artifact_refs", {}).items():
                source = _path(artifacts[(ref["id"], ref["version"])]["object_url"])
                if app == "bench-sentinel":
                    shutil.copy(source, folder / Path(rel).name)
                elif in_workspace(rel):
                    workspace_app = app
                    target = folder / "workspace" / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(source, target)

    recording = md["computer_recordings"]["trial"]
    namespace = _path(recording["namespace"])
    manifest = json.loads((namespace / "manifest.json").read_text())
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
    listing = folder / "segments.txt"
    listing.write_text("".join(f"file '{namespace / s['path']}'\n" for s in manifest["segments"]))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(folder / "recording.mp4")], check=True)
    listing.unlink()

    verifications = md.get("verifications", {})
    (folder / "grade.json").write_text(json.dumps(verifications, indent=1))
    start = _epoch(manifest["started_at"])
    sentinel = _lines(folder / "sentinel.jsonl")
    track = timeline(events, sentinel, start, _epoch(manifest["ended_at"]), md.get("script_results", {}))
    (folder / "timeline.json").write_text(json.dumps(track, indent=1))

    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    init = next((e for e in events if (e.get("type"), e.get("subtype")) == ("system", "init")), {})
    graded = verifications.get("grade", {})
    grade = {r["id"]: r for r in (graded.get("extracted_files") or {}).get("/grade/result.json", {}).get("results")
             or graded.get("results", [])}
    gui = {r["id"]: r for r in verifications.get("gui_only", {}).get("results", [])}
    trajectory_check = gui.get("gui_only_trajectory") or {}
    reward = graded.get("score")
    facts = {
        "trial_id": name,
        "task": task,
        "task_file": stem,
        "probe": task.upper() if not task.startswith("cdb") else "CDB-" + task.split("-")[1].upper(),
        "condition": condition,
        "run_index": run_index,
        "seed": seed,
        "prompt": steps["task"]["prompt"],
        "system_prompt": steps["agent"].get("system_prompt"),
        "max_turns": steps["task"].get("max_turns"),
        "timeout_s": steps["task"].get("timeout_seconds"),
        "os": os.environ.get("RUN_OS") or "linux",
        "driver": driver or "cua-driver",
        "computer": named(ctx["deployed_envs"][0]["env_id"]),
        "settings": [setting for setting in os.environ.get("RUN_SETTINGS", "").splitlines() if setting],
        "app": workspace_app,
        "model": response.get("model"),
        "harness": "codex-cli" if codex else "claude-code",
        "harness_version": codex_version() if codex else init.get("claude_code_version"),
        "effort": steps["task"].get("effort"),
        "framework_version": metadata.version("agentenv-framework"),
        "bench_commit": subprocess.run(["git", "-C", str(BENCH), "rev-parse", "HEAD"], capture_output=True,
                                       text=True).stdout.strip(),
        "trycua_commit": tomllib.loads((BENCH / "taskpack.lock.toml").read_text())["commit"],
        "started_at": manifest["started_at"],
        "ended_at": manifest["ended_at"],
        "status": instance.get("status"),
        "steps": instance.get("completed_steps"),
        "agent_error": response.get("error_message"),
        "cost_usd": cost(usage, events) if (usage := result.get("modelUsage") or (
            None if codex else from_calls(events))) else None,
        "cost_from_calls": not result.get("modelUsage"),
        "cost_usd_reported": result.get("total_cost_usd"),
        "tokens": {model: {k: usage.get(k) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                                                      "cacheCreationInputTokens", "thinkingTokens")}
                   for model, usage in (result.get("modelUsage") or {}).items()},
        "num_turns": result.get("num_turns"),
        "duration_s": (result.get("duration_ms") or 0) / 1000 or None,
        "model_calls": result.get("num_turns") if codex else
        len({(e.get("message") or {}).get("id") for e in events if e.get("type") == "assistant"}),
        "tool_calls": len(track["calls"]),
        "tool_errors": sum(c["error"] for c in track["calls"]),
        "reward": reward,
        "passed": reward == 1.0 and trajectory_check.get("result") is True,
        "grade": grade,
        "gui_only_trajectory": trajectory_check or None,
    }
    (folder / "trial.json").write_text(json.dumps(facts, indent=1))
    leaked = [p.name for p in folder.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl", ".txt")
              and KEY.search(p.read_text(errors="ignore"))]
    print(json.dumps({"trial": name, "reward": facts["reward"], "passed": facts["passed"], "calls": facts["tool_calls"],
                      "cost": facts["cost_usd"], "leaked": leaked}))


def named(entity_id):
    """An entity's name: the last segment of its id, less the settings an ``agent-env run --set`` run's ids end in."""
    return re.sub(r"\(.*\)$", "", entity_id).rsplit("/", 1)[-1]


def timeline(events, sentinel, start, end, scripts):
    calls, texts, pending, model_ids, compactions = [], [], {}, [], []
    for e in events:
        t = _epoch(e["timestamp"]) - start if e.get("timestamp") else None
        if (e.get("type"), e.get("subtype")) == ("system", "compact_boundary"):
            compactions.append(t)
        if e.get("type") == "assistant":
            message = e.get("message") or {}
            if message.get("id") not in model_ids:
                model_ids.append(message.get("id"))
            for block in message.get("content") or []:
                if block.get("type") == "tool_use":
                    server, _, tool = block["name"].rpartition("__")
                    call = {"i": len(calls), "id": block["id"], "turn": len(model_ids), "t0": t, "t1": None,
                            "tool": tool, "server": server.removeprefix("mcp__") or None, "input": block.get("input"),
                            "error": False, "result": None, "image": False}
                    pending[block["id"]] = call
                    calls.append(call)
                elif block.get("type") == "text" and block.get("text", "").strip():
                    texts.append({"t": t, "turn": len(model_ids), "text": block["text"]})
        if e.get("type") == "user":
            for block in (e.get("message") or {}).get("content") or []:
                if (isinstance(block, dict) and block.get("type") == "tool_result"
                        and block.get("tool_use_id") in pending):
                    call = pending.pop(block["tool_use_id"])
                    content = block.get("content")
                    parts = content if isinstance(content, list) else [{"type": "text", "text": str(content)}]
                    call.update(t1=t, error=bool(block.get("is_error")),
                                result=" ".join(p.get("text", "") for p in parts if p.get("type") == "text")[:600],
                                image=any(p.get("type") == "image" for p in parts))
    user = [{**{k: v for k, v in line.items() if k not in ("t",)}, "t": line["t"] / 1000 - start}
            for line in sentinel if line.get("ev") != "s"]
    samples = [{"t": line["t"] / 1000 - start, "active": line.get("active"), "key": line.get("key"),
                "front": (line.get("front") or {}).get("bid"), "above_n": line.get("above_n"),
                "mouse": line.get("mouse")}
               for line in _states(sentinel) if line.get("ev") == "s" and line.get("armed")][::10]
    arm = (scripts.get("arm") or {}).get("line") or {}
    disarm = (scripts.get("disarm") or {}).get("line") or {}
    return {"duration": end - start, "armed_at": arm.get("t", 0) / 1000 - start if arm else None,
            "disarmed_at": disarm.get("t", 0) / 1000 - start if disarm else None, "calls": calls, "texts": texts,
            "compactions": compactions, "user": user, "samples": samples}


def from_codex(recorded, model):
    """codex-cli's exec events as claude-code's stream-json, for the timeline and the facts: each tool call a tool_use
    at the time its item started and its tool_result when it completed, its own tools named as trycua's runner maps
    them; each message a text; and the usage the agent recorded last a result, the model requests its turns. Each item
    once, by its id within its CLI run, which numbers them afresh. A result's image counts as the model's only when the
    result has no structured content, which the CLI sends the model instead."""
    names = {"command_execution": "Bash", "file_change": "Edit", "web_search": "WebSearch", "collab_tool_call": "Agent"}
    events, run, started = [], 0, set()
    for e in recorded:
        run += e.get("type") == "thread.started"
        item = e.get("item") if e.get("type") in ("item.started", "item.completed") else None
        if not isinstance(item, dict) or item.get("type") in ("reasoning", "todo_list", "error"):
            continue
        key, t = f"{run}:{item.get('id')}", e.get("timestamp")
        if item.get("type") == "agent_message":
            if e["type"] == "item.completed":
                events.append({"type": "assistant", "timestamp": t,
                               "message": {"id": key, "content": [{"type": "text", "text": item.get("text") or ""}]}})
            continue
        if key not in started:
            started.add(key)
            mcp = item.get("type") == "mcp_tool_call"
            name = f"mcp__{item.get('server')}__{item.get('tool')}" if mcp else names.get(item.get("type"), "Task")
            tool_input = item.get("arguments") if mcp else {k: v for k, v in item.items() if k not in ("id", "type")}
            events.append({"type": "assistant", "timestamp": t, "message": {"id": key, "content": [
                {"type": "tool_use", "id": key, "name": name, "input": tool_input}]}})
        if e["type"] == "item.completed":
            result = item.get("result") or {}
            content = [p for p in result.get("content") or [] if p.get("type") == "text" or not result.get(
                "structured_content")] or [{"type": "text", "text": str((item.get("error") or {}).get("message")
                                                                         or item.get("aggregated_output") or "")}]
            failed = item.get("status") == "failed" or bool(item.get("error")) or (item.get("exit_code") or 0) != 0
            events.append({"type": "user", "timestamp": t, "message": {"content": [
                {"type": "tool_result", "tool_use_id": key, "is_error": failed, "content": content}]}})
    recorded_usage = next((e for e in reversed(recorded) if e.get("type") == "agentenv.usage"), {})
    usage = recorded_usage.get("usage") or {}
    times = [_epoch(e["timestamp"]) for e in recorded if e.get("timestamp")]
    cached = usage.get("cached_input_tokens", 0)
    model_usage = {model: {"inputTokens": usage.get("input_tokens", 0) - cached, "cacheReadInputTokens": cached,
                           "cacheCreationInputTokens": 0, "outputTokens": usage.get("output_tokens", 0),
                           "thinkingTokens": usage.get("reasoning_output_tokens")}} if usage and model else None
    events.append({"type": "result", "num_turns": recorded_usage.get("model_requests"), "modelUsage": model_usage,
                   "duration_ms": (times[-1] - times[0]) * 1000 if times else None})
    return events


def codex_version():
    """The Codex CLI the installed framework's agent pins."""
    package = Path(util.find_spec("agent_env").origin).parent / "agents" / "agents" / "codex" / "package.json"
    return json.loads(package.read_text())["dependencies"]["@openai/codex"]


def cost(model_usage, events):
    """List price per MTok (input, output, cache read), cache writes at 1.25x input: from the token totals, or call by
    call for a model whose price depends on the prompt's size, with the totals' output spread over the calls."""
    total = 0.0
    for model, usage in model_usage.items():
        name = usage.get("canonicalModel") or model.rsplit("/", 1)[-1]
        if name in TIERED:
            total += _tiered(TIERED[name], usage, events)
            continue
        if name not in PRICES:
            return None
        total += _priced(PRICES[name], usage.get("inputTokens", 0), usage.get("cacheCreationInputTokens", 0),
                         usage.get("cacheReadInputTokens", 0), usage.get("outputTokens", 0))
    return round(total, 4)


def from_calls(events):
    """Token totals summed over the trajectory's calls, for a run cut off before Claude Code's result: its thinking
    tokens may be missing from the calls' output counts."""
    calls = {}
    for e in events:
        if e.get("type") == "assistant":
            message = e.get("message") or {}
            calls[message.get("id")] = (message.get("model"), message.get("usage") or {})
    totals = {}
    for model, usage in calls.values():
        entry = totals.setdefault(model, {"canonicalModel": model})
        for ours, theirs in (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"),
                             ("cacheReadInputTokens", "cache_read_input_tokens"),
                             ("cacheCreationInputTokens", "cache_creation_input_tokens")):
            entry[ours] = entry.get(ours, 0) + usage.get(theirs, 0)
    return totals


def _states(sentinel):
    """The sentinel's lines, each sample with whether the bench armed it and the user's window was active and held the
    keyboard: as Linux's and macOS's sentinels write on each, and for Windows', whose samples carry none of them, from
    its armed and disarmed lines and its focus events, the user's window holding both once it's armed."""
    armed = active = key = False
    for line in sentinel:
        ev = line.get("ev")
        if ev == "armed":
            armed = active = key = True
        elif ev == "disarmed":
            armed = False
        elif ev in ("didResignKey", "didBecomeKey"):
            key = ev == "didBecomeKey"
        elif ev in ("didResignActive", "didBecomeActive"):
            active = ev == "didBecomeActive"
        yield {**line, "armed": armed, "active": active, "key": key} if ev == "s" and "armed" not in line else line


def in_workspace(rel):
    """Whether a snapshot's file is the trial's workspace: not under an app's .runtime (its browser profile and such),
    nor Explorer's desktop.ini, which each shell folder of a Windows home holds."""
    return "/.runtime/" not in f"/{rel}" and Path(rel).name.lower() != "desktop.ini"


def _tiered(tiers, usage, events):
    limit, small, large = tiers
    calls = {}
    for e in events:
        if e.get("type") == "assistant":
            calls[(e.get("message") or {}).get("id")] = (e.get("message") or {}).get("usage") or {}
    counted = sum(u.get("output_tokens", 0) for u in calls.values()) or 1
    scale = usage.get("outputTokens", 0) / counted
    total = 0.0
    for u in calls.values():
        fresh, written, read = (u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                       "cache_read_input_tokens"))
        total += _priced(large if fresh + written + read > limit else small, fresh, written, read,
                         u.get("output_tokens", 0) * scale)
    return total


def _priced(price, fresh, written, read, output):
    inp, out, cached = price
    return (fresh * inp + written * inp * 1.25 + read * cached + output * out) / 1e6


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _epoch(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def _path(url):
    return Path(url.removeprefix("file://"))


if __name__ == "__main__":
    main()
