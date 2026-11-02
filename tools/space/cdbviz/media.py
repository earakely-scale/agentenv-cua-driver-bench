import json
import shutil
import subprocess
from pathlib import Path


def need(tool):
    if not shutil.which(tool):
        raise SystemExit(f"{tool} is not on PATH")


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = (d.get("streams") or [{}])[0]
    return float(d["format"]["duration"]), s.get("width"), s.get("height")


def fresh(out, src):
    return out.exists() and out.stat().st_size > 0 and out.stat().st_mtime >= src.stat().st_mtime


def web_video(src, out, cfg, force=False):
    v = cfg["video"]
    if not force and fresh(out, src):
        return out.stat().st_size
    out.parent.mkdir(parents=True, exist_ok=True)
    crf = v["crf"]
    while True:
        tmp = out.with_suffix(".tmp.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                        f"fps=10,scale={v['width']}:{v['height']}:flags=lanczos,format=yuv420p",
                        "-c:v", "libx264", "-preset", "slow", "-tune", "stillimage", "-crf", str(crf),
                        "-g", "50", "-profile:v", "high", "-movflags", "+faststart", "-an", str(tmp)], check=True)
        size = tmp.stat().st_size
        if size <= v["max_mb"] * 1e6 or crf >= 40:
            tmp.replace(out)
            return size
        crf += 2


def frame(src, t, out, width=960, quality=3):
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1",
                    "-vf", f"scale={width}:-2:flags=lanczos", "-q:v", str(quality), str(out)], check=True)


def frames(src, start, fps, count, size):
    w, h = size
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-i", str(src), "-vf",
           f"fps={fps},scale={w}:{h}:flags=lanczos", "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield buf
    finally:
        proc.stdout.close()
        proc.wait()


def copy_tree(src, dst):
    src, dst = Path(src), Path(dst)
    for p in src.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            target = dst / p.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
