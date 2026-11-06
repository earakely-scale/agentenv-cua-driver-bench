"""A trial's failure as a short clip for the gallery: the recording cropped to the windows that matter, with the pair's
overlays and AGENT/USER strip, under a chip naming what goes wrong. It plays from a few seconds before the moment, or
the agent's whole run sped up when the failure is the run itself, and ends on a freeze with the grade; an MP4 for the
Space and a GIF of a few MB for the card."""
import json
import math
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from . import media, pair
from .hero import C, FPS, Scene, fit, font, nice_speed, pill

W, EDGE = 720, 16
PW = W - 2 * EDGE
PV = round(PW * 9 / 16)
HDR, STRIP = 76, 81
TOP = HDR + pair.LAB
H = TOP + PV + STRIP
SECONDS, SHOWN, HOLD, MAX_MB = 7, 2.6, 3.0, 3
#: Each moment's mode's seconds of the trial before and after the moment, and its speed: a disturbance in real time,
#: the driver's refusals over the next quarter minute at twice it.
SPANS = {"refused": (2.0, 16.5, 2)}
SPAN = (3.0, 4.5, 1)
#: The user's log events a disturbing mode's moment is the first of, in the order its callout names them.
EVENTS = {"focus": ("key_focus",), "raise": ("window_raised",), "dialog": ("dialog", "window_raised", "key_focus")}
REFUSED = "Background delivery is not available"


def render(trial, want, cat, cfg, out_dir, name):
    """``trial``'s failure as the gallery entry ``want`` names it (its mode and title, and the screen region to show
    when the trial's calls place no window), as ``name``.gif and ``name``.mp4."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = pair.Panel(trial, cat, cfg, EDGE, TOP, (PW, PV))
    panel.view = tuple(want["view"]) if want.get("view") else pair.view(panel)
    sc = panel.scene
    a, b, speed, at = window(sc, panel.m, want)
    crop = (panel.view[0] / sc.sw, panel.view[1] / sc.sh, panel.view[2] / sc.sw, panel.view[3] / sc.sh)
    n = max(1, math.ceil((b - a) * FPS / speed))
    notes = [] if at is None else callouts(panel, want["mode"])
    gif, mp4 = out_dir / f"{name}.gif", out_dir / f"{name}.mp4"
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        save = pair.saver(Path(tmp))
        for k, buf in enumerate(media.frames(trial["folder"] / "recording.mp4", a, FPS / speed, n, (PW, PV), crop)):
            img = frame(panel, want, Image.frombytes("RGB", (PW, PV), buf), a + k * speed / FPS, speed, notes)
            save(img)
        save(ending(img, panel), HOLD)
        pair.encode(Path(tmp), gif, mp4, MAX_MB * 1e6)
    return gif, mp4


def window(sc, m, want):
    """The part of the trial a clip plays, its speed and its moment: around the moment as its mode's span says, or the
    agent's whole run sped up to about SECONDS when the mode has no one moment."""
    at = want.get("at") or moment(sc, m, want["mode"])
    if at is None:
        return sc.start, sc.end, nice_speed(sc.end - sc.start, SECONDS), None
    lead, tail, speed = SPANS.get(want["mode"], SPAN)
    return max(sc.start, at - lead), min(sc.end, at + tail), speed, at


def moment(sc, m, mode):
    """When a clip's failure happens on the trial's clock: the user's first disturbance of the mode's kind, the first
    call the driver refused to deliver in the background (one with a point to ring, when there is one), or the first
    call the GUI-only grade names; None for a mode the whole run shows, running out of turns or a pass."""
    if mode in EVENTS:
        return min(e["t"] for e in sc.user["events"] if e["c"] in EVENTS[mode])
    if mode == "refused":
        refused = [c for c in sc.calls if (c.get("err") or "").startswith(REFUSED)]
        return next((c for c in refused if c.get("pt")), refused[0])["t0"]
    if mode == "gui":
        return side_door(sc, m)["t0"]
    return None


def side_door(sc, m):
    """The first call to a tool the GUI-only grade names, as ``mcp__server__tool:argument``."""
    tools = {v.rsplit("__", 1)[-1].split(":")[0] for v in m["grade"]["gui_only"]["violations"]}
    return next(c for c in sc.calls if c["tool"] in tools)


def callouts(panel, mode):
    """What the clip says over the video as it happens, each from its time: the kinds of disturbance the user hadn't had
    yet, the mode's own first; each driver call that failed, with the driver's words; and in a side-door clip the call
    that opened it, with its arguments."""
    sc, crit = panel.scene, [k["id"] for k in panel.scene.cat["criteria"]]
    first = EVENTS.get(mode, ())
    out, seen = [], set()
    for mo in sc.moments:
        new = {e["c"]: e for e in mo["items"] if e["c"] in crit and e["c"] not in seen}
        seen |= set(new)
        said = [cap(e["what"]) for e in sorted(new.values(), key=lambda e: (
            first.index(e["c"]) if e["c"] in first else len(first), crit.index(e["c"])))]
        if said:
            out.append({"t": mo["t"], "head": said[0], "lines": said[1:]})
    raw = {x["i"]: x.get("input") or {} for x in
           json.loads((panel.trial["folder"] / "timeline.json").read_text()).get("calls") or []}
    door = side_door(sc, panel.m) if mode == "gui" else None
    for c in sc.calls:
        inp = raw.get(c["i"], {})
        if c is door:
            args = " ".join(f"{k}: {v if isinstance(v, str) else json.dumps(v)}" for k, v in inp.items())
            out.append({"t": c["t0"], "head": f"{c['tool']}, called with", "text": args, "mono": True})
        elif c.get("err") and c["kind"] != "setup":
            what = c["obj"] or next((v for v in inp.values() if isinstance(v, str)), "")
            out.append({"t": c["t0"], "head": f"{c['verb']} {what}".strip(), "text": c["err"]})
    return sorted(out, key=lambda x: x["t"])


def cap(text):
    return text[:1].upper() + text[1:]


def frame(panel, want, video, t, speed, notes):
    img = Image.new("RGB", (W, H), C["bg"])
    d = ImageDraw.Draw(img, "RGBA")
    header(d, panel, want, speed)
    panel.draw(img, d, video, t, speed)
    meter(d, panel, t)
    note = next((x for x in reversed(notes) if x["t"] <= t), None)
    if note and t - note["t"] < SHOWN * speed:
        callout(d, note)
    return img


def header(d, panel, want, speed):
    """The chip naming what goes wrong, the bench's name, and the OS, driver, model and task with the playing speed."""
    m, cat = panel.m, panel.scene.cat
    brand, on = "CUA DRIVER BENCH", " on AgentEnv"
    bw = d.textlength(brand, font=font(800, 12)) + d.textlength(on, font=font(500, 12))
    d.text((W - EDGE - bw, 20), brand, font=font(800, 12), fill=C["ink2"])
    d.text((W - EDGE - d.textlength(on, font=font(500, 12)), 20), on, font=font(500, 12), fill=C["ink4"])
    f = font(800, 20)
    title = fit(d, ("✓  " if m["passed"] else "✗  ") + want["title"], f, PW - bw - 44)
    pill(d, (EDGE, 9, EDGE + d.textlength(title, font=f) + 26, 43), fill=C["good"] if m["passed"] else C["bad"], r=9)
    d.text((EDGE + 13, 13.5), title, font=f, fill=(6, 32, 18) if m["passed"] else (255, 255, 255))
    osn = next((o["name"] for o in cat["oses"] if o["id"] == m["os"]), m["os"])
    drv = next((dv.get("label") or dv["name"] for dv in cat["drivers"] if dv["id"] == m["driver"]), m["driver"])
    setup, fb, fr = f"{osn} · {drv} · {m['model_name']}", font(700, 13.5), font(500, 13.5)
    pace = "real time" if speed == 1 else f"{speed}× speed"
    pw_ = d.textlength(pace, font=font(600, 13))
    d.text((W - EDGE - pw_, 53.5), pace, font=font(600, 13), fill=C["ink2"])
    d.text((EDGE, 53), setup, font=fb, fill=C["ink"])
    task = panel.scene.task
    x = EDGE + d.textlength(setup, font=fb) + 12
    named = f"{(task.get('probe') or m['task']).replace('CDB-', '')} · {task.get('title', '')}"
    d.text((x, 53), fit(d, named, fr, W - EDGE - pw_ - 14 - x), font=fr, fill=C["ink3"])
    d.line((EDGE, HDR - 2, W - EDGE, HDR - 2), fill=C["line"], width=1)


def meter(d, panel, t):
    """The turns the agent has used of the prompt's limit, at the right of the condition's row, red once all are."""
    limit = re.search(r"at most (\d+) turns", panel.m.get("prompt") or "")
    if not limit:
        return
    sc, total, y = panel.scene, int(limit[1]), TOP - pair.LAB + 8
    i = sc.cur(t)
    used = min(total, sc.calls[i]["turn"] or 0) if i >= 0 else 0
    full = used >= total
    label, fm = f"{used} of {total}", font("mono", 11)
    x1 = W - EDGE - d.textlength(label, font=fm)
    d.text((x1, y), label, font=fm, fill=C["bad"] if full else C["ink2"])
    x0 = x1 - 10 - total * 4
    for k in range(total):
        d.rectangle((x0 + 4 * k, y + 2, x0 + 4 * k + 2, y + 14), fill=(C["bad"] if full else C["agent"]) if k < used
                    else C["panel2"])
    d.text((x0 - 8 - d.textlength("TURNS", font=font(800, 10)), y + 2), "TURNS", font=font(800, 10), fill=C["ink3"])


def callout(d, note):
    """``note`` over the video's top right corner: what just went wrong in a line, and up to three more."""
    fh, fb = font(700, 14), font("mono", 12) if note.get("mono") else font(500, 12.5)
    maxw = round(PW * 0.64) - 26
    head = fit(d, "✗  " + note["head"], fh, maxw)
    lines = [fit(d, ln, fb, maxw) for ln in note.get("lines") or []]
    if note.get("text"):
        lines += Scene.wrap(d, note["text"], fb, maxw)
    if len(lines) > 3:
        lines = lines[:2] + [fit(d, " ".join(lines[2:]), fb, maxw)]
    w = max([d.textlength(head, font=fh)] + [d.textlength(ln, font=fb) for ln in lines]) + 26
    x1, y0 = EDGE + PW - 10, TOP + 10
    box = (x1 - w, y0, x1, y0 + 31 + 18 * len(lines))
    pill(d, box, fill=(8, 11, 18, 236), r=8, outline=C["bad"] + (200,))
    d.rectangle((box[0] + 1, box[1] + 8, box[0] + 4, box[3] - 8), fill=C["bad"])
    d.text((box[0] + 14, y0 + 7), head, font=fh, fill=(255, 178, 178))
    for k, line in enumerate(lines):
        d.text((box[0] + 14, y0 + 28 + 18 * k), line, font=fb, fill=C["ink2"])


def ending(base, panel):
    """The last frame under the trial's grade, with how the agent's run ended."""
    img = base.copy()
    d = ImageDraw.Draw(img, "RGBA")
    panel.grade(img, d)
    m, texts = panel.m, panel.scene.texts
    said = f"“{re.sub(r'[*`]', '', texts[-1]['text'])}”" if texts else ""
    if m["ending"] and not m["ending"].startswith("Replied"):
        words = f"{m['ending']}." + (f" Its last words: {said}" if said else "")
    else:
        words = f"Its reply: {said}" if said else ""
    if not words:
        return img
    x, y, f = EDGE + 20, TOP + PV - 98, font(500, 13.5)
    d.text((x, y), "HOW IT ENDED", font=font(800, 10.5), fill=C["ink3"])
    lines = Scene.wrap(d, words, f, PW - 40)
    if len(lines) > 3:
        lines = lines[:2] + [fit(d, " ".join(lines[2:]), f, PW - 40)]
    for k, line in enumerate(lines):
        d.text((x, y + 17 + 20 * k), line, font=f, fill=C["ink"])
    return img
