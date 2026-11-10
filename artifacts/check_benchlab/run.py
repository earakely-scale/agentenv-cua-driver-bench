"""Inside BenchLab's computer, run as its session user once the task pack is loaded into ``~/bench``: BenchLab shows its
window in the app's mode, titled ``BenchLab — <mode>`` (on macOS, trycua's app itself, ``BenchLab``), its outer frame at
the place trycua's macOS BenchLab takes (on Omarchy their Hyprland runner's frame for it), having written its state and its ``app_start`` for that mode and seed, which
its data plane returns; and with ``solve``, it does the task as an agent does, through the computer's driver over its
MCP endpoint, element by element, with the values trycua's files derive from the seed, the pointer only where the task
needs one, for the grade to score with their evaluator; and with ``background``, its interruption brought up and
answered by background actions alone, as an agent would in trycua's background condition, and what the user's window
went through, reported: under this computer's xfwm4 the modal dialog takes the keyboard and comes to the front, so
``user_kept_focus`` and ``user_window_on_top`` are "no" (openbox, trycua's Linux window manager, leaves the keyboard but
still stacks it on top); on Hyprland, whose sentinel's samples carry no focus flags, the user's window kept the focus
when it stayed the front window. ``args``: ``mode``, ``seed``, ``solve`` and ``background``."""
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
SENTINEL_LOG = Path.home() / ".bench-sentinel" / "sentinel.jsonl"
LOST = {"didResignKey", "didResignActive"}
DATA_OBJECTS = "urn:agentenv:data-objects/v1"
WAIT_S = 30.0
MACOS = sys.platform == "darwin"
#: An Omarchy computer, whose BenchLab app alone installs trycua's Hyprland files.
HYPRLAND = not MACOS and Path("/opt/agentenv/apps/benchlab/lab/hyprland").is_dir()
FRAME_AT = (40, 40) if HYPRLAND else (60, 80)
#: The identity trycua's sentinel on Hyprland gives its own window in its samples.
SENTINEL_BID = "ai.cua.benchsentinel"
#: What trycua's macOS BenchLab calls the fields their Linux BenchLab names otherwise, by mode.
MAC_NAMES = {"irmodal": {"Name": "Full name", "Email": "Work email"}, "irconsent": {"Reject optional": "Reject non-essential"}}
#: Where trycua's macOS BenchLab draws what its accessibility tree leaves out, or what takes input only as a person
#: gives it, in its window's pixels: the notes' first row and their pitch, the first tooltip icon's centre and the
#: icons' pitch, the hover zone's button, and IR-04's email field, whose web form takes typed keys only after a click.
MAC_ROWS, MAC_ROW_PITCH = (75, 93), 24
MAC_ICONS, MAC_ICON_PITCH = (125, 127), 165
MAC_ACTIONS = (103, 78)
MAC_EMAIL = (210, 181)
#: How a background set_value is sent: macOS's cua-driver sets a value through the accessibility API alone, which
#: never activates the app, and takes no delivery mode.
BACKGROUND_SET = {} if MACOS else {"delivery_mode": "background"}
#: An element in cua-driver's tree, by its title or by its value, and a field by its label, as macOS gives it beside
#: its value.
ROW = re.compile(r'\s*- \[(\d+)\] (.+?) "([^"]*)"')
LABEL = re.compile(r'\s*- \[(\d+)\] [^"]*?(?:= "[^"]*" )?\(([^)]*)\)')


def run(input):
    args, env = input["args"], input["env"]
    driver = Driver(env)
    title = "BenchLab" if MACOS else f"BenchLab — {args['mode']}"
    lab = driver.window(lambda window: window["app_name"] == "BenchLab" and window["title"] == title)
    state = _wait(lambda: _json(DATA / "state.json"))
    events = _events()
    bounds = lab["bounds"]
    report = {"title_ok": lab["title"] == title and lab["app_name"] == "BenchLab",
              "placed_ok": 0 <= bounds["x"] - FRAME_AT[0] <= 12 and 0 <= bounds["y"] - FRAME_AT[1] <= 48,
              "bounds": bounds,
              "state_ok": (state["mode"], state["seed"]) == (args["mode"], args["seed"]),
              "started_ok": events[0]["type"] == "app_start" and events[0]["details"] == {
                  "mode": args["mode"], "seed": args["seed"]},
              "exported_ok": {".benchlab/state.json", ".benchlab/events.jsonl"} <= _exported(env)}
    if args.get("background"):
        mark = len(SENTINEL_LOG.read_text().splitlines())
        report["interrupted"] = INTERRUPTIONS[args["mode"]](driver, lab, getattr(C, f"derive_{args['mode']}")(args["seed"]))
        lines = [json.loads(line) for line in SENTINEL_LOG.read_text().splitlines()[mark:] if line.strip()]
        samples = [line for line in lines if line["ev"] == "s"]
        report["user_kept_focus"] = "yes" if samples and not any(line["ev"] in LOST for line in lines) and all(
            _focused(sample) for sample in samples) else "no"
        report["user_window_on_top"] = "yes" if samples and not any(_raised(s, samples[0]) for s in samples) else "no"
        report["user_samples"] = {"samples": len(samples), "not_key": sum(not s.get("key", _focused(s)) for s in samples),
                                  "not_active": sum(not s.get("active", _focused(s)) for s in samples),
                                  "under_another": sum(bool(_raised(s, samples[0])) for s in samples),
                                  "lost": sorted({line["ev"] for line in lines if line["ev"] in LOST})}
    if args.get("solve"):
        driver.call("bring_to_front", pid=lab["pid"], window_id=lab["window_id"])
        report["solved"] = SOLVERS[args["mode"]](driver, lab, getattr(C, f"derive_{args['mode']}")(args["seed"]))
        report["events"] = [event["type"] for event in _events()]
    failed = sorted(key for key, value in report.items() if value is False)
    if failed:
        raise AssertionError(f"{', '.join(failed)} failed: {json.dumps(report)}")
    return report


def _irmodal(driver, lab, values):
    """IR-01: the form's first step, the permission prompt denied, the second step, Submit once. On macOS the prompt
    is a sheet on BenchLab's window, and Team a pop-up menu that set_value picks from."""
    driver.act("set_value", lab, _name("irmodal", "Name"), value=values["name"])
    driver.act("set_value", lab, _name("irmodal", "Email"), value=values["email"])
    driver.act("click", lab, "Next")
    prompt = lab if MACOS else driver.window(
        lambda window: window["pid"] == lab["pid"] and window["title"].startswith("Allow BenchLab"))
    driver.act("click", prompt, "Don’t Allow")
    driver.act("set_value", lab, "Team", value=values["team"])
    driver.act("set_value", lab, "Seats", value=str(values["seats"]))
    driver.act("click", lab, "Submit")
    return values


def _tooltip(driver, lab, values):
    """MB-11: the pointer rested on the target's icon until BenchLab is asked for its tooltip, then its code typed
    and Submit once."""
    cell = (760 - 2 * 24 - 3 * 24) // 4
    x, y = ((MAC_ICONS[0] + values["target_index"] * MAC_ICON_PITCH, MAC_ICONS[1]) if MACOS
            else (24 + values["target_index"] * (cell + 24) + cell // 2, 60))
    _rest(driver, lab, x, y, lambda: any(event["type"] == "tooltip_query"
                                         and event["details"].get("icon") == values["target"] for event in _events()))
    driver.act("set_value", lab, "Code", value=values["target_code"])
    driver.act("click", lab, "Submit")
    return values


def _hover(driver, lab, values):
    """MB-10: the pointer into the Actions zone until the buttons show, then the target's clicked once."""
    _rest(driver, lab, *(MAC_ACTIONS if MACOS else (380, 40)),
          lambda: any(event["type"] == "overlay_shown" for event in _events()))
    driver.act("click", lab, values["target"])
    return values


SOLVERS = {"irmodal": _irmodal, "tooltip": _tooltip, "hover": _hover}


def _permission_prompt(driver, lab, values):
    """IR-01's prompt: the first step filled and Next pressed, then Don't Allow, all in the background."""
    driver.act("set_value", lab, _name("irmodal", "Name"), value=values["name"], **BACKGROUND_SET)
    driver.act("click", lab, "Next", delivery_mode="background")
    return _answered(driver, lab, "Allow BenchLab", "Don’t Allow")


def _unsaved_prompt(driver, lab, values):
    """IR-03's prompt: the open note's title edited and another note chosen, then Cancel, all in the background."""
    driver.act("set_value", lab, "Title", value=values["titles"][0] + " (edited)", **BACKGROUND_SET)
    if MACOS:
        _at(driver, lab, "click", MAC_ROWS[0], MAC_ROWS[1] + MAC_ROW_PITCH)
    else:
        driver.act("click", lab, values["titles"][1], delivery_mode="background")
    return _answered(driver, lab, "Save changes", "Cancel")


def _consent_prompt(driver, lab, values):
    """IR-04's overlay: the form's email edited, then the optional cookies rejected, all in the background."""
    if MACOS:
        _at(driver, lab, "click", *MAC_EMAIL)
        _at(driver, lab, "type_text", *MAC_EMAIL, text="user@example.com")
    else:
        driver.act("set_value", lab, "Email", value="user@example.com", delivery_mode="background")
    return _answered(driver, lab, "Cookie preferences", _name("irconsent", "Reject optional"))


def _answered(driver, lab, title, answer):
    """The dialog titled ``title`` of BenchLab's process answered with ``answer`` in the background, a moment after it
    showed; its title. On macOS it's a sheet or an overlay on BenchLab's own window."""
    dialog = lab if MACOS else driver.window(
        lambda window: window["pid"] == lab["pid"] and window["title"].startswith(title))
    if MACOS:
        _wait(lambda: driver.elements(lab).get(answer))
    time.sleep(1.0)
    driver.act("click", dialog, answer, delivery_mode="background")
    time.sleep(1.0)
    return title if MACOS else dialog["title"]


INTERRUPTIONS = {"irmodal": _permission_prompt, "irunsaved": _unsaved_prompt, "irconsent": _consent_prompt}


def _raised(sample, first):
    """What draws over the user's window in ``sample`` that didn't at the first sample, as trycua's summarizer counts
    a raise: a desktop's own bar or layers, there from the start, aren't one."""
    return set(sample.get("above") or []) - set(first.get("above") or [])


def _focused(sample):
    """Whether a sample says the user's window was active with the focus: its own flags, or on Hyprland its front
    window, the sentinel's."""
    if "key" not in sample:
        return (sample.get("front") or {}).get("bid") == SENTINEL_BID
    return bool(sample["key"] and sample["active"])


def _rest(driver, window, x, y, done):
    """The pointer at ``x``, ``y`` of the window, nudged, and left there until ``done``: on macOS and Hyprland moved
    through the driver, as neither has xdotool."""
    point = (window["bounds"]["x"] + x, window["bounds"]["y"] + y)
    if MACOS or HYPRLAND:
        for dx, dy in ((0, 0), (2, 1)):
            driver.call("move_cursor", x=point[0] + dx, y=point[1] + dy, scope="desktop")
    else:
        subprocess.run(["xdotool", "mousemove", *map(str, point)], check=True)
        subprocess.run(["xdotool", "mousemove_relative", "--", "2", "1"], check=True)
    _wait(lambda: done() or None)


def _at(driver, window, tool, x, y, **args):
    """``tool`` at ``x``, ``y`` of the window, in the background, once the window's frame is captured, as the driver
    places a point only in a frame it has captured."""
    driver.call("get_window_state", pid=window["pid"], window_id=window["window_id"], include_screenshot=True)
    driver.call(tool, pid=window["pid"], window_id=window["window_id"], x=x, y=y, delivery_mode="background", **args)


def _name(mode, name):
    return MAC_NAMES.get(mode, {}).get(name, name) if MACOS else name


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
        """The window's actionable elements by name, their title or value, or a field's label: their role and element
        token."""
        state = self.call("get_window_state", pid=window["pid"], window_id=window["window_id"],
                          include_screenshot=False)["structuredContent"]
        found = {}
        for line in state["tree_markdown"].splitlines():
            if match := ROW.match(line):
                found.setdefault(match.group(3), (match.group(2), f"{state['snapshot_id']}:{match.group(1)}"))
            if match := LABEL.match(line):
                found.setdefault(match.group(2), ("", f"{state['snapshot_id']}:{match.group(1)}"))
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
