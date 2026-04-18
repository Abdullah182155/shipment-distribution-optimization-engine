"""
Spatial index — centroids, cKDTree, locality candidates, cluster helpers.
All functions are parameterized (no globals).
"""

from __future__ import annotations

from typing import Dict, List, Set

import numpy as np
from scipy.spatial import cKDTree

from app.utils.cache import ThreadLocalState
from app.utils.geometry import hull_area


# ═══════════════════════════════════════════════════════════════════════════════
# CENTROIDS & SPATIAL INDEX
# ═══════════════════════════════════════════════════════════════════════════════

def rebuild_centroids(labels: np.ndarray, coords_km: np.ndarray,
                      num_couriers: int, tls: ThreadLocalState) -> None:
    """Recompute all centroids and rebuild the centroid kd-tree."""
    tls.tl.centroids = np.array([
        coords_km[labels == c].mean(axis=0) if np.any(labels == c) else np.zeros(2)
        for c in range(num_couriers)
    ])
    tls.tl.centroid_tree = cKDTree(tls.tl.centroids)
    tls.tl.cluster_radius = {}


def update_centroids_batch(couriers: Set[int], labels: np.ndarray,
                           coords_km: np.ndarray, tls: ThreadLocalState) -> None:
    """Incrementally update centroids for a subset of couriers."""
    for c in couriers:
        pts = coords_km[labels == c]
        tls.tl.centroids[c] = pts.mean(axis=0) if len(pts) > 0 else np.zeros(2)
        tls.tl.cluster_radius.pop(c, None)
    tls.tl.centroid_tree = cKDTree(tls.tl.centroids)


def compute_locality_radius(labels: np.ndarray, coords_km: np.ndarray,
                            num_couriers: int, locality_r_fac: float,
                            tls: ThreadLocalState) -> float:
    """Average cluster spread × factor → locality search radius."""
    radii = []
    for c in range(num_couriers):
        pts = coords_km[labels == c]
        if len(pts) >= 2:
            radii.append(float(np.linalg.norm(pts - pts.mean(axis=0), axis=1).mean()))
    avg_r = float(np.mean(radii)) if radii else 1.0
    tls.tl.locality_radius = avg_r * locality_r_fac
    return tls.tl.locality_radius


def locality_candidates(i: int, coords_km: np.ndarray,
                        num_couriers: int, tls: ThreadLocalState,
                        n: int = 12) -> List[int]:
    """Return nearby courier indices for delivery point i."""
    if tls.tl.centroid_tree is None:
        return list(range(num_couriers))
    R = getattr(tls.tl, "locality_radius", 2.0)
    idx = tls.tl.centroid_tree.query_ball_point(coords_km[i], R)
    if not idx:
        _, idx = tls.tl.centroid_tree.query(coords_km[i], k=min(3, num_couriers))
        return list(np.atleast_1d(idx))
    return idx[:n]


# ═══════════════════════════════════════════════════════════════════════════════
# CLUSTER HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_sizes(labels: np.ndarray, num_couriers: int) -> np.ndarray:
    return np.bincount(labels.clip(min=0), minlength=num_couriers)


def validate(labels: np.ndarray, num_couriers: int,
             min_del: int, max_del: int) -> bool:
    s = get_sizes(labels, num_couriers)
    return bool(np.all(s >= min_del) and np.all(s <= max_del))


def build_clusters(labels: np.ndarray, num_couriers: int) -> Dict[int, List[int]]:
    return {c: np.where(labels == c)[0].tolist() for c in range(num_couriers)}


def build_areas(clusters: Dict, coords_km: np.ndarray,
                tls: ThreadLocalState) -> Dict[int, float]:
    return {c: hull_area(clusters[c], coords_km, tls) for c in clusters}


def cluster_radius_cached(c: int, labels: np.ndarray, coords_km: np.ndarray,
                          tls: ThreadLocalState) -> float:
    """Mean distance of cluster members from centroid (cached)."""
    if c in tls.tl.cluster_radius:
        return tls.tl.cluster_radius[c]
    pts = coords_km[labels == c]
    r = float(np.linalg.norm(pts - tls.tl.centroids[c], axis=1).mean()) if len(pts) >= 2 else 0.0
    tls.tl.cluster_radius[c] = r
    return r


def pre_check_candidate(i: int, dst: int, labels: np.ndarray,
                        coords_km: np.ndarray, tls: ThreadLocalState) -> bool:
    """Quick distance-based filter before computing full move delta."""
    r = cluster_radius_cached(dst, labels, coords_km, tls)
    dist = float(np.linalg.norm(coords_km[i] - tls.tl.centroids[dst]))
    return dist <= max(2.0 * r, 1.5)
