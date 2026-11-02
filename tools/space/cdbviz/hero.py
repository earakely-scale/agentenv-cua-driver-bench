import math
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import media

FONTS = Path(__file__).resolve().parent.parent / "fonts"
FACES = {400: "Inter-Regular.ttf", 500: "Inter-Medium.ttf", 600: "Inter-SemiBold.ttf", 700: "Inter-Bold.ttf",
         800: "Inter-ExtraBold.ttf", "mono": "JetBrainsMono-Medium.ttf", "mono600": "JetBrainsMono-SemiBold.ttf"}
C = {"bg": (11, 15, 25), "panel": (17, 22, 34), "panel2": (24, 30, 45), "line": (40, 48, 66), "ink": (243, 244, 246),
     "ink2": (185, 192, 204), "ink3": (130, 138, 153), "ink4": (88, 96, 112), "agent": (76, 155, 255),
     "user": (245, 165, 36), "bad": (255, 82, 82), "good": (52, 193, 114),
     "good_dim": (21, 70, 45), "bad_dim": (92, 30, 34)}
NICE = [2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 20, 24, 30, 40, 50, 60]
FPS = 10
W = 960
HEAD, VID, PANEL = 38, 540, 128


@lru_cache(maxsize=None)
def font(face, size):
    return ImageFont.truetype(str(FONTS / FACES[face]), max(1, round(size)))


def fit(draw, text, f, maxw):
    if draw.textlength(text, font=f) <= maxw:
        return text
    while text and draw.textlength(text + "…", font=f) > maxw:
        text = text[:-1]
    return text.rstrip() + "…" if text else ""


def pill(draw, box, fill, r=6, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def nice_speed(span, seconds):
    want = span / max(1.0, seconds)
    return next((s for s in NICE if s >= want), NICE[-1])


def fmt(t):
    t = max(0, t or 0)
    return f"{int(t // 60)}:{int(t % 60):02d}"


def pct(v):
    return "–" if v is None else f"{round(100 * v)}%"


def mins(s):
    if s is None:
        return "–"
    return f"{int(s // 60)} min {round(s % 60)} s" if s >= 60 else f"{round(s)} s"


class Scene:
    def __init__(self, trial, cat, cfg, s=1):
        self.m, self.web, self.cat, self.cfg, self.s = trial["meta"], trial["web"], cat, cfg, s
        self.W, self.H = W * s, (HEAD + VID + PANEL) * s
        self.calls = self.web["calls"]
        self.texts = self.web["texts"]
        self.user = self.web["user"]
        self.dur = self.web["duration"] or 1
        a, d = self.web["armed"]
        self.start = max(0.0, (a or 0) - 0.5)
        self.end = min(self.dur, (d or self.dur) + 0.6)
        self.crit = {c["id"]: c for c in cat["criteria"]}
        self.task = next((t for t in cat["tasks"] if t["id"] == self.m["task"]), {"title": self.m["task"]})
        self.cond = next((c for c in cat["conditions"] if c["id"] == self.m["condition"]), {"name": self.m["condition"]})
        events = [e for e in (self.user or {}).get("events", []) if e["c"] in self.crit or e["c"] == "close"]
        self.moments = []
        for e in events:
            if self.moments and e["t"] - self.moments[-1]["t"] < 0.8:
                self.moments[-1]["items"].append(e)
            else:
                self.moments.append({"t": e["t"], "items": [e]})
        self.sw, self.sh = cfg["screen"]

    def vx(self, x):
        return x * W * self.s / self.sw

    def vy(self, y):
        return HEAD * self.s + y * VID * self.s / self.sh

    def cur(self, t):
        idx = -1
        for k, c in enumerate(self.calls):
            if c["t0"] <= t:
                idx = k
            else:
                break
        return idx

    def broken(self, t):
        out = {e["c"] for m in self.moments if m["t"] <= t for e in m["items"] if e["c"] in self.crit}
        if t >= (self.web["armed"][1] or self.dur) - 0.05:
            u = self.m["grade"].get("user_undisturbed") or {}
            out |= {k for k, v in (u.get("criteria") or {}).items() if v is False}
        return out

    def frame(self, video, t, speed):
        s = self.s
        img = Image.new("RGB", (self.W, self.H), C["bg"])
        img.paste(video, (0, HEAD * s))
        d = ImageDraw.Draw(img, "RGBA")
        self.header(d, speed)
        self.overlays(img, d, t, speed)
        self.panel(d, t, speed)
        return img

    def header(self, d, speed):
        s = self.s
        f, fb = font(600, 13 * s), font(800, 13 * s)
        y = 12 * s
        d.text((14 * s, y), "CUA DRIVER BENCH", font=fb, fill=C["ink"])
        x = 14 * s + d.textlength("CUA DRIVER BENCH", font=fb) + 8 * s
        d.text((x, y), "on AgentEnv", font=font(500, 13 * s), fill=C["ink3"])
        x += d.textlength("on AgentEnv", font=font(500, 13 * s)) + 14 * s
        probe = (self.task.get("probe") or self.m["task"]).replace("CDB-", "")
        cond = self.cond["name"]
        title = f"{probe} · {self.task.get('title', '')}"
        right = f"{self.m['model_name']}  ·  {speed}× speed"
        rw = d.textlength(right, font=f)
        chip_w = d.textlength(cond.upper(), font=font(800, 10.5 * s)) + 16 * s
        avail = self.W - x - rw - chip_w - 40 * s
        d.text((x, y), fit(d, title, font(600, 13 * s), avail), font=font(600, 13 * s), fill=C["ink2"])
        cx = self.W - 14 * s - rw - 12 * s - chip_w
        col = C["user"] if self.m["condition"] == "background" else C["agent"]
        pill(d, (cx, 9 * s, cx + chip_w, 29 * s), fill=col + (40,), r=10 * s)
        d.text((cx + 8 * s, 13.5 * s), cond.upper(), font=font(800, 10.5 * s), fill=col)
        d.text((self.W - 14 * s - rw, y), right, font=f, fill=C["ink2"])

    def overlays(self, img, d, t, speed):
        s = self.s
        i = self.cur(t)
        c = self.calls[i] if i >= 0 else None
        nxt = self.calls[i + 1] if 0 <= i + 1 < len(self.calls) else None
        fresh = c and t - c["t0"] < max(3, min(8, (nxt["t0"] if nxt else self.end) - c["t0"]))
        if fresh and c.get("win") and c["kind"] != "setup":
            x, y, w, h = c["win"]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(self.sw, x + w), min(self.sh, y + h)
            if x1 - x0 > 20 and y1 - y0 > 20:
                box = (self.vx(x0), self.vy(y0), self.vx(x1), self.vy(y1))
                d.rectangle(box, outline=C["agent"] + (230,), width=max(1, round(2 * s)))
                tag = f"AGENT → {c.get('where') or 'window'}"
                f = font(600, 11.5 * s)
                tw = min(d.textlength(tag, font=f), 300 * s)
                tx, ty = min(box[0] + 2 * s, self.W - tw - 20 * s), box[1] + 3 * s
                pill(d, (tx, ty, tx + tw + 14 * s, ty + 20 * s), fill=C["agent"] + (235,), r=5 * s)
                d.text((tx + 7 * s, ty + 3.5 * s), fit(d, tag, f, 300 * s), font=f, fill=(255, 255, 255))
        if self.m["condition"] == "background":
            fx, fy, fw, fh = (self.user or {}).get("frame") or self.cfg["user_frame"]
            box = (self.vx(fx), self.vy(fy), self.vx(fx + fw), self.vy(fy + fh))
            broken = self.broken(t) if self.user or t >= (self.web["armed"][1] or self.dur) - 0.05 else set()
            recent = next((m for m in reversed(self.moments) if m["t"] <= t), None)
            flash = recent and (t - recent["t"]) < 1.3 * speed
            hurt = bool(broken)
            col = C["bad"] if hurt or flash else C["user"]
            if flash:
                k = (t - recent["t"]) / (1.3 * speed)
                d.rectangle(box, fill=C["bad"] + (int(70 * (1 - k)),))
            d.rectangle((box[0] - 1 * s, box[1] - 1 * s, box[2] + 1 * s, box[3] + 1 * s), outline=(0, 0, 0, 150),
                        width=max(1, round(5 * s)))
            d.rectangle(box, outline=col + (255,), width=max(1, round((5 if flash else 3) * s)))
            if flash:
                e = recent["items"][0]
                label = f"{self.crit.get(e['c'], {}).get('short', 'Window')}: {self.crit.get(e['c'], {}).get('broken', e['what'])}"
            elif hurt:
                label = f"disturbed · {len(broken)} of 8 broken"
            elif not self.user:
                label = "User activity"
            else:
                label = "typing · undisturbed"
            f, fb = font(600, 12.5 * s), font(800, 11 * s)
            tw = d.textlength("USER", font=fb) + 8 * s + d.textlength(label, font=f)
            tx, ty = box[0], box[1] - 26 * s
            pill(d, (tx, ty, tx + tw + 18 * s, ty + 22 * s), fill=col + (255,), r=6 * s)
            ink = (29, 19, 0) if col == C["user"] else (255, 255, 255)
            d.text((tx + 9 * s, ty + 5 * s), "USER", font=fb, fill=ink)
            d.text((tx + 9 * s + d.textlength("USER", font=fb) + 8 * s, ty + 3.5 * s), label, font=f, fill=ink)
        p = c and (c.get("pt") or c.get("near")) if fresh else None
        if p:
            cx, cy = self.vx(p[0]), self.vy(p[1])
            col = C["bad"] if c.get("err") else C["agent"]
            age = (t - c["t0"]) / speed
            if age < 0.7:
                rr = (9 + 26 * age / 0.7) * s
                d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=col + (int(255 * (1 - age / 0.7)),), width=max(1, round(2 * s)))
            r = 9 * s
            if c.get("pt"):
                d.ellipse((cx - r - 2 * s, cy - r - 2 * s, cx + r + 2 * s, cy + r + 2 * s), outline=(255, 255, 255, 220), width=max(1, round(2 * s)))
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col + (255,), width=max(1, round(3 * s)))
                d.ellipse((cx - 2.5 * s, cy - 2.5 * s, cx + 2.5 * s, cy + 2.5 * s), fill=col + (255,))
            else:
                d.rounded_rectangle((cx - 9 * s, cy - 7 * s, cx + 9 * s, cy + 7 * s), radius=3 * s, outline=col + (255,), width=max(1, round(2.5 * s)))
            tag = f"{c['verb']}" + (f" {c['obj']}" if c.get("obj") and len(c["obj"]) < 30 else "")
            f = font(600, 11.5 * s)
            tw = min(d.textlength(tag, font=f), 260 * s)
            left = cx + 14 * s if cx + 14 * s + tw + 14 * s < self.W else cx - 14 * s - tw - 14 * s
            pill(d, (left, cy - 10 * s, left + tw + 14 * s, cy + 10 * s), fill=(8, 11, 18, 225), r=5 * s)
            d.text((left + 7 * s, cy - 7 * s), fit(d, tag, f, 260 * s), font=f, fill=(255, 255, 255))
        si = max((k for k, x in enumerate(self.texts) if x["t"] <= t), default=-1)
        if si >= 0:
            x = self.texts[si]
            nxt_t = self.texts[si + 1]["t"] if si + 1 < len(self.texts) else math.inf
            if t - x["t"] < max(6, 2.2 * speed) and t < nxt_t:
                self.caption(d, x["text"])

    def caption(self, d, text):
        s = self.s
        f, fb = font(500, 15 * s), font(700, 15 * s)
        maxw = 700 * s
        words, lines, line = text.split(), [], ""
        for w_ in words:
            cand = f"{line} {w_}".strip()
            if d.textlength(cand, font=f) > maxw - 80 * s and line:
                lines.append(line)
                line = w_
            else:
                line = cand
        lines.append(line)
        lines = lines[:2]
        if len(lines) == 2 and len(" ".join(lines)) < len(text):
            lines[1] = fit(d, lines[1] + " …", f, maxw - 80 * s)
        lines[0] = "“" + lines[0]
        lines[-1] = lines[-1] + "”"
        lab = "Claude "
        lw = d.textlength(lab, font=fb)
        widths = [d.textlength(ln, font=f) for ln in lines]
        bw = max(widths[0] + lw, max(widths)) + 28 * s
        bh = (22 * len(lines) + 14) * s
        x0 = (self.W - bw) / 2
        y1 = self.vy(self.sh) - 74 * s
        pill(d, (x0, y1 - bh, x0 + bw, y1), fill=(8, 11, 18, 228), r=10 * s)
        y = y1 - bh + 7 * s
        d.text((x0 + 14 * s, y), lab, font=fb, fill=(156, 198, 255))
        d.text((x0 + 14 * s + lw, y), lines[0], font=f, fill=(255, 255, 255))
        for k, ln in enumerate(lines[1:], 1):
            d.text((x0 + 14 * s, y + 22 * k * s), ln, font=f, fill=(255, 255, 255))

    def panel(self, d, t, speed):
        s = self.s
        top = (HEAD + VID) * s
        d.rectangle((0, top, self.W, self.H), fill=C["panel"])
        d.line((0, top, self.W, top), fill=C["line"], width=max(1, s))
        lx = 14 * s
        lab_w = 112 * s
        d.text((lx, top + 12 * s), "AGENT", font=font(800, 11 * s), fill=C["agent"])
        d.text((lx, top + 27 * s), fit(d, self.m["model_name"], font(500, 11 * s), lab_w - 4 * s), font=font(500, 11 * s), fill=C["ink3"])
        i = self.cur(t)
        x0, x1 = lx + lab_w, self.W - 14 * s
        self.strip(d, i, x0, x1, top + 9 * s, 26 * s)
        c = self.calls[i] if i >= 0 else None
        y2 = top + 41 * s
        if c:
            tool = f"{c['tool']}"
            fm = font("mono", 11 * s)
            d.text((x0, y2), tool, font=fm, fill=C["ink3"])
            xx = x0 + d.textlength(tool, font=fm) + 10 * s
            n = f"call {c['i'] + 1} of {len(self.calls)}"
            d.text((xx, y2), n, font=font(500, 11.5 * s), fill=C["ink4"])
            xx += d.textlength(n, font=font(500, 11.5 * s)) + 10 * s
            if c.get("err"):
                d.text((xx, y2 - 0.5 * s), fit(d, "✗ " + c["err"], font(500, 12 * s), x1 - xx), font=font(500, 12 * s), fill=C["bad"])
            elif c.get("where"):
                d.text((xx, y2 - 0.5 * s), fit(d, c["where"], font(500, 12 * s), x1 - xx), font=font(500, 12 * s), fill=C["ink2"])
        uy = top + 62 * s
        d.line((lx, uy - 3 * s, self.W - lx, uy - 3 * s), fill=C["line"], width=max(1, s))
        self.userrow(d, t, uy, lx, lab_w)
        self.timeline(d, t, speed, top + 102 * s)

    def strip(self, d, i, x0, x1, y, hgt):
        s = self.s
        f, fb = font(500, 12.5 * s), font(700, 12.5 * s)
        gap = 6 * s
        if i < 0:
            d.text((x0, y + 5 * s), "Starting the agent…", font=f, fill=C["ink3"])
            return
        widths = {}

        def chip_w(k):
            if k not in widths:
                c = self.calls[k]
                text = c["verb"] + (f" {c['obj']}" if c.get("obj") else "")
                face = fb if k == i else f
                cap = 330 * s if k == i else 170 * s
                widths[k] = (fit(d, text, face, cap), min(cap, d.textlength(fit(d, text, face, cap), font=face)) + 20 * s)
            return widths[k]

        left_room = (x1 - x0) * 0.36
        ks, used = [], 0
        k = i - 1
        while k >= 0 and used + chip_w(k)[1] + gap <= left_room:
            used += chip_w(k)[1] + gap
            ks.insert(0, k)
            k -= 1
        x = x0
        if k >= 0:
            d.text((x, y + 5 * s), "…", font=f, fill=C["ink4"])
            x += 14 * s
        for k in ks:
            text, w = chip_w(k)
            c = self.calls[k]
            col = C["bad"] if c.get("err") else C["ink3"]
            pill(d, (x, y, x + w, y + hgt), fill=C["panel2"], r=7 * s, outline=(C["bad_dim"] if c.get("err") else C["line"]), width=max(1, s))
            d.text((x + 10 * s, y + 5.5 * s), text, font=f, fill=col)
            x += w + gap
        text, w = chip_w(i)
        c = self.calls[i]
        fill = C["bad"] if c.get("err") else C["agent"]
        pill(d, (x, y - 1 * s, x + w, y + hgt + 1 * s), fill=fill, r=7 * s)
        d.text((x + 10 * s, y + 5 * s), text, font=fb, fill=(255, 255, 255))
        x += w + gap
        k = i + 1
        while k < len(self.calls):
            text, w = chip_w(k)
            if x + w > x1:
                if x + 14 * s < x1:
                    d.text((x, y + 5 * s), "…", font=f, fill=C["ink4"])
                break
            pill(d, (x, y, x + w, y + hgt), fill=None, r=7 * s, outline=C["line"], width=max(1, s))
            d.text((x + 10 * s, y + 5.5 * s), text, font=f, fill=C["ink4"])
            x += w + gap
            k += 1

    def userrow(self, d, t, y, lx, lab_w):
        s = self.s
        d.text((lx, y + 7 * s), "USER", font=font(800, 11 * s), fill=C["user"])
        d.text((lx, y + 22 * s), "User activity", font=font(500, 11 * s), fill=C["ink3"])
        x0 = lx + lab_w
        if self.m["condition"] != "background":
            d.text((x0, y + 12 * s), "Foreground: the agent owns the desktop; a small witness window only watches.",
                   font=font(500, 12.5 * s), fill=C["ink3"])
            return
        final = t >= (self.web["armed"][1] or self.dur) - 0.05
        broken = self.broken(t) if self.user or final else set()
        fw = 372 * s
        box = (x0, y + 4 * s, x0 + fw, y + 34 * s)
        pill(d, box, fill=C["bg"], r=6 * s, outline=C["line"], width=max(1, s))
        sx = box[2] + 12 * s
        if self.user:
            n = sum(1 for x in self.user["typed"] if x <= t)
            script = self.user.get("script") or self.cfg["user_script"]
            typed = (script * (n // max(1, len(script)) + 1))[:n]
            nb = sum(1 for x in self.user["blocked"] if x <= t)
            note = f"{n} landed" + (f" · {nb} blocked" if nb else "")
            f = font(500, 10.5 * s)
            nw = d.textlength(note, font=f)
            fm = font("mono", 12 * s)
            inner = fw - nw - 40 * s
            shown = typed
            while shown and d.textlength(shown, font=fm) > inner:
                shown = shown[1:]
            d.text((x0 + 10 * s, y + 11 * s), shown, font=fm, fill=C["ink"])
            cx = x0 + 10 * s + d.textlength(shown, font=fm) + 1 * s
            d.rectangle((cx, y + 11 * s, cx + 2 * s, y + 26 * s), fill=C["user"])
            pill(d, (box[2] - nw - 16 * s, y + 9 * s, box[2] - 5 * s, y + 29 * s), fill=C["panel2"], r=5 * s)
            d.text((box[2] - nw - 10 * s, y + 12.5 * s), note, font=f, fill=C["bad"] if nb else C["ink3"])
        else:
            d.text((x0 + 10 * s, y + 11.5 * s), fit(d, "lane not recorded for this trial (no sentinel log)", font(500, 12 * s), fw - 20 * s),
                   font=font(500, 12 * s), fill=C["ink3"])
        if not self.user and not final:
            d.text((sx, y + 11.5 * s), "the eight criteria come from the grade at the end", font=font(500, 12 * s), fill=C["ink3"])
            return
        if not broken:
            label = "Undisturbed · all 8 criteria hold"
            f = font(700, 12.5 * s)
            w = d.textlength(label, font=f) + 34 * s
            pill(d, (sx, y + 6 * s, sx + w, y + 32 * s), fill=C["good_dim"], r=7 * s)
            d.text((sx + 10 * s, y + 10 * s), "✓", font=font(800, 13 * s), fill=C["good"])
            d.text((sx + 26 * s, y + 10.5 * s), label, font=f, fill=C["good"])
            return
        f = font(700, 12 * s)
        d.text((sx, y + 11 * s), f"{len(broken)}/8 broken", font=font(800, 12 * s), fill=C["bad"])
        x = sx + d.textlength(f"{len(broken)}/8 broken", font=font(800, 12 * s)) + 8 * s
        right = self.W - 14 * s
        for c in self.cat["criteria"]:
            if c["id"] not in broken:
                continue
            label = c["short"]
            w = d.textlength(label, font=f) + 30 * s
            if x + w > right:
                d.text((x, y + 11 * s), "…", font=f, fill=C["bad"])
                break
            pill(d, (x, y + 6 * s, x + w, y + 32 * s), fill=C["bad_dim"], r=7 * s)
            d.text((x + 9 * s, y + 10 * s), "✗", font=font(800, 12.5 * s), fill=C["bad"])
            d.text((x + 23 * s, y + 11 * s), label, font=f, fill=(255, 178, 178))
            x += w + 5 * s

    def timeline(self, d, t, speed, y):
        s = self.s
        x0, x1 = 14 * s + 112 * s, self.W - 112 * s
        hgt = 16 * s
        pill(d, (x0, y, x1, y + hgt), fill=C["bg"], r=4 * s)
        span = self.end - self.start
        X = lambda tt: x0 + (x1 - x0) * min(1, max(0, (tt - self.start) / span))
        for c in self.calls:
            col = C["bad"] if c.get("err") else (C["agent"] if c["kind"] == "act" else C["ink4"])
            xx = X(c["t0"])
            d.line((xx, y + 2 * s, xx, y + hgt / 2), fill=col, width=max(1, round(1.5 * s)))
        if self.user:
            for tt in self.user["typed"]:
                xx = X(tt)
                d.line((xx, y + hgt / 2 + 2 * s, xx, y + hgt - 3 * s), fill=C["user"] + (150,), width=max(1, s))
            for m in self.moments:
                xx = X(m["t"])
                d.line((xx, y + hgt / 2, xx, y + hgt - 1 * s), fill=C["bad"], width=max(1, round(2.5 * s)))
        ph = X(t)
        d.rectangle((x0, y + hgt - 2 * s, ph, y + hgt), fill=C["ink2"])
        d.line((ph, y - 3 * s, ph, y + hgt + 3 * s), fill=C["ink"], width=max(1, round(2 * s)))
        d.text((14 * s, y + 1.5 * s), "TIMELINE", font=font(800, 10 * s), fill=C["ink4"])
        label = f"{fmt(t)} / {fmt(self.dur)}"
        d.text((x1 + 12 * s, y + 0.5 * s), label, font=font("mono", 12 * s), fill=C["ink2"])

    def card(self, base, kind, speed):
        s = self.s
        img = base.copy()
        top = HEAD * s
        region = img.crop((0, top, self.W, top + VID * s)).filter(ImageFilter.GaussianBlur(3 * s))
        img.paste(region, (0, top))
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle((0, top, self.W, top + VID * s), fill=(5, 7, 12, 175))
        rows = 3 if self.m["condition"] == "background" else 2
        cw, chh = 600 * s, ((142 + 54 * rows) if kind == "grade" else 300) * s
        x0, y0 = (self.W - cw) / 2, top + (VID * s - chh) / 2
        pill(d, (x0, y0, x0 + cw, y0 + chh), fill=(17, 22, 34, 248), r=16 * s, outline=C["line"], width=max(1, s))
        if kind == "intro":
            self.intro(d, x0, y0, cw)
        else:
            self.grade(d, x0, y0, cw)
        return img

    def intro(self, d, x0, y0, cw):
        s = self.s
        x, y = x0 + 28 * s, y0 + 26 * s
        probe = (self.task.get("probe") or self.m["task"]).replace("CDB-", "")
        d.text((x, y), f"{probe} · {self.cond['name'].upper()} CONDITION", font=font(800, 11.5 * s), fill=C["user"] if self.m["condition"] == "background" else C["agent"])
        y += 22 * s
        d.text((x, y), fit(d, self.task.get("title", ""), font(800, 26 * s), cw - 56 * s), font=font(800, 26 * s), fill=C["ink"])
        y += 42 * s
        if self.m["condition"] == "background":
            body = (f"A simulated user types in their own window, “User activity”, the whole time. "
                    f"{self.m['model_name']} must do the task in the other apps, through the GUI only, without disturbing them.")
        else:
            body = f"{self.m['model_name']} has the desktop to itself and must do the task through the GUI only."
        for line in self.wrap(d, body, font(500, 15 * s), cw - 56 * s)[:4]:
            d.text((x, y), line, font=font(500, 15 * s), fill=C["ink2"])
            y += 22 * s
        y += 14 * s
        items = [("AGENT", C["agent"], "its real tool calls, in order"), ("USER", C["user"], "their window and typing"),
                 ("✗", C["bad"], "a disturbance or an error")]
        for lab, col, txt in items:
            pill(d, (x, y, x + d.textlength(lab, font=font(800, 11 * s)) + 16 * s, y + 21 * s), fill=col, r=6 * s)
            ink = (29, 19, 0) if col == C["user"] else (255, 255, 255)
            d.text((x + 8 * s, y + 4.5 * s), lab, font=font(800, 11 * s), fill=ink)
            d.text((x + d.textlength(lab, font=font(800, 11 * s)) + 26 * s, y + 2.5 * s), txt, font=font(500, 13.5 * s), fill=C["ink2"])
            y += 29 * s

    def grade(self, d, x0, y0, cw):
        s = self.s
        m, g = self.m, self.m["grade"]
        x, y = x0 + 28 * s, y0 + 24 * s
        d.text((x, y), "THE GRADE", font=font(800, 11.5 * s), fill=C["ink3"])
        y += 20 * s
        ok = m["passed"]
        d.text((x, y), "Pass" if ok else "Fail", font=font(800, 34 * s), fill=C["good"] if ok else C["bad"])
        vx = x + d.textlength("Pass" if ok else "Fail", font=font(800, 34 * s)) + 16 * s
        why = self.why()
        for k, line in enumerate(self.wrap(d, why, font(500, 14 * s), x0 + cw - 28 * s - vx)[:2]):
            d.text((vx, y + (6 + 19 * k) * s), line, font=font(500, 14 * s), fill=C["ink2"])
        y += 54 * s
        rows = [("Task", (g.get("task") or {}).get("result"), f"trycua's evaluator · {pct((g.get('task') or {}).get('score'))} of the points",
                 pct((g.get("task") or {}).get("score")))]
        gu = g.get("gui_only") or {}
        rows.append(("GUI only", gu.get("result"), "no way out of the GUI" if gu.get("result") else
                     f"violation: {', '.join(gu.get('violations') or []) or 'see the grade'}", ""))
        if m["condition"] == "background":
            u = g.get("user_undisturbed")
            br = [c["short"] for c in self.cat["criteria"] if u and u["criteria"].get(c["id"]) is False]
            rows.append(("User undisturbed", u["result"] if u else None,
                         ("broken: " + ", ".join(br)) if br else ("all eight criteria held" if u else "not graded"),
                         f"{8 - len(br)} of 8 held" if u else ""))
        for name, okk, sub, val in rows:
            pill(d, (x, y, x0 + cw - 28 * s, y + 46 * s), fill=C["panel2"], r=10 * s, outline=C["line"], width=max(1, s))
            col = C["ink4"] if okk is None else (C["good"] if okk else C["bad"])
            d.ellipse((x + 12 * s, y + 12 * s, x + 34 * s, y + 34 * s), fill=col)
            mark = "–" if okk is None else ("✓" if okk else "✗")
            mw = d.textlength(mark, font=font(800, 13 * s))
            d.text((x + 23 * s - mw / 2, y + 14.5 * s), mark, font=font(800, 13 * s), fill=(255, 255, 255))
            d.text((x + 46 * s, y + 6 * s), name, font=font(700, 14.5 * s), fill=C["ink"])
            vw = d.textlength(val, font=font(800, 15 * s)) if val else 0
            d.text((x + 46 * s, y + 25 * s), fit(d, sub, font(500, 12 * s), cw - 56 * s - 60 * s - vw), font=font(500, 12 * s), fill=C["ink3"])
            if val:
                d.text((x0 + cw - 42 * s - vw, y + 13 * s), val, font=font(800, 15 * s), fill=C["ink"])
            y += 54 * s
        facts = " · ".join(str(v) for v in [m["model_name"], f"{m.get('harness') or ''} {m.get('harness_version') or ''}".strip(),
                                            m.get("turns") is not None and f"{m['turns']} turns",
                                            m.get("tool_calls") is not None and f"{m['tool_calls']} tool calls",
                                            mins(m.get("duration")), m.get("cost") is not None and f"${m['cost']:.2f}"] if v)
        d.text((x, y + 4 * s), fit(d, facts, font(500, 12 * s), cw - 56 * s), font=font(500, 12 * s), fill=C["ink3"])

    def why(self):
        m, g = self.m, self.m["grade"]
        if m["passed"]:
            return "Every half held."
        out = []
        if g.get("task") and not g["task"]["result"]:
            out.append("the task checks failed")
        if g.get("gui_only") and not g["gui_only"]["result"]:
            out.append("it left the GUI")
        if m["condition"] == "background" and g.get("user_undisturbed") and not g["user_undisturbed"]["result"]:
            out.append("the user was disturbed")
        if g.get("sentinel") and not g["sentinel"]["result"]:
            out.append("the sentinel's log is incomplete")
        s = ", ".join(out) or "a half of the grade is missing"
        return s[0].upper() + s[1:] + "."

    @staticmethod
    def wrap(d, text, f, maxw):
        out, line = [], ""
        for w_ in text.split():
            cand = f"{line} {w_}".strip()
            if d.textlength(cand, font=f) > maxw and line:
                out.append(line)
                line = w_
            else:
                line = cand
        return out + ([line] if line else [])


def render(trial, cat, cfg, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = trial["folder"] / "recording.mp4"
    scene = Scene(trial, cat, cfg, 1)
    speed = nice_speed(scene.end - scene.start, (cfg.get("hero") or {}).get("seconds", 24))
    n = max(1, math.ceil((scene.end - scene.start) * FPS / speed))
    gif, still = out_dir / "hero.gif", out_dir / "hero.jpg"
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        tmp = Path(tmp)
        k = 0
        last = None
        for buf in media.frames(src, scene.start, FPS / speed, n, (W, VID)):
            t = scene.start + k * speed / FPS
            video = Image.frombytes("RGB", (W, VID), buf)
            img = scene.frame(video, t, speed)
            if k == 0:
                intro = scene.card(img, "intro", speed)
                for j in range(int(FPS * 2.6)):
                    intro.save(tmp / f"{j:05d}.png", compress_level=1)
                base = int(FPS * 2.6)
            img.save(tmp / f"{base + k:05d}.png", compress_level=1)
            last = (video, t)
            k += 1
        video, t = last
        final = scene.frame(video, scene.end, speed)
        card = scene.card(final, "grade", speed)
        for j in range(int(FPS * 4.5)):
            card.save(tmp / f"{base + k + j:05d}.png", compress_level=1)
        pattern = str(tmp / "%05d.png")
        pal = tmp / "palette.png"
        limit = (cfg.get("hero") or {}).get("max_mb", 12) * 1e6
        for colors, scale in ((256, 4), (192, 5), (128, 5)):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", pattern, "-vf",
                            f"palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=0", str(pal)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", pattern, "-i", str(pal),
                            "-lavfi", f"paletteuse=dither=bayer:bayer_scale={scale}:diff_mode=rectangle", "-loop", "0",
                            str(gif)], check=True)
            if gif.stat().st_size <= limit:
                break
    still_scene = Scene(trial, cat, cfg, 2)
    a, d = trial["web"]["armed"]
    t = (a or 0) + (cfg.get("hero") or {}).get("still_at", 0.56) * ((d or scene.dur) - (a or 0))
    t = best_still(scene, t)
    frame_png = out_dir / ".still.png"
    media.frame(src, t, frame_png, W * 2, quality=2)
    video = Image.open(frame_png).convert("RGB").resize((W * 2, VID * 2), Image.LANCZOS)
    still_scene.frame(video, t, speed).save(still, quality=88, optimize=True, progressive=True)
    frame_png.unlink(missing_ok=True)
    return gif, still


def best_still(scene, t):
    span = max(1.0, scene.end - scene.start)

    def score(c):
        said = any(0 <= c["t0"] + 0.4 - x["t"] < 6 for x in scene.texts)
        return (bool(c.get("pt") or c.get("near")) * 3 + bool(c.get("win")) * 2 + said * 2 + (c["kind"] == "act")
                - 4 * abs(c["t0"] - t) / span)

    cands = [c for c in scene.calls if c["kind"] != "setup"]
    return max(cands, key=score)["t0"] + 0.4 if cands else t
