"""One task's foreground and background trials side by side, the same model, driver and run, played at one speed: a GIF
for the card and an MP4 for the Space. Each panel is the trial's recording at half width with what the agent acted on
and the user's window drawn at that scale; the words sit in the header and in each panel's strip, where they stay
readable."""
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import media
from .hero import C, FPS, Scene, fit, fmt, font, mins, nice_speed, pct, pill

W = 960
EDGE, GAP = 16, 16
PW = (W - 2 * EDGE - GAP) // 2
PV = round(PW * 9 / 16)
HDR, LAB, STRIP, FOOT = 60, 32, 80, 34
H = HDR + LAB + PV + STRIP + FOOT
TOP = HDR + LAB
WORDS = {"foreground": "the agent has the desktop to itself", "background": "a person keeps typing in their own window"}


class Panel:
    """One trial's half of the frame: its scene for timing and the grade, and where it sits."""

    def __init__(self, trial, cat, cfg, x0):
        self.trial, self.scene, self.x0 = trial, Scene(trial, cat, cfg, 1), x0
        self.m, self.cfg = trial["meta"], cfg
        self.view = (0, 0, self.scene.sw, self.scene.sh)

    @property
    def span(self):
        return self.scene.end - self.scene.start

    def at(self, tau, speed):
        return min(self.scene.end, self.scene.start + tau * speed)

    def px(self, x):
        return self.x0 + (x - self.view[0]) * PW / self.view[2]

    def py(self, y):
        return TOP + (y - self.view[1]) * PV / self.view[3]

    def boxes(self):
        sc = self.scene
        out = [(x, y, x + w, y + h) for x, y, w, h in (c["win"] for c in sc.calls if c.get("win") and c["kind"] != "setup")]
        if self.m["condition"] == "background":
            fx, fy, fw, fh = (sc.user or {}).get("frame") or self.cfg["user_frame"]
            out.append((fx, fy, fx + fw, fy + fh))
        return out

    def draw(self, img, d, video, t, speed):
        sc = self.scene
        img.paste(video, (self.x0, TOP))
        d.rectangle((self.x0 - 1, TOP - 1, self.x0 + PW, TOP + PV), outline=C["line"], width=1)
        self.label(d)
        i = sc.cur(t)
        c = sc.calls[i] if i >= 0 else None
        nxt = sc.calls[i + 1] if 0 <= i + 1 < len(sc.calls) else None
        fresh = c and t - c["t0"] < max(3, min(8, (nxt["t0"] if nxt else sc.end) - c["t0"]))
        if fresh and c.get("win") and c["kind"] != "setup":
            x, y, w, h = c["win"]
            box = (self.px(max(0, x)), self.py(max(0, y)), self.px(min(sc.sw, x + w)), self.py(min(sc.sh, y + h)))
            if box[2] - box[0] > 8 and box[3] - box[1] > 8:
                d.rectangle(box, outline=C["agent"] + (235,), width=2)
        if self.m["condition"] == "background":
            fx, fy, fw, fh = (sc.user or {}).get("frame") or self.cfg["user_frame"]
            box = (self.px(fx), self.py(fy), self.px(fx + fw), self.py(fy + fh))
            broken = self.broken(t)
            recent = next((m for m in reversed(sc.moments) if m["t"] <= t), None)
            flash = recent and t - recent["t"] < 1.3 * speed
            col = C["bad"] if broken or flash else C["user"]
            if flash:
                d.rectangle(box, fill=C["bad"] + (int(80 * (1 - (t - recent["t"]) / (1.3 * speed))),))
            d.rectangle((box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1), outline=(0, 0, 0, 160), width=4)
            d.rectangle(box, outline=col + (255,), width=3 if flash else 2)
            tag = font(800, 10)
            tw = d.textlength("USER", font=tag) + 12
            pill(d, (box[0], box[1] - 17, box[0] + tw, box[1] - 2), fill=col + (255,), r=4)
            d.text((box[0] + 6, box[1] - 15.5), "USER", font=tag, fill=(29, 19, 0) if col == C["user"] else (255, 255, 255))
        p = c and (c.get("pt") or c.get("near")) if fresh else None
        if p and self.view[0] <= p[0] <= self.view[0] + self.view[2] and self.view[1] <= p[1] <= self.view[1] + self.view[3]:
            cx, cy = self.px(p[0]), self.py(p[1])
            col = C["bad"] if c.get("err") else C["agent"]
            age = (t - c["t0"]) / speed
            if age < 0.7:
                rr = 5 + 14 * age / 0.7
                d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=col + (int(255 * (1 - age / 0.7)),), width=2)
            d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=(255, 255, 255, 230), width=2)
            d.ellipse((cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5), outline=col + (255,), width=2)
            d.ellipse((cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5), fill=col + (255,))
        self.strip(d, c, t, speed)

    def broken(self, t):
        sc = self.scene
        final = t >= (sc.web["armed"][1] or sc.dur) - 0.05
        return sc.broken(t) if sc.user or final else set()

    def label(self, d):
        cond = self.m["condition"]
        name = next((c["name"] for c in self.scene.cat["conditions"] if c["id"] == cond), cond)
        col = C["user"] if cond == "background" else C["agent"]
        f = font(800, 10.5)
        cw = d.textlength(name.upper(), font=f) + 16
        y = HDR + 6
        pill(d, (self.x0, y, self.x0 + cw, y + 20), fill=col + (44,), r=10, outline=col + (150,))
        d.text((self.x0 + 8, y + 4), name.upper(), font=f, fill=col)
        d.text((self.x0 + cw + 9, y + 2.5), fit(d, WORDS.get(cond, ""), font(500, 12.5), PW - cw - 10), font=font(500, 12.5),
               fill=C["ink2"])

    def strip(self, d, c, t, speed):
        sc, x0, y0 = self.scene, self.x0, TOP + PV + 8
        f = font(800, 10)
        d.text((x0, y0 + 5), "AGENT", font=f, fill=C["agent"])
        lx = x0 + 52
        if c is None:
            d.text((lx, y0 + 3), "starting…", font=font(500, 12.5), fill=C["ink3"])
        else:
            text = c["verb"] + (f" {c['obj']}" if c.get("obj") else "")
            fb = font(700, 12)
            room = x0 + PW - lx - 70
            shown = fit(d, text, fb, room)
            w = d.textlength(shown, font=fb) + 16
            pill(d, (lx, y0, lx + w, y0 + 21), fill=C["bad"] if c.get("err") else C["agent"], r=6)
            d.text((lx + 8, y0 + 3.5), shown, font=fb, fill=(255, 255, 255))
            n = f"{c['i'] + 1} of {len(sc.calls)}"
            d.text((x0 + PW - d.textlength(n, font=font(500, 11)), y0 + 4.5), n, font=font(500, 11), fill=C["ink4"])
        y1 = y0 + 28
        d.text((x0, y1 + 5), "USER", font=f, fill=C["user"])
        if self.m["condition"] == "background":
            broken = self.broken(t)
            if not broken:
                pill(d, (lx, y1, lx + 196, y1 + 21), fill=C["good_dim"], r=6)
                d.text((lx + 8, y1 + 3), "✓", font=font(800, 12.5), fill=C["good"])
                d.text((lx + 23, y1 + 3.5), "Undisturbed, still typing", font=font(700, 12), fill=C["good"])
            else:
                names = [k["short"] for k in sc.cat["criteria"] if k["id"] in broken]
                text = fit(d, "Disturbed: " + ", ".join(names), font(700, 12), PW - 70)
                w = d.textlength(text, font=font(700, 12)) + 31
                pill(d, (lx, y1, lx + w, y1 + 21), fill=C["bad_dim"], r=6)
                d.text((lx + 8, y1 + 3), "✗", font=font(800, 12.5), fill=C["bad"])
                d.text((lx + 23, y1 + 3.5), text, font=font(700, 12), fill=(255, 178, 178))
        else:
            d.text((lx, y1 + 3.5), "only a witness window; nobody to disturb", font=font(500, 12), fill=C["ink3"])
        self.timeline(d, t, y0 + 56)

    def timeline(self, d, t, y):
        sc, x0 = self.scene, self.x0
        label = f"{fmt(t)} / {fmt(sc.dur)}"
        lw = d.textlength(label, font=font("mono", 11)) + 8
        x1 = x0 + PW - lw
        pill(d, (x0, y, x1, y + 10), fill=C["bg"], r=3)
        span = sc.end - sc.start
        X = lambda tt: x0 + (x1 - x0) * min(1, max(0, (tt - sc.start) / span))
        for c in sc.calls:
            col = C["bad"] if c.get("err") else (C["agent"] if c["kind"] == "act" else C["ink4"])
            d.line((X(c["t0"]), y + 1, X(c["t0"]), y + 5), fill=col, width=1)
        for m in sc.moments:
            d.line((X(m["t"]), y + 5, X(m["t"]), y + 9), fill=C["bad"], width=2)
        ph = X(t)
        d.rectangle((x0, y + 8, ph, y + 10), fill=C["ink2"])
        d.line((ph, y - 2, ph, y + 12), fill=C["ink"], width=2)
        d.text((x1 + 8, y - 2), label, font=font("mono", 11), fill=C["ink2"])

    def grade(self, img, d):
        """The trial's grade over its video, as the hero's card says it, at the panel's size."""
        m, g = self.m, self.m["grade"]
        region = img.crop((self.x0, TOP, self.x0 + PW, TOP + PV)).filter(ImageFilter.GaussianBlur(2))
        img.paste(region, (self.x0, TOP))
        d.rectangle((self.x0, TOP, self.x0 + PW, TOP + PV), fill=(5, 7, 12, 185))
        x, y = self.x0 + 20, TOP + 18
        ok = m["passed"]
        d.text((x, y), "THE GRADE", font=font(800, 10.5), fill=C["ink3"])
        d.text((x, y + 15), "Pass" if ok else "Fail", font=font(800, 30), fill=C["good"] if ok else C["bad"])
        rows = [("Task", (g.get("task") or {}).get("result"), pct((g.get("task") or {}).get("score")))]
        gu = g.get("gui_only") or {}
        rows.append(("GUI only", gu.get("result"), ""))
        if m["condition"] == "background":
            u = g.get("user_undisturbed")
            br = [k for k in self.scene.cat["criteria"] if u and u["criteria"].get(k["id"]) is False]
            rows.append(("User undisturbed", u["result"] if u else None, f"{8 - len(br)} of 8" if u else ""))
        y += 60
        for name, okk, val in rows:
            pill(d, (x, y, self.x0 + PW - 20, y + 32), fill=C["panel2"], r=8, outline=C["line"])
            col = C["ink4"] if okk is None else (C["good"] if okk else C["bad"])
            d.ellipse((x + 9, y + 8, x + 25, y + 24), fill=col)
            mark = "–" if okk is None else ("✓" if okk else "✗")
            d.text((x + 17 - d.textlength(mark, font=font(800, 11)) / 2, y + 9), mark, font=font(800, 11), fill=(255, 255, 255))
            d.text((x + 34, y + 7), name, font=font(700, 13), fill=C["ink"])
            if val:
                d.text((self.x0 + PW - 32 - d.textlength(val, font=font(800, 13)), y + 7), val, font=font(800, 13), fill=C["ink"])
            y += 38
        facts = " · ".join(v for v in [m.get("tool_calls") is not None and f"{m['tool_calls']} tool calls",
                                        mins(m.get("duration"))] if v)
        d.text((x, y + 2), facts, font=font(500, 11.5), fill=C["ink3"])


def render(fg, bg, cat, cfg, out_dir, name, seconds=26):
    """``fg`` and ``bg``, loaded trials of one task, model and driver, side by side as ``name``.gif and ``name``.mp4."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    left, right = panels(fg, bg, cat, cfg)
    speed = nice_speed(max(left.span, right.span), seconds)
    gif, mp4 = out_dir / f"{name}.gif", out_dir / f"{name}.mp4"
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        save = saver(Path(tmp))
        for k, img in enumerate(play(left, right, speed)):
            if k == 0:
                save(intro_card(img, left, right), 3.2)
            save(img)
        save(graded(img, left, right), 5)
        encode(Path(tmp), gif, mp4, (cfg.get("pairs_max_mb") or 10) * 1e6)
    return gif, mp4


def panels(fg, bg, cat, cfg):
    """The foreground trial's panel on the left and the background's on the right, both showing one region."""
    left, right = Panel(fg, cat, cfg, EDGE), Panel(bg, cat, cfg, EDGE + PW + GAP)
    left.view = right.view = view(left, right)
    return left, right


def play(left, right, speed, note="Recorded trials, sped up"):
    """Each frame of the two panels' trials at ``speed`` from their start; a panel whose trial ended first holds its last
    frame under its grade."""
    sw, sh = left.scene.sw, left.scene.sh
    crop = (left.view[0] / sw, left.view[1] / sh, left.view[2] / sw, left.view[3] / sh)
    n = {p: max(1, math.ceil(p.span * FPS / speed)) for p in (left, right)}
    frames = {p: media.frames(p.trial["folder"] / "recording.mp4", p.scene.start, FPS / speed, n[p], (PW, PV), crop)
              for p in (left, right)}
    held = {p: Image.new("RGB", (PW, PV), C["bg"]) for p in (left, right)}
    for k in range(max(n.values())):
        img = Image.new("RGB", (W, H), C["bg"])
        d = ImageDraw.Draw(img, "RGBA")
        header(d, left, right, speed)
        footer(d, note)
        for p in (left, right):
            if k < n[p] and (buf := next(frames[p], None)):
                held[p] = Image.frombytes("RGB", (PW, PV), buf)
            p.draw(img, d, held[p], p.at(k / FPS, speed), speed)
            if k >= n[p]:
                p.grade(img, d)
        yield img


def graded(img, left, right):
    """The last frame with both trials' grades over it."""
    img = img.copy()
    d = ImageDraw.Draw(img, "RGBA")
    for p in (left, right):
        p.grade(img, d)
    return img


def saver(folder):
    """A function that writes a frame into ``folder`` as the next of a numbered sequence, held ``seconds`` when given."""
    count = [0]

    def save(img, seconds=None):
        for _ in range(int(FPS * seconds) if seconds else 1):
            img.save(folder / f"{count[0]:05d}.png", compress_level=1)
            count[0] += 1
    return save


def encode(folder, gif, mp4, limit):
    """The numbered frames in ``folder`` as an MP4 and a looping GIF of at most ``limit`` bytes, with fewer colours and
    coarser dither as needed."""
    pattern = str(folder / "%05d.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", pattern, "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow", "-movflags", "+faststart", str(mp4)],
                   check=True)
    pal = folder / "palette.png"
    for colors, scale in ((256, 4), (192, 5), (128, 5)):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", pattern, "-vf",
                        f"palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=0", str(pal)], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", pattern, "-i", str(pal), "-lavfi",
                        f"paletteuse=dither=bayer:bayer_scale={scale}:diff_mode=rectangle", "-loop", "0", str(gif)],
                       check=True)
        if gif.stat().st_size <= limit:
            break


def view(*panels, margin=56):
    """The part of the screen both panels show, at the screen's aspect: every window the agents acted on and the user's
    window, with a margin, so small windows on a large screen stay legible at half width."""
    sw, sh = panels[0].scene.sw, panels[0].scene.sh
    boxes = [b for p in panels for b in p.boxes()]
    if not boxes:
        return 0, 0, sw, sh
    x0, y0 = max(0, min(b[0] for b in boxes) - margin), max(0, min(b[1] for b in boxes) - margin)
    x1, y1 = min(sw, max(b[2] for b in boxes) + margin), min(sh, max(b[3] for b in boxes) + margin)
    w, h = x1 - x0, y1 - y0
    if w / h < sw / sh:
        w = h * sw / sh
    else:
        h = w * sh / sw
    w, h = min(w, sw), min(h, sh)
    x0 = min(max(0, (x0 + x1) / 2 - w / 2), sw - w)
    y0 = min(max(0, (y0 + y1) / 2 - h / 2), sh - h)
    return x0, y0, w, h


def header(d, left, right, speed):
    sc, m = left.scene, left.m
    fb = font(800, 13)
    d.text((EDGE, 12), "CUA DRIVER BENCH", font=fb, fill=C["ink"])
    x = EDGE + d.textlength("CUA DRIVER BENCH", font=fb) + 8
    d.text((x, 12), "on AgentEnv", font=font(500, 13), fill=C["ink3"])
    osn = next((o["name"] for o in sc.cat["oses"] if o["id"] == m["os"]), m["os"])
    drv = next((dv.get("label") or dv["name"] for dv in sc.cat["drivers"] if dv["id"] == m["driver"]), m["driver"])
    right_text = f"{m['model_name']}  ·  {drv}  ·  {osn}  ·  {speed}× speed"
    f = font(600, 12.5)
    d.text((W - EDGE - d.textlength(right_text, font=f), 12.5), right_text, font=f, fill=C["ink2"])
    probe = (sc.task.get("probe") or m["task"]).replace("CDB-", "")
    title = f"{probe} · {sc.task.get('title', '')}"
    run = f"run {m.get('run_index')}, both conditions" if m.get("run_index") else "both conditions"
    fr = font(500, 12.5)
    rw = d.textlength(run, font=fr)
    d.text((EDGE, 34), fit(d, title, font(700, 15), W - 2 * EDGE - rw - 24), font=font(700, 15), fill=C["ink"])
    d.text((W - EDGE - rw, 36.5), run, font=fr, fill=C["ink3"])
    d.line((EDGE, HDR - 2, W - EDGE, HDR - 2), fill=C["line"], width=1)


def footer(d, note="Recorded trials, sped up"):
    y = H - FOOT + 9
    x = EDGE
    for lab, col, txt in (("AGENT", C["agent"], "what it acts on"), ("USER", C["user"], "their window"),
                          ("✗", C["bad"], "a disturbance")):
        f = font(800, 10)
        w = d.textlength(lab, font=f) + 12
        pill(d, (x, y, x + w, y + 17), fill=col, r=4)
        d.text((x + 6, y + 2.5), lab, font=f, fill=(29, 19, 0) if col == C["user"] else (255, 255, 255))
        d.text((x + w + 7, y + 1), txt, font=font(500, 12), fill=C["ink3"])
        x += w + 7 + d.textlength(txt, font=font(500, 12)) + 18
    d.text((W - EDGE - d.textlength(note, font=font(500, 12)), y + 1), note, font=font(500, 12), fill=C["ink4"])


def intro_card(base, left, right):
    img = base.copy()
    region = img.crop((0, HDR, W, H - FOOT)).filter(ImageFilter.GaussianBlur(3))
    img.paste(region, (0, HDR))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle((0, HDR, W, H - FOOT), fill=(5, 7, 12, 190))
    cw, ch = 640, 200
    x0, y0 = (W - cw) / 2, HDR + (H - FOOT - HDR - ch) / 2
    pill(d, (x0, y0, x0 + cw, y0 + ch), fill=(17, 22, 34, 250), r=14, outline=C["line"])
    x, y = x0 + 26, y0 + 22
    d.text((x, y), "THE SAME TASK, TWO CONDITIONS", font=font(800, 11.5), fill=C["ink3"])
    y += 24
    model = left.m["model_name"]
    for col, cond, body in ((C["agent"], "FOREGROUND", f"{model} has the desktop to itself."),
                            (C["user"], "BACKGROUND", "A person keeps typing in their own window the whole time; the "
                                                      "agent must do the same task without disturbing them.")):
        f = font(800, 10.5)
        w = d.textlength(cond, font=f) + 16
        pill(d, (x, y + 1, x + w, y + 21), fill=col + (44,), r=10, outline=col + (150,))
        d.text((x + 8, y + 5), cond, font=f, fill=col)
        lines = left.scene.wrap(d, body, font(500, 14.5), cw - 52 - w - 12)
        for j, line in enumerate(lines[:3]):
            d.text((x + w + 12, y + 2 + 21 * j), line, font=font(500, 14.5), fill=C["ink2"])
        y += 21 * max(1, len(lines[:3])) + 16
    d.text((x, y0 + ch - 34), "Left and right play at one speed; each ends on its grade.", font=font(500, 12.5),
           fill=C["ink3"])
    return img
