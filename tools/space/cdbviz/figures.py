import base64
import io
import random
from functools import lru_cache
from html import escape
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


def write_all(cat, out_dirs):
    """Each figure with a panel, in light and dark, desktop and phone, into every one of ``out_dirs``: the keys written,
    as the catalog's results, drivers and failure figures."""
    written = {"figures": [], "driver_figures": [], "failure_figures": []}
    for group, all_specs in (("figures", specs(cat)), ("driver_figures", driver_specs(cat)),
                             ("failure_figures", failure_specs(cat))):
        for key, spec in all_specs.items():
            if not spec["panels"]:
                continue
            draw = {"bars": bars, "grid": grid}.get(spec.get("kind"), figure)
            for suffix, theme, phone in (("", "light", False), ("-dark", "dark", False), ("-phone", "light", True),
                                         ("-phone-dark", "dark", True)):
                body = draw(spec, theme, phone)
                for d in out_dirs:
                    Path(d).mkdir(parents=True, exist_ok=True)
                    (Path(d) / f"{key}{suffix}.svg").write_text(body)
            written[group].append(key)
    return written


#: Each outcome's colour, a SERIES slot and its strength in the light and the dark theme: a pass and the dialog over the
#: user are tints, so the failures the agent made stand out; the full hues, in failures.MODES' order, keep neighbours
#: apart for colour-blind readers.
OUTCOME = {"pass": (2, 0.3, 0.42), "wrong": (7, 1, 1), "out_of_turns": (0, 1, 1), "blocked": (1, 1, 1),
           "no_background": (6, 1, 1), "dialog": (3, 0.35, 0.45), "disturbed": (3, 1, 1), "left_gui": (4, 1, 1)}


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
            "kind": "bars", "title": "How the trials ended",
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
        "kind": "grid", "title": "How the user was disturbed",
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
    slot, light, dark = OUTCOME[outcome]
    return slot, light if theme == "light" else dark


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


def grid(spec, theme, phone):
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
