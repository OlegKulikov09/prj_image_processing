"""Step 3 — Compute SigLIP2 image embeddings for every keyframe.

Saves two aligned arrays:
  * embeddings.npy  (N, D) float32, L2-normalized
  * shot_ids.npy    (N,)  int   -> row i corresponds to shots.shot_id[i]

Run:  python scripts/03_embed.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from common import connect_db, embed_images

BATCH_SIZE = 64


def main():
    conn = connect_db()
    rows = conn.execute(
        "SELECT shot_id, keyframe_path FROM shots ORDER BY shot_id"
    ).fetchall()
    conn.close()

    all_embs, all_ids = [], []
    batch_imgs, batch_ids = [], []

    def flush():
        if not batch_imgs:
            return
        all_embs.append(embed_images(batch_imgs))
        all_ids.extend(batch_ids)
        for im in batch_imgs:
            im.close()
        batch_imgs.clear()
        batch_ids.clear()

    missing = 0
    for r in tqdm(rows, desc="embedding"):
        img_path = config.KEYFRAME_DIR / r["keyframe_path"]
        if not img_path.exists():
            missing += 1
            continue
        batch_imgs.append(Image.open(img_path).convert("RGB"))
        batch_ids.append(r["shot_id"])
        if len(batch_imgs) >= BATCH_SIZE:
            flush()
    flush()

    embeddings = np.concatenate(all_embs, axis=0)
    shot_ids = np.array(all_ids, dtype=np.int64)
    np.save(config.EMB_PATH, embeddings)
    np.save(config.EMB_IDS_PATH, shot_ids)

    print(f"\nDone: {embeddings.shape[0]} embeddings, dim={embeddings.shape[1]}, "
          f"{missing} keyframes missing")
    print(f"  -> {config.EMB_PATH}")
    print(f"  -> {config.EMB_IDS_PATH}")


if __name__ == "__main__":
    main()
