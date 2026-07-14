# V3C Content-Based Video Retrieval (IVADL Assignment 3)

Interactive retrieval system for finding short video segments in the V3C-1 subset
(200 videos, ~25 h) for **Known-Item Search (KIS)** and **Visual Question Answering
(VQA)** tasks, with one-click submission to the **DRES** evaluation server.

## How it works

**Offline (indexing):** each video is split into shots using the provided TransNet2
boundaries; one representative keyframe (middle frame) is extracted per shot and
embedded with **SigLIP 2**; embeddings + shot metadata (with exact per-video fps for
frame→ms conversion) are stored for search; videos are transcoded to 480p proxies for
smooth in-browser playback.

**Online (search):** a text query is embedded with the same model and matched against
all keyframe embeddings by cosine similarity (NumPy, brute force — <1 ms at this scale).
The GUI shows a keyframe grid, an integrated video player (opens at the shot, step
±shot, find-similar), and submits the selected segment to DRES.

```
query ──SigLIP text──▶ cosine vs 14k keyframe embeddings ──▶ grid ──▶ player ──▶ DRES submit
```

## Stack

| Component        | Choice                                   |
|------------------|------------------------------------------|
| Embeddings       | SigLIP 2 (`google/siglip2-so400m-patch14-384`) via HuggingFace transformers, on Apple MPS |
| Vector search    | NumPy brute-force cosine (~14k × 1152)   |
| Metadata storage | SQLite                                   |
| Video processing | ffmpeg / ffprobe                         |
| Backend          | FastAPI + uvicorn                        |
| Frontend         | Plain HTML/CSS/JS (no build step)        |
| DRES client      | `requests`, written to the DRES v2 OpenAPI spec |

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
brew install ffmpeg                      # needs ffmpeg + ffprobe on PATH
```

Dataset layout expected (already in place):
```
V3C1_200/                 200 × NNNNN.mp4
V3C1_200/scenes_v3c1_204/ 200 × NNNNN.mp4.scenes.txt   (TransNet2 shot boundaries)
```

## Build the index (offline pipeline)

Run once, in order (each step is idempotent / resumable):

```bash
./.venv/bin/python scripts/01_build_db.py    # SQLite: videos + shots (frames→ms via fps)
./.venv/bin/python scripts/02_keyframes.py   # one keyframe per shot (ffmpeg)
./.venv/bin/python scripts/03_embed.py       # SigLIP2 embeddings → data/embeddings.npy
./.venv/bin/python scripts/04_transcode.py   # 480p proxy videos for playback
```

Produces (in `data/`): `index.sqlite`, `keyframes/`, `embeddings.npy` + `shot_ids.npy`,
`proxies/`.

## Run the system

```bash
./run.sh                                 # or: ./.venv/bin/python -m uvicorn backend.app:app
```

Open **http://127.0.0.1:8000**. The model is warmed up at startup so the first query is
instant.

## Using the GUI

- **Search** — type a description, Enter. Results are ranked keyframes.
- **Inspect** — click a keyframe to open the player at that shot. `[` / `]` step to the
  previous / next shot of the same video; `≈ Similar` finds visually similar shots.
- **Submit to DRES** — log in (top-right; credentials from the instructor), then
  `▶ Submit` (or press `S`) sends the current shot's `[start_ms, end_ms]` for video.
  For VQA, type the answer in the text field before submitting.
- **Shortcuts** — `/` focus search · `[` `]` prev/next shot · `F` similar · `S` submit ·
  `Esc` close player.

## Config

All paths, the model name, and DRES settings (`DRES_BASE_URL`, evaluation name
`IVADL2026`, collection `IVADL`) live in [`config.py`](config.py).

## Notes

- **Metadata** — the Vimeo upload descriptions were not part of the download; the schema
  keeps an optional `videos.description` column so they can be added later without rework.
  Search is fully visual and does not depend on them.
- **DRES submit** is implemented against the official OpenAPI spec but can only be tested
  against a live evaluation session (needs credentials + a running task on the server).
