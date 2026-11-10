import json
import math
import re
from datetime import datetime
from pathlib import Path

SENTINEL_BID = "ai.cua.benchsentinel"
OVERLAY_RE = re.compile(r"(?i)cua ?driver|chatgpt computer use|computer use|codex|app-cu-helper|claude")
FRONT_EVENTS = ("s", "front", "armed", "disarmed")
POINTER_STILL_PX = 1.0
LOOK_PREFIXES = ("get_", "list_", "check_", "verify_", "read_", "find_")
LOOK_TOOLS = {"computer_screenshot", "zoom", "clipboard_read", "screenshot"}
WAIT_TOOLS = {"computer_wait", "wait", "wait_for", "sleep"}
SETUP_TOOLS = {"Skill", "Read", "ToolSearch", "TodoWrite", "tool_search", "update_plan", "list_mcp_resources",
               "list_mcp_resource_templates", "read_mcp_resource"}
KEYBOARD_TOOLS = {"type_text", "computer_type", "press_key", "hotkey", "computer_key", "set_value"}
APP_NAMES = {"soffice": "LibreOffice", "libreoffice-calc": "LibreOffice Calc", "gnucash": "GnuCash",
             "chromium": "Chromium", "google-chrome": "Chromium", "chrome": "Chromium", "xfdesktop": "Desktop",
             SENTINEL_BID: "User activity", "benchsentinel": "User activity"}
KEY_NAMES = {"\t": "⇥", "\n": "⏎", "\r": "⏎"}
#: The lane's verbs for the other drivers' steps (see ``arm_steps``) and which of them only look.
ARM_VERBS = {"snapshot": "Read window", "get_app_state": "Read window", "find": "Find", "get": "Read element",
             "is": "Check element", "screenshot": "Screenshot", "list_apps": "List apps", "list_windows": "List windows",
             "list_surfaces": "List surfaces", "skill": "Read skill", "skills_get": "Read skill", "help": "Read help",
             "click": "Click", "mouse_click": "Click", "double_click": "Double-click", "triple_click": "Triple-click",
             "right_click": "Right-click", "perform_secondary_action": "Secondary action", "type": "Type",
             "type_text": "Type", "set_value": "Set value", "press": "Press", "press_key": "Press", "scroll": "Scroll",
             "drag": "Drag", "hover": "Hover", "mouse_move": "Move pointer", "focus_window": "Focus window",
             "wait": "Wait", "batch": "Run steps", "js": "Run JavaScript", "js_reset": "Reset the REPL",
             "repl": "Run JavaScript"}
#: The cua API calls of Codex Computer Use's ``js``, and Aside's ``computer`` calls of the same names in its ``repl``, the
#: lane shows, and the step each is; others are their own code.
CUA_STEPS = {"getApp": "get_app_state", "getState": "get_app_state", "getAXState": "get_app_state",
             "getAXStateAndScreenshot": "get_app_state", "getScreenshot": "screenshot", "click": "click",
             "doubleClick": "double_click", "rightClick": "right_click", "setValue": "set_value",
             "typeText": "type_text", "pressKey": "press_key", "drag": "drag", "scroll": "scroll",
             "performSecondaryAction": "perform_secondary_action"}
CUA_CALL = re.compile(r"\.\s*(" + "|".join(CUA_STEPS) + r")\s*\(([^()]*)\)")
ARM_LOOKS = {"snapshot", "get_app_state", "find", "get", "is", "screenshot", "list_apps", "list_windows",
             "list_surfaces", "list_displays", "list_notifications", "skill", "skills_get", "skills_list", "help",
             "status", "version", "permissions"}
#: The driver of a trial whose trial.json names none: the bench's first, which every trial before the macOS arms ran on.
DRIVER = "cua-driver"
#: A task file's stem: the OS but Linux or the harness but claude-code, then the driver but cua-driver, as
#: macos-agent-desktop-ir-01-r1-background, codex-ir-01-r1-background or
#: codex-macos-codex-computer-use-ir-01-r1-background.
STEM = re.compile(r"^(?:codex-)?(?:macos-)?(?:(?P<driver>[a-z0-9-]+?)-)?(?P<task>(?:cdb-g|mb-|ir-)\d\d)(?:-r\d+)?"
                  r"-(?P<condition>foreground|background)$")


def discover(root):
    return sorted({p.parent for p in Path(root).rglob("trial.json")}, key=lambda p: p.name)


def run_of(folder, root):
    """A trial folder's run as ``OS/RUN``, as the config's ``exclude_runs`` names the runs the board leaves out."""
    return "/".join(Path(folder).relative_to(root).parts[1:3])


def discover_missing(root):
    """Each trial whose re-runs were spent, from the runs/OS/RUN/NAME/missing.json the fleet's worker uploads: its OS,
    driver, run, task and condition."""
    out = []
    for path in sorted(Path(root).glob("runs/*/*/*/missing.json")):
        record = read_json(path)
        stem = STEM.match(record["task_file"])
        out.append({"os": record.get("os") or "linux", "driver": stem["driver"] or DRIVER,
                    "run": path.parent.parent.name, "name": record["name"], "task": stem["task"],
                    "condition": stem["condition"]})
    return out


def epoch(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def read_lines(path):
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(errors="replace").splitlines():
        raw = raw.strip()
        if raw.endswith("}"):
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if isinstance(line, dict) and isinstance(line.get("t"), (int, float)):
                out.append(line)
    return out


def model_name(model, cfg):
    known = (cfg.get("models") or {}).get(model) or {}
    if known.get("name"):
        return known["name"]
    base = model.rsplit("/", 1)[-1]
    m = re.match(r"claude-(opus|sonnet|haiku|fable)-(\d+)-(\d+)", base)
    if m:
        return f"Claude {m[1].title()} {m[2]}.{m[3]}"
    return base


def app_name(bid):
    if not bid:
        return "another app"
    return APP_NAMES.get(bid.lower(), bid)


def use_names(cfg):
    APP_NAMES.update({k.lower(): v for k, v in (cfg.get("app_names") or {}).items()})


def halves(trial, folder):
    g = trial.get("grade") or {}
    if "task" not in g:
        doc = read_json(folder / "grade.json", {}) or {}
        files = ((doc.get("grade") or {}).get("extracted_files") or {})
        g = {r["id"]: r for r in (files.get("/grade/result.json") or {}).get("results") or []}
    traj = trial.get("gui_only_trajectory")
    out = {"sentinel": None, "task": None, "gui_only": None, "user_undisturbed": None}
    if s := g.get("sentinel"):
        out["sentinel"] = {"result": s.get("result") is True, "problems": s.get("problems") or []}
    if t := g.get("task"):
        out["task"] = {"result": t.get("result") is True, "score": t.get("score"), "checks": t.get("checks") or {}}
    live = g.get("gui_only")
    if live or traj:
        parts = [x for x in (live, traj) if x]
        out["gui_only"] = {
            "result": all(x.get("result") is True for x in parts),
            "violations": list(dict.fromkeys(v for x in parts for v in x.get("violations") or [])),
            "transient": list(dict.fromkeys(v for x in parts for v in x.get("transient") or [])),
            "refused": (traj or {}).get("refused_calls") or {},
            "live": live is not None,
            "trajectory": bool((traj or live or {}).get("trajectory_checked")),
        }
    if u := g.get("user_undisturbed"):
        out["user_undisturbed"] = {"result": u.get("result") is True, "criteria": u.get("criteria") or {},
                                   "unmeasured": u.get("unmeasured") or [], "close_refused": u.get("close_refused") or 0}
    return out


def passed(h, condition):
    need = ["sentinel", "task", "gui_only"] + (["user_undisturbed"] if condition == "background" else [])
    return all(h.get(k) and h[k]["result"] for k in need)


def tool_results(folder):
    out = {}
    for e in read_json(folder / "trajectory.json", []) or []:
        if e.get("type") != "user":
            continue
        for b in (e.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                parts = c if isinstance(c, list) else [{"type": "text", "text": str(c)}]
                out[b.get("tool_use_id")] = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
    return out


def jparse(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def clean(text, n=60):
    text = re.sub(r"\s+", " ", (text or "").replace("￼", " ")).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def show_text(text, n=44):
    text = "".join(KEY_NAMES.get(ch, ch) for ch in text or "")
    return text if len(text) <= n else text[: n - 1] + "…"


EL_LINE = re.compile(r'^\s*-\s+\[(\d+)\]\s+([^"\[]+?)\s+"((?:[^"\\]|\\.)*)"(.*)$')
DESC = re.compile(r'\(description "((?:[^"\\]|\\.)*)"\)')
WIN_RE = re.compile(r'\{"app_name":"([^"]*)","bounds":\{"height":(-?\d+),"width":(-?\d+),"x":(-?\d+),"y":(-?\d+)\}'
                    r'[^{}]*?"pid":(\d+),"title":"([^"]*)"[^{}]*?"window_id":(\d+)')
CLICKED_AT = re.compile(r"at \((-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\) in (f\d+)")
CAPTURED = re.compile(r"Captured (f\d+): (\d+)×(\d+) of the (\d+)×(\d+) display")
CROPPED = re.compile(r"Cropped (f\d+): (\d+)×(\d+) of (f\d+) at \((-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\)")
SCREEN_POINT = re.compile(r"screen_point=\((-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\)")


class Desk:
    def __init__(self, cfg):
        self.w, self.h = cfg["screen"]
        self.bar = cfg.get("titlebar_px", 28)
        self.windows, self.frames, self.snaps, self.last_frame = {}, {}, {}, None

    def learn(self, call, res):
        obj = jparse(res)
        inp = call.get("input") or {}
        if obj is None:
            for m in WIN_RE.finditer(res or ""):
                self.add_window(int(m[8]), m[7], m[1], int(m[6]), int(m[4]), int(m[5]), int(m[3]), int(m[2]))
        for d in walk(obj):
            wid = d.get("window_id")
            b = d.get("bounds")
            if isinstance(wid, int) and isinstance(b, dict) and "title" in d:
                self.add_window(wid, d.get("title"), d.get("app_name"), d.get("pid"), b.get("x"), b.get("y"),
                                b.get("width"), b.get("height"))
            wb = d.get("window_bounds")
            if isinstance(wb, dict) and isinstance(wid, int):
                old = self.windows.get(wid) or {}
                self.add_window(wid, d.get("window_title") or old.get("title"), d.get("app_name") or old.get("app"),
                                d.get("pid") or old.get("pid"), wb.get("x"), wb.get("y"), wb.get("width"), wb.get("height"))
            if isinstance(d.get("snapshot_id"), str) and ("tree_markdown" in d or "elements" in d):
                self.add_snapshot(d, inp)
        tool = call["tool"]
        if tool == "set_window_frame" and isinstance(obj, dict) and obj.get("effect") in ("confirmed", "unverifiable"):
            win = self.windows.get(inp.get("window_id"))
            if win and None not in (inp.get("x"), inp.get("y"), inp.get("width"), inp.get("height")):
                win.update(x=inp["x"], y=inp["y"], w=inp["width"], h=inp["height"])
        if tool in ("get_window_state", "get_accessibility_tree") and isinstance(obj, dict):
            wid = inp.get("window_id")
            title = None
            for line in (obj.get("tree_markdown") or "").splitlines()[:3]:
                m = re.search(r'frame (?:= )?"([^"]+)"', line)
                if m:
                    title = m[1]
                    break
            if wid is not None and title:
                self.windows.setdefault(wid, {"pid": inp.get("pid"), "app": obj.get("app_name")})["title"] = title
        self.learn_frames(res, inp)

    def learn_frames(self, res, inp):
        for m in CAPTURED.finditer(res or ""):
            s = int(m[4]) / int(m[2]) if int(m[2]) else 1.0
            self.frames[m[1]] = (0.0, 0.0, s)
            self.last_frame = m[1]
        for m in CROPPED.finditer(res or ""):
            pox, poy, ps = self.frames.get(m[4], (0.0, 0.0, 1.0))
            region = inp.get("region")
            extra = 1.0
            if isinstance(region, list) and len(region) == 4 and int(m[2]):
                extra = (region[2] - region[0]) / int(m[2]) or 1.0
            self.frames[m[1]] = (pox + float(m[5]) * ps, poy + float(m[6]) * ps, ps * extra)
            self.last_frame = m[1]
        obj = jparse(res)
        for d in walk(obj):
            fid = d.get("frame_id")
            disp = d.get("display")
            if isinstance(fid, str) and fid not in self.frames and isinstance(disp, dict) and not d.get("parent_frame_id"):
                s = (disp.get("width") or self.w) / (d.get("width") or self.w)
                self.frames[fid] = (0.0, 0.0, s)
                self.last_frame = fid

    def add_window(self, wid, title, app, pid, x, y, w, h):
        if None in (x, y, w, h):
            return
        self.windows[wid] = {"title": title, "app": app, "pid": pid, "x": x, "y": y, "w": w, "h": h}

    def add_snapshot(self, d, inp):
        sid = d["snapshot_id"]
        snap = self.snaps.setdefault(sid, {"win": inp.get("window_id"), "pid": d.get("pid") or inp.get("pid"), "els": {}})
        for line in (d.get("tree_markdown") or "").splitlines():
            m = EL_LINE.match(line)
            if m:
                name = m[3].replace('\\"', '"')
                desc = DESC.search(m[4])
                snap["els"][int(m[1])] = {"role": m[2].strip(), "name": clean(name) or (desc and clean(desc[1]))}
        for el in d.get("elements") or []:
            if not isinstance(el, dict) or not isinstance(el.get("element_token"), str):
                continue
            sid2, _, n = el["element_token"].partition(":")
            target = self.snaps.setdefault(sid2, {"win": inp.get("window_id"), "pid": inp.get("pid"), "els": {}})
            if n.isdigit():
                name = clean(el.get("label")) or clean(el.get("name")) or clean(el.get("description"))
                target["els"][int(n)] = {"role": el.get("role") or "", "name": name, "frame": el.get("frame")}

    def element(self, token):
        if not isinstance(token, str) or ":" not in token:
            return None, None
        sid, _, n = token.partition(":")
        snap = self.snaps.get(sid)
        if not snap or not n.isdigit():
            return None, snap
        return snap["els"].get(int(n)), snap

    def window(self, wid=None, pid=None):
        if wid is not None and wid in self.windows:
            return wid, self.windows[wid]
        if pid is not None:
            hits = [(k, v) for k, v in self.windows.items() if v.get("pid") == pid and v.get("w")]
            if hits:
                return hits[-1]
        return None, None

    def outer(self, win):
        if not win or win.get("w") is None:
            return None
        return [win["x"], win["y"] - self.bar, win["w"], win["h"] + self.bar]

    def on_screen(self, x, y):
        return [round(x), round(y)] if 0 <= x <= self.w and 0 <= y <= self.h else None

    def frame_point(self, x, y, fid):
        ox, oy, s = self.frames.get(fid, (0.0, 0.0, 1.0))
        return self.on_screen(ox + x * s, oy + y * s)


def kind_of(tool, inp=None):
    steps = arm_steps(tool, inp)
    if steps is not None:
        names = {name for name, _ in steps}
        return "look" if names <= ARM_LOOKS else "wait" if names == {"wait"} else "act"
    if tool in SETUP_TOOLS:
        return "setup"
    if tool in WAIT_TOOLS:
        return "wait"
    if tool in LOOK_TOOLS or tool.startswith(LOOK_PREFIXES):
        return "look"
    return "act"


def step_parts(st):
    """A run_steps step as its tool and arguments, written ``{"tool": ..., "args": ...}`` or as ``{tool: args}``."""
    if "tool" in st:
        return str(st["tool"]), st.get("args") if isinstance(st.get("args"), dict) else {}
    name, args = next(iter(st.items()), ("?", {}))
    return str(name), args if isinstance(args, dict) else {}


def arm_steps(tool, inp):
    """Another driver's call as the steps it takes, each a name and its arguments: an agent-desktop tool less its
    ``desktop_`` prefix, or its batch's commands, the command lines macos-harness's one tool runs, and the app calls
    Codex Computer Use's and Aside Computer Use's JavaScript makes, whose APIs share their methods' names; None for
    cua-driver's."""
    inp = inp if isinstance(inp, dict) else {}
    if tool in ("js", "repl"):
        return cua_steps(inp.get("code")) or [(tool, {})]
    if tool == "js_reset":
        return [("js_reset", {})]
    if tool == "desktop_batch":
        batch = jparse(inp.get("commands_json")) or []
        return [(str(c.get("command")), c.get("args") or {}) for c in batch if isinstance(c, dict)] or [("batch", {})]
    if tool.startswith("desktop_"):
        return [(tool.removeprefix("desktop_"), inp)]
    if tool == "macos_harness":
        steps = []
        for line in inp.get("commands") or []:
            if not isinstance(line, list) or not line:
                continue
            args, words = {}, [str(w) for w in line[1:]]
            for k, word in enumerate(words):
                if word.startswith("--"):
                    nxt = words[k + 1] if k + 1 < len(words) else None
                    args[word[2:]] = nxt if nxt is not None and not nxt.startswith("--") else True
            steps.append((str(line[0]), args))
        return steps or [("macos_harness", {})]
    return None


def cua_steps(code):
    """The cua API calls in Codex Computer Use's ``js`` code, in order, as steps: an element by its index, a point
    ``[x, y]``, and the text, key, value or direction each takes."""
    steps = []
    for method, raw in CUA_CALL.findall(code or ""):
        args, step = jparse("[" + re.sub(r"'([^'\\]*)'", r'"\1"', raw) + "]") or [], {}
        first = args[0] if args else None
        if method == "getApp" and isinstance(first, str):
            step["app"] = first
        elif method == "drag" and len(args) > 1 and all(isinstance(a, list) and len(a) == 2 for a in args[:2]):
            step = {"from_xy": ",".join(map(str, args[0])), "to_xy": ",".join(map(str, args[1]))}
        elif isinstance(first, list) and len(first) == 2:
            step["xy"] = ",".join(map(str, first))
        elif isinstance(first, (int, float)) and not isinstance(first, bool):
            step["element_index"] = first
        if method in ("setValue", "typeText") and isinstance(args[-1] if args else None, str):
            step["value" if method == "setValue" else "text"] = args[-1]
        if method == "pressKey" and isinstance(first, str):
            step["key"] = first
        if method == "scroll" and len(args) > 1:
            step["direction"] = args[1]
        steps.append((CUA_STEPS[method], step))
    return steps


def arm_step(name, args):
    """A step of another driver's as the lane says it: its verb, and the element, point or text it acts on."""
    point = lambda a, b: f"({args[a]}, {args[b]})" if a in args and b in args else None
    xy = lambda key: f"({args[key].replace(',', ', ')})" if isinstance(args.get(key), str) else None
    ref = lambda key: f"element {args[key].rsplit(':', 1)[-1]}" if isinstance(args.get(key), str) else None
    if args.get("help") is True:
        return "Read help", humanize(name).lower()
    if name == "drag":
        start = xy("from_xy") or point("from_x", "from_y") or ref("from")
        end = xy("to_xy") or point("to_x", "to_y") or ref("to")
        obj = f"from {start} to {end}" if start and end else ""
    elif args.get("text") is not None or args.get("value") is not None:
        obj = f"“{show_text(str(args.get('text') if args.get('text') is not None else args.get('value')))}”"
    elif args.get("keys") or args.get("key"):
        obj = keys_text(args.get("keys") or args.get("key"))
    elif args.get("ref_id") or args.get("element_index") is not None:
        obj = f"element {str(args.get('ref_id') or args.get('element_index')).rsplit(':', 1)[-1]}"
    elif xy("xy") or point("x", "y"):
        obj = f"at {xy('xy') or point('x', 'y')}"
    elif name == "scroll":
        obj = " ".join(str(args[k]) for k in ("direction", "pages", "amount") if k in args)
    elif name == "wait" and str(args.get("ms", "")).isdigit():
        obj = f"{int(args['ms']) / 1000:g} s"
    elif name == "find":
        obj = clean(" ".join(str(args[k]) for k in ("role", "name", "text") if args.get(k)), 32)
    else:
        obj = ""
    return ARM_VERBS.get(name) or humanize(name), obj


def err_text(res):
    text = re.sub(r"</?tool_use_error>", "", res or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "error"
    pick = next((ln for ln in lines if "ERROR (" in ln), lines[0])
    pick = re.sub(r"^\d+\.\s+\w+\s+ERROR \([^)]*\):\s*", "", pick)
    pick = re.sub(r"^Error:\s*", "", pick)
    cut = re.search(r"(?<=.{48})[.;](\s|$)", pick)
    if cut:
        pick = pick[: cut.start()]
    return clean(pick, 170)


def keys_text(keys, repeat=None):
    if isinstance(keys, str):
        keys = [keys]
    text = "+".join(str(k) for k in keys or [])
    return text + (f" ×{repeat}" if repeat and repeat > 1 else "")


def humanize(tool):
    return tool.replace("_", " ").strip().capitalize()


def describe(call, res, desk):
    tool, inp = call["tool"], call.get("input") or {}
    if not isinstance(inp, dict):
        inp = {}
    steps = arm_steps(tool, inp)
    if steps is not None:
        said = [arm_step(name, args) for name, args in steps]
        verb, obj = said[0] if len(said) == 1 else (f"Run {len(said)} steps", " → ".join(
            f"{v.lower()} {o}".strip() for v, o in said[:2]) + (f" → +{len(said) - 2} more" if len(said) > 2 else ""))
        where = next((args["app"] for _, args in steps if isinstance(args.get("app"), str)), None)
        return {"verb": verb, "obj": obj, "where": clean(where, 48) if where else None, "pt": None, "win": None}
    verb, obj, where, pt = humanize(tool), "", None, None
    wid, win = desk.window(inp.get("window_id"), inp.get("pid"))
    count = inp.get("count") or inp.get("clicks") or 1

    def click_verb(base="Click"):
        n = int(count) if str(count).isdigit() else 1
        return {2: "Double-click", 3: "Triple-click"}.get(n, base)

    def target_from_token(token):
        nonlocal wid, win
        el, snap = desk.element(token)
        if snap and win is None:
            wid, win = desk.window(snap.get("win"), snap.get("pid"))
        if el:
            name = el.get("name")
            label = f"“{name}”" if name else f"{el.get('role') or 'element'} [{token.partition(':')[2]}]"
            fr = el.get("frame")
            if isinstance(fr, dict) and None not in (fr.get("x"), fr.get("y")):
                return label, desk.on_screen(fr["x"] + (fr.get("w") or 0) / 2, fr["y"] + (fr.get("h") or 0) / 2)
            return label, None
        return f"element [{token.partition(':')[2]}]", None

    def window_point(x, y):
        m = SCREEN_POINT.search(res or "")
        if m:
            return desk.on_screen(float(m[1]), float(m[2]))
        if win and win.get("w") is not None and isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return desk.on_screen(win["x"] + x, win["y"] + y)
        return None

    if tool == "Skill":
        verb, obj = "Load skill", inp.get("skill") or ""
    elif tool == "Read":
        verb, obj = "Read file", inp.get("file_path") or ""
    elif tool == "list_windows":
        verb = "List windows"
        if inp.get("pid") is not None:
            obj = "of one app"
    elif tool == "list_apps":
        verb = "List apps"
    elif tool in ("get_window_state", "get_accessibility_tree"):
        verb = "Read window"
        if inp.get("query"):
            obj = f"search “{clean(str(inp['query']), 28)}”"
        elif call.get("image"):
            obj = "with screenshot"
    elif tool == "get_desktop_state":
        verb, obj = "Read desktop", "with screenshot" if call.get("image") else ""
    elif tool in ("computer_screenshot", "screenshot"):
        verb = "Screenshot"
        region = inp.get("region")
        if isinstance(region, list) and len(region) == 4:
            obj = f"of a region {round(region[2] - region[0])}×{round(region[3] - region[1])}"
    elif tool == "zoom":
        verb, obj = "Zoom", "into a region"
    elif tool == "get_guide":
        verb, obj = "Read guide", inp.get("topic") or ""
    elif tool in ("click", "double_click", "right_click"):
        verb = {"double_click": "Double-click", "right_click": "Right-click"}.get(tool) or click_verb()
        if inp.get("element_token"):
            obj, pt = target_from_token(inp["element_token"])
        elif "x" in inp and "y" in inp:
            obj, pt = f"at ({inp['x']}, {inp['y']})", window_point(inp["x"], inp["y"])
    elif tool in ("computer_click", "computer_double_click"):
        verb = "Double-click" if tool == "computer_double_click" else click_verb()
        if inp.get("button") in ("right", "middle"):
            verb = f"{inp['button'].title()}-click"
        m = CLICKED_AT.search(res or "")
        if m:
            pt = desk.frame_point(float(m[1]), float(m[2]), m[3])
        elif not call.get("error") and isinstance(inp.get("x"), (int, float)):
            pt = desk.frame_point(inp["x"], inp["y"], desk.last_frame)
        x, y = inp.get("x"), inp.get("y")
        obj = f"at ({x}, {y})" if x is not None else ""
    elif tool in ("type_text", "computer_type", "set_value", "browser_type"):
        verb = "Set value" if tool == "set_value" else "Type"
        obj = f"“{show_text(str(inp.get('text') or inp.get('value') or ''))}”"
        if inp.get("element_token"):
            target, pt = target_from_token(inp["element_token"])
            obj += f" into {target}"
    elif tool in ("press_key", "hotkey", "computer_key"):
        verb = "Press"
        keys = inp.get("keys") or inp.get("key")
        mods = inp.get("modifiers") or []
        if isinstance(keys, str) and mods:
            keys = list(mods) + [keys]
        obj = keys_text(keys, inp.get("repeat"))
    elif tool in ("scroll", "computer_scroll"):
        verb = "Scroll"
        obj = " ".join(str(v) for v in (inp.get("direction"), inp.get("amount")) if v is not None)
        if tool == "computer_scroll":
            m = CLICKED_AT.search(res or "")
            if m:
                pt = desk.frame_point(float(m[1]), float(m[2]), m[3])
            elif isinstance(inp.get("x"), (int, float)) and not call.get("error"):
                pt = desk.frame_point(inp["x"], inp["y"], desk.last_frame)
        elif inp.get("element_token"):
            _, pt = target_from_token(inp["element_token"])
        elif "x" in inp:
            pt = window_point(inp.get("x"), inp.get("y"))
    elif tool in ("drag", "computer_drag"):
        verb = "Drag"
    elif tool == "invoke_menu":
        verb, obj = "Menu", " › ".join(str(p) for p in inp.get("path") or [])
    elif tool == "run_steps":
        steps = [step_parts(st) for st in inp.get("steps") or [] if isinstance(st, dict)]
        base = {k: inp[k] for k in ("pid", "window_id") if k in inp}
        inner = [describe({"tool": name, "input": {**base, **args}, "error": call.get("error")}, res, desk)
                 for name, args in steps[:3]]
        if len(steps) == 1 and inner:
            d = inner[0]
            verb, obj, pt = d["verb"], d["obj"], d["pt"]
        else:
            verb = f"Run {len(steps)} steps"
            obj = " → ".join(f"{d['verb'].lower()} {d['obj']}".strip() for d in inner[:2])
            if len(steps) > 2:
                obj += f" → +{len(steps) - 2} more"
            pt = next((d["pt"] for d in inner if d["pt"]), None)
        if win is None:
            first = next((args for _, args in steps if args), {})
            wid, win = desk.window(first.get("window_id"), first.get("pid"))
            if win is None:
                tok = first.get("element_token")
                _, snap = desk.element(tok)
                if snap:
                    wid, win = desk.window(snap.get("win"), snap.get("pid"))
    elif tool == "run_script":
        verb = "Run script"
        script = str(inp.get("script") or "")
        m_pid, m_win = re.search(r"pid\s*:\s*(\d+)", script), re.search(r"windowId\s*:\s*(\d+)", script)
        if win is None and (m_pid or m_win):
            wid, win = desk.window(int(m_win[1]) if m_win else None, int(m_pid[1]) if m_pid else None)
        parsed = jparse(res) or {}
        ops = [c for c in parsed.get("calls") or [] if isinstance(c, dict) and c.get("op") not in ("get_app",)]
        if ops:
            names = [str(c.get("op")) for c in ops]
            first = next((c.get("detail") for c in ops if c.get("detail")), "")
            m = re.search(r'"([^"]+)"', first or "")
            if len(ops) == 1 and m:
                verb, obj = humanize(names[0]), f"“{clean(m[1], 48)}”"
            else:
                counts = {n: names.count(n) for n in dict.fromkeys(names)}
                obj = ", ".join(f"{n.replace('_', ' ')} ×{k}" if k > 1 else n.replace("_", " ") for n, k in counts.items())
        else:
            lines = [ln for ln in script.splitlines() if ln.strip()]
            obj = f"{len(lines)} line{'s' if len(lines) != 1 else ''} of driver script"
    elif tool == "set_window_frame":
        verb = "Move window"
        if None not in (inp.get("x"), inp.get("y")):
            obj = f"to ({inp['x']}, {inp['y']}) {inp.get('width')}×{inp.get('height')}"
    elif tool == "bring_to_front":
        verb = "Bring to front"
    elif tool == "launch_app":
        verb = "Launch app"
        obj = clean(str(inp.get("name") or inp.get("app") or inp.get("bundle_id") or inp.get("path") or ""), 40)
    elif tool == "clipboard_write":
        verb, obj = "Write clipboard", f"{len(str(inp.get('text') or ''))} characters"
    elif tool == "clipboard_read":
        verb = "Read clipboard"
    elif tool in WAIT_TOOLS:
        verb = "Wait"
        ms = inp.get("ms") or inp.get("milliseconds")
        if ms:
            obj = f"{ms / 1000:g} s"
    elif tool == "get_screen_size":
        verb = "Read screen size"
    elif tool.startswith("browser_"):
        verb = "Browser " + tool.removeprefix("browser_").replace("_", " ")
        obj = clean(str(inp.get("url") or inp.get("text") or ""), 40)
    if win:
        where = win.get("title") or app_name(win.get("app"))
    elif inp.get("pid") is not None and tool not in ("list_windows",):
        where = f"pid {inp['pid']}"
    return {
        "verb": verb, "obj": obj, "where": clean(where, 48) if where else None, "pt": pt,
        "win": desk.outer(win) if win else None,
    }


def calls_of(timeline, results, cfg):
    desk = Desk(cfg)
    out = []
    for c in timeline.get("calls") or []:
        res = results.get(c.get("id")) or c.get("result") or ""
        d = describe(c, res, desk)
        out.append({
            "i": c["i"], "t0": rnd(c.get("t0")), "t1": rnd(c.get("t1")), "turn": c.get("turn"), "tool": c["tool"],
            "server": c.get("server"), "kind": kind_of(c["tool"], c.get("input")), **d,
            "err": err_text(res) if c.get("error") else None, "img": bool(c.get("image")),
        })
        desk.learn(c, res)
    t_last, pt_last, pt_t = None, None, None
    for c in out:
        if c["t0"] is None:
            c["t0"] = t_last
        t_last = c["t0"]
        c["near"] = None
        if c["pt"] and not c["err"]:
            pt_last, pt_t = c["pt"], c["t0"]
        elif c["tool"] in KEYBOARD_TOOLS and not c["err"] and pt_last and c["t0"] is not None and c["t0"] - pt_t < 8:
            c["near"] = pt_last
    return [c for c in out if c["t0"] is not None]


def rnd(v, n=3):
    return None if v is None else round(float(v), n)


def bid_of(front):
    if not isinstance(front, dict):
        return None
    bid = front.get("bid")
    if isinstance(bid, str) and bid:
        return bid
    pid = front.get("pid")
    return f"pid:{pid}" if isinstance(pid, int) and pid >= 0 else None


def task_owners(line):
    return {o for o in line.get("above") or [] if isinstance(o, str) and not OVERLAY_RE.search(o)}


def user_lane(lines, rec, cfg):
    starts = [i for i, ln in enumerate(lines) if ln.get("ev") == "start"]
    lines = lines[starts[-1]:] if starts else lines
    a = next((i for i, ln in enumerate(lines) if ln.get("ev") == "armed"), None)
    if a is None:
        return None
    b = next((i for i in range(a + 1, len(lines)) if lines[i].get("ev") == "disarmed"), len(lines) - 1)
    window = lines[a: b + 1]
    armed, events, typed, blocked = window[0], [], [], []
    origin = armed.get("mouse")
    prev_front = bid_of(armed.get("front"))
    prev_above = task_owners(armed)
    prev_clip, prev_space, prev_sheet = armed.get("clip"), armed.get("onspace"), armed.get("sheet")
    in_ep, end = False, None

    def add(t, c, what):
        events.append({"t": rnd(rec(t)), "c": c, "what": what})

    for ln in window[1:]:
        ev, t = ln.get("ev"), ln["t"]
        last = ln is window[-1] and ev == "disarmed"
        if ev in FRONT_EVENTS:
            f = bid_of(ln.get("front"))
            if f is not None:
                if f != prev_front and f != SENTINEL_BID:
                    add(t, "activation", f"{app_name(f)} became the active app")
                prev_front = f
        if ev in ("s", "disarmed"):
            if "above_n" in ln:
                now = task_owners(ln)
                new = now - prev_above
                if new:
                    add(t, "window_raised", f"{', '.join(sorted(app_name(o) for o in new))} raised over the user's window")
                prev_above = now
            clip = ln.get("clip")
            if isinstance(clip, int) and isinstance(prev_clip, int) and clip > prev_clip:
                add(t, "clipboard", "the user's clipboard changed")
            if isinstance(clip, int):
                prev_clip = clip
            if prev_space is True and ln.get("onspace") is False:
                add(t, "space", "the user's desktop was switched away")
            if "onspace" in ln:
                prev_space = ln.get("onspace")
            if ln.get("sheet") is True and prev_sheet is False:
                add(t, "dialog", "a dialog opened over the user's window")
            if "sheet" in ln:
                prev_sheet = ln.get("sheet")
        if last:
            continue
        if ev == "s":
            p = ln.get("mouse")
            if origin is None and isinstance(p, list):
                origin = p
            if isinstance(p, list) and isinstance(origin, list) and len(p) == 2 and len(origin) == 2:
                d = math.hypot(p[0] - origin[0], p[1] - origin[1])
                if d > POINTER_STILL_PX and not in_ep:
                    add(t, "pointer", f"the pointer moved {d:.0f} px")
                in_ep = d > POINTER_STILL_PX
        elif ev == "didResignKey":
            add(t, "key_focus", "the user's window lost keyboard focus")
        elif ev == "didResignActive":
            add(t, "activation", "the user's app was deactivated")
        elif ev == "didBecomeActive":
            add(t, "activation", "the user's app was activated again")
        elif ev == "keyDown":
            ch = show_text(str(ln.get("chars") or ""), 6)
            add(t, "typing", f"a keystroke{f' “{ch}”' if ch else ''} landed in the user's window")
        elif ev == "mouseDown":
            add(t, "typing", "a click landed in the user's window")
        elif ev == "scrollWheel":
            add(t, "typing", "a scroll landed in the user's window")
        elif ev == "user_blocked":
            blocked.append(rnd(rec(t)))
            add(t, "typing", "the user's keystroke was blocked")
        elif ev == "user_text_disrupted":
            add(t, "typing", "the user's text was changed under them")
        elif ev == "user_type":
            typed.append(rnd(rec(t)))
        elif ev == "space":
            add(t, "space", "the user's desktop was switched")
        elif ev == "close_refused":
            add(t, "close", "something tried to close the user's window")
        elif ev == "user_text":
            end = {"intact": ln.get("intact"), "expected": ln.get("expected_len"), "actual": ln.get("actual_len")}
            if ln.get("intact") is False:
                add(t, "typing", "the user's text is not what they typed")
    if end is None:
        ut = next((ln for ln in lines[b:] if ln.get("ev") == "user_text"), None)
        if ut:
            end = {"intact": ut.get("intact"), "expected": ut.get("expected_len"), "actual": ut.get("actual_len")}
            if ut.get("intact") is False:
                add(ut["t"], "typing", "the user's text is not what they typed")
    events.sort(key=lambda e: e["t"])
    return {"frame": cfg["user_frame"], "script": cfg["user_script"], "typed": typed, "blocked": blocked,
            "events": events, "end": end, "armed": rnd(rec(armed["t"])), "disarmed": rnd(rec(window[-1]["t"]))}


def guard_events(lines, rec):
    out = []
    for ln in lines:
        if ln.get("ev") in ("gui_only_violation", "gui_only_transient") and ln.get("armed", True):
            out.append({"t": rnd(rec(ln["t"])), "violation": ln["ev"] == "gui_only_violation",
                        "what": str(ln.get("detail") or ln.get("kind") or "side door")})
    return out


def ending(trial, texts):
    err = trial.get("agent_error") or ""
    m = re.search(r"maximum number of turns \((\d+)\)", err)
    if m:
        return f"Hit the {m[1]}-turn limit"
    if re.search(r"(?i)time(d)? ?out", err):
        return "Ran out of time"
    if err:
        return clean(err, 80)
    last = (texts[-1]["text"].strip() if texts else "")
    if last.upper().startswith("DONE"):
        return "Replied DONE"
    if last.upper().startswith("BLOCKED"):
        return clean("Replied " + last, 90)
    return None


def dataset_rel(folder, data_dir):
    parts = folder.resolve().parts
    if "runs" in parts:
        k = len(parts) - 1 - parts[::-1].index("runs")
        return Path(*parts[k:])
    return folder.resolve().relative_to(Path(data_dir).resolve())


def task_id(trial, condition):
    task = trial.get("task") or trial["trial_id"]
    task = re.sub(rf"-{re.escape(condition)}$", "", task)
    return re.sub(r"-r\d+$", "", task)


def load(folder, cfg, data_dir=None):
    use_names(cfg)
    folder = Path(folder)
    trial = read_json(folder / "trial.json")
    timeline = read_json(folder / "timeline.json", {}) or {}
    manifest = read_json(folder / "manifest.json", {}) or {}
    start = epoch(manifest.get("started_at") or trial["started_at"])
    condition = trial.get("condition") or trial["task"].rsplit("-", 1)[-1]
    task = task_id(trial, condition)
    rel = dataset_rel(folder, data_dir or folder.parent)
    uid = re.sub(r"[^A-Za-z0-9._-]+", "-", "--".join(p for p in rel.parts if p != "runs")).strip("-")
    h = halves(trial, folder)
    calls = calls_of(timeline, tool_results(folder), cfg)
    texts = [{"t": rnd(x["t"]), "turn": x.get("turn"), "text": clean(x.get("text"), 600)}
             for x in timeline.get("texts") or [] if x.get("t") is not None and (x.get("text") or "").strip()]
    sentinel = read_lines(folder / "sentinel.jsonl")
    if sentinel:
        lines, rec = sentinel, (lambda t: t / 1000 - start)
    else:
        lines = sorted([*(timeline.get("user") or []), *({**s, "ev": "s", "front": {"bid": s.get("front")}}
                                                          for s in timeline.get("samples") or [])],
                       key=lambda ln: ln["t"])
        lines, rec = [ln for ln in lines if isinstance(ln.get("t"), (int, float))], (lambda t: t)
    user = user_lane(lines, rec, cfg) if condition == "background" and lines else None
    run = rel.parts[-2] if len(rel.parts) >= 4 and rel.parts[0] == "runs" else None
    m_run = re.search(r"-r(\d+)(?:-|$)", folder.name)
    run_index = trial.get("run_index", int(m_run[1]) if m_run else None)
    meta = {
        "id": trial["trial_id"], "uid": uid, "rel": rel.as_posix(), "run_index": run_index, "seed": trial.get("seed"),
        "os": trial.get("os") or "linux", "driver": trial.get("driver") or DRIVER, "task": task,
        "probe": trial.get("probe"), "condition": condition, "model": trial.get("model"),
        "model_name": model_name(trial.get("model") or "?", cfg),
        "harness": trial.get("harness"), "harness_version": trial.get("harness_version"), "effort": trial.get("effort"),
        "computer": trial.get("computer"), "started_at": trial.get("started_at"), "run": run,
        "duration": rnd(trial.get("duration_s"), 1), "cost": rnd(trial.get("cost_usd"), 2),
        "turns": trial.get("num_turns"), "model_calls": trial.get("model_calls"),
        "tool_calls": trial.get("tool_calls", len(calls)), "tool_errors": trial.get("tool_errors"),
        "ending": ending(trial, texts), "reward": trial.get("reward"), "passed": passed(h, condition),
        "grade": h, "user_lane": user is not None, "prompt": trial.get("prompt"),
    }
    web = {
        "v": 1, "id": meta["id"], "duration": rnd(timeline.get("duration")),
        "armed": [rnd(timeline.get("armed_at")), rnd(timeline.get("disarmed_at"))],
        "screen": cfg["screen"], "calls": calls, "texts": texts,
        "compactions": [rnd(t) for t in timeline.get("compactions") or [] if t is not None],
        "user": user, "guard": guard_events(lines, rec) if lines else [],
    }
    return {"folder": folder, "meta": meta, "web": web}
