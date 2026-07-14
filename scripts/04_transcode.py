"""Step 4 — Transcode each video to a small 480p proxy for smooth GUI playback.

H.264 + faststart so the browser can seek instantly. Never upscales.
Idempotent: skips proxies that already exist.

Run:  python scripts/04_transcode.py
"""
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

N_WORKERS = 4   # each ffmpeg encode is itself multi-threaded


def transcode_one(video_path: Path) -> str | None:
    out_path = config.PROXY_DIR / f"{video_path.stem}.mp4"
    if out_path.exists():
        return None
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(video_path),
        "-vf", f"scale=-2:'min({config.PROXY_HEIGHT},ih)'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart", "-y", str(out_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_path.exists():
        return f"{video_path.name}: {res.stderr.strip()[:150]}"
    return None


def main():
    config.PROXY_DIR.mkdir(parents=True, exist_ok=True)
    videos = sorted(config.VIDEO_DIR.glob("*.mp4"))

    errors = []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as pool:
        futures = [pool.submit(transcode_one, v) for v in videos]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="transcode"):
            err = fut.result()
            if err:
                errors.append(err)

    print(f"\nDone: {len(videos)} videos, {len(errors)} errors")
    for e in errors[:20]:
        print("  !", e)


if __name__ == "__main__":
    main()
