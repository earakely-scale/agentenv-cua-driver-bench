import base64
import io
import random
from collections import defaultdict
from functools import lru_cache
from itertools import permutations
from html import escape
from math import ceil, floor, log10
from os.path import commonprefix
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import ImageFont

from . import catalog, failures

FONTS = Path(__file__).resolve().parent.parent / "fonts"
WEIGHTS = {400: "Inter-Regular.ttf", 600: "Inter-SemiBold.ttf", 700: "Inter-Bold.ttf", 800: "Inter-ExtraBold.ttf"}
SERIES = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
}
THEMES = {
    "light": {"surface": "#ffffff", "ink": "#101114", "ink2": "#4f535c", "ink3": "#80848d", "grid": "#e5e6e9",
              "axis": "#c9ccd2"},
    "dark": {"surface": "#0b0f19", "ink": "#eef0f4", "ink2": "#b4b8c3", "ink3": "#878c99", "grid": "#232838",
             "axis": "#3a4052"},
}


@lru_cache(maxsize=None)
def font(weight, size):
    return ImageFont.truetype(str(FONTS / WEIGHTS[weight]), size)


def width(text, weight, size):
    return font(weight, round(size * 4)).getlength(text) / 4


def pct(v):
    return f"{floor(100 * v + 0.5)}%"


class Svg:
    def __init__(self, w, h, theme):
        self.w, self.h, self.t, self.items, self.used = w, h, THEMES[theme], [], {}

    def text(self, x, y, s, size, weight=400, fill="ink", anchor="start", extra="", num=False):
        """``num`` sets the text in tabular figures; only numbers take them, since Inter's also widen the hyphen,
        the space and the comma."""
        self.used.setdefault(weight, set()).update(s)
        color = self.t.get(fill, fill)
        cls = ' class="n"' if num else ""
        self.items.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{color}" '
                          f'text-anchor="{anchor}"{extra}{cls}>{escape(s)}</text>')

    def add(self, s):
        self.items.append(s)

    def render(self, title, desc):
        faces = []
        for weight, chars in sorted(self.used.items()):
            faces.append(f"@font-face{{font-family:'CDB Inter';font-weight:{weight};"
                         f"src:url(data:font/woff2;base64,{woff2(weight, ''.join(sorted(chars)))}) format('woff2')}}")
        style = "".join(faces) + "text{font-family:'CDB Inter',Inter,system-ui,-apple-system,'Segoe UI',sans-serif}" \
                                 ".n{font-variant-numeric:tabular-nums}"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
                f'height="{self.h}" role="img" aria-labelledby="t d"><title id="t">{escape(title)}</title>'
                f'<desc id="d">{escape(desc)}</desc><style>{style}</style>' + "".join(self.items) + "</svg>\n")


@lru_cache(maxsize=None)
def woff2(weight, chars):
    f = TTFont(str(FONTS / WEIGHTS[weight]))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "tnum"]
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text=chars + " ")
    sub.subset(f)
    buf = io.BytesIO()
    f.flavor = "woff2"
    f.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def spread(items, gap, floor=float("inf")):
    """``items`` moved apart to at least ``gap`` between neighbours, then the whole column raised so that none sits
    below ``floor``."""
    items = sorted(items, key=lambda it: it["y"])
    for _ in range(50):
        moved = False
        for a, b in zip(items, items[1:]):
            if b["y"] - a["y"] < gap:
                mid = (a["y"] + b["y"]) / 2
                a["y"], b["y"] = mid - gap / 2, mid + gap / 2
                moved = True
        if not moved:
            break
    over = items[-1]["y"] - floor if items else 0
    for it in items if over > 0 else ():
        it["y"] -= over
    return items


#: The room between a side label and its point, for the leader to a point the label had to leave.
LEADER = 14


def label_h(s, label, note):
    return (s["os"] + 12 if label else 0) + (s["sub"] + 6 if label and note else 0)


def panel(svg, x0, y0, pw, ph, series, conds, theme, s, label=None, note=None):
    """A panel of lines, every point's value printed: above or below it, or with ``s["side"]`` beside it, the first
    condition's to its left and the last's to its right before the line's name, for lines too close to stack."""
    t = svg.t
    top = y0 + label_h(s, label, note)
    if label:
        svg.text(x0, y0 + s["os"] * 0.8, label, s["os"], 700)
        if note:
            svg.text(x0, y0 + s["os"] + 6 + s["sub"] * 0.8, note, s["sub"], 400, "ink3")
    side = s.get("side")
    val_w = width("100%", 700, s["val"])
    plot_top, plot_bot = top + (s["val"] * 0.5 + 6 if side else s["pad_top"]), y0 + ph - s["xlab"]
    name_w = max([width(sr["name"], 600, s["name"]) for sr in series] + [60])
    name_off = max(s["dot"] + s["end_gap"], val_w / 2 + 6)
    left = val_w + s["dot"] + LEADER + 7 if side else s["gut"]
    right = (s["dot"] + val_w + 16 + name_w if side else name_w + name_off - s["dot"]) + s["gut2"]
    xs = [x0 + left + i * (pw - left - right) / max(1, len(conds) - 1) for i in range(len(conds))]
    y = lambda v: plot_bot - v * (plot_bot - plot_top)
    grid_end = xs[-1] + s["dot"] + 3
    for g in (0, 0.5, 1.0):
        gy = y(g)
        svg.add(f'<line x1="{xs[0] - s["dot"] - 4 if side else x0 + s["gut"] - 26:.1f}" x2="{grid_end:.1f}" '
                f'y1="{gy:.1f}" y2="{gy:.1f}" stroke="{t["axis"] if g == 0 else t["grid"]}" stroke-width="1"/>')
        if not side:
            svg.text(x0 + s["gut"] - 32, gy + s["tick"] * 0.36, pct(g), s["tick"], 400, "ink3", "end", num=True)
    glosses = gloss_lines(conds, xs, s)
    for i, c in enumerate(conds):
        svg.text(xs[i], plot_bot + s["cond"] + 14, c["name"], s["cond"], 600, "ink", "middle")
        for k, line in enumerate(glosses[i]):
            svg.text(xs[i], plot_bot + s["cond"] + 20 + s["sub"] + k * (s["sub"] + 3), line, s["sub"], 400, "ink3",
                     "middle")
    halo = f' stroke="{t["surface"]}" stroke-width="4" stroke-linejoin="round" paint-order="stroke"'
    labels = {i: [] for i in range(len(conds))}
    ends, deltas = [], []
    for sr in series:
        for i, ci in enumerate(sr.get("ci") or []):
            if ci and sr["values"][i] is not None:
                lo, hi = y(ci[0]), y(ci[1])
                cap = s["dot"] + 3
                svg.add(f'<path d="M{xs[i]:.1f},{lo:.1f}V{hi:.1f}M{xs[i] - cap:.1f},{lo:.1f}H{xs[i] + cap:.1f}'
                        f'M{xs[i] - cap:.1f},{hi:.1f}H{xs[i] + cap:.1f}" stroke="{sr["color"]}" stroke-opacity=".38" '
                        f'stroke-width="2" fill="none" stroke-linecap="round"/>')
    drawn = []
    for sr in series:
        pts = [(xs[i], y(v), v) for i, v in enumerate(sr["values"]) if v is not None]
        if len(pts) >= 2:
            d = " ".join(f"{'M' if k == 0 else 'L'}{px:.1f},{py:.1f}" for k, (px, py, _) in enumerate(pts))
            over = any(all((a is None) == (b is None) and (a is None or abs(a - b) < 0.005)
                           for a, b in zip(sr["values"], prev)) for prev in drawn)
            dash = (f'stroke-linecap="butt" stroke-dasharray="{3 * s["line"]:.1f} {2.5 * s["line"]:.1f}"' if over
                    else 'stroke-linecap="round"')
            svg.add(f'<path d="{d}" fill="none" stroke="{sr["color"]}" stroke-width="{s["line"]}" {dash} '
                    f'stroke-linejoin="round"/>')
            drawn.append(sr["values"])
            if s.get("delta") and len(series) <= 3:
                (ax, ay, av), (bx, by, bv) = pts[0], pts[-1]
                dv = round(100 * (bv - av))
                if dv:
                    deltas.append({"x": (ax + bx) / 2, "y": (ay + by) / 2, "dv": dv})
        for i, v in enumerate(sr["values"]):
            if v is None:
                continue
            svg.add(f'<circle cx="{xs[i]:.1f}" cy="{y(v):.1f}" r="{s["dot"]}" fill="{sr["color"]}" '
                    f'stroke="{t["surface"]}" stroke-width="{s["ring"]}"/>')
            labels[i].append({"y": y(v), "v": v, "x": xs[i]})
        last = max((i for i, v in enumerate(sr["values"]) if v is not None), default=None)
        if last is not None:
            ends.append({"y": y(sr["values"][last]) + s["name"] * 0.36, "dot": y(sr["values"][last]),
                         "x": xs[last], "name": sr["name"], "v": sr["values"][last]})
    if side:
        side_labels(svg, s, labels[0], ends, val_w, halo, plot_bot)
        return
    taken = []
    for i, items in labels.items():
        placed = sides(items, 1, plot_bot - s["dot"] - s["val"] - 8)
        above = spread([{**it, "y": it["y"] - s["dot"] - 11} for it in placed if not it["below"]], s["val"] + 4)
        below = spread([{**it, "y": it["y"] + s["dot"] + s["val"] * 0.72 + 7} for it in placed if it["below"]],
                       s["val"] + 4)
        for it in above + below:
            ty = it["y"] if it["below"] else max(it["y"], top + s["val"])
            svg.text(it["x"], ty, pct(it["v"]), s["val"], 700, "ink", "middle", halo, num=True)
            taken.append(box(it["x"], ty, pct(it["v"]), 700, s["val"], "middle"))
    notes = []
    for d in sides(deltas, 2, plot_bot - 24, lambda d: d["dv"] > 0):
        rising, below = d["dv"] > 0, d["below"]
        text = f"{'−' if d['dv'] < 0 else '+'}{abs(d['dv'])} pts"
        nx, ny, anchor = d["x"] + (10 if rising == below else -10), d["y"] + (22 if below else -12), \
            "start" if rising == below else "end"
        notes.append((nx, ny, text, anchor, box(nx, ny, text, 600, s["sub"], anchor)))
    if not any(clash(b, other) for k, (*_, b) in enumerate(notes) for other in taken + [n[-1] for n in notes[:k]]):
        for nx, ny, text, anchor, _ in notes:
            svg.text(nx, ny, text, s["sub"], 600, "ink3", anchor, halo, num=True)
    for e in spread(ends, s["name"] + 6, plot_bot + s["name"] * 0.36):
        lx = e["x"] + name_off
        if abs(e["y"] - s["name"] * 0.36 - e["dot"]) > 3:
            svg.add(f'<path d="M{e["x"] + s["dot"] + 3:.1f},{e["dot"]:.1f} L{lx - 4:.1f},{e["y"] - s["name"] * 0.36:.1f}" '
                    f'stroke="{t["ink3"]}" stroke-width="1" fill="none"/>')
        svg.text(lx, e["y"], e["name"], s["name"], 600, "ink", "start")


def gloss_lines(conds, xs, s):
    """Each condition's gloss under its name, in lines: of two that would touch, the wider on two, or both when that
    isn't enough."""
    lines = [[c["short"]] for c in conds]
    ws = [width(c["short"], 400, s["sub"]) for c in conds]
    for i in range(len(conds) - 1):
        room = xs[i + 1] - xs[i] - 10
        if (ws[i] + ws[i + 1]) / 2 <= room:
            continue
        wide, narrow = (i, i + 1) if ws[i] >= ws[i + 1] else (i + 1, i)
        lines[wide] = balanced(conds[wide]["short"], 400, s["sub"], 2 * room - ws[narrow])
        if max(width(x, 400, s["sub"]) for x in lines[wide]) > 2 * room - ws[narrow]:
            lines[i], lines[i + 1] = (balanced(conds[j]["short"], 400, s["sub"], room) for j in (i, i + 1))
    return lines


def side_labels(svg, s, firsts, ends, val_w, halo, floor=float("inf")):
    """The first condition's values in a column left of their points; the last's in a column right of theirs, each
    before its line's name. Both spread apart in order, and a leader goes to any point its label had to leave."""
    for it in spread([{**it, "dot": it["y"], "y": it["y"] + s["val"] * 0.36} for it in sides(firsts, 2, float("inf"))],
                     s["val"] + 3):
        vx = it["x"] - s["dot"] - LEADER - 3
        if abs(it["y"] - s["val"] * 0.36 - it["dot"]) > 3:
            svg.add(f'<path d="M{vx + 4:.1f},{it["y"] - s["val"] * 0.36:.1f} L{it["x"] - s["dot"] - 3:.1f},{it["dot"]:.1f}" '
                    f'stroke="{svg.t["ink3"]}" stroke-width="1" fill="none"/>')
        svg.text(vx, it["y"], pct(it["v"]), s["val"], 700, "ink", "end", halo, num=True)
    size = max(s["val"], s["name"])
    for e in spread([{**e, "y": e["dot"] + size * 0.36} for e in ends], size + 5, floor):
        vx, text = e["x"] + s["dot"] + 8 + val_w, pct(e["v"])
        if abs(e["y"] - size * 0.36 - e["dot"]) > 3:
            svg.add(f'<path d="M{e["x"] + s["dot"] + 3:.1f},{e["dot"]:.1f} L{vx - width(text, 700, s["val"]) - 4:.1f},'
                    f'{e["y"] - size * 0.36:.1f}" stroke="{svg.t["ink3"]}" stroke-width="1" fill="none"/>')
        svg.text(vx, e["y"], text, s["val"], 700, "ink", "end", halo, num=True)
        svg.text(vx + 8, e["y"], e["name"], s["name"], 600, "ink", "start")


def sides(items, same, floor, alone=lambda it: False):
    """The labels at one place, top first, less any that repeats one within ``same`` px; the lowest of several goes
    `below` its point when that is above ``floor``, so two close lines keep their labels apart; a lone one as
    ``alone`` says."""
    kept = []
    for it in sorted(items, key=lambda it: it["y"]):
        text = it["dv"] if "dv" in it else pct(it["v"])
        if not any(k["text"] == text and abs(k["y"] - it["y"]) <= same for k in kept):
            kept.append({**it, "text": text})
    for k, it in enumerate(kept):
        it["below"] = alone(it) if len(kept) == 1 else k == len(kept) - 1 and it["y"] <= floor
    return kept


def box(x, baseline, text, weight, size, anchor):
    w = width(text, weight, size)
    left = x - {"start": 0, "middle": w / 2, "end": w}[anchor]
    return left - 3, baseline - 0.75 * size - 3, left + w + 3, baseline + 0.25 * size + 3


def clash(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


DESKTOP = {"title": 24, "subtitle": 14, "os": 15, "tick": 12, "cond": 14, "sub": 12, "val": 17, "name": 15,
           "foot": 12, "line": 3.5, "dot": 7, "ring": 3, "gut": 84, "gut2": 8, "end_gap": 12, "pad_top": 44,
           "xlab": 64, "delta": True}
PHONE = {"title": 20, "subtitle": 12.5, "os": 14, "tick": 11.5, "cond": 13, "sub": 11.5, "val": 15, "name": 13,
         "foot": 11, "line": 3, "dot": 6, "ring": 2.5, "gut": 64, "gut2": 4, "end_gap": 9, "pad_top": 38,
         "xlab": 58, "delta": True}


def wrap(text, weight, size, maxw):
    out, line = [], ""
    for word in text.split():
        cand = f"{line} {word}".strip()
        if width(cand, weight, size) <= maxw or not line:
            line = cand
        else:
            out.append(line)
            line = word
    return out + ([line] if line else [])


def balanced(text, weight, size, maxw):
    """``text`` on one line when it fits ``maxw``, else on two split where the longer is shortest, else wrapped."""
    if width(text, weight, size) <= maxw:
        return [text]
    words = text.split()
    longest = lambda pair: max(width(x, weight, size) for x in pair)
    pairs = [(" ".join(words[:k]), " ".join(words[k:])) for k in range(1, len(words))]
    fits = [p for p in pairs if longest(p) <= maxw]
    return list(min(fits, key=longest)) if fits else wrap(text, weight, size, maxw)


def figure(spec, theme, phone):
    s = {**(PHONE if phone else DESKTOP), "delta": spec.get("delta", True), "side": spec.get("side", False)}
    panels = spec["panels"]
    n = len(panels)
    W = 360 if phone else (720 if n == 1 else 60 + spec.get("panel_w", 360) * n)
    margin = 16 if phone else 28
    head_lines = wrap(spec["subtitle"], 400, s["subtitle"], W - 2 * margin)
    head = margin + s["title"] + 8 + len(head_lines) * (s["subtitle"] + 5)
    ph = 250 if phone else 300
    foot_lines = wrap(spec["foot"], 400, s["foot"], W - 2 * margin)
    labelled = n > 1 or spec.get("labelled")
    lab = label_h(s, labelled, any(p.get("note") for p in panels))
    if phone:
        H = head + 14 + n * (ph + lab) + (n - 1) * 18 + 16 + len(foot_lines) * (s["foot"] + 5) + margin - 6
    else:
        H = head + 18 + ph + lab + 18 + len(foot_lines) * (s["foot"] + 5) + margin - 6
    svg = Svg(W, round(H), theme)
    svg.text(margin, margin + s["title"] * 0.8, spec["title"], s["title"], 800)
    for k, line in enumerate(head_lines):
        svg.text(margin, margin + s["title"] + 10 + k * (s["subtitle"] + 5) + s["subtitle"] * 0.75, line,
                 s["subtitle"], 400, "ink2")
    y0 = head + (14 if phone else 18)
    colors = SERIES[theme]
    for k, p in enumerate(panels):
        series = [{"name": sr["name"], "values": sr["values"], "ci": sr.get("ci"), "color": colors[sr["slot"] % len(colors)]}
                  for sr in p["series"]]
        label = p["label"] if labelled else None
        hh = ph + lab
        if phone:
            panel(svg, margin, y0, W - 2 * margin, hh, series, spec["conds"], theme, s, label, p.get("note"))
            y0 += hh + 18
        else:
            pw = (W - 2 * margin - (n - 1) * 36) / n
            panel(svg, margin + k * (pw + 36), y0, pw, hh, series, spec["conds"], theme, s, label, p.get("note"))
    fy = H - margin + 6 - (len(foot_lines) - 1) * (s["foot"] + 5) - 4
    for k, line in enumerate(foot_lines):
        svg.text(margin, fy + k * (s["foot"] + 5), line, s["foot"], 400, "ink3")
    return svg.render(spec["title"], spec["desc"])


def boot_ci(values, n=2000, seed=7):
    rng = random.Random(seed)
    k = len(values)
    means = sorted(sum(values[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def specs(cat):
    """The results figures, of the board's rows on the bench's first driver: a panel per OS, a line per model."""
    conds = [c for c in cat["conditions"] if c["id"] in ("foreground", "background")]
    cids = [c["id"] for c in conds]
    models = {m["id"]: m for m in cat["models"] if m["board"]}
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    order = [t["id"] for t in cat["tasks"]]
    runs_in = {t["id"]: t["conditions"] for t in cat["tasks"]}
    board = [r for r in cat["board"] if r["driver"] == cat["driver"]]
    runs = sorted({p["n"] for r in board for p in r["tasks"].values()} or {1})
    out = {}
    for key, metric, title in (("task-score", "score", "Task score"), ("full-pass", "pass", "Full pass")):
        panels, used, counts, ci_any = [], set(), set(), False
        for o in cat["oses"]:
            series = []
            for mid, m in models.items():
                rows = {r["condition"]: r for r in board if r["os"] == o["id"] and r["model"] == mid}
                if not rows:
                    continue
                sets = [set(rows[c]["tasks"]) for c in cids if c in rows]
                common = {t for t in set().union(*sets) if all(t in rows[c]["tasks"] or c not in runs_in[t]
                                                               for c in cids)} if len(sets) == len(cids) and sets else set()
                vals, cis = [], []
                for c in cids:
                    if c not in rows:
                        vals.append(None)
                        cis.append(None)
                        continue
                    ts = [t for t in order if t in (common or rows[c]["tasks"]) and t in rows[c]["tasks"]]
                    used |= set(ts)
                    counts.add(len(ts))
                    xs = [rows[c]["tasks"][t][metric] for t in ts if rows[c]["tasks"][t][metric] is not None]
                    vals.append(sum(xs) / len(xs) if xs else None)
                    cis.append(boot_ci(xs) if len(xs) >= 3 else None)
                ci_any |= any(cis)
                series.append({"name": m["name"], "slot": m["slot"], "values": vals, "ci": cis})
            if series:
                panels.append({"label": o["name"], "series": series})
        span = catalog.ranges([short[t] for t in order if t in used])
        n_tasks = (f"{min(counts)}" if len(counts) == 1 else f"the {min(counts)}–{max(counts)}") if counts else "0"
        many = max(counts, default=0) != 1
        via = next((d["name"] for d in cat["drivers"] if d["id"] == cat["driver"]), cat["driver"])
        if key == "task-score":
            sub = (f"trycua's evaluator (weighted checks), mean over {span}, all through {via}. The drop is the "
                   "bench's point: the same tasks while a user keeps typing.")
        else:
            sub = (f"Share of trials of {span}, all through {via}, where every half of the grade held: the task, GUI "
                   "only, and in the background the user undisturbed.")
        nrun = f"{runs[0]}" if len(runs) == 1 else f"{runs[0]}–{runs[-1]}"
        only = catalog.only_in(cat, used)
        foot = (f"n = {nrun} run{'s' if runs[-1] != 1 else ''} per task and condition; each point averages {n_tasks} "
                f"task{'s' if many else ''} its model ran on that OS in both conditions"
                + (f" ({only}). " if only else ". ")
                + ("Whiskers: 95% bootstrap interval over tasks. " if ci_any else "Too few tasks for an interval. ")
                + " · ".join(o["name"] + (f" ({o['detail'].split(' · ')[0]})" if o.get("detail") else "") for o in cat["oses"])
                + ". Tasks by trycua's Cua Driver Bench, run on AgentEnv; not trycua's official results.")
        desc = "; ".join(f"{p['label']} {sr['name']}: " + ", ".join(
            f"{c['name'].lower()} {pct(v) if v is not None else 'n/a'}" for c, v in zip(conds, sr["values"]))
            for p in panels for sr in p["series"])
        out[key] = {"title": title, "subtitle": sub, "panels": panels, "conds": conds, "foot": foot, "desc": desc}
    return out


def driver_specs(cat):
    """The drivers figures: a panel per OS and model that several drivers ran, a line per driver, each panel over the
    tasks all its drivers ran in each condition they ran (the catalog's comparisons), each condition over those it
    scores, so a panel compares like with like; a driver that didn't run a condition has no point there."""
    conds = [c for c in cat["conditions"] if c["id"] in ("foreground", "background")]
    drivers = {d["id"]: d for d in cat["drivers"]}
    names = {m["id"]: m["name"] for m in cat["models"]}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    rows = {(r["os"], r["model"], r["driver"], r["condition"]): r for r in cat["board"]}
    runs = sorted({cell["n"] for c in cat["comparisons"] for d in c["drivers"] for k in conds if k["id"] in d
                   for t, cell in rows[(c["os"], c["model"], d["id"], k["id"])]["tasks"].items() if t in c["tasks"]}
                  or {1})
    out = {}
    for key, metric, title in (("drivers-task-score", "score", "Task score by driver"),
                               ("drivers-full-pass", "pass", "Full pass by driver")):
        panels, halves = [], []
        for c in cat["comparisons"]:
            per = {(d["id"], k["id"]): {t: cell[metric] for t, cell in rows[(c["os"], c["model"], d["id"], k["id"])][
                "tasks"].items() if t in c["tasks"]} for d in c["drivers"] for k in conds if k["id"] in d}
            base = cat["driver"] if any(d["id"] == cat["driver"] for d in c["drivers"]) else c["drivers"][0]["id"]
            for d in c["drivers"]:
                for k in conds:
                    mine, theirs = per.get((d["id"], k["id"]), {}), per.get((base, k["id"]), {})
                    gaps = [mine[t] - theirs[t] for t in mine if t in theirs and None not in (mine[t], theirs[t])]
                    if d["id"] != base and len(gaps) >= 3:
                        lo, hi = boot_ci(gaps)
                        halves.append((hi - lo) / 2)
            panels.append({"label": f"{names[c['model']]} on {osn[c['os']]}",
                           "note": f"{len(c['tasks'])} task{'s' if len(c['tasks']) != 1 else ''} · "
                                   f"{catalog.ranges([short[t] for t in c['tasks']])}",
                           "series": [{"name": drivers[d["id"]].get("label") or drivers[d["id"]]["name"],
                                       "slot": drivers[d["id"]]["slot"],
                                       "values": [d[k["id"]][metric] if k["id"] in d else None for k in conds]}
                                      for d in c["drivers"]]})
        if key == "drivers-task-score":
            sub = ("The same OS, model and tasks; only the computer-use driver changes. trycua's evaluator (weighted "
                   "checks), mean over the tasks every driver ran, each condition over those it scores.")
        else:
            sub = ("The same OS, model and tasks; only the computer-use driver changes. Share of trials where every "
                   "half of the grade held: the task, GUI only, and in the background the user undisturbed.")
        nrun = f"{runs[0]}" if len(runs) == 1 else f"{runs[0]}–{runs[-1]}"
        noise = sorted(halves)[len(halves) // 2] if halves else None
        foot = (f"n = {nrun} run{'s' if runs[-1] != 1 else ''} per task and condition. "
                + (f"Over so few tasks, a gap under about {round(100 * noise)} points between two drivers is within "
                   "the 95% bootstrap interval of their difference, paired by task. " if noise else "")
                + " · ".join(d["detail"].split(",")[0] for d in cat["drivers"] if d.get("detail"))
                + ". Tasks by trycua's Cua Driver Bench, run on AgentEnv; not trycua's official results.")
        desc = "; ".join(f"{p['label']}, {sr['name']}: " + ", ".join(
            f"{k['name'].lower()} {pct(v) if v is not None else 'n/a'}" for k, v in zip(conds, sr["values"]))
            for p in panels for sr in p["series"])
        out[key] = {"title": title, "subtitle": sub, "panels": panels, "conds": conds, "foot": foot, "desc": desc,
                    "labelled": True, "delta": False, "side": True, "panel_w": 390}
    return out


def compare_specs(cat):
    """The comparison figures: each task's passes per model on the OS where the bench's first driver ran the most models,
    and as ``models-tasks-<os>`` on each other OS where it ran two or more; the share of trials passed against what a
    trial costs, with the frontier; and each model's full pass on each OS; each with the notes the card and the Space
    print under it."""
    grids = {"models-tasks": tasks_spec(cat)}
    widest_os = widest(cat)[0]["id"]
    grids |= {f"models-tasks-{os_id}": tasks_spec(cat, os_id) for os_id, models in ran_models(cat).items()
              if os_id != widest_os and len(models) >= 2}
    return {**grids, "pareto": pareto_spec(cat), "os-gap": gap_spec(cat)}


def tasks_spec(cat, os_id=None):
    """A block per condition of a row per task under its family and a column per model, on ``os_id``, by default the OS
    where the bench's first driver ran the most models: each cell the task's row on the board, "off" where the bench
    doesn't run the task in that condition, None where it hasn't run yet."""
    os_, models = widest(cat) if os_id is None else (next(o for o in cat["oses"] if o["id"] == os_id),
                                                       ran_models(cat)[os_id])
    rows = {(r["model"], r["condition"]): r["tasks"] for r in cat["board"]
            if r["os"] == os_["id"] and r["driver"] == cat["driver"]}
    groups = []
    for t in cat["tasks"]:
        if not groups or groups[-1][0] != t["family_name"]:
            groups.append((t["family_name"], []))
        groups[-1][1].append({"id": t["id"], "probe": catalog.short(t), "label": t.get("label") or "",
                              "conditions": t["conditions"]})
    blocks = []
    for c in (c for c in cat["conditions"] if c["id"] in catalog.CONDITIONS):
        cells = {(t["id"], m["id"]): rows[(m["id"], c["id"])].get(t["id"]) if c["id"] in t["conditions"] else "off"
                 for t in cat["tasks"] for m in models}
        marks = {t: cv for cv in cat.get("caveats") or [] if cv.get("os") in (None, os_["id"]) and cv["condition"] == c["id"]
                 for t in cv["tasks"]}
        blocks.append({"id": c["id"], "label": c["name"], "short": c.get("short", ""), "cells": cells, "marks": marks})
    ran = [x for b in blocks for x in b["cells"].values() if isinstance(x, dict)]
    full = max((x["n"] for x in ran), default=0)
    codex = [m["name"] for m in models if m["harness"] == "codex-cli"]
    cols = [{"id": m["id"], "name": m["name"], "family": f, "variant": v, "harness": m["harness"]}
            for m, (f, v) in zip(models, heads([m["name"] for m in models]))]
    sub = (f"{os_['name']}, all through {label_of(cat, cat['driver'])}: how many of each task's {full} runs passed."
           + (f" {kin(codex)} runs in Codex, which gives it the driver's accessibility tree but never its screenshots."
              if codex else ""))
    foot = ("A run passes when the task is done, through the GUI only, and in the background with the user undisturbed"
            + ("; 2/4 is 2 of the 4 runs so far" if any(x["n"] < full for x in ran) else "") + ". "
            + ("An outlined cell hasn't run yet. " if any(x is None for b in blocks for x in b["cells"].values()) else "")
            + "Tasks by trycua's Cua Driver Bench, run on AgentEnv; not trycua's official results.")
    desc = "; ".join(f"{b['label']}, {c['name']}: " + ", ".join(
        f"{r['probe']} {x['passed']} of {x['n']}" for _, rs in groups for r in rs
        if isinstance(x := b["cells"][(r["id"], c["id"])], dict)) for b in blocks for c in cols)
    return {"title": "Passes by task and model", "subtitle": sub, "foot": foot, "desc": desc, "draw": task_grid,
            "panels": blocks if models else [], "cols": cols, "groups": groups, "full": full,
            "notes": tasks_notes(os_, blocks, groups, cols) if models else []}


def tasks_notes(os_, blocks, groups, cols):
    """The grid's sentences: what passes in the background and which rows can't, how the harnesses' models part in the
    foreground and where most, and the family no model gets far in."""
    fg, bg = blocks
    rows = {r["id"]: r for _, rs in groups for r in rs}
    named = lambda r: f"{r['probe']} ({r['label']})" if r["label"] else r["probe"]
    ids = [c["id"] for c in cols]

    def total(block, tasks, models):
        got = [x for t in tasks for m in models if isinstance(x := block["cells"][(t, m)], dict)]
        return sum(x["passed"] for x in got), sum(x["n"] for x in got)

    passing = [t for t in rows if total(bg, [t], ids)[0]]
    p, n = total(bg, list(rows), ids)
    if len(passing) == 1:
        a, b = total(bg, passing, ids)
        every = all(total(bg, passing, [m])[0] for m in ids)
        out = [f"With the user typing on {os_['name']}, {'every model passes' if every else 'the models pass'} "
               f"{named(rows[passing[0]])} and no other task: {f'all {b}' if a == b else a} of its "
               f"{'' if a == b else f'{b} '}trials" + (f", against none of the other {n - b}." if n > b else ".")]
    else:
        out = [f"With the user typing on {os_['name']}, the models pass {p} of {n} trials"
               + (f", all of them in {join([rows[t]['probe'] for t in passing])}." if passing else ".")]
    marked = defaultdict(list)
    for t, cv in bg["marks"].items():
        marked[(cv["mark"], cv["short"])].append(rows[t]["probe"])
    if marked:
        out.append("The marked rows can't pass there: " + join([f"{join(ps)} ({mark} {short[0].lower()}{short[1:]})"
                                                                for (mark, short), ps in marked.items()]) + ".")
    by = defaultdict(list)
    for c in cols:
        by[c["harness"]].append(c["id"])
    if len(by) > 1:
        rate = lambda ms: (lambda k: k[0] / max(1, k[1]))(total(fg, list(rows), ms))
        a, b = sorted(by.values(), key=rate, reverse=True)[:2]
        share = lambda t, ms: (lambda k: k[0] / max(1, k[1]))(total(fg, [t], ms))
        wide = max((t for t in rows if "foreground" in rows[t]["conditions"]), key=lambda t: share(t, a) - share(t, b))
        name = lambda ms: kin([c["name"] for c in cols if c["id"] in ms])
        out.append(f"With the desktop to itself, the {name(a)} models pass {of(*total(fg, list(rows), a))} trials and "
                   f"the {name(b)} models {of(*total(fg, list(rows), b))}; they part most on {named(rows[wide])}, "
                   f"{of(*total(fg, [wide], a))} against {of(*total(fg, [wide], b))}.")
    fam = min(groups, key=lambda g: (lambda k: k[0] / max(1, k[1]))(total(fg, [r["id"] for r in g[1]], ids)))
    tasks = [r["id"] for r in fam[1]]
    never = [r for r in fam[1] if not total(fg, [r["id"]], ids)[0] and not total(bg, [r["id"]], ids)[0]]
    best = max(cols, key=lambda c: total(fg, tasks, [c["id"]])[0])
    top = [c["name"] for c in cols if total(fg, tasks, [c["id"]])[0] == total(fg, tasks, [best["id"]])[0]]
    out.append(f"{fam[0]} are the hardest: "
               + (f"no model passes {join([named(r) for r in never])} in either condition, and " if never else "")
               + f"the best in the foreground, {join(top)}, pass{'es' if len(top) == 1 else ''} "
               f"{of(*total(fg, tasks, [best['id']]))}.")
    return out

def pareto_spec(cat):
    """The share of trials that fully pass against a trial's mean cost at list price, a row of panels per condition: the
    models the bench's first driver ran on the OS with the most of them, and the drivers of the widest comparison, each
    over the trials every point of it ran, with the frontier."""
    os_, models = widest(cat)
    names = {m["id"]: m["name"] for m in cat["models"]}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    sets = [("models", f"Models on {os_['name']}", f"through {label_of(cat, cat['driver'])}", os_["id"],
             [(cat["driver"], m["id"], m["name"], m["slot"]) for m in models])]
    if cat["comparisons"]:
        c = max(cat["comparisons"], key=lambda c: (len(c["drivers"]), len(c["tasks"])))
        slots = {d["id"]: d["slot"] for d in cat["drivers"]}
        sets.append(("drivers", f"Drivers on {osn[c['os']]}", names[c["model"]], c["os"],
                     [(d["id"], c["model"], label_of(cat, d["id"]), slots[d["id"]]) for d in c["drivers"]]))
        ran = {d["id"]: d for d in c["drivers"]}
    panels = []
    for cond in (c for c in cat["conditions"] if c["id"] in catalog.CONDITIONS):
        for kind, label, via, os_id, entries in sets:
            entries = [e for e in entries if kind != "drivers" or cond["id"] in ran[e[0]]]
            points = tally(cat, os_id, entries, cond["id"])
            if len(points) < 2:
                continue
            for p in frontier(points):
                p["frontier"] = True
            ns = sorted({p["n"] for p in points})
            panels.append({"label": f"{label} · {cond['name'].lower()}", "kind": kind, "cond": cond["name"].lower(),
                           "note": f"{via} · {ns[0]}{f'–{ns[-1]}' if len(ns) > 1 else ''} trials each",
                           "points": points, "os": osn[os_id], "via": via})
    sub = ("The share of trials that fully pass against what a trial costs at list price, on a log scale, a row per "
           "condition. The line is the frontier: the most any point passes at that cost or less; a hollow point passes "
           "no more than a cheaper one.")
    foot = ("Each panel counts the same trials for every point: those of the tasks all of them ran in that condition. "
            "Cost from the tokens each trial's trajectory reports, at Anthropic's and OpenAI's list prices. Tasks by "
            "trycua's Cua Driver Bench, run on AgentEnv; not trycua's official results.")
    desc = "; ".join(f"{p['label']}, {q['name']}: {pct(q['share'])} of {q['n']} trials passed at ${q['cost']:.2f} a "
                     f"trial{', on the frontier' if q['frontier'] else ''}" for p in panels for q in p["points"])
    return {"title": "Passes against cost", "subtitle": sub, "foot": foot, "desc": desc, "draw": scatter,
            "panels": panels, "cols": len(sets), "notes": pareto_notes(panels)}


def pareto_notes(panels):
    """A sentence per panel: what passes the most and at what cost, and the frontier up to it; or, when every point
    passes as much, that the cheapest is the whole frontier."""
    out = []
    said = lambda q: f"{q['name']} ({pct(q['share'])} at ${q['cost']:.2f})"
    for p in panels:
        pts = p["points"]
        front = sorted((q for q in pts if q["frontier"]), key=lambda q: q["cost"])
        where = f"In the {p['cond']} on {p['os']}" + (f", with {p['via']}" if p["kind"] == "drivers" else "")
        if len({q["share"] for q in pts}) == 1:
            out.append(f"{where}, every {p['kind'][:-1]} passes {pct(pts[0]['share'])}, so the cheapest, "
                       f"{said(front[0])}, is the whole frontier.")
            continue
        top = max(pts, key=lambda q: (q["share"], -q["cost"]))
        out.append(f"{where}, {top['name']} passes the most, {pct(top['share'])} at ${top['cost']:.2f} a trial; "
                   + (f"the frontier is {join([said(q) for q in front])}." if len(front) > 1
                      else "nothing cheaper passes as much."))
    return out

def gap_spec(cat):
    """Full pass by OS: a panel per model the bench's first driver ran on several OSes, a line per OS, each panel over the
    tasks all its OSes ran in both conditions, each condition over those it scores."""
    conds = [c for c in cat["conditions"] if c["id"] in catalog.CONDITIONS]
    slots = {o["id"]: k for k, o in enumerate(cat["oses"])}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    names = {m["id"]: m["name"] for m in cat["models"]}
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    gaps = os_gaps(cat)
    panels = [{"label": names[g["model"]],
               "note": f"{len(g['tasks'])} task{'s' if len(g['tasks']) != 1 else ''} · "
                       f"{catalog.ranges([short[t] for t in g['tasks']])}",
               "series": [{"name": osn[o["id"]], "slot": slots[o["id"]], "values": [o[c["id"]]["pass"] for c in conds]}
                          for o in g["oses"]]} for g in gaps]
    via = label_of(cat, cat["driver"])
    runs = sorted({o[c]["n"] for g in gaps for o in g["oses"] for c in catalog.CONDITIONS})
    sub = (f"The same model and driver, {via}; only the operating system changes. Share of trials where every half of "
           "the grade held: the task, GUI only, and in the background the user undisturbed.")
    foot = ("Each panel averages the tasks every OS ran for its model, each condition over those it scores; "
            + (f"{runs[0]}–{runs[-1]}" if len(runs) > 1 else f"{runs[0] if runs else 0}") + " trials a point. "
            + " · ".join(o["name"] + (f" ({o['detail'].split(' · ')[0]})" if o.get("detail") else "")
                         for o in cat["oses"] if any(x["id"] == o["id"] for g in gaps for x in g["oses"]))
            + ". Tasks by trycua's Cua Driver Bench, run on AgentEnv; not trycua's official results.")
    desc = "; ".join(f"{p['label']}, {sr['name']}: " + ", ".join(
        f"{c['name'].lower()} {pct(v) if v is not None else 'n/a'}" for c, v in zip(conds, sr["values"]))
        for p in panels for sr in p["series"])
    return {"title": "Full pass by operating system", "subtitle": sub, "panels": panels, "conds": conds, "foot": foot,
            "desc": desc, "labelled": True, "delta": False, "side": True, "panel_w": 390, "draw": rows,
            "notes": gap_notes(gaps, names, osn, via, next(((cv["os"], [short[x] for x in cv["tasks"]], cv["mark"])
                                                            for cv in cat.get("caveats") or [] if cv.get("os")
                                                            and cv["condition"] == "background"), None))}


def gap_notes(gaps, names, osn, via, marks):
    """The OS gap's sentences: the widest panel's two conditions on each OS, the other panels' backgrounds, how far the
    OSes part in each condition, and the tasks one OS can't pass in the background."""
    if not gaps:
        return []
    order = lambda g: sorted(g["oses"], key=lambda o: -(o["background"]["pass"] or 0))
    g = max(gaps, key=lambda g: len(g["tasks"]))
    hi, lo = order(g)[:2]
    out = [f"Through {via}, with the user typing, {names[g['model']]} passes {pct(hi['background']['pass'])} of its "
           f"trials on {osn[hi['id']]} against {pct(lo['background']['pass'])} on {osn[lo['id']]}, after "
           f"{pct(hi['foreground']['pass'])} and {pct(lo['foreground']['pass'])} with the desktop to itself, over "
           f"{len(g['tasks'])} tasks."]
    rest = [x for x in gaps if x is not g]
    if rest:
        same = all(order(x)[0]["id"] == hi["id"] for x in rest)
        each = [f"{names[x['model']]} {pct(order(x)[0]['background']['pass'])} on {osn[order(x)[0]['id']]} against "
                f"{pct(order(x)[1]['background']['pass'])} over its {len(x['tasks'])} "
                f"task{'s' if len(x['tasks']) != 1 else ''}" for x in rest]
        out.append(("The others go the same way: " if same else "The others: ") + join(each) + ".")
    part = lambda c: join([str(round(100 * abs(x["oses"][0][c]["pass"] - x["oses"][1][c]["pass"]))) for x in gaps])
    who = join([v for _, v in heads([names[x["model"]] for x in gaps])])
    out.append(f"For {who} the OSes part by {part('foreground')} points in the foreground and {part('background')} "
               "in the background" + (f"; on {osn[marks[0]]}, {join(marks[1])} can't pass in the background ({marks[2]})"
                                      if marks else "") + ".")
    return out


#: A model's lab, by its id's prefix, and the series slot its dots take.
LABS = {"anthropic/": ("Claude", 0), "openai/": ("GPT", 1)}


def story_specs(cat):
    """The card's opening figure, ``decides``: whether the model or the setup decides a result; and its showcase of the
    operating systems, ``by-os``."""
    return {"decides": decides_spec(cat), "by-os": os_spec(cat)}


def os_spec(cat):
    """Full pass per model, a dot each, a row per OS, the bench's first driver held fixed: the models it ran on every
    one of those OSes in both conditions, each condition over the tasks every one of them ran there, so a row's spread is
    the model's part and the rows' gap is the OS's."""
    conds = [c for c in cat["conditions"] if c["id"] in catalog.CONDITIONS]
    rows_by = {(r["os"], r["model"], r["condition"]): r for r in cat["board"] if r["driver"] == cat["driver"]}
    oses = [o for o in cat["oses"] if any((o["id"], m["id"], c) in rows_by for m in cat["models"] for c in catalog.CONDITIONS)]
    models = [m for m in cat["models"] if all((o["id"], m["id"], c) in rows_by for o in oses for c in catalog.CONDITIONS)]
    tasks = {c["id"]: [t["id"] for t in cat["tasks"] if c["id"] in t["conditions"] and all(
        t["id"] in rows_by[(o["id"], m["id"], c["id"])]["tasks"] for o in oses for m in models)] for c in conds}
    via = label_of(cat, cat["driver"])
    rows = []
    if len(oses) > 1 and models:
        for o in oses:
            cells = {c["id"]: [{"model": m["id"], "name": m["name"], "lab": lab_of(m["id"]),
                                **{k: v for k, v in catalog.summary(rows_by[(o["id"], m["id"], c["id"])], tasks[c["id"]]).items()
                                   if k in ("passed", "n")}} for m in models] for c in conds if tasks[c["id"]]}
            rows.append({"os": o["name"], "driver": via, "label": o["name"], "os_id": o["id"], "driver_id": cat["driver"],
                         "cells": cells})
    full = {c: usual([p["n"] for r in rows for p in r["cells"].get(c, [])]) for c in catalog.CONDITIONS}
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    span = {c: catalog.ranges([short[t] for t in ts]) for c, ts in tasks.items()}
    sub = (f"The same models and driver, {via}, on each operating system: full passes per model, a dot each, over the "
           "tasks every one of them ran. Every row holds the same models, so the rows' gap is the operating system's.")
    foot = (f"A dot is one model's {full.get('foreground', 0)} foreground or {full.get('background', 0)} background "
            f"trials ({span.get('foreground', '')} in the foreground, {span.get('background', '')} in the background); "
            "tied models share a dot, with their count above it. Full pass: the task done, through the GUI only, and in "
            "the background with the user undisturbed on all eight of trycua's criteria. Tasks by trycua's Cua Driver "
            "Bench, run on AgentEnv; not trycua's official results.")
    desc = "; ".join(f"{r['label']}, {c['name'].lower()}: " + ", ".join(f"{p['name']} {p['passed']} of {p['n']}"
                                                                         for p in r["cells"][c["id"]])
                     for r in rows for c in conds if r["cells"].get(c["id"]))
    return {"title": "The same models and driver on each operating system", "subtitle": sub, "foot": foot, "desc": desc,
            "panels": rows, "conds": conds, "full": full, "tasks": tasks, "models": [m["id"] for m in models],
            "draw": strips}


def decides_spec(cat):
    """Full pass per model, a dot each, for each OS and driver over the whole bench in each condition: the models that
    ran every trial of a condition, a row per OS and driver with two of them or more, so a row's spread is the model's
    part and the rows' gap is the setup's. An OS whose complete count isn't the bench's, one that runs part of it or
    merges two runs of a model, has no row."""
    conds = [c for c in cat["conditions"] if c["id"] in catalog.CONDITIONS]
    whole = complete_counts(cat["board"])
    full = {c["id"]: usual([n for (_, cond), n in whole.items() if cond == c["id"]]) for c in conds}
    names = {m["id"]: m["name"] for m in cat["models"]}
    rows = []
    for o in cat["oses"]:
        for d in cat["drivers"]:
            cells = {}
            for c in conds:
                got = [b for b in cat["board"] if (b["os"], b["driver"], b["condition"]) == (o["id"], d["id"], c["id"])
                       and b["n_trials"] == whole.get((o["id"], c["id"])) == full[c["id"]] and b["model"] in names]
                cells[c["id"]] = [{"model": b["model"], "name": names[b["model"]], "passed": b["passed"],
                                   "n": b["n_trials"], "lab": lab_of(b["model"])} for b in got]
            if max(len(v) for v in cells.values()) >= 2:
                rows.append({"os": o["name"], "driver": label_of(cat, d["id"]),
                             "label": f"{o['name']} · {label_of(cat, d['id'])}", "cells": cells})
    sub = ("Full passes per model, a dot each, for every operating system and driver that ran the whole bench. With the "
           "desktop to itself the models spread out; with the user typing in their own window they bunch together, at "
           "a level the driver and the operating system set.")
    foot = (f"A dot is one model's {full.get('foreground', 0)} foreground or {full.get('background', 0)} background "
            "trials; tied models share a dot, with their count above it. Full pass: the task done, through the GUI only, "
            "and in the background with the user undisturbed on all eight of trycua's criteria. Tasks by trycua's Cua "
            "Driver Bench, run on AgentEnv; not trycua's official results.")
    desc = "; ".join(f"{r['label']}, {c['name'].lower()}: " + ", ".join(f"{p['name']} {p['passed']} of {p['n']}"
                                                                         for p in r["cells"][c["id"]])
                     for r in rows for c in conds if r["cells"][c["id"]])
    return {"title": "With the user typing, the setup decides, not the model", "subtitle": sub, "foot": foot,
            "desc": desc, "panels": rows, "conds": conds, "full": full, "draw": strips}


def complete_counts(board):
    """Each OS and condition's count of trials in a complete run of the bench: the most common among its board rows,
    the larger on a tie, so a run still uploading, or two runs of one model merged, doesn't set it."""
    counts = defaultdict(list)
    for b in board:
        counts[b["os"], b["condition"]].append(b["n_trials"])
    return {key: usual(ns) for key, ns in counts.items()}


def usual(values):
    """The most common of ``values``, the larger on a tie; 0 for none."""
    return max(values, key=lambda v: (values.count(v), v)) if values else 0


def lab_of(model):
    return next((lab for prefix, lab in LABS.items() if model.startswith(prefix)), ("Other", 2))


def strips(spec, theme, phone):
    """The opening figure: a row per OS and driver, a track per condition from none to every trial, each model's full
    pass a dot on it in its lab's colour, tied models one dot (split between labs when both tied) with their count, and
    the row's lowest to highest printed beside them. Side by side on a desktop, one condition under the other on a
    phone."""
    s = PHONE if phone else DESKTOP
    t, colors = THEMES[theme], SERIES[theme]
    rows, conds, full = spec["panels"], spec["conds"], spec["full"]
    margin = 16 if phone else 28
    r = 5.5 if phone else 6.5
    W = 360 if phone else 900
    legend_h = s["sub"] + 14
    head_h = s["cond"] + s["sub"] + 18
    axis_h = s["tick"] + 12
    if phone:
        rh = s["sub"] + 6 + s["sub"] + 2 * r + 12
        block = head_h + len(rows) * rh + axis_h
        body = legend_h + len(conds) * block + (len(conds) - 1) * 22
    else:
        rh = 2 * r + 30
        gaps = sum(1 for a, b in zip(rows, rows[1:]) if a["os"] != b["os"])
        body = legend_h + head_h + len(rows) * rh + gaps * 10 + axis_h
    svg, y0 = frame(spec, W, body, theme, phone)
    lx = margin
    for name, slot in (("Claude", 0), ("GPT", 1)):
        svg.add(f'<circle cx="{lx + r:.1f}" cy="{y0 + s["sub"] * 0.45:.1f}" r="{r}" fill="{colors[slot]}"/>')
        svg.text(lx + 2 * r + 6, y0 + s["sub"] * 0.8, name, s["sub"], 600, "ink2")
        lx += 2 * r + 6 + width(name, 600, s["sub"]) + 18
    split_dot(svg, lx + r, y0 + s["sub"] * 0.45, r, colors[0], colors[1], t["surface"], 0)
    svg.text(lx + 2 * r + 6, y0 + s["sub"] * 0.8, "Claude and GPT tied", s["sub"], 600, "ink2")
    y0 += legend_h
    label_w = 0 if phone else max(width(f"{row['os']} · ", 700, s["name"]) + width(row["driver"], 400, s["name"])
                                  for row in rows) + 24
    gap = 36
    pw = W - 2 * margin if phone else (W - 2 * margin - label_w - gap * (len(conds) - 1)) / len(conds)
    pad = r + 4
    range_w = width("00–00", 600, s["tick"]) + 12
    for k, c in enumerate(conds):
        if phone:
            x0, top = margin, y0 + k * (head_h + len(rows) * rh + axis_h + 22)
        else:
            x0, top = margin + label_w + k * (pw + gap), y0
        track_l, track_r = x0 + pad, x0 + pw - range_w
        X = lambda share: track_l + share * (track_r - track_l)
        gloss = "the desktop to itself" if c["id"] == "foreground" else "the user typing in their own window"
        svg.text(x0, top + s["cond"] * 0.8, c["name"], s["cond"], 700)
        svg.text(x0, top + s["cond"] + 6 + s["sub"] * 0.8, f"{gloss} · {full[c['id']]} trials a dot", s["sub"], 400,
                 "ink3")
        ry = top + head_h
        centres = []
        for i, row in enumerate(rows):
            if not phone and i and row["os"] != rows[i - 1]["os"]:
                ry += 10
            if phone:
                svg.text(x0, ry + s["sub"] * 0.8, row["os"] + " · ", s["sub"], 700, "ink")
                svg.text(x0 + width(row["os"] + " · ", 700, s["sub"]), ry + s["sub"] * 0.8, row["driver"], s["sub"],
                         400, "ink2")
                cy = ry + s["sub"] + 6 + s["sub"] + r + 2
            else:
                cy = ry + rh / 2
                if k == 0:
                    os_w = width(f"{row['os']} · ", 700, s["name"])
                    svg.text(margin, cy + s["name"] * 0.36, f"{row['os']} · ", s["name"], 700)
                    svg.text(margin + os_w, cy + s["name"] * 0.36, row["driver"], s["name"], 400, "ink2")
            centres.append((cy, row))
            ry += rh
        bottom = ry
        for g in (0, 0.25, 0.5, 0.75, 1.0):
            gx = X(g)
            svg.add(f'<line x1="{gx:.1f}" x2="{gx:.1f}" y1="{top + head_h - 6:.1f}" y2="{bottom:.1f}" '
                    f'stroke="{t["axis"] if g == 0 else t["grid"]}" stroke-width="1"/>')
            svg.text(gx, bottom + s["tick"] + 4, pct(g), s["tick"], 400, "ink3", "middle", num=True)
        for cy, row in centres:
            cell = row["cells"].get(c["id"]) or []
            if not cell:
                svg.text(track_l + 4, cy + s["tick"] * 0.36, "not run", s["tick"], 400, "ink3")
                continue
            n = cell[0]["n"]
            lo, hi = min(p["passed"] for p in cell), max(p["passed"] for p in cell)
            if hi > lo:
                svg.add(f'<line x1="{X(lo / n):.1f}" x2="{X(hi / n):.1f}" y1="{cy:.1f}" y2="{cy:.1f}" '
                        f'stroke="{t["ink3"]}" stroke-opacity=".4" stroke-width="{3 if phone else 4}" '
                        f'stroke-linecap="round"/>')
            groups = defaultdict(list)
            for p in cell:
                groups[p["passed"]].append(p)
            last = {"above": -1e9, "below": -1e9}
            count_w = width("8", 700, s["sub"] - 1.5) + 6
            for passed, ps in sorted(groups.items()):
                cx = X(passed / n)
                slots = sorted({p["lab"][1] for p in ps})
                tip = escape(f"{row['label']}, {c['name'].lower()}: " + ", ".join(p["name"] for p in ps)
                             + f" passed {passed} of {n}")
                svg.add(f"<g><title>{tip}</title>")
                if len(slots) == 1:
                    svg.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{colors[slots[0]]}" '
                            f'stroke="{t["surface"]}" stroke-width="1.5"/>')
                else:
                    split_dot(svg, cx, cy, r, colors[slots[0]], colors[slots[1]], t["surface"], 1.5)
                svg.add("</g>")
                if len(ps) > 1:
                    where = next((w for w in ("above", "below") if cx - last[w] >= count_w), None)
                    if where:
                        ty = cy - r - 4 if where == "above" else cy + r + (s["sub"] - 1.5) * 0.8 + 3
                        svg.text(cx, ty, str(len(ps)), s["sub"] - 1.5, 700, "ink2", "middle", num=True)
                        last[where] = cx
            said = f"{lo}" if lo == hi else f"{lo}–{hi}"
            svg.text(track_r + 12, cy + s["tick"] * 0.36, said, s["tick"], 600, "ink2", num=True)
    return svg.render(spec["title"], spec["desc"])


def split_dot(svg, cx, cy, r, left, right, ring, ring_w):
    """A dot half ``left`` and half ``right``, for labs tied on one value."""
    svg.add(f'<path d="M{cx:.1f},{cy - r:.1f}A{r},{r} 0 0 0 {cx:.1f},{cy + r:.1f}Z" fill="{left}"/>'
            f'<path d="M{cx:.1f},{cy - r:.1f}A{r},{r} 0 0 1 {cx:.1f},{cy + r:.1f}Z" fill="{right}"/>'
            + (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="none" stroke="{ring}" stroke-width="{ring_w:.1f}"/>'
               if ring_w else ""))


def widest(cat):
    """The OS on which the bench's first driver ran the most models in both conditions, the first of a tie, and those
    models."""
    both = ran_models(cat)
    os_ = max(cat["oses"], key=lambda o: len(both[o["id"]]))
    return os_, both[os_["id"]]


def ran_models(cat):
    """Each OS's models the bench's first driver ran in both conditions."""
    ran = defaultdict(set)
    for r in cat["board"]:
        if r["driver"] == cat["driver"]:
            ran[(r["os"], r["model"])].add(r["condition"])
    return {o["id"]: [m for m in cat["models"] if ran[(o["id"], m["id"])] >= set(catalog.CONDITIONS)] for o in cat["oses"]}


def os_gaps(cat):
    """Each model the bench's first driver ran on several OSes in both conditions, over the tasks every one of those OSes
    ran in each of the task's conditions: a drivers comparison with the driver held fixed and the OS changing."""
    rows = {(r["os"], r["model"], r["condition"]): r for r in cat["board"] if r["driver"] == cat["driver"]}
    out = []
    for m in cat["models"]:
        oses = [o["id"] for o in cat["oses"] if all((o["id"], m["id"], c) in rows for c in catalog.CONDITIONS)]
        tasks = [t["id"] for t in cat["tasks"]
                 if all(t["id"] in rows[(o, m["id"], c)]["tasks"] for o in oses for c in t["conditions"])]
        if len(oses) > 1 and tasks:
            out.append({"model": m["id"], "tasks": tasks, "oses": [
                {"id": o, **{c: catalog.summary(rows[(o, m["id"], c)], tasks) for c in catalog.CONDITIONS}} for o in oses]})
    return out


def tally(cat, os_, entries, cond=None):
    """Each of ``entries`` (driver, model, name, slot) on ``os_`` as the share of its trials that passed and their mean cost
    at list price, over the tasks and conditions (``cond`` alone if given) every entry has trials of, so that every point
    counts the same ones."""
    by = defaultdict(list)
    for t in cat["trials"]:
        if t["os"] == os_:
            by[(t["driver"], t["model"], t["task"], t["condition"])].append(t)
    cells = [(t["id"], c) for t in cat["tasks"] for c in t["conditions"]
             if c == (cond or c) and all(by[(d, m, t["id"], c)] for d, m, *_ in entries)]
    out = []
    for d, m, name, slot in entries:
        trials = [x for t, c in cells for x in by[(d, m, t, c)]]
        costs = [x["cost"] for x in trials if x["cost"] is not None]
        if costs:
            passed = sum(x["passed"] for x in trials)
            out.append({"name": name, "slot": slot, "n": len(trials), "passed": passed, "share": passed / len(trials),
                        "cost": sum(costs) / len(costs), "frontier": False})
    return out


def frontier(points):
    """The points no other matches, none passing as large a share at the same cost or less, cheapest first."""
    out = []
    for p in sorted(points, key=lambda p: (p["cost"], -p["share"])):
        if not out or p["share"] > out[-1]["share"]:
            out.append(p)
    return out


def heads(names):
    """Each name as its family and its variant: the words it shares with every other name of its first word, and the
    rest; a name alone under its first word keeps its last word as the variant, as GPT-6 / Luna."""
    kin_ = defaultdict(list)
    for n in names:
        kin_[n.split()[0]].append(set(n.split()))
    out = []
    for n in names:
        words = n.split()
        shared = set.intersection(*kin_[words[0]]) if len(kin_[words[0]]) > 1 else set(words[:-1])
        out.append((" ".join(w for w in words if w in shared), " ".join(w for w in words if w not in shared)))
    return out


def kin(names):
    """What ``names`` share at their start, as GPT-6 of GPT-6 Luna and GPT-6.1 Sol."""
    return commonprefix(names).rstrip(" .-")


def join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def of(passed, n):
    return f"all {n}" if passed == n else f"none of {n}" if not passed else f"{passed} of {n}"


def label_of(cat, driver):
    d = next((d for d in cat["drivers"] if d["id"] == driver), {"name": driver})
    return d.get("label") or d["name"]


#: The grid's fills, by the share of a cell's runs that passed: one hue, light to dark on a light page and dark to light
#: on a dark one, so the near-empty end recedes into the page; a cell none passed keeps the quiet ``zero``.
RAMP = {"light": {"zero": "#f0f1f3", "steps": ["#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"]},
        "dark": {"zero": "#161b27", "steps": ["#123f7a", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef"]}}


def frame(spec, W, body, theme, phone):
    """A figure ``W`` wide: the spec's title and subtitle over ``body`` px for its panels, and its foot under them; the
    Svg, and the y where the panels start."""
    s = PHONE if phone else DESKTOP
    margin = 16 if phone else 28
    titles = balanced(spec["title"], 800, s["title"], W - 2 * margin)
    lift = (len(titles) - 1) * (s["title"] + 4)
    head_lines = wrap(spec["subtitle"], 400, s["subtitle"], W - 2 * margin)
    head = margin + s["title"] + lift + 8 + len(head_lines) * (s["subtitle"] + 5)
    foot_lines = wrap(spec["foot"], 400, s["foot"], W - 2 * margin)
    H = head + 16 + body + 14 + len(foot_lines) * (s["foot"] + 5) + margin - 6
    svg = Svg(W, round(H), theme)
    for k, line in enumerate(titles):
        svg.text(margin, margin + s["title"] * 0.8 + k * (s["title"] + 4), line, s["title"], 800)
    for k, line in enumerate(head_lines):
        svg.text(margin, margin + s["title"] + lift + 10 + k * (s["subtitle"] + 5) + s["subtitle"] * 0.75, line,
                 s["subtitle"], 400, "ink2")
    fy = H - margin + 6 - (len(foot_lines) - 1) * (s["foot"] + 5) - 4
    for k, line in enumerate(foot_lines):
        svg.text(margin, fy + k * (s["foot"] + 5), line, s["foot"], 400, "ink3")
    return svg, head + 16


def rows(spec, theme, phone):
    """Line panels as the results figures draw them, two to a row on a desktop, so that a third panel keeps the room its
    labels need, and one to a row on a phone."""
    s = {**(PHONE if phone else DESKTOP), "delta": spec.get("delta", True), "side": spec.get("side", False)}
    panels = spec["panels"]
    across = 1 if phone else min(2, len(panels))
    margin = 16 if phone else 28
    W = 360 if phone else 60 + spec.get("panel_w", 360) * across
    ph = (250 if phone else 300) + label_h(s, True, any(p.get("note") for p in panels))
    lines = ceil(len(panels) / across)
    svg, y0 = frame(spec, W, lines * ph + (lines - 1) * 26, theme, phone)
    pw = (W - 2 * margin - (across - 1) * 36) / across
    for k, p in enumerate(panels):
        series = [{"name": sr["name"], "values": sr["values"], "color": SERIES[theme][sr["slot"] % len(SERIES[theme])]}
                  for sr in p["series"]]
        panel(svg, margin + k % across * (pw + 36), y0 + k // across * (ph + 26), pw, ph, series, spec["conds"], theme,
              s, p["label"], p.get("note"))
    return svg.render(spec["title"], spec["desc"])


#: The grid's fills, by the share of a cell's runs that passed: one hue, light to dark on a light page and dark to light
#: on a dark one, so the near-empty end recedes into the page; a cell none passed keeps the quiet ``zero``.
RAMP = {"light": {"zero": "#f0f1f3", "steps": ["#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"]},
        "dark": {"zero": "#161b27", "steps": ["#123f7a", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef"]}}


def task_grid(spec, theme, phone):
    """The passes grid: a block per condition, side by side or on a phone one above the other, of a row per task under its
    family and a column per model under its family's name, each cell its passing runs on a fill as strong as their share;
    a row the bench can't pass in a condition bears its mark, explained under the blocks."""
    s = PHONE if phone else DESKTOP
    margin = 16 if phone else 28
    cols, groups, blocks = spec["cols"], spec["groups"], spec["panels"]
    rows_ = [r for _, rs in groups for r in rs]
    probe, gloss = (12.5, 10.5) if phone else (13, 12)
    if phone:
        labw = max(max(width(r["probe"] + " ‡", 600, probe), width(r["label"], 400, gloss)) for r in rows_) + 8
    else:
        labw = max(width(r["probe"], 600, probe) + 6 + width(r["label"], 400, gloss) for r in rows_) + 18
    markw = 0 if phone or not any(b["marks"] for b in blocks) else 14
    split = 6 if phone else 9
    splits = sum(a["harness"] != b["harness"] for a, b in zip(cols, cols[1:]))
    cw = (360 - 2 * margin - labw - splits * split) / len(cols) if phone else 46
    xs, x = [], 0.0
    for k, c in enumerate(cols):
        x += split if k and c["harness"] != cols[k - 1]["harness"] else 0
        xs.append(x)
        x += cw
    bw, gap = x, 22
    W = 360 if phone else round(2 * margin + labw + len(blocks) * (bw + markw) + (len(blocks) - 1) * gap)
    rh, glabel, top_h = (32, 24, 66) if phone else (30, 26, 64)
    marks = {cv["mark"]: cv["short"] for b in blocks for cv in b["marks"].values()}
    legend = (24 + (s["sub"] + 8) * (phone and len(marks) > 1)) if marks else 0
    body = top_h + sum(glabel + len(rs) * rh for _, rs in groups)
    svg, y0 = frame(spec, W, (len(blocks) * body + (len(blocks) - 1) * 22 if phone else body) + legend, theme, phone)
    names = [width(c["variant"], 600, 1) for c in cols]
    fit = min([(xs[k + 1] - xs[k] - 4) / ((names[k] + names[k + 1]) / 2) for k in range(len(cols) - 1)] or [12])
    for k, b in enumerate(blocks):
        by = y0 + (k * (body + 22) if phone else 0)
        bx = margin + labw + (0 if phone else k * (bw + markw + gap))
        if phone or k == 0:
            row_labels(svg, groups, b["marks"] if phone else {}, margin, by + top_h, rh, glabel, probe, gloss, phone)
        block(svg, b, cols, xs, cw, bw, margin if phone else bx, bx, by, top_h, rh, glabel, groups, spec["full"],
              theme, s, min(11.5 if phone else 12, fit), not phone)
    marks = {cv["mark"]: cv["short"] for b in blocks for cv in b["marks"].values()}
    if marks:
        x0 = margin + labw + (0 if phone else (len(blocks) - 1) * (bw + markw + gap))
        lx, ly = x0, y0 + (len(blocks) * body + (len(blocks) - 1) * 22 if phone else body) + 16
        for mark, short in marks.items():
            if lx > x0 and lx + 12 + width(short, 400, s["sub"]) > W - margin:
                lx, ly = x0, ly + s["sub"] + 8
            svg.text(lx, ly, mark, 13, 600, "ink2")
            svg.text(lx + 12, ly, short, s["sub"], 400, "ink3")
            lx += 12 + width(short, 400, s["sub"]) + 16
    return svg.render(spec["title"], spec["desc"])


def row_labels(svg, groups, marks, x, y, rh, glabel, probe, gloss, phone):
    """Each family's name over its tasks, and each task's probe and short name, on one line or on a phone on two, the
    probe followed by its mark when the block below has one for it."""
    for name, rs in groups:
        svg.text(x, y + glabel - 9, name, 11.5 if phone else 12, 600, "ink2")
        y += glabel
        for r in rs:
            mid = y + rh / 2
            head = r["probe"] + (f" {marks[r['id']]['mark']}" if r["id"] in marks else "")
            if phone:
                svg.text(x, mid - 2, head, probe, 600)
                svg.text(x, mid + gloss, r["label"], gloss, 400, "ink3")
            else:
                svg.text(x, mid + probe * 0.36, head, probe, 600)
                svg.text(x + width(head, 600, probe) + 6, mid + gloss * 0.36, r["label"], gloss, 400, "ink3")
            y += rh


def block(svg, b, cols, xs, cw, bw, tx, bx, y0, top_h, rh, glabel, groups, full, theme, s, head_size, marked):
    """One condition's block: its name from ``tx``, the models' family and variant names over their columns, and a cell
    per task and model; a row the bench doesn't run in the condition says where it runs, and with ``marked`` a row the
    bench can't pass bears its mark at the block's end."""
    t = svg.t
    svg.text(tx, y0 + s["cond"] * 0.8, b["label"], s["cond"], 700)
    svg.text(tx + width(b["label"], 700, s["cond"]) + 8, y0 + s["cond"] * 0.8, b["short"], s["sub"], 400, "ink3")
    fam_y, var_y = y0 + 38, y0 + 57
    k = 0
    while k < len(cols):
        j = k
        while j + 1 < len(cols) and (cols[j + 1]["family"], cols[j + 1]["harness"]) == (cols[k]["family"],
                                                                                         cols[k]["harness"]):
            j += 1
        left, right = bx + xs[k] + 2, bx + xs[j] + cw - 2
        svg.text((left + right) / 2, fam_y, cols[k]["family"], 11 if s is PHONE else 11.5, 600, "ink3", "middle")
        svg.add(f'<line x1="{left:.1f}" x2="{right:.1f}" y1="{fam_y + 6:.1f}" y2="{fam_y + 6:.1f}" stroke="{t["axis"]}" '
                f'stroke-width="1"/>')
        k = j + 1
    for c, x in zip(cols, xs):
        svg.text(bx + x + cw / 2, var_y, c["variant"], head_size, 600, "ink", "middle")
    y = y0 + top_h
    size = 12 if s is PHONE else 13
    for _, rs in groups:
        y += glabel
        for r in rs:
            cells = [b["cells"][(r["id"], c["id"])] for c in cols]
            if all(x == "off" for x in cells):
                svg.text(bx + bw / 2, y + rh / 2 + s["sub"] * 0.36, f"{join(r['conditions'])} only", s["sub"], 400,
                         "ink3", "middle")
            for x, cell in zip(xs, cells):
                if cell != "off":
                    square(svg, bx + x, y, cw, rh, cell, full, theme, size)
            if marked and r["id"] in b["marks"]:
                svg.text(bx + bw + 4, y + rh / 2 + 4.5, b["marks"][r["id"]]["mark"], 13, 600, "ink2")
            y += rh


def square(svg, x, y, w, h, cell, full, theme, size):
    """One cell: its passing runs on its fill, with how many ran when that's short of the rest; an outline alone when
    none has run yet."""
    box = f'x="{x + 1.5:.1f}" y="{y + 1.5:.1f}" width="{w - 3:.1f}" height="{h - 3:.1f}" rx="4"'
    if cell is None:
        svg.add(f'<rect {box} fill="none" stroke="{svg.t["axis"]}" stroke-width="1" stroke-dasharray="3 3"/>')
        return
    color, ink = shade(cell["passed"] / cell["n"], theme)
    svg.add(f'<rect {box} fill="{color}"/>')
    text = str(cell["passed"]) if cell["n"] == full else f"{cell['passed']}/{cell['n']}"
    small = size - (2 if cell["n"] != full else 0)
    svg.text(x + w / 2, y + h / 2 + small * 0.36, text, small, 700, ink, "middle", num=True)


def shade(share, theme):
    """The fill of a cell whose runs passed at ``share``, and the ink its number takes there."""
    ramp = RAMP[theme]
    if not share:
        return ramp["zero"], THEMES[theme]["ink3"]
    steps = ramp["steps"]
    pos = min(max(share * len(steps) - 1, 0), len(steps) - 1)
    k = int(pos)
    color = mix(steps[k], steps[min(k + 1, len(steps) - 1)], pos - k)
    return color, "#101114" if luminance(color) > 0.2 else "#ffffff"


def mix(a, b, k):
    return "#" + "".join(f"{round(int(a[i:i + 2], 16) * (1 - k) + int(b[i:i + 2], 16) * k):02x}" for i in (1, 3, 5))


def luminance(color):
    lin = [(c / 255) / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4
           for c in (int(color[i:i + 2], 16) for i in (1, 3, 5))]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def scatter(spec, theme, phone):
    """Points on a log axis of cost against the share of trials passed, a panel each with scales of its own, side by side
    or on a phone one above the other: the frontier as a staircase over the dominated region, a frontier point filled
    and the rest hollow, each named with its share and cost where it collides least."""
    s = PHONE if phone else DESKTOP
    panels = spec["panels"]
    n = len(panels)
    cols = 1 if phone else min(n, spec.get("cols") or n)
    rows = ceil(n / cols)
    margin = 16 if phone else 28
    W = 360 if phone else 60 + spec.get("panel_w", 380) * cols
    ph = (300 if phone else 330) + label_h(s, True, True)
    svg, y0 = frame(spec, W, rows * ph + (rows - 1) * 26, theme, phone)
    pw = (W - 2 * margin - (cols - 1) * 36) / cols
    for k, p in enumerate(panels):
        plane(svg, margin + (k % cols) * (pw + 36), y0 + (k // cols) * (ph + 26), pw, ph, p, theme, s, phone)
    return svg.render(spec["title"], spec["desc"])


def plane(svg, x0, y0, pw, ph, p, theme, s, phone):
    """One panel of the scatter: its name and note, its axes fitted to its points, the dominated region under the
    frontier, and the points with their labels."""
    t = svg.t
    svg.text(x0, y0 + s["os"] * 0.8, p["label"], s["os"], 700)
    svg.text(x0, y0 + s["os"] + 6 + s["sub"] * 0.8, p["note"], s["sub"], 400, "ink3")
    pts = p["points"]
    costs, shares = [q["cost"] for q in pts], [q["share"] for q in pts]
    xdom = (min(costs) / 1.6, max(costs) * 1.6)
    step = 0.05 if max(shares) - min(shares) < 0.2 else 0.1
    ydom = (max(0.0, floor((min(shares) - 0.04) / step) * step), min(1.0, ceil((max(shares) + 0.04) / step) * step))
    top = y0 + label_h(s, True, True) + 26
    left, right, bottom = x0 + (36 if phone else 40), x0 + pw - 4, y0 + ph - 40
    span = log10(xdom[1]) - log10(xdom[0])
    X = lambda c: left + (log10(c) - log10(xdom[0])) / span * (right - left)
    Y = lambda v: bottom - (v - ydom[0]) / (ydom[1] - ydom[0]) * (bottom - top)
    front = sorted((q for q in pts if q["frontier"]), key=lambda q: q["cost"])
    steps = f"M{X(front[0]['cost']):.1f},{bottom:.1f} V{Y(front[0]['share']):.1f}" + "".join(
        f" H{X(b['cost']):.1f} V{Y(b['share']):.1f}" for b in front[1:]) + f" H{right:.1f}"
    svg.add(f'<path d="{steps} V{bottom:.1f} Z" fill="{t["grid"]}" fill-opacity="{0.55 if theme == "light" else 0.6}"/>')
    ticks = []
    for v in [k * step for k in range(ceil(ydom[0] / step - 1e-9), floor(ydom[1] / step + 1e-9) + 1)]:
        ticks.append((left - 10 - width(pct(v), 400, s["tick"]), Y(v) - s["tick"] * 0.7, left - 6, Y(v) + s["tick"] * 0.5))
        svg.add(f'<line x1="{left:.1f}" x2="{right:.1f}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{t["grid"]}" '
                f'stroke-width="1"/>')
        svg.text(left - 8, Y(v) + s["tick"] * 0.36, pct(v), s["tick"], 400, "ink3", "end", num=True)
    for c in log_ticks(*xdom):
        svg.add(f'<line x1="{X(c):.1f}" x2="{X(c):.1f}" y1="{top:.1f}" y2="{bottom:.1f}" stroke="{t["grid"]}" '
                f'stroke-width="1"/>')
        svg.text(X(c), bottom + s["tick"] + 6, f"${c:g}", s["tick"], 400, "ink3", "middle", num=True)
    svg.text((left + right) / 2, bottom + s["tick"] + 24, "cost per trial, log scale", s["sub"], 400, "ink3", "middle")
    title = (x0, top - 12 - s["sub"], x0 + width("trials passed", 400, s["sub"]), top - 8)
    svg.text(x0, top - 12, "trials passed", s["sub"], 400, "ink3")
    svg.add(f'<path d="{steps}" fill="none" stroke="{t["ink2"]}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    dots = [title, *ticks]
    for q in pts:
        cx, cy, color = X(q["cost"]), Y(q["share"]), SERIES[theme][q["slot"] % len(SERIES[theme])]
        if q["frontier"]:
            svg.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{s["dot"]}" fill="{color}" stroke="{t["surface"]}" '
                    f'stroke-width="{s["ring"]}"/>')
        else:
            svg.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{s["dot"] - 1.5}" fill="{t["surface"]}" stroke="{color}" '
                    f'stroke-width="3"/>')
        dots.append((cx - s["dot"] - 3, cy - s["dot"] - 3, cx + s["dot"] + 3, cy + s["dot"] + 3))
    corners = [(X(front[0]["cost"]), bottom), *((X(q["cost"]), Y(q["share"])) for q in front),
               (right, Y(front[-1]["share"]))]
    turns = [corners[0]] + [c for a, b in zip(corners[1:], corners[2:]) for c in (a, (b[0], a[1]))] + [corners[-1]]
    lines = [(min(a[0], b[0]) - 2, min(a[1], b[1]) - 2, max(a[0], b[0]) + 2, max(a[1], b[1]) + 2)
             for a, b in zip(turns, turns[1:])]
    bounds = (x0 - 2, top - 14, x0 + pw + 2, bottom + 2)
    halo = f' stroke="{t["surface"]}" stroke-width="4" stroke-linejoin="round" paint-order="stroke"'
    val_size, near = s["sub"] + 1, s["dot"] + 5

    def lay(order, limit):
        """Each point's label where it costs least among those placed before it, and what they cost in all; None once
        they cost ``limit``."""
        placed, spent = [], 0.0
        for q in order:
            cx, cy = X(q["cost"]), Y(q["share"])
            vals = f"{pct(q['share'])} · ${q['cost']:.2f}"
            weight = 700 if q["frontier"] else 600
            lw = max(width(q["name"], weight, s["name"]), width(vals, 400, val_size))
            lh = s["name"] + 3 + val_size
            best = None
            for reach in (near, 2 * s["dot"] + 14):
                for anchor, bx, by in (("start", cx + reach, cy - lh / 2), ("end", cx - reach - lw, cy - lh / 2),
                                       ("start", cx + reach, cy - lh + 4), ("start", cx + reach, cy - 4),
                                       ("end", cx - reach - lw, cy - lh + 4), ("end", cx - reach - lw, cy - 4),
                                       ("middle", cx - lw / 2, cy - reach - lh), ("middle", cx - lw / 2, cy + reach),
                                       ("start", cx + reach * 0.6, cy - reach * 0.6 - lh),
                                       ("start", cx + reach * 0.6, cy + reach * 0.6),
                                       ("end", cx - reach * 0.6 - lw, cy - reach * 0.6 - lh),
                                       ("end", cx - reach * 0.6 - lw, cy + reach * 0.6)):
                    rect = (bx - 2, by - 1, bx + lw + 2, by + lh + 1)
                    cost = (sum(area(rect, o) * 30 for o in dots) + sum(area(rect, p["rect"]) * 12 for p in placed)
                            + sum(area(rect, o) * 2 for o in lines) + outside(rect, bounds) * 200 + (reach > near) * 40)
                    if best is None or cost < best[0]:
                        best = (cost, {"q": q, "anchor": anchor, "x": bx, "y": by, "w": lw, "rect": rect, "far": reach > near,
                                       "vals": vals, "weight": weight, "at": (cx, cy)})
            spent += best[0]
            if spent >= limit:
                return None
            placed.append(best[1])
        return spent, placed

    limit, placed = float("inf"), None
    for order in permutations(pts):
        if got := lay(order, limit):
            limit, placed = got
    for p_ in placed:
        q, (cx, cy), rect = p_["q"], p_["at"], p_["rect"]
        tx = {"start": p_["x"], "end": p_["x"] + p_["w"], "middle": p_["x"] + p_["w"] / 2}[p_["anchor"]]
        if p_["far"]:
            svg.add(f'<path d="M{cx:.1f},{cy:.1f} L{min(max(cx, rect[0]), rect[2]):.1f},{min(max(cy, rect[1]), rect[3]):.1f}" '
                    f'stroke="{t["ink3"]}" stroke-width="1"/>')
        svg.text(tx, p_["y"] + s["name"] * 0.8, q["name"], s["name"], p_["weight"], "ink" if q["frontier"] else "ink2",
                 p_["anchor"], halo)
        svg.text(tx, p_["y"] + s["name"] + 3 + val_size * 0.8, p_["vals"], val_size, 400,
                 "ink2" if q["frontier"] else "ink3", p_["anchor"], halo, num=True)

def log_ticks(lo, hi):
    """Round costs between ``lo`` and ``hi`` for a log axis: 1, 2, 3 and 5 of each power of ten, or over a wide span 1
    and 3."""
    steps = (1, 3) if hi / lo > 30 else (1, 2, 3, 5)
    return [round(m * 10 ** e, 6) for e in range(floor(log10(lo)), ceil(log10(hi)) + 1) for m in steps
            if lo <= m * 10 ** e <= hi]


def area(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def outside(a, bounds):
    return max(0, bounds[0] - a[0]) + max(0, a[2] - bounds[2]) + max(0, bounds[1] - a[1]) + max(0, a[3] - bounds[3])

def write_all(cat, out_dirs):
    """Each figure with a panel, in light and dark, desktop and phone, into every one of ``out_dirs``: the keys written,
    as the catalog's results, drivers, comparison and failure figures, and the comparison figures' notes."""
    written = {"figures": [], "driver_figures": [], "compare_figures": [], "failure_figures": [], "story_figures": [],
               "compare_notes": {}}
    for group, all_specs in (("figures", specs(cat)), ("driver_figures", driver_specs(cat)),
                             ("compare_figures", compare_specs(cat)), ("failure_figures", failure_specs(cat)),
                             ("story_figures", story_specs(cat))):
        for key, spec in all_specs.items():
            if not spec["panels"]:
                continue
            for suffix, theme, phone in (("", "light", False), ("-dark", "dark", False), ("-phone", "light", True),
                                         ("-phone-dark", "dark", True)):
                body = spec.get("draw", figure)(spec, theme, phone)
                for d in out_dirs:
                    Path(d).mkdir(parents=True, exist_ok=True)
                    (Path(d) / f"{key}{suffix}.svg").write_text(body)
            written[group].append(key)
            if "notes" in spec:
                written["compare_notes"][key] = spec["notes"]
    return written


def failure_specs(cat):
    """The failure figures, of the board's trials: how each OS, driver and model's trials ended in each condition, and
    which of trycua's A22 criteria its background trials broke."""
    counts = failures.tally(cat)
    names = {k: {x["id"]: x.get("label") or x["name"] for x in cat[k]} for k in ("oses", "drivers", "models")}
    conds = [c for c in cat["conditions"] if c["id"] in ("foreground", "background")]
    modes = [m for m in failures.MODES if any(c[m["id"]] for c in counts.values())]
    groups = []
    for os_, driver, model in failures.setups(cat):
        if not groups or groups[-1]["key"] != (os_, driver):
            groups.append({"key": (os_, driver), "label": f"{names['oses'][os_]} · {names['drivers'][driver]}",
                           "rows": []})
        groups[-1]["rows"].append({"model": model, "label": names["models"][model], "bars": {
            c["id"]: [(m["id"], counts[(os_, driver, model, c["id"])][m["id"]]) for m in modes] for c in conds}})
    total = sum(sum(c.values()) for c in counts.values())
    return {
        "failure-modes": {
            "draw": bars, "title": "How the trials ended",
            "subtitle": "Each trial once, under the gravest way it failed (furthest right in the key), a bar per OS, "
                        "driver and model in each condition. The numbers count trials.",
            "modes": modes, "conds": conds, "panels": groups,
            "foot": f"{total} trials of the board. {unpassable(cat)} Tasks by trycua's Cua Driver Bench, run on "
                    "AgentEnv; not trycua's official results.",
            "desc": "; ".join(f"{g['label']}, {r['label']}, {c['name'].lower()}: " + ", ".join(
                f"{n} {m}" for m, n in r["bars"][c["id"]] if n) for g in groups for r in g["rows"] for c in conds)},
        "disturbances": disturbance_spec(cat, groups),
    }


def disturbance_spec(cat, groups):
    """The heat grid of the A22 criteria: ``groups``' rows that ran in the background, each cell the share of the
    row's background trials that broke the column's criterion, the first column's any of them."""
    crit = [{"id": "any", "name": "Any"}] + [{"id": c["id"], "name": c["short"]} for c in cat["criteria"]]
    by_trial = cat["failures"]["by_trial"]
    panels = []
    for g in groups:
        rows = []
        for r in g["rows"]:
            u = [t["grade"]["user_undisturbed"] for t in cat["trials"] if t["uid"] in by_trial and (
                t["os"], t["driver"], t["model"], t["condition"]) == (*g["key"], r["model"], "background")]
            if u:
                rows.append({"label": r["label"], "cells": [
                    sum(not x["result"] for x in u) / len(u) if c["id"] == "any" else
                    sum(x["criteria"].get(c["id"]) is False for x in u) / len(u) for c in crit]})
        if rows:
            panels.append({"label": g["label"], "rows": rows})
    broke = [c for k, c in enumerate(cat["criteria"]) if any(r["cells"][k + 1] for p in panels for r in p["rows"])]
    return {
        "draw": heat_grid, "title": "How the user was disturbed",
        "subtitle": "The share of each setup's background trials, in %, that broke each of trycua's eight A22 criteria; "
                    "Any, that broke one or more. A blank cell: never.",
        "columns": crit, "panels": panels,
        "foot": "".join(f"{c['short']}: {c['broken']}. " for c in broke) + unpassable(cat),
        "desc": "; ".join(f"{p['label']}, {r['label']}: " + ", ".join(
            f"{c['name']} {pct(v)}" for c, v in zip(crit, r["cells"]) if v) for p in panels for r in p["rows"])}


def unpassable(cat):
    """The caveats of tasks no trial can pass, as "‡ Not passable on Linux: IR-01, IR-03 and IR-04." each."""
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    return " ".join(f"{cv['mark']} {cv['short']}: "
                    + " and ".join(catalog.ranges([short[t] for t in cv["tasks"]]).rsplit(", ", 1)) + "."
                    for cv in cat["caveats"] if cv.get("passable") is False)


def tone(theme, slot, strength):
    """A SERIES colour at ``strength`` over the theme's surface, as hex."""
    over, under = SERIES[theme][slot], THEMES[theme]["surface"]
    rgb = [round(strength * int(over[k:k + 2], 16) + (1 - strength) * int(under[k:k + 2], 16)) for k in (1, 3, 5)]
    return "#" + "".join(f"{v:02x}" for v in rgb)


def ink_on(theme, slot, strength):
    """A label's colour inside SERIES ``slot`` at ``strength``: white, but near-black on a light tint and on the light
    theme's yellow, the one full hue white doesn't read on (APCA)."""
    return THEMES["light"]["ink"] if theme == "light" and (strength < 1 or slot == 3) else "#ffffff"


def tinted(theme, outcome):
    """An outcome's SERIES slot and strength in ``theme``."""
    m = next(m for m in failures.MODES if m["id"] == outcome)
    return m["slot"], m["tint"][theme == "dark"] if m.get("tint") else 1


def head(svg, spec, s, margin):
    """The title and subtitle; the y below them."""
    svg.text(margin, margin + s["title"] * 0.8, spec["title"], s["title"], 800)
    lines = wrap(spec["subtitle"], 400, s["subtitle"], svg.w - 2 * margin)
    for k, line in enumerate(lines):
        svg.text(margin, margin + s["title"] + 10 + k * (s["subtitle"] + 5) + s["subtitle"] * 0.75, line,
                 s["subtitle"], 400, "ink2")
    return margin + s["title"] + 8 + len(lines) * (s["subtitle"] + 5)


def foot(svg, spec, s, margin, y):
    """The foot's lines from ``y``; the figure's height."""
    lines = wrap(spec["foot"], 400, s["foot"], svg.w - 2 * margin)
    for k, line in enumerate(lines):
        svg.text(margin, y + s["foot"] + k * (s["foot"] + 5), line, s["foot"], 400, "ink3")
    return y + len(lines) * (s["foot"] + 5) + margin


BARS = {False: {"title": 24, "subtitle": 14, "key": 13, "group": 14, "label": 13.5, "cond": 14, "sub": 12, "count": 12,
                "foot": 12, "bar": 20, "pitch": 30, "gap": 3},
        True: {"title": 20, "subtitle": 12.5, "key": 12, "group": 13, "label": 12.5, "cond": 11, "sub": 11,
               "count": 11, "foot": 11, "bar": 17, "pitch": 22, "gap": 2.5}}


def bars(spec, theme, phone):
    """Stacked bars, one per row and condition, each trial counted once in its outcome's colour, passes first; a
    segment wide enough carries its count. On a phone each row's two bars stack under its name."""
    s = BARS[phone]
    W, margin = (360, 16) if phone else (780, 28)
    svg = Svg(W, 10, theme)
    y = head(svg, spec, s, margin) + (12 if phone else 16)
    y = key(svg, spec["modes"], theme, s, margin, y)
    n_w = width("50", 400, s["count"]) + 8
    if phone:
        cond_w = max(width(c["name"], 400, s["cond"]) for c in spec["conds"]) + 8
        x0, bw = margin + cond_w, W - 2 * margin - cond_w - n_w
    else:
        label_w = max(width(r["label"], 400, s["label"]) for g in spec["panels"] for r in g["rows"]) + 18
        bw = (W - 2 * margin - label_w - 2 * n_w - 22) / 2
        xs = [margin + label_w, margin + label_w + bw + n_w + 22]
        y += 6
        for x, c in zip(xs, spec["conds"]):
            svg.text(x, y + s["cond"] * 0.8, c["name"], s["cond"], 600)
            svg.text(x + width(c["name"], 600, s["cond"]) + 8, y + s["cond"] * 0.8, c["short"], s["sub"], 400, "ink3")
        y += s["cond"] + 10
    for g in spec["panels"]:
        y += 12
        svg.text(margin, y + s["group"] * 0.8, g["label"], s["group"], 700)
        y += s["group"] + 8
        for r in g["rows"]:
            if phone:
                svg.text(margin, y + s["label"] * 0.8, r["label"], s["label"], 600)
                y += s["label"] + 6
                for c in spec["conds"]:
                    svg.text(margin, y + s["bar"] / 2 + s["cond"] * 0.36, c["name"], s["cond"], 400, "ink3")
                    bar(svg, r["bars"][c["id"]], x0, y, bw, theme, s)
                    y += s["pitch"]
                y += 6
            else:
                svg.text(margin, y + s["bar"] / 2 + s["label"] * 0.36, r["label"], s["label"], 400)
                for x, c in zip(xs, spec["conds"]):
                    bar(svg, r["bars"][c["id"]], x, y, bw, theme, s)
                y += s["pitch"]
    svg.h = round(foot(svg, spec, s, margin, y + 10))
    return svg.render(spec["title"], spec["desc"])


def key(svg, modes, theme, s, margin, y):
    """The outcomes' swatches and names in stacking order, wrapped to the width; the y below them."""
    x, sw = margin, s["key"] * 0.9
    for m in modes:
        w = sw + 6 + width(m["name"], 400, s["key"])
        if x + w > svg.w - margin:
            x, y = margin, y + s["key"] + 9
        svg.add(f'<rect x="{x:.1f}" y="{y + s["key"] * 0.5 - sw / 2:.1f}" width="{sw:.1f}" height="{sw:.1f}" rx="2.5" '
                f'fill="{tone(theme, *tinted(theme, m["id"]))}"/>')
        svg.text(x + sw + 6, y + s["key"] * 0.85, m["name"], s["key"], 400, "ink2")
        x += w + 16
    return y + s["key"] + 8


def bar(svg, parts, x, y, w, theme, s):
    """One stacked bar of (outcome, count) parts across ``w``, its ends rounded and a gap between parts, then its
    trials' number; a part wide enough carries its count."""
    total = sum(n for _, n in parts)
    shown = [(m, n) for m, n in parts if n]
    names = {m["id"]: m["name"] for m in failures.MODES}
    gaps = s["gap"] * (len(shown) - 1)
    at = x
    for k, (m, n) in enumerate(shown):
        pw = max((w - gaps) * n / total, 1.0)
        slot, strength = tinted(theme, m)
        svg.add(f'<path d="{rounded(at, y, pw, s["bar"], k == 0, k == len(shown) - 1)}" '
                f'fill="{tone(theme, slot, strength)}"><title>{escape(names[m])}: {n}</title></path>')
        if pw >= width(str(n), 600, s["count"]) + 8:
            svg.text(at + pw / 2, y + s["bar"] / 2 + s["count"] * 0.36, str(n), s["count"], 600,
                     ink_on(theme, slot, strength), "middle", num=True)
        at += pw + s["gap"]
    svg.text(x + w + 6, y + s["bar"] / 2 + s["count"] * 0.36, str(total), s["count"], 400, "ink3", num=True)


def rounded(x, y, w, h, left, right, r=4):
    """A rectangle's path with its left and right corners rounded as asked."""
    a, b = min(r, w / 2) if left else 0, min(r, w / 2) if right else 0
    return (f"M{x + a:.2f},{y:.2f}H{x + w - b:.2f}" + (f"A{b:.2f},{b:.2f} 0 0 1 {x + w:.2f},{y + b:.2f}" if b else "")
            + f"V{y + h - b:.2f}" + (f"A{b:.2f},{b:.2f} 0 0 1 {x + w - b:.2f},{y + h:.2f}" if b else "")
            + f"H{x + a:.2f}" + (f"A{a:.2f},{a:.2f} 0 0 1 {x:.2f},{y + h - a:.2f}" if a else "")
            + f"V{y + a:.2f}" + (f"A{a:.2f},{a:.2f} 0 0 1 {x + a:.2f},{y:.2f}" if a else "") + "Z")


GRID = {False: {"title": 24, "subtitle": 14, "group": 14, "label": 13.5, "head": 12, "cell": 12.5, "foot": 12,
                "h": 24, "gap": 3},
        True: {"title": 20, "subtitle": 12.5, "group": 13, "label": 12, "head": 10.5, "cell": 11, "foot": 11,
               "h": 21, "gap": 2.5}}


def heat_grid(spec, theme, phone):
    """A heat grid, a row per setup and a column per criterion, each cell's share as the strength of the user's amber
    and as its number; the first column, Any, set apart."""
    s = GRID[phone]
    W, margin = (360, 16) if phone else (780, 28)
    svg = Svg(W, 10, theme)
    y = head(svg, spec, s, margin) + (14 if phone else 18)
    labels = [r["label"] for g in spec["panels"] for r in g["rows"]]
    label_w = max(width(x, 400, s["label"]) for x in labels) + (10 if phone else 18)
    cols = spec["columns"]
    apart = 8 if phone else 12
    spill = max(0, width(cols[-1]["name"], 600, s["head"]) * 0.71 - 10) if phone else 0
    cw = (W - 2 * margin - label_w - apart - spill) / len(cols)
    xs = [margin + label_w + k * cw + (apart if k else 0) for k in range(len(cols))]
    if phone:
        rise = max(width(c["name"], 600, s["head"]) for c in cols) * 0.71 + s["head"]
        for x, c in zip(xs, cols):
            cx, cy = x + cw / 2 - s["head"] * 0.3, y + rise
            svg.text(cx, cy, c["name"], s["head"], 600, "ink2", "start", f' transform="rotate(-45 {cx:.1f} {cy:.1f})"')
        y += rise + 8
    else:
        heads = [balanced(c["name"], 600, s["head"], cw - 2) for c in cols]
        tall = max(len(h) for h in heads)
        for x, lines in zip(xs, heads):
            for k, line in enumerate(lines):
                svg.text(x + cw / 2, y + (tall - len(lines) + k) * (s["head"] + 3) + s["head"] * 0.8, line,
                         s["head"], 600, "ink2", "middle")
        y += tall * (s["head"] + 3) + 6
    for g in spec["panels"]:
        y += 10
        svg.text(margin, y + s["group"] * 0.8, g["label"], s["group"], 700)
        y += s["group"] + 6
        for r in g["rows"]:
            svg.text(margin, y + s["h"] / 2 + s["label"] * 0.36, r["label"], s["label"], 400)
            for x, v in zip(xs, r["cells"]):
                fill = tone(theme, 3, 0.14 + 0.86 * v) if v else THEMES[theme]["grid"]
                svg.add(f'<rect x="{x + s["gap"] / 2:.1f}" y="{y:.1f}" width="{cw - s["gap"]:.1f}" height="{s["h"]}" '
                        f'rx="3" fill="{fill}" fill-opacity="{1 if v else 0.45}"/>')
                if v:
                    svg.text(x + cw / 2, y + s["h"] / 2 + s["cell"] * 0.36, str(round(100 * v)), s["cell"],
                             700 if x == xs[0] else 600, ink_on(theme, 3, 0.14 + 0.86 * v), "middle", num=True)
            y += s["h"] + s["gap"]
    svg.h = round(foot(svg, spec, s, margin, y + 10))
    return svg.render(spec["title"], spec["desc"])
