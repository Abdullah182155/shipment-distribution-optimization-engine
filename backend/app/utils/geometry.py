"""
Geometry primitives — convex hull area, perimeter, vertices, compactness,
hull equations, overlap (Sutherland-Hodgman), etc.

All functions take `coords_km` and `tls` (ThreadLocalState) as parameters
instead of relying on module-level globals.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from scipy.spatial import ConvexHull

from app.utils.cache import ThreadLocalState, stable_key


# ═══════════════════════════════════════════════════════════════════════════════
# RAW GEOMETRY (no caching)
# ═══════════════════════════════════════════════════════════════════════════════

def raw_area(pts: np.ndarray) -> float:
    """Convex hull area of a point set (km²)."""
    if len(pts) < 3:
        return 0.0
    try:
        return float(ConvexHull(pts).volume)
    except Exception:
        return 0.0


def raw_perimeter(pts: np.ndarray) -> float:
    """Convex hull perimeter of a point set (km)."""
    if len(pts) < 2:
        return 0.0
    if len(pts) == 2:
        return float(np.linalg.norm(pts[0] - pts[1]) * 2)
    try:
        h = ConvexHull(pts)
        vp = pts[h.vertices]
        return float(np.sum(np.linalg.norm(np.roll(vp, -1, axis=0) - vp, axis=1)))
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# CACHED GEOMETRY — use thread-local LRU caches
# ═══════════════════════════════════════════════════════════════════════════════

def hull_area(indices, coords_km: np.ndarray, tls: ThreadLocalState) -> float:
    """Cached convex hull area."""
    hc, _, _ = tls.get_caches()
    if not indices:
        return 0.0
    key = stable_key(indices)
    val = hc.get(key)
    if val is not None:
        return val
    val = raw_area(coords_km[list(indices)])
    hc[key] = val
    return val


def hull_perimeter(indices, coords_km: np.ndarray, tls: ThreadLocalState) -> float:
    """Cached convex hull perimeter."""
    _, _, pc = tls.get_caches()
    if not indices:
        return 0.0
    key = stable_key(indices)
    val = pc.get(key)
    if val is not None:
        return val
    val = raw_perimeter(coords_km[list(indices)])
    pc[key] = val
    return val


def hull_verts(indices, coords_km: np.ndarray, tls: ThreadLocalState) -> List[int]:
    """Cached hull vertex indices (in original point numbering)."""
    _, vc, _ = tls.get_caches()
    if not indices:
        return []
    key = stable_key(indices)
    cached = vc.get(key)
    if cached is not None:
        return cached
    idx_list = list(indices)
    pts = coords_km[idx_list]
    if len(pts) < 3:
        vc[key] = idx_list[:]
        return idx_list[:]
    try:
        h = ConvexHull(pts)
        result = [idx_list[vi] for vi in h.vertices]
        vc[key] = result
        return result
    except Exception:
        vc[key] = idx_list[:]
        return idx_list[:]


def compactness(indices, coords_km: np.ndarray, tls: ThreadLocalState) -> float:
    """Isoperimetric quotient: 4π·area / perimeter²."""
    a = hull_area(indices, coords_km, tls)
    p = hull_perimeter(indices, coords_km, tls)
    if p < 1e-9:
        return 1.0
    return min(1.0, 4.0 * math.pi * a / (p * p))


# ═══════════════════════════════════════════════════════════════════════════════
# HULL EQUATIONS (for point-in-hull tests)
# ═══════════════════════════════════════════════════════════════════════════════

def rebuild_eq(c: int, clusters: Dict, coords_km: np.ndarray,
               tls: ThreadLocalState) -> None:
    """Rebuild half-plane equations for courier c's hull."""
    pts = coords_km[clusters[c]]
    if len(pts) < 3:
        tls.tl.eq_cache[c] = None
        return
    try:
        tls.tl.eq_cache[c] = ConvexHull(pts).equations
    except Exception:
        tls.tl.eq_cache[c] = None


def inside_hull(pt: np.ndarray, c: int, tls: ThreadLocalState) -> bool:
    """Test whether `pt` lies inside courier c's convex hull."""
    eq = tls.tl.eq_cache.get(c)
    if eq is None:
        return False
    return bool(np.all(eq @ np.append(pt, 1.0) <= 1e-10))


# ═══════════════════════════════════════════════════════════════════════════════
# CACHE INVALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def invalidate(c: int, clusters: Dict, tls: ThreadLocalState) -> None:
    """Invalidate all cached data for courier c."""
    hc, vc, pc = tls.get_caches()
    key = stable_key(clusters[c])
    hc.pop(key, None)
    vc.pop(key, None)
    pc.pop(key, None)
    tls.tl.eq_cache[c] = None
    tls.tl.hull_vert_set.pop(c, None)
    tls.tl.max_diameter.pop(c, None)
    tls.tl.cluster_radius.pop(c, None)


def hull_vert_set_cached(c: int, clusters: Dict, coords_km: np.ndarray,
                         tls: ThreadLocalState) -> Set[int]:
    """Cached set of hull vertex indices for courier c."""
    hvs = tls.tl.hull_vert_set
    if c not in hvs:
        hvs[c] = set(hull_verts(clusters[c], coords_km, tls))
    return hvs[c]


# ═══════════════════════════════════════════════════════════════════════════════
# OVERLAP (Sutherland-Hodgman polygon clipping)
# ═══════════════════════════════════════════════════════════════════════════════

def _sutherland_hodgman(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Clip subject polygon by clip polygon (both CCW vertex arrays)."""
    def _inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0.0

    def _intersect(p1, p2, p3, p4):
        d1 = p2 - p1
        d2 = p4 - p3
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(cross) < 1e-12:
            return p1
        t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / cross
        return p1 + t * d1

    output = list(subject)
    n_clip = len(clip)
    for i in range(n_clip):
        if not output:
            break
        a, b = clip[i], clip[(i + 1) % n_clip]
        inp = output
        output = []
        for j in range(len(inp)):
            cur = inp[j]
            prev = inp[j - 1]
            if _inside(cur, a, b):
                if not _inside(prev, a, b):
                    output.append(_intersect(prev, cur, a, b))
                output.append(cur)
            elif _inside(prev, a, b):
                output.append(_intersect(prev, cur, a, b))
    return np.array(output) if len(output) >= 3 else np.empty((0, 2))


def polygon_area(pts: np.ndarray) -> float:
    """Shoelace formula for polygon area."""
    if len(pts) < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) * 0.5


def hull_polygon(indices: List[int], coords_km: np.ndarray) -> Optional[np.ndarray]:
    """Return hull boundary vertices for a set of point indices."""
    if len(indices) < 3:
        return None
    pts = coords_km[indices]
    try:
        h = ConvexHull(pts)
        return pts[h.vertices]
    except Exception:
        return None


def exact_overlap_area(c1: int, c2: int, clusters: Dict,
                       areas: Dict, coords_km: np.ndarray) -> float:
    """Exact overlap area between two courier hulls via polygon clipping."""
    if areas[c1] < 1e-9 or areas[c2] < 1e-9:
        return 0.0
    p1 = hull_polygon(clusters[c1], coords_km)
    p2 = hull_polygon(clusters[c2], coords_km)
    if p1 is None or p2 is None:
        return 0.0
    clipped = _sutherland_hodgman(p1, p2)
    return polygon_area(clipped) if len(clipped) >= 3 else 0.0


def rebuild_overlap_matrix(clusters: Dict, areas: Dict,
                           coords_km: np.ndarray, num_couriers: int,
                           tls: ThreadLocalState) -> None:
    """Full pairwise overlap matrix rebuild."""
    mat = np.zeros((num_couriers, num_couriers))
    for c1 in range(num_couriers):
        for c2 in range(c1 + 1, num_couriers):
            if np.linalg.norm(tls.tl.centroids[c1] - tls.tl.centroids[c2]) > 3.0:
                continue
            ov = exact_overlap_area(c1, c2, clusters, areas, coords_km)
            mat[c1, c2] = ov
            mat[c2, c1] = ov
    tls.tl.overlap_mat = mat


def rebuild_overlap_flags(labels: np.ndarray, clusters: Dict,
                          coords_km: np.ndarray, n_deliveries: int,
                          num_couriers: int, tls: ThreadLocalState) -> None:
    """Flag each delivery that falls inside another courier's hull."""
    flags = np.zeros(n_deliveries, dtype=bool)
    for i in range(n_deliveries):
        pt = coords_km[i]
        c_own = int(labels[i])
        for c2 in range(num_couriers):
            if c2 == c_own:
                continue
            if inside_hull(pt, c2, tls):
                flags[i] = True
                break
    tls.tl.overlap_point = flags


def update_overlap_row(c: int, clusters: Dict, areas: Dict,
                       coords_km: np.ndarray, num_couriers: int,
                       tls: ThreadLocalState) -> None:
    """Update one row/column of the overlap matrix."""
    if tls.tl.overlap_mat is None:
        return
    mat = tls.tl.overlap_mat
    for c2 in range(num_couriers):
        if c2 == c:
            continue
        dist = np.linalg.norm(tls.tl.centroids[c] - tls.tl.centroids[c2])
        if dist > 3.0:
            mat[c, c2] = mat[c2, c] = 0.0
            continue
        ov = exact_overlap_area(c, c2, clusters, areas, coords_km)
        mat[c, c2] = ov
        mat[c2, c] = ov


def total_overlap(tls: ThreadLocalState) -> float:
    if tls.tl.overlap_mat is None:
        return 0.0
    return float(tls.tl.overlap_mat.sum()) / 2.0


def courier_overlap(c: int, tls: ThreadLocalState) -> float:
    if tls.tl.overlap_mat is None:
        return 0.0
    return float(tls.tl.overlap_mat[c].sum())


def full_overlap_rebuild(labels: np.ndarray, clusters: Dict, areas: Dict,
                         coords_km: np.ndarray, n_deliveries: int,
                         num_couriers: int, tls: ThreadLocalState) -> None:
    """Complete overlap rebuild: equations + matrix + flags."""
    for c in range(num_couriers):
        rebuild_eq(c, clusters, coords_km, tls)
    rebuild_overlap_matrix(clusters, areas, coords_km, num_couriers, tls)
    rebuild_overlap_flags(labels, clusters, coords_km, n_deliveries, num_couriers, tls)
