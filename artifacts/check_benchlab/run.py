"""Inside BenchLab's computer, run as its session user once the task pack is loaded into ``~/bench``: BenchLab shows its
window in the app's mode, titled ``BenchLab — <mode>``, its outer frame at the place trycua's macOS BenchLab takes,
having written its state and its ``app_start`` for that mode and seed, which its data plane returns; and with ``solve``,
it does the task as an agent does, through the computer's driver over its MCP endpoint, element by element, with the
values trycua's files derive from the seed, the pointer only where the task needs one, for the grade to score with
their evaluator. ``args``: ``mode``, ``seed`` and ``solve``."""
import base64
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path.home() / "bench" / "probes" / "_common"))
import benchlab_common as C  # noqa: E402

DATA = Path.home() / ".benchlab"
DATA_OBJECTS = "urn:agentenv:data-objects/v1"
FRAME_AT = (60, 80)
WAIT_S = 30.0


def run(input):
    args, env = input["args"], input["env"]
    driver = Driver(env)
    lab = driver.window(lambda window: window["app_name"] == "BenchLab" and window["title"].startswith("BenchLab — "))
    state = _wait(lambda: _json(DATA / "state.json"))
    events = _events()
    bounds = lab["bounds"]
    report = {"title_ok": lab["title"] == f"BenchLab — {args['mode']}" and lab["app_name"] == "BenchLab",
              "placed_ok": 0 <= bounds["x"] - FRAME_AT[0] <= 12 and 0 <= bounds["y"] - FRAME_AT[1] <= 48,
              "state_ok": (state["mode"], state["seed"]) == (args["mode"], args["seed"]),
              "started_ok": events[0]["type"] == "app_start" and events[0]["details"] == {
                  "mode": args["mode"], "seed": args["seed"]},
              "exported_ok": {".benchlab/state.json", ".benchlab/events.jsonl"} <= _exported(env)}
    if args.get("solve"):
        driver.call("bring_to_front", pid=lab["pid"], window_id=lab["window_id"])
        report["solved"] = SOLVERS[args["mode"]](driver, lab, getattr(C, f"derive_{args['mode']}")(args["seed"]))
        report["events"] = [event["type"] for event in _events()]
    failed = sorted(key for key, value in report.items() if value is False)
    if failed:
        raise AssertionError(f"{', '.join(failed)} failed: {json.dumps(report)}")
    return report


def _irmodal(driver, lab, values):
    """IR-01: the form's first step, the permission prompt denied, the second step, Submit once."""
    driver.act("set_value", lab, "Name", value=values["name"])
    driver.act("set_value", lab, "Email", value=values["email"])
    driver.act("click", lab, "Next")
    prompt = driver.window(lambda window: window["pid"] == lab["pid"] and window["title"].startswith("Allow BenchLab"))
    driver.act("click", prompt, "Don’t Allow")
    driver.act("set_value", lab, "Team", value=values["team"])
    driver.act("set_value", lab, "Seats", value=str(values["seats"]))
    driver.act("click", lab, "Submit")
    return values


def _tooltip(driver, lab, values):
    """MB-11: the pointer rested on the target's icon until BenchLab is asked for its tooltip, then its code typed
    and Submit once."""
    cell = (760 - 2 * 24 - 3 * 24) // 4
    _rest(lab, 24 + values["target_index"] * (cell + 24) + cell // 2, 60,
          lambda: any(event["type"] == "tooltip_query" and event["details"].get("icon") == values["target"]
                      for event in _events()))
    driver.act("set_value", lab, "Code", value=values["target_code"])
    driver.act("click", lab, "Submit")
    return values


def _hover(driver, lab, values):
    """MB-10: the pointer into the Actions zone until the buttons show, then the target's clicked once."""
    _rest(lab, 380, 40, lambda: any(event["type"] == "overlay_shown" for event in _events()))
    driver.act("click", lab, values["target"])
    return values


SOLVERS = {"irmodal": _irmodal, "tooltip": _tooltip, "hover": _hover}


def _rest(window, x, y, done):
    """The pointer at ``x``, ``y`` of the window's content, nudged, and left there until ``done``."""
    point = (window["bounds"]["x"] + x, window["bounds"]["y"] + y)
    subprocess.run(["xdotool", "mousemove", *map(str, point)], check=True)
    subprocess.run(["xdotool", "mousemove_relative", "--", "2", "1"], check=True)
    _wait(lambda: done() or None)


class Driver:
    """The computer's driver over its MCP endpoint, called as an agent calls it."""

    def __init__(self, env):
        self.url, self.headers, self.session, self.ids = env["mcp_url"], env["headers"], None, 0
        self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "check_benchlab", "version": "1"}})
        self._rpc("notifications/initialized", None)

    def call(self, name, **args):
        result = self._rpc("tools/call", {"name": name, "arguments": args})
        if result.get("isError"):
            raise AssertionError(f"{name}({json.dumps(args)}): {result['content'][0].get('text')}")
        return result

    def window(self, match):
        """The first window ``match`` takes; BenchLab's dialogs are its process's, of another class than its own."""
        return _wait(lambda: next((window for window in self.call("list_windows")["structuredContent"]["windows"]
                                   if match(window)), None))

    def elements(self, window):
        """The window's actionable elements by name: their role and element token."""
        state = self.call("get_window_state", pid=window["pid"], window_id=window["window_id"],
                          include_screenshot=False)["structuredContent"]
        found = {}
        for line in state["tree_markdown"].splitlines():
            if match := re.match(r'\s*- \[(\d+)\] (.+?) "([^"]*)"', line):
                found.setdefault(match.group(3), (match.group(2), f"{state['snapshot_id']}:{match.group(1)}"))
        return found

    def act(self, tool, window, name, **args):
        _, token = _wait(lambda: self.elements(window).get(name))
        return self.call(tool, pid=window["pid"], window_id=window["window_id"], element_token=token, **args)

    def _rpc(self, method, params):
        notify = params is None
        self.ids += 1
        body = {"jsonrpc": "2.0", "method": method, **({} if notify else {"id": self.ids, "params": params})}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   **self.headers, **({"mcp-session-id": self.session} if self.session else {})}
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            self.session = self.session or response.headers.get("mcp-session-id")
            text = response.read().decode()
        if notify:
            return None
        if "data:" in text:
            text = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")][-1]
        reply = json.loads(text)
        if "error" in reply:
            raise AssertionError(f"{method}: {reply['error']}")
        return reply["result"]


def _exported(env):
    request = urllib.request.Request(f"{env['url']}/svc/benchlab/agentenv", data=json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "data/get", "params": {}}).encode(),
        headers={"Content-Type": "application/json", **env["headers"]})
    with urllib.request.urlopen(request, timeout=120) as response:
        parts = json.load(response)["result"]["parts"]
    return {part["metadata"][DATA_OBJECTS]["path"] for part in parts if base64.b64decode(part["file"]["bytes"])}


def _events():
    return [json.loads(line) for line in (DATA / "events.jsonl").read_text().splitlines() if line.strip()]


def _json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _wait(get):
    deadline = time.monotonic() + WAIT_S
    while (value := get()) is None:
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting on {get}")
        time.sleep(0.3)
    return value
