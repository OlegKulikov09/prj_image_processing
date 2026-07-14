"""Step 1 — Build the SQLite database.

For every video:
  * read fps / duration / resolution via ffprobe,
  * parse its TransNet2 shot boundaries (start_frame end_frame per line),
  * convert frames -> milliseconds (needed for DRES submissions).

Run:  python scripts/01_build_db.py
"""
import json
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from common import connect_db, frame_to_ms, parse_fps


def ffprobe_video(path: Path) -> dict:
    """Return fps, duration, width, height, n_frames for a video file."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height,nb_frames",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    stream = info["streams"][0]
    fps = parse_fps(stream["r_frame_rate"])
    duration = float(info["format"]["duration"])
    width = int(stream["width"])
    height = int(stream["height"])
    # nb_frames is often missing/unreliable -> fall back to duration * fps
    try:
        n_frames = int(stream["nb_frames"])
    except (KeyError, ValueError):
        n_frames = int(round(duration * fps))
    return {"fps": fps, "duration": duration, "width": width,
            "height": height, "n_frames": n_frames}


def parse_scenes(path: Path):
    """Yield (start_frame, end_frame) pairs from a .scenes.txt file."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        start, end = line.split()
        yield int(start), int(end)


def create_schema(conn):
    conn.executescript(
        """
        DROP TABLE IF EXISTS shots;
        DROP TABLE IF EXISTS videos;

        CREATE TABLE videos (
            video_id    TEXT PRIMARY KEY,   -- "00001" (no extension = DRES media item id)
            filename    TEXT NOT NULL,
            fps         REAL NOT NULL,
            duration    REAL NOT NULL,      -- seconds
            n_frames    INTEGER,
            width       INTEGER,
            height      INTEGER,
            description TEXT                 -- optional Vimeo upload description
        );

        CREATE TABLE shots (
            shot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id     TEXT NOT NULL REFERENCES videos(video_id),
            shot_idx     INTEGER NOT NULL,   -- 0-based index within the video
            start_frame  INTEGER NOT NULL,
            end_frame    INTEGER NOT NULL,
            mid_frame    INTEGER NOT NULL,
            start_ms     INTEGER NOT NULL,
            end_ms       INTEGER NOT NULL,
            keyframe_path TEXT NOT NULL      -- relative to config.KEYFRAME_DIR
        );
        CREATE INDEX idx_shots_video ON shots(video_id);
        """
    )


def main():
    videos = sorted(config.VIDEO_DIR.glob("*.mp4"))
    if not videos:
        sys.exit(f"No videos found in {config.VIDEO_DIR}")

    conn = connect_db()
    create_schema(conn)

    n_shots = 0
    for video_path in tqdm(videos, desc="videos"):
        video_id = video_path.stem                  # "00001"
        scenes_path = config.SCENES_DIR / f"{video_path.name}.scenes.txt"
        if not scenes_path.exists():
            print(f"  ! no scenes file for {video_id}, skipping")
            continue

        meta = ffprobe_video(video_path)
        fps = meta["fps"]
        conn.execute(
            "INSERT INTO videos (video_id, filename, fps, duration, n_frames, "
            "width, height, description) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (video_id, video_path.name, fps, meta["duration"],
             meta["n_frames"], meta["width"], meta["height"]),
        )

        for shot_idx, (start_f, end_f) in enumerate(parse_scenes(scenes_path)):
            mid_f = (start_f + end_f) // 2
            keyframe_path = f"{video_id}/{shot_idx:04d}.jpg"
            conn.execute(
                "INSERT INTO shots (video_id, shot_idx, start_frame, end_frame, "
                "mid_frame, start_ms, end_ms, keyframe_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (video_id, shot_idx, start_f, end_f, mid_f,
                 frame_to_ms(start_f, fps),
                 frame_to_ms(end_f + 1, fps),   # end of the last frame
                 keyframe_path),
            )
            n_shots += 1

    conn.commit()
    n_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    conn.close()
    print(f"\nDone: {n_videos} videos, {n_shots} shots -> {config.DB_PATH}")


if __name__ == "__main__":
    main()
