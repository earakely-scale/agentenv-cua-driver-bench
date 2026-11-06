"""The bench's headline: one task's foreground and background trials side by side, a scene for each operating system
and computer-use driver, the same model in each, then each one's record over the whole bench in both conditions; a GIF
for the card's hero and an MP4 for the Space's landing."""
import tempfile
from pathlib import Path

from PIL import ImageDraw, ImageFilter

from . import pair
from .hero import C, font, nice_speed, pill
from .pair import EDGE, FOOT, H, HDR, W


def render(scenes, cat, cfg, out_dir, seconds=7):
    """``scenes``, each a (foreground, background) pair of loaded trials of one task, as hero.gif and reel.mp4."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gif, mp4 = out_dir / "hero.gif", out_dir / "reel.mp4"
    shown = [pair.panels(fg, bg, cat, cfg) for fg, bg in scenes]
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        save = pair.saver(Path(tmp))
        for i, (left, right) in enumerate(shown):
            speed = nice_speed(max(left.span, right.span), seconds)
            for k, img in enumerate(pair.play(left, right, speed, f"Setup {i + 1} of {len(shown)}")):
                if k == 0:
                    save(intro(img, shown) if i == 0 else title(img, left, i, len(shown)), 4.2 if i == 0 else 1.6)
                save(img)
            save(pair.graded(img, left, right), 2.6)
        save(record(img, shown, cat), 6)
        pair.encode(Path(tmp), gif, mp4, (cfg.get("reel") or {}).get("max_mb", 12) * 1e6)
    return gif, mp4


def setup(panel):
    """A panel's operating system and driver, as the Space names them."""
    m, cat = panel.m, panel.scene.cat
    osn = next((o["name"] for o in cat["oses"] if o["id"] == m["os"]), m["os"])
    drv = next((d.get("label") or d["name"] for d in cat["drivers"] if d["id"] == m["driver"]), m["driver"])
    return osn, drv


def veil(base):
    """``base`` blurred and darkened under a card, and the card's drawing context."""
    img = base.copy()
    img.paste(img.crop((0, HDR, W, H - FOOT)).filter(ImageFilter.GaussianBlur(3)), (0, HDR))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle((0, HDR, W, H - FOOT), fill=(5, 7, 12, 200))
    return img, d


def chip(d, x, y, text, col):
    f = font(800, 10.5)
    w = d.textlength(text, font=f) + 16
    pill(d, (x, y, x + w, y + 20), fill=col + (44,), r=10, outline=col + (150,))
    d.text((x + 8, y + 4), text, font=f, fill=col)
    return w


def intro(base, shown):
    """The reel's opening card: one task, the setups it runs on, and the two conditions."""
    img, d = veil(base)
    left = shown[0][0]
    cw, ch = 700, 268
    x0, y0 = (W - cw) / 2, HDR + (H - FOOT - HDR - ch) / 2
    pill(d, (x0, y0, x0 + cw, y0 + ch), fill=(17, 22, 34, 250), r=14, outline=C["line"])
    x, y = x0 + 26, y0 + 22
    task = left.scene.task
    count = {2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX"}.get(len(shown), str(len(shown)))
    d.text((x, y), f"ONE TASK, {count} SETUPS, TWO CONDITIONS", font=font(800, 11.5), fill=C["ink3"])
    y += 22
    head = f"{(task.get('probe') or left.m['task'])} · {task.get('title', '')}"
    d.text((x, y), head, font=font(700, 19), fill=C["ink"])
    y += 34
    for i, (lp, _) in enumerate(shown):
        osn, drv = setup(lp)
        d.text((x, y), f"{i + 1}", font=font(800, 13), fill=C["ink4"])
        d.text((x + 20, y), f"{osn} · {drv}", font=font(700, 14), fill=C["ink2"])
        y += 22
    y += 8
    model = left.m["model_name"]
    for col, cond, body in ((C["agent"], "FOREGROUND", f"{model} has the desktop to itself."),
                            (C["user"], "BACKGROUND", "A person keeps typing in their own window; the agent must not "
                                                      "disturb them.")):
        w = chip(d, x, y, cond, col)
        d.text((x + w + 12, y + 2), body, font=font(500, 14), fill=C["ink2"])
        y += 28
    return img


def title(base, left, i, n):
    """The card between scenes: which setup comes next."""
    img, d = veil(base)
    osn, drv = setup(left)
    f = font(800, 30)
    text = f"{osn} · {drv}"
    tw = d.textlength(text, font=f)
    cy = HDR + (H - FOOT - HDR) / 2
    d.text((W / 2 - d.textlength(f"SETUP {i + 1} OF {n}", font=font(800, 11.5)) / 2, cy - 44), f"SETUP {i + 1} OF {n}",
           font=font(800, 11.5), fill=C["ink3"])
    d.text((W / 2 - tw / 2, cy - 22), text, font=f, fill=C["ink"])
    sub = f"{left.m['model_name']}, the same task, foreground beside background"
    d.text((W / 2 - d.textlength(sub, font=font(500, 14)) / 2, cy + 22), sub, font=font(500, 14), fill=C["ink2"])
    return img


def record(base, shown, cat):
    """The closing card: each setup's passes over the whole bench in both conditions, the scenes' model's board rows."""
    img, d = veil(base)
    model = shown[0][0].m["model"]
    rows = {(r["os"], r["driver"], r["condition"]): r for r in cat["board"] if r["model"] == model}
    cw = 720
    ch = 118 + 46 * len(shown)
    x0, y0 = (W - cw) / 2, HDR + (H - FOOT - HDR - ch) / 2
    pill(d, (x0, y0, x0 + cw, y0 + ch), fill=(17, 22, 34, 250), r=14, outline=C["line"])
    x, y = x0 + 26, y0 + 22
    d.text((x, y), f"OVER THE WHOLE BENCH · {shown[0][0].m['model_name'].upper()}", font=font(800, 11.5),
           fill=C["ink3"])
    cols = {"foreground": x0 + 300, "background": x0 + 510}
    for cond, cx in cols.items():
        chip(d, cx, y + 24, cond.upper(), C["agent"] if cond == "foreground" else C["user"])
    y += 60
    bar = 150
    for lp, _ in shown:
        osn, drv = setup(lp)
        d.line((x, y - 6, x0 + cw - 26, y - 6), fill=C["line"], width=1)
        d.text((x, y + 6), f"{osn} · {drv}", font=font(700, 14.5), fill=C["ink"])
        for cond, cx in cols.items():
            r = rows.get((lp.m["os"], lp.m["driver"], cond))
            if not r:
                d.text((cx, y + 6), "–", font=font(700, 14), fill=C["ink4"])
                continue
            share = r["passed"] / r["n_trials"] if r["n_trials"] else 0
            col = C["agent"] if cond == "foreground" else C["user"]
            pill(d, (cx, y + 10, cx + bar, y + 22), fill=C["panel2"], r=6)
            if share:
                pill(d, (cx, y + 10, cx + max(12, bar * share), y + 22), fill=col + (230,), r=6)
            d.text((cx + bar + 10, y + 6), f"{r['passed']} of {r['n_trials']}", font=font(700, 14), fill=C["ink2"])
        y += 46
    note = "A pass: the task done, inside the GUI, and in the background the user undisturbed."
    d.text((x, y0 + ch - 32), note, font=font(500, 12.5), fill=C["ink3"])
    return img
