"""Central configuration: all paths and knobs live here."""
from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).resolve().parent
VIDEO_DIR = ROOT / "V3C1_200"                       # raw .mp4 files
SCENES_DIR = VIDEO_DIR / "scenes_v3c1_204"          # TransNet2 shot boundaries
DATA_DIR = ROOT / "data"
KEYFRAME_DIR = DATA_DIR / "keyframes"               # <video_id>/<shot_idx>.jpg
PROXY_DIR = DATA_DIR / "proxies"                    # <video_id>.mp4 (480p)
DB_PATH = DATA_DIR / "index.sqlite"
EMB_PATH = DATA_DIR / "embeddings.npy"              # (N, D) float32, L2-normalized
EMB_IDS_PATH = DATA_DIR / "shot_ids.npy"            # (N,) int, row i -> shots.shot_id

# --- Model ---
# SigLIP 2 via HuggingFace transformers. so400m-patch14-384 = strong retrieval quality.
# Swap to "google/siglip2-base-patch16-256" if you want a smaller/faster model.
MODEL_NAME = "google/siglip2-so400m-patch14-384"

# --- Keyframe extraction ---
KEYFRAME_WIDTH = 384       # thumbnail width in px (height auto); 384 feeds SigLIP nicely

# --- Proxy transcoding ---
PROXY_HEIGHT = 480         # proxy video height in px

# --- DRES ---
DRES_BASE_URL = "https://vbs.videobrowsing.org"
DRES_EVALUATION_NAME = "IVADL2026"   # evaluation to auto-select from evaluation/list
DRES_COLLECTION = "IVADL"            # media collection name required by submit
