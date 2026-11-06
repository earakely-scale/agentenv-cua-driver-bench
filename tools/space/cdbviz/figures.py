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

from . import catalog

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
    return f"{round(100 * v)}%"


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


def spread(items, gap):
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
        side_labels(svg, s, labels[0], ends, val_w, halo)
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
    for e in spread(ends, s["name"] + 6):
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


def side_labels(svg, s, firsts, ends, val_w, halo):
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
    for e in spread([{**e, "y": e["dot"] + size * 0.36} for e in ends], size + 5):
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
    tasks all its drivers ran in both conditions (the catalog's comparisons), each condition over those it scores, so a
    panel compares like with like."""
    conds = [c for c in cat["conditions"] if c["id"] in ("foreground", "background")]
    drivers = {d["id"]: d for d in cat["drivers"]}
    names = {m["id"]: m["name"] for m in cat["models"]}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    rows = {(r["os"], r["model"], r["driver"], r["condition"]): r for r in cat["board"]}
    runs = sorted({cell["n"] for c in cat["comparisons"] for d in c["drivers"] for k in conds
                   for t, cell in rows[(c["os"], c["model"], d["id"], k["id"])]["tasks"].items() if t in c["tasks"]}
                  or {1})
    out = {}
    for key, metric, title in (("drivers-task-score", "score", "Task score by driver"),
                               ("drivers-full-pass", "pass", "Full pass by driver")):
        panels, halves = [], []
        for c in cat["comparisons"]:
            per = {(d["id"], k["id"]): {t: cell[metric] for t, cell in rows[(c["os"], c["model"], d["id"], k["id"])][
                "tasks"].items() if t in c["tasks"]} for d in c["drivers"] for k in conds}
            base = cat["driver"] if any(d["id"] == cat["driver"] for d in c["drivers"]) else c["drivers"][0]["id"]
            for d in c["drivers"]:
                for k in conds:
                    mine, theirs = per[(d["id"], k["id"])], per[(base, k["id"])]
                    gaps = [mine[t] - theirs[t] for t in mine if t in theirs and None not in (mine[t], theirs[t])]
                    if d["id"] != base and len(gaps) >= 3:
                        lo, hi = boot_ci(gaps)
                        halves.append((hi - lo) / 2)
            panels.append({"label": f"{names[c['model']]} on {osn[c['os']]}",
                           "note": f"{len(c['tasks'])} task{'s' if len(c['tasks']) != 1 else ''} · "
                                   f"{catalog.ranges([short[t] for t in c['tasks']])}",
                           "series": [{"name": drivers[d["id"]].get("label") or drivers[d["id"]]["name"],
                                       "slot": drivers[d["id"]]["slot"],
                                       "values": [d[k["id"]][metric] for k in conds]} for d in c["drivers"]]})
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
    the share of trials passed against what a trial costs, with the frontier, and each model's full pass on each OS; each
    with the notes the card and the Space print under it."""
    return {"models-tasks": tasks_spec(cat), "pareto": pareto_spec(cat), "os-gap": gap_spec(cat)}


def tasks_spec(cat):
    """A block per condition of a row per task under its family and a column per model, on the OS where the bench's first
    driver ran the most models: each cell the task's row on the board, "off" where the bench doesn't run the task in that
    condition, None where it hasn't run yet."""
    os_, models = widest(cat)
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
    return {"title": "Passes by task and model", "subtitle": sub, "foot": foot, "desc": desc, "draw": grid,
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
               f"{named(rows[passing[0]])} and no other task: {of(a, b)} of its trials, against none of the other "
               f"{n - b}."]
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
    """The share of trials passed against a trial's mean cost at list price: a panel of the models the bench's first
    driver ran on the OS with the most of them, and one of the drivers of the widest comparison, each over the trials
    every point of it ran, with the frontier."""
    os_, models = widest(cat)
    names = {m["id"]: m["name"] for m in cat["models"]}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    sets = [(f"Models on {os_['name']}", f"through {label_of(cat, cat['driver'])}", os_["id"],
             [(cat["driver"], m["id"], m["name"], m["slot"]) for m in models])]
    if cat["comparisons"]:
        c = max(cat["comparisons"], key=lambda c: (len(c["drivers"]), len(c["tasks"])))
        slots = {d["id"]: d["slot"] for d in cat["drivers"]}
        sets.append((f"Drivers on {osn[c['os']]}", names[c["model"]], c["os"],
                     [(d["id"], c["model"], label_of(cat, d["id"]), slots[d["id"]]) for d in c["drivers"]]))
    panels = []
    for label, via, os_id, entries in sets:
        points = tally(cat, os_id, entries)
        if len(points) < 2:
            continue
        for p in frontier(points):
            p["frontier"] = True
        ns = sorted({p["n"] for p in points})
        panels.append({"label": label, "note": f"{via} · {ns[0]}{f'–{ns[-1]}' if len(ns) > 1 else ''} trials each",
                       "points": points, "os": osn[os_id], "via": via})
    sub = ("The share of trials passed against what a trial costs at list price, on a log scale. The line is the "
           "frontier: the most any point passes at that cost or less; a hollow point passes less than a cheaper one.")
    foot = ("Each panel counts the same trials for every point: those of the tasks and conditions all of them ran. Cost "
            "from the tokens each trial's trajectory reports, at Anthropic's and OpenAI's list prices. Tasks by trycua's "
            "Cua Driver Bench, run on AgentEnv; not trycua's official results.")
    desc = "; ".join(f"{p['label']}, {q['name']}: {pct(q['share'])} of {q['n']} trials passed at ${q['cost']:.2f} a "
                     f"trial{', on the frontier' if q['frontier'] else ''}" for p in panels for q in p["points"])
    return {"title": "Passes against cost", "subtitle": sub, "foot": foot, "desc": desc, "draw": scatter,
            "panels": panels, "notes": pareto_notes(panels)}


def pareto_notes(panels):
    """The frontier's sentences: the first panel's most passes and what more money buys past them, its frontier and what
    beats each point off it, and the other panels' points in order."""
    out = []
    said = lambda q: f"{q['name']} ({pct(q['share'])} at ${q['cost']:.2f})"
    for k, p in enumerate(panels):
        pts, front = p["points"], sorted((q for q in p["points"] if q["frontier"]), key=lambda q: q["cost"])
        if k == 0:
            top = max(pts, key=lambda q: (q["share"], -q["cost"]))
            out.append(f"On {p['os']}, {top['name']} passes the most trials, {pct(top['share'])} ({top['passed']} of "
                       f"{top['n']}), at ${top['cost']:.2f} a trial" + "".join(
                           f"; {q['name']} costs {q['cost'] / top['cost']:.1f}× as much and passes {pct(q['share'])}"
                           for q in pts if q["cost"] > top["cost"]) + ".")
            beaten = [f"{q['name']} than " + next(f["name"] for f in front if f["cost"] <= q["cost"]
                                                  and f["share"] >= q["share"])
                      for q in sorted(pts, key=lambda q: -q["cost"]) if not q["frontier"]]
            out.append(f"The frontier is {join([said(q) for q in front])}"
                       + (f". Every other model passes less than a cheaper one: {join(beaten)}." if beaten else "."))
        else:
            order = sorted(pts, key=lambda q: -q["share"])
            out.append(f"On {p['os']}, with {p['via']}, " + ", ".join(
                f"{q['name']} passes {pct(q['share'])} at ${q['cost']:.2f} a trial" if j == 0
                else f"{q['name']} {pct(q['share'])} at ${q['cost']:.2f}" for j, q in enumerate(order))
                + (": each costlier driver passes more." if all(q["frontier"] for q in pts) else "."))
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

def widest(cat):
    """The OS on which the bench's first driver ran the most models in both conditions, the first of a tie, and those
    models."""
    ran = defaultdict(set)
    for r in cat["board"]:
        if r["driver"] == cat["driver"]:
            ran[(r["os"], r["model"])].add(r["condition"])
    both = {o["id"]: [m for m in cat["models"] if ran[(o["id"], m["id"])] >= set(catalog.CONDITIONS)] for o in cat["oses"]}
    os_ = max(cat["oses"], key=lambda o: len(both[o["id"]]))
    return os_, both[os_["id"]]


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


def tally(cat, os_, entries):
    """Each of ``entries`` (driver, model, name, slot) on ``os_`` as the share of its trials that passed and their mean cost
    at list price, over the tasks and conditions every entry has trials of, so that every point counts the same ones."""
    by = defaultdict(list)
    for t in cat["trials"]:
        if t["os"] == os_:
            by[(t["driver"], t["model"], t["task"], t["condition"])].append(t)
    cells = [(t["id"], c) for t in cat["tasks"] for c in t["conditions"]
             if all(by[(d, m, t["id"], c)] for d, m, *_ in entries)]
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
    head_lines = wrap(spec["subtitle"], 400, s["subtitle"], W - 2 * margin)
    head = margin + s["title"] + 8 + len(head_lines) * (s["subtitle"] + 5)
    foot_lines = wrap(spec["foot"], 400, s["foot"], W - 2 * margin)
    H = head + 16 + body + 14 + len(foot_lines) * (s["foot"] + 5) + margin - 6
    svg = Svg(W, round(H), theme)
    svg.text(margin, margin + s["title"] * 0.8, spec["title"], s["title"], 800)
    for k, line in enumerate(head_lines):
        svg.text(margin, margin + s["title"] + 10 + k * (s["subtitle"] + 5) + s["subtitle"] * 0.75, line,
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


def grid(spec, theme, phone):
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
    margin = 16 if phone else 28
    W = 360 if phone else 60 + spec.get("panel_w", 380) * n
    ph = (300 if phone else 330) + label_h(s, True, True)
    svg, y0 = frame(spec, W, n * ph + (n - 1) * 26 if phone else ph, theme, phone)
    pw = W - 2 * margin if phone else (W - 2 * margin - (n - 1) * 36) / n
    for k, p in enumerate(panels):
        plane(svg, margin + (0 if phone else k * (pw + 36)), y0 + (k * (ph + 26) if phone else 0), pw, ph, p, theme, s,
              phone)
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
    as the catalog's results, drivers and comparison figures, and the comparison figures' notes."""
    written = {"figures": [], "driver_figures": [], "compare_figures": [], "compare_notes": {}}
    for group, all_specs in (("figures", specs(cat)), ("driver_figures", driver_specs(cat)),
                             ("compare_figures", compare_specs(cat))):
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
