"""
Move primitives + greedy/swap/converge passes.
Sections 7, 12, 13 from the original script.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Set

import numpy as np

from app.utils.cache import ThreadLocalState
from app.utils.geometry import (
    hull_area, hull_verts, invalidate, rebuild_eq,
    update_overlap_row, compactness,
)
from app.utils.spatial import (
    locality_candidates, update_centroids_batch, cluster_radius_cached,
)


# ═══════════════════════════════════════════════════════════════════════════════
# MOVE DELTA  [V17-7: pure area, no compact penalty]
# ═══════════════════════════════════════════════════════════════════════════════

def move_delta(i: int, src: int, dst: int,
               clusters: Dict, areas: Dict, labels: np.ndarray,
               coords_km: np.ndarray, tls: ThreadLocalState) -> float:
    """Evaluate move delta including objective weights (alpha, delta)."""
    src_new = [p for p in clusters[src] if p != i]
    dst_new = clusters[dst] + [i]
    
    da = (hull_area(src_new, coords_km, tls) +
          hull_area(dst_new, coords_km, tls) -
          areas[src] - areas[dst])
          
    alpha = getattr(tls.tl, 'alpha', 1.0)
    delta_w = getattr(tls.tl, 'delta', 0.0)
    
    cost = alpha * da
    if delta_w > 0.001:
        dc = (compactness(src_new, coords_km, tls) + compactness(dst_new, coords_km, tls)
              - compactness(clusters[src], coords_km, tls) - compactness(clusters[dst], coords_km, tls))
        # compactness is 0..1 (higher is better). We want to minimize cost, so subtract dc times weight
        cost -= delta_w * dc * 10.0
        
    return cost


def full_cost(areas: Dict, clusters: Dict, coords_km: np.ndarray, tls: ThreadLocalState) -> float:
    """Evaluate total objective cost across all couriers."""
    alpha = getattr(tls.tl, 'alpha', 1.0)
    beta = getattr(tls.tl, 'beta', 0.0)
    delta_w = getattr(tls.tl, 'delta', 0.0)
    
    base_area = sum(areas.values())
    cost = alpha * base_area
    
    if beta > 0.001:
        from app.utils.geometry import total_overlap
        # Apply heavy penalty for overlapping area to encourage distinct zones
        cost += beta * total_overlap(tls) * 5.0
        
    if delta_w > 0.001:
        comp_sum = sum(compactness(clusters[c], coords_km, tls) for c in clusters if len(clusters[c]) >= 3)
        cost -= delta_w * comp_sum * 5.0
        
    return cost


# ═══════════════════════════════════════════════════════════════════════════════
# APPLY MOVE / SWAP
# ═══════════════════════════════════════════════════════════════════════════════

def apply_move(i: int, src: int, dst: int,
               labels: np.ndarray, clusters: Dict,
               areas: Dict, sizes: np.ndarray,
               coords_km: np.ndarray, num_couriers: int,
               tls: ThreadLocalState) -> float:
    """Move delivery i from src to dst, update all state."""
    old = areas[src] + areas[dst]
    invalidate(src, clusters, tls)
    invalidate(dst, clusters, tls)
    clusters[src].remove(i)
    clusters[dst].append(i)
    labels[i] = dst
    sizes[src] -= 1
    sizes[dst] += 1
    areas[src] = hull_area(clusters[src], coords_km, tls)
    areas[dst] = hull_area(clusters[dst], coords_km, tls)
    rebuild_eq(src, clusters, coords_km, tls)
    rebuild_eq(dst, clusters, coords_km, tls)
    update_centroids_batch({src, dst}, labels, coords_km, tls)
    if tls.tl.overlap_mat is not None:
        update_overlap_row(src, clusters, areas, coords_km, num_couriers, tls)
        update_overlap_row(dst, clusters, areas, coords_km, num_couriers, tls)
    if tls.tl.overlap_point is not None:
        tls.tl.overlap_point[i] = False
    return areas[src] + areas[dst] - old


def apply_swap(i: int, j: int,
               labels: np.ndarray, clusters: Dict,
               areas: Dict, sizes: np.ndarray,
               coords_km: np.ndarray, num_couriers: int,
               tls: ThreadLocalState) -> float:
    """Swap deliveries i and j between their couriers if it reduces area."""
    a, b = int(labels[i]), int(labels[j])
    if a == b:
        return 0.0
    a_without_i = [x for x in clusters[a] if x != i]
    b_without_j = [x for x in clusters[b] if x != j]
    
    da = (hull_area(a_without_i + [j], coords_km, tls) +
          hull_area(b_without_j + [i], coords_km, tls) -
          areas[a] - areas[b])
          
    alpha = getattr(tls.tl, 'alpha', 1.0)
    delta_w = getattr(tls.tl, 'delta', 0.0)
    
    delta = alpha * da
    if delta_w > 0.001:
        dc = (compactness(a_without_i + [j], coords_km, tls) + compactness(b_without_j + [i], coords_km, tls)
              - compactness(clusters[a], coords_km, tls) - compactness(clusters[b], coords_km, tls))
        delta -= delta_w * dc * 10.0

    if delta < -1e-9:
        invalidate(a, clusters, tls)
        invalidate(b, clusters, tls)
        clusters[a].remove(i)
        clusters[b].remove(j)
        clusters[a].append(j)
        clusters[b].append(i)
        labels[i] = b
        labels[j] = a
        areas[a] = hull_area(clusters[a], coords_km, tls)
        areas[b] = hull_area(clusters[b], coords_km, tls)
        rebuild_eq(a, clusters, coords_km, tls)
        rebuild_eq(b, clusters, coords_km, tls)
        update_centroids_batch({a, b}, labels, coords_km, tls)
        if tls.tl.overlap_mat is not None:
            update_overlap_row(a, clusters, areas, coords_km, num_couriers, tls)
            update_overlap_row(b, clusters, areas, coords_km, num_couriers, tls)
    return delta


# ═══════════════════════════════════════════════════════════════════════════════
# GREEDY PASS  [V17-2: no elongation check]
# ═══════════════════════════════════════════════════════════════════════════════

def greedy_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                sizes: np.ndarray, coords_km: np.ndarray,
                n_deliveries: int, num_couriers: int,
                min_del: int, max_del: int,
                tls: ThreadLocalState,
                hull_only: bool = False) -> float:
    """Try moving each delivery to a better courier (greedy)."""
    total = 0.0
    order = []
    if hull_only:
        for c in range(num_couriers):
            order.extend(hull_verts(clusters[c], coords_km, tls))
    else:
        order = list(range(n_deliveries))
    random.shuffle(order)

    for i in order:
        src = int(labels[i])
        if sizes[src] <= min_del:
            continue
        best_dst = src
        best_d = 0.0
        for dst in locality_candidates(i, coords_km, num_couriers, tls, n=15):
            dst = int(dst)
            if dst == src or sizes[dst] >= max_del:
                continue
            d = move_delta(i, src, dst, clusters, areas, labels, coords_km, tls)
            if d < best_d:
                best_d = d
                best_dst = dst
        if best_dst != src:
            total += apply_move(i, src, best_dst, labels, clusters, areas, sizes,
                                coords_km, num_couriers, tls)
    return total


def swap_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
              sizes: np.ndarray, coords_km: np.ndarray,
              n_deliveries: int, num_couriers: int,
              tls: ThreadLocalState,
              n_sample: int = 500) -> float:
    """Random hull-vertex pairwise swap attempts."""
    pool = []
    for c in range(num_couriers):
        pool.extend(hull_verts(clusters[c], coords_km, tls))
    cdist_mat = np.linalg.norm(
        tls.tl.centroids[:, None, :] - tls.tl.centroids[None, :, :], axis=2)
    for _ in range(n_sample):
        i = random.choice(pool) if pool and random.random() < 0.6 else random.randint(0, n_deliveries - 1)
        j = random.choice(pool) if pool and random.random() < 0.6 else random.randint(0, n_deliveries - 1)
        if i == j:
            continue
        a, b = int(labels[i]), int(labels[j])
        if a == b:
            continue
        apply_swap(i, j, labels, clusters, areas, sizes, coords_km, num_couriers, tls)
    return 0.0


def converge(labels: np.ndarray, clusters: Dict, areas: Dict,
             sizes: np.ndarray, coords_km: np.ndarray,
             n_deliveries: int, num_couriers: int,
             min_del: int, max_del: int,
             tls: ThreadLocalState,
             max_outer: int = 200) -> float:
    """Alternate greedy + swap until no improvement."""
    total = 0.0
    for _ in range(max_outer):
        d1 = greedy_pass(labels, clusters, areas, sizes, coords_km,
                         n_deliveries, num_couriers, min_del, max_del, tls, hull_only=True)
        d2 = greedy_pass(labels, clusters, areas, sizes, coords_km,
                         n_deliveries, num_couriers, min_del, max_del, tls, hull_only=False)
        swap_pass(labels, clusters, areas, sizes, coords_km,
                  n_deliveries, num_couriers, tls, n_sample=200)
        total += d1 + d2
        if d1 >= -1e-9 and d2 >= -1e-9:
            break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# COMPACTNESS (logging only)
# ═══════════════════════════════════════════════════════════════════════════════

def update_adaptive_compact_threshold(clusters: Dict, coords_km: np.ndarray,
                                      num_couriers: int, compact_adapt_k: float,
                                      tls: ThreadLocalState) -> float:
    vals = [compactness(clusters[c], coords_km, tls)
            for c in range(num_couriers) if len(clusters[c]) >= 3]
    mean_c = float(np.mean(vals)) if vals else 0.20
    thr = compact_adapt_k * mean_c
    tls.tl.adapt_compact_thr = thr
    return thr
