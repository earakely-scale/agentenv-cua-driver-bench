"""build.py DATA_DIR OUT_DIR: the Space, the hero GIF and still, the results and drivers figures, and the card's
results.md and drivers.md tables, from a folder of trials.

DATA_DIR is the dataset's root (holding runs/<os>/<run>/<trial>/), runs/ itself, or any folder of trial folders.
Each trial's web copy is written next to its recording as web.mp4; the Space streams it from config media_base, or
from the dataset HF_REPO names when that's set. The Space's own files are site/; it needs ffmpeg."""
import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cdbviz import catalog, figures, hero, media, trials  # noqa: E402


def pick_hero(metas, cfg):
    want = (cfg.get("hero") or {}).get("trial")
    for m in metas:
        if want and want in (m["id"], m["uid"]):
            return m["uid"]
    bg = [m for m in metas if m["condition"] == "background" and catalog.on_board(m["model"], cfg)]
    if not bg:
        return None
    score = lambda m: (m["user_lane"], m["passed"], (m["grade"]["task"] or {}).get("score") or 0, m["tool_calls"] or 0)
    return max(bg, key=score)["uid"]


def encode(t, cfg, space, force):
    m, web, folder = t["meta"], t["web"], t["folder"]
    src = folder / "recording.mp4"
    out = space / "data" / "trials" / m["uid"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "timeline.json").write_text(json.dumps(web, separators=(",", ":"), ensure_ascii=False))
    entry = {"timeline": f"data/trials/{m['uid']}/timeline.json"}
    if src.exists():
        size = media.web_video(src, folder / "web.mp4", cfg, force)
        a, d = web["armed"]
        mid = (a or 0) + cfg["hero"]["still_at"] * ((d or web["duration"] or 0) - (a or 0))
        if force or not media.fresh(out / "poster.jpg", src):
            media.frame(src, mid, out / "poster.jpg", 640, quality=4)
        entry.update(poster=f"data/trials/{m['uid']}/poster.jpg", video_mb=round(size / 1e6, 2))
    return entry


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--config", type=Path, default=HERE / "config.json")
    ap.add_argument("--force", action="store_true", help="re-encode videos and posters even when up to date")
    ap.add_argument("--no-gif", action="store_true", help="skip the hero GIF and still")
    ap.add_argument("--local-media", action="store_true",
                    help="copy every web video into the Space instead of streaming")
    ap.add_argument("--jobs", type=int, default=2, help="parallel video encodes")
    args = ap.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        media.need(tool)
    cfg = json.loads(args.config.read_text())
    if os.environ.get("HF_REPO"):
        cfg["media_base"] = f"https://huggingface.co/datasets/{os.environ['HF_REPO']}/resolve/main"
        cfg["links"]["dataset"] = f"https://huggingface.co/datasets/{os.environ['HF_REPO']}"
    skip = set(cfg.get("exclude_runs") or [])
    folders = [f for f in trials.discover(args.data) if trials.run_of(f, args.data) not in skip]
    if not folders:
        raise SystemExit(f"no trial folders (with trial.json) under {args.data}")
    space, assets = args.out / "space", args.out / "assets"
    data = space / "data"
    loaded = [trials.load(f, cfg, args.data) for f in folders]
    seen = {}
    for t in loaded:
        uid = t["meta"]["uid"]
        if uid in seen:
            raise SystemExit(f"two trials map to {uid}: {seen[uid]} and {t['folder']}")
        seen[uid] = t["folder"]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        entries = list(pool.map(lambda t: encode(t, cfg, space, args.force), loaded))
    metas = [t["meta"] for t in loaded]
    hero_uid = pick_hero(metas, cfg)
    base = None if args.local_media else (cfg.get("media_base") or "").rstrip("/") or None
    local = (cfg.get("space_local") or "hero")
    files = {}
    for t, entry in zip(loaded, entries):
        m = t["meta"]
        web_mp4 = t["folder"] / "web.mp4"
        if not web_mp4.exists():
            files[m["uid"]] = entry
            continue
        keep_local = base is None or local == "all" or (local == "hero" and m["uid"] == hero_uid)
        local_path = space / "data" / "trials" / m["uid"] / "video.mp4"
        if keep_local:
            if not media.fresh(local_path, web_mp4):
                shutil.copy2(web_mp4, local_path)
            entry["video_local"] = f"data/trials/{m['uid']}/video.mp4"
        else:
            local_path.unlink(missing_ok=True)
        entry["video"] = f"{base}/{m['rel']}/web.mp4" if base else entry.get("video_local")
        files[m["uid"]] = entry
        print(f"{m['uid']}: {len(t['web']['calls'])} calls, user lane {'yes' if t['web']['user'] else 'no'}, "
              f"web.mp4 {entry.get('video_mb', '–')} MB{', Space copy' if keep_local else ''}")
    cat = catalog.build(metas, cfg, hero_uid, files, [m for m in trials.discover_missing(args.data)
                                                     if f"{m['os']}/{m['run']}" not in skip])
    keep = {m["uid"] for m in metas}
    for stale in (data / "trials").iterdir():
        if stale.is_dir() and stale.name not in keep:
            shutil.rmtree(stale)
    media.copy_tree(HERE / "site", space)
    shutil.copytree(HERE / "fonts" / "web", space / "fonts", dirs_exist_ok=True)
    cat.update(figures.write_all(cat, [assets, space / "figures"]))
    (data / "catalog.json").write_text(json.dumps(cat, separators=(",", ":"), ensure_ascii=False))
    (args.out / "results.md").write_text(catalog.results_md(cat))
    (args.out / "drivers.md").write_text(catalog.drivers_md(cat))
    print(f"figures: {4 * (len(cat['figures']) + len(cat['driver_figures']))} SVGs in {assets}")
    if hero_uid and not args.no_gif:
        t = next(x for x in loaded if x["meta"]["uid"] == hero_uid)
        gif, still = hero.render(t, cat, cfg, assets)
        print(f"hero: {hero_uid} -> {gif} ({gif.stat().st_size / 1e6:.1f} MB), {still}")
    print(f"catalog: {len(metas)} trials -> {data / 'catalog.json'}")


if __name__ == "__main__":
    main()
