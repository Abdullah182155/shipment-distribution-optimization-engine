"""
Rebalance — ensure all couriers satisfy [min, max] delivery constraints.
"""

from __future__ import annotations

import numpy as np


def rebalance(labels: np.ndarray, coords_km: np.ndarray,
              num_couriers: int, min_del: int, max_del: int,
              max_iter: int = 15_000) -> np.ndarray:
    """
    Iteratively move deliveries from over-capacity couriers to
    under-capacity ones (nearest-centroid heuristic).
    Returns a new labels array.
    """
    labels = labels.copy()
    sizes = np.bincount(labels.clip(min=0), minlength=num_couriers)

    for _ in range(max_iter):
        over = np.where(sizes > max_del)[0]
        under = np.where(sizes < min_del)[0]
        if not len(over) and not len(under):
            break

        if len(over) and len(under):
            src = over[np.argmax(sizes[over])]
            dst = under[np.argmin(sizes[under])]
        elif len(over):
            src = over[np.argmax(sizes[over])]
            cands = np.where(sizes < max_del)[0]
            if not len(cands):
                break
            dst = cands[0]
        else:
            cands = np.where(sizes > min_del)[0]
            if not len(cands):
                break
            src = cands[0]
            dst = under[0]

        src_idx = np.where(labels == src)[0]
        if not len(src_idx):
            break
        src_pts = coords_km[labels == src]
        dst_ctr = (coords_km[labels == dst].mean(axis=0)
                   if np.any(labels == dst) else np.zeros(2))
        best_i = src_idx[np.argmin(np.linalg.norm(src_pts - dst_ctr, axis=1))]
        labels[best_i] = dst
        sizes[src] -= 1
        sizes[dst] += 1

    return labels
