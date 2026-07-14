"""Step 2 — Extract one representative keyframe (middle frame) per shot.

Uses ffmpeg fast-seek (one JPEG per shot), parallelized across threads.
Idempotent: skips keyframes that already exist, so it can be re-run to finish
an interrupted extraction.

Run:  python scripts/02_keyframes.py
"""
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from common import connect_db

N_WORKERS = 10


def extract_one(job) -> str | None:
    """Extract a single keyframe. Returns an error string, or None on success."""
    video_path, mid_time, out_path = job
    if out_path.exists():
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error",
        "-ss", f"{mid_time:.3f}", "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={config.KEYFRAME_WIDTH}:-2",
        "-q:v", "3", "-y", str(out_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_path.exists():
        return f"{out_path.name}: {res.stderr.strip()[:120]}"
    return None


def main():
    conn = connect_db()
    rows = conn.execute(
        "SELECT s.mid_frame, s.keyframe_path, v.filename, v.fps "
        "FROM shots s JOIN videos v ON v.video_id = s.video_id"
    ).fetchall()
    conn.close()

    jobs = []
    for r in rows:
        video_path = config.VIDEO_DIR / r["filename"]
        mid_time = r["mid_frame"] / r["fps"]
        out_path = config.KEYFRAME_DIR / r["keyframe_path"]
        jobs.append((video_path, mid_time, out_path))

    errors = []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as pool:
        futures = [pool.submit(extract_one, j) for j in jobs]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="keyframes"):
            err = fut.result()
            if err:
                errors.append(err)

    print(f"\nDone: {len(jobs)} shots, {len(errors)} errors")
    for e in errors[:20]:
        print("  !", e)


if __name__ == "__main__":
    main()
