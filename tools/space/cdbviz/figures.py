import base64
import io
import random
import re
from functools import lru_cache
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import ImageFont

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

    def text(self, x, y, s, size, weight=400, fill="ink", anchor="start", extra=""):
        self.used.setdefault(weight, set()).update(s)
        color = self.t.get(fill, fill)
        self.items.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{color}" '
                          f'text-anchor="{anchor}"{extra}>{escape(s)}</text>')

    def add(self, s):
        self.items.append(s)

    def render(self, title, desc):
        faces = []
        for weight, chars in sorted(self.used.items()):
            faces.append(f"@font-face{{font-family:'CDB Inter';font-weight:{weight};"
                         f"src:url(data:font/woff2;base64,{woff2(weight, ''.join(sorted(chars)))}) format('woff2')}}")
        style = "".join(faces) + "text{font-family:'CDB Inter',Inter,system-ui,-apple-system,'Segoe UI',sans-serif;" \
                                 "font-variant-numeric:tabular-nums}"
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


def panel(svg, x0, y0, pw, ph, series, conds, theme, s, label=None):
    t = svg.t
    top = y0 + (s["os"] + 12 if label else 0)
    if label:
        svg.text(x0, y0 + s["os"] * 0.8, label, s["os"], 700)
    plot_top, plot_bot = top + s["pad_top"], y0 + ph - s["xlab"]
    name_w = max([width(sr["name"], 600, s["name"]) for sr in series] + [60])
    xs = [x0 + s["gut"] + i * (pw - s["gut"] - name_w - s["end_gap"] - s["gut2"]) / max(1, len(conds) - 1)
          for i in range(len(conds))]
    y = lambda v: plot_bot - v * (plot_bot - plot_top)
    grid_end = xs[-1] + s["dot"] + 3
    for g in (0, 0.5, 1.0):
        gy = y(g)
        svg.add(f'<line x1="{x0 + s["gut"] - 26:.1f}" x2="{grid_end:.1f}" y1="{gy:.1f}" y2="{gy:.1f}" '
                f'stroke="{t["axis"] if g == 0 else t["grid"]}" stroke-width="1"/>')
        svg.text(x0 + s["gut"] - 32, gy + s["tick"] * 0.36, pct(g), s["tick"], 400, "ink3", "end")
    for i, c in enumerate(conds):
        svg.text(xs[i], plot_bot + s["cond"] + 14, c["name"], s["cond"], 600, "ink", "middle")
        svg.text(xs[i], plot_bot + s["cond"] + 14 + s["sub"] + 6, c["short"], s["sub"], 400, "ink3", "middle")
    labels = {i: [] for i in range(len(conds))}
    ends = []
    for sr in series:
        for i, ci in enumerate(sr.get("ci") or []):
            if ci and sr["values"][i] is not None:
                lo, hi = y(ci[0]), y(ci[1])
                cap = s["dot"] + 3
                svg.add(f'<path d="M{xs[i]:.1f},{lo:.1f}V{hi:.1f}M{xs[i] - cap:.1f},{lo:.1f}H{xs[i] + cap:.1f}'
                        f'M{xs[i] - cap:.1f},{hi:.1f}H{xs[i] + cap:.1f}" stroke="{sr["color"]}" stroke-opacity=".38" '
                        f'stroke-width="2" fill="none" stroke-linecap="round"/>')
    for sr in series:
        pts = [(xs[i], y(v), v) for i, v in enumerate(sr["values"]) if v is not None]
        if len(pts) >= 2:
            d = " ".join(f"{'M' if k == 0 else 'L'}{px:.1f},{py:.1f}" for k, (px, py, _) in enumerate(pts))
            svg.add(f'<path d="{d}" fill="none" stroke="{sr["color"]}" stroke-width="{s["line"]}" '
                    f'stroke-linecap="round" stroke-linejoin="round"/>')
            if s.get("delta") and len(series) <= 3:
                (ax, ay, av), (bx, by, bv) = pts[0], pts[-1]
                dv = round(100 * (bv - av))
                if dv:
                    mx, my = (ax + bx) / 2, (ay + by) / 2
                    svg.text(mx + 10, my - 12 if dv < 0 else my + 22, f"{'−' if dv < 0 else '+'}{abs(dv)} pts",
                             s["sub"], 600, "ink3", "start")
        for i, v in enumerate(sr["values"]):
            if v is None:
                continue
            svg.add(f'<circle cx="{xs[i]:.1f}" cy="{y(v):.1f}" r="{s["dot"]}" fill="{sr["color"]}" '
                    f'stroke="{t["surface"]}" stroke-width="{s["ring"]}"/>')
            labels[i].append({"y": y(v) - s["dot"] - 11, "v": v, "x": xs[i]})
        last = max((i for i, v in enumerate(sr["values"]) if v is not None), default=None)
        if last is not None:
            ends.append({"y": y(sr["values"][last]) + s["name"] * 0.36, "dot": y(sr["values"][last]),
                         "x": xs[last], "name": sr["name"]})
    for i, items in labels.items():
        for it in spread(items, s["val"] + 4):
            svg.text(it["x"], max(it["y"], top + s["val"]), pct(it["v"]), s["val"], 700, "ink", "middle")
    for e in spread(ends, s["name"] + 6):
        lx = e["x"] + s["dot"] + s["end_gap"]
        if abs(e["y"] - s["name"] * 0.36 - e["dot"]) > 3:
            svg.add(f'<path d="M{e["x"] + s["dot"] + 3:.1f},{e["dot"]:.1f} L{lx - 4:.1f},{e["y"] - s["name"] * 0.36:.1f}" '
                    f'stroke="{t["ink3"]}" stroke-width="1" fill="none"/>')
        svg.text(lx, e["y"], e["name"], s["name"], 600, "ink", "start")


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


def figure(spec, theme, phone):
    s = PHONE if phone else DESKTOP
    panels = spec["panels"]
    n = len(panels)
    W = 360 if phone else (720 if n == 1 else 60 + 360 * n)
    margin = 16 if phone else 28
    head_lines = wrap(spec["subtitle"], 400, s["subtitle"], W - 2 * margin)
    head = margin + s["title"] + 8 + len(head_lines) * (s["subtitle"] + 5)
    ph = 250 if phone else 300
    foot_lines = wrap(spec["foot"], 400, s["foot"], W - 2 * margin)
    if phone:
        H = head + 14 + n * (ph + (s["os"] + 12 if n > 1 else 0)) + (n - 1) * 18 + 16 + len(foot_lines) * (s["foot"] + 5) + margin - 6
    else:
        H = head + 18 + ph + (s["os"] + 12 if n > 1 else 0) + 18 + len(foot_lines) * (s["foot"] + 5) + margin - 6
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
        label = p["label"] if n > 1 else None
        hh = ph + (s["os"] + 12 if label else 0)
        if phone:
            panel(svg, margin, y0, W - 2 * margin, hh, series, spec["conds"], theme, s, label)
            y0 += hh + 18
        else:
            pw = (W - 2 * margin - (n - 1) * 36) / n
            panel(svg, margin + k * (pw + 36), y0, pw, hh, series, spec["conds"], theme, s, label)
    fy = H - margin + 6 - (len(foot_lines) - 1) * (s["foot"] + 5) - 4
    for k, line in enumerate(foot_lines):
        svg.text(margin, fy + k * (s["foot"] + 5), line, s["foot"], 400, "ink3")
    return svg.render(spec["title"], spec["desc"])


def ranges(probes):
    items = []
    for raw in probes:
        m = re.match(r"^([A-Z]+)-?(\d+)$", raw)
        items.append((m[1], int(m[2]), raw) if m else (raw, None, raw))
    out, run = [], []
    for it in items:
        if run and it[1] is not None and run[-1][0] == it[0] and run[-1][1] is not None and it[1] == run[-1][1] + 1:
            run.append(it)
            continue
        if run:
            out.append(run)
        run = [it]
    if run:
        out.append(run)
    return ", ".join(r[0][2] if len(r) < 3 else f"{r[0][2]}–{r[-1][2]}" for r in out)


def boot_ci(values, n=2000, seed=7):
    rng = random.Random(seed)
    k = len(values)
    means = sorted(sum(values[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def specs(cat):
    conds = [c for c in cat["conditions"] if c["id"] in ("foreground", "background")]
    cids = [c["id"] for c in conds]
    models = {m["id"]: m for m in cat["models"] if m["board"]}
    short = {t["id"]: (t.get("probe") or t["id"]).replace("CDB-", "") for t in cat["tasks"]}
    order = [t["id"] for t in cat["tasks"]]
    runs = sorted({p["n"] for r in cat["board"] for p in r["tasks"].values()} or {1})
    out = {}
    for key, metric, title in (("task-score", "score", "Task score"), ("full-pass", "pass", "Full pass")):
        panels, used, ci_any = [], set(), False
        for o in cat["oses"]:
            series = []
            for mid, m in models.items():
                rows = {r["condition"]: r for r in cat["board"] if r["os"] == o["id"] and r["model"] == mid}
                if not rows:
                    continue
                sets = [set(rows[c]["tasks"]) for c in cids if c in rows]
                common = set.intersection(*sets) if len(sets) == len(cids) and sets else set()
                vals, cis = [], []
                for c in cids:
                    if c not in rows:
                        vals.append(None)
                        cis.append(None)
                        continue
                    ts = [t for t in order if t in (common or rows[c]["tasks"])]
                    used |= set(ts)
                    xs = [rows[c]["tasks"][t][metric] for t in ts if rows[c]["tasks"][t][metric] is not None]
                    vals.append(sum(xs) / len(xs) if xs else None)
                    cis.append(boot_ci(xs) if len(xs) >= 3 else None)
                ci_any |= any(cis)
                series.append({"name": m["name"], "slot": m["slot"], "values": vals, "ci": cis})
            if series:
                panels.append({"label": o["name"], "series": series})
        span = ranges([short[t] for t in order if t in used])
        n_tasks = len(used)
        if key == "task-score":
            sub = (f"trycua's evaluator (weighted checks), mean over {span}. The drop is the bench's point: the same "
                   "tasks while a user keeps typing.")
        else:
            sub = (f"Share of trials of {span} where every half of the grade held: the task, GUI only, and in the "
                   "background the user undisturbed.")
        nrun = f"{runs[0]}" if len(runs) == 1 else f"{runs[0]}–{runs[-1]}"
        foot = (f"n = {nrun} run{'s' if runs[-1] != 1 else ''} per task and condition; each point averages {n_tasks} "
                f"task{'s' if n_tasks != 1 else ''} run in both conditions. "
                + ("Whiskers: 95% bootstrap interval over tasks. " if ci_any else "Too few tasks for an interval. ")
                + " · ".join(o["name"] + (f" ({o['detail'].split(' · ')[0]})" if o.get("detail") else "") for o in cat["oses"])
                + ". Tasks by trycua's Cua Driver Bench, run on AgentEnv; not trycua's official results.")
        desc = "; ".join(f"{p['label']} {sr['name']}: " + ", ".join(
            f"{c['name'].lower()} {pct(v) if v is not None else 'n/a'}" for c, v in zip(conds, sr["values"]))
            for p in panels for sr in p["series"])
        out[key] = {"title": title, "subtitle": sub, "panels": panels, "conds": conds, "foot": foot, "desc": desc}
    return out


def write_all(cat, out_dirs):
    names = []
    for key, spec in specs(cat).items():
        if not spec["panels"]:
            continue
        for suffix, theme, phone in (("", "light", False), ("-dark", "dark", False), ("-phone", "light", True),
                                     ("-phone-dark", "dark", True)):
            body = figure(spec, theme, phone)
            for d in out_dirs:
                Path(d).mkdir(parents=True, exist_ok=True)
                (Path(d) / f"{key}{suffix}.svg").write_text(body)
            names.append(f"{key}{suffix}.svg")
    return names
