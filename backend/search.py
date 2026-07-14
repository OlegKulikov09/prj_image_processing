"""In-memory similarity search over keyframe embeddings (NumPy brute force).

All embeddings are L2-normalized, so cosine similarity is a single matrix-vector
product. At ~14k vectors this returns in well under a millisecond.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from common import embed_texts


class SearchIndex:
    def __init__(self):
        self.emb = np.load(config.EMB_PATH)              # (N, D) float32, normalized
        self.shot_ids = np.load(config.EMB_IDS_PATH)     # (N,) int
        # shot_id -> row index, for similarity-by-shot lookups
        self.row_of = {int(sid): i for i, sid in enumerate(self.shot_ids)}

    def _top_k(self, sims: np.ndarray, k: int, exclude_row: int | None = None):
        if exclude_row is not None:
            sims = sims.copy()
            sims[exclude_row] = -np.inf
        k = min(k, len(sims))
        # argpartition for the top-k, then sort just those k
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [(int(self.shot_ids[i]), float(sims[i])) for i in idx]

    def search_text(self, query: str, k: int = 60):
        q = embed_texts([query])[0]           # (D,)
        sims = self.emb @ q                    # (N,)
        return self._top_k(sims, k)

    def search_similar(self, shot_id: int, k: int = 60):
        row = self.row_of.get(int(shot_id))
        if row is None:
            return []
        sims = self.emb @ self.emb[row]
        return self._top_k(sims, k, exclude_row=row)
