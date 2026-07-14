"""Shared helpers used by both the offline pipeline and the backend:
database access, frame<->ms conversion, and the SigLIP2 model (image/text embeddings).
"""
import sqlite3
from functools import lru_cache

import numpy as np

import config


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def connect_db():
    """Open the SQLite DB with row access by column name."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------
# Frame / time helpers
# --------------------------------------------------------------------------
def parse_fps(r_frame_rate: str) -> float:
    """ffprobe reports fps as a fraction like '25/1' or '30000/1001'."""
    num, den = r_frame_rate.split("/")
    return float(num) / float(den)


def frame_to_ms(frame: int, fps: float) -> int:
    """Convert a frame index to milliseconds (rounded)."""
    return int(round(frame / fps * 1000.0))


# --------------------------------------------------------------------------
# SigLIP2 model (loaded once, cached)
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_model():
    """Load SigLIP2 model + processor onto the best available device.
    Cached so repeated calls in the backend reuse the same instance.
    """
    import torch
    from transformers import AutoModel, AutoProcessor

    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    model = AutoModel.from_pretrained(config.MODEL_NAME).to(device).eval()
    processor = AutoProcessor.from_pretrained(config.MODEL_NAME)
    return model, processor, device


def _pooled(out):
    """transformers 5.x returns BaseModelOutputWithPooling from get_*_features;
    the SigLIP embedding lives in .pooler_output. Older versions return a tensor.
    """
    return out.pooler_output if hasattr(out, "pooler_output") else out


def _normalize(feats):
    return feats / feats.norm(p=2, dim=-1, keepdim=True)


def embed_images(pil_images) -> np.ndarray:
    """Embed a list of PIL images -> (N, D) float32, L2-normalized."""
    import torch

    model, processor, device = load_model()
    inputs = processor(images=list(pil_images), return_tensors="pt").to(device)
    with torch.no_grad():
        feats = _normalize(_pooled(model.get_image_features(**inputs)))
    return feats.cpu().numpy().astype("float32")


def embed_texts(texts) -> np.ndarray:
    """Embed a list of text queries -> (N, D) float32, L2-normalized.
    SigLIP needs padding='max_length' (fixed 64-token context).
    """
    import torch

    model, processor, device = load_model()
    inputs = processor(
        text=list(texts), padding="max_length", return_tensors="pt"
    ).to(device)
    with torch.no_grad():
        feats = _normalize(_pooled(model.get_text_features(**inputs)))
    return feats.cpu().numpy().astype("float32")
