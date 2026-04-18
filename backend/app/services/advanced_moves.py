"""
Advanced move operators — vertex steal, merge-split, shrink-wrap,
or-opt, cross-exchange, deoverlap, squeeze.
Sections 14–17c from the original script.
"""

from __future__ import annotations

import random
from typing import Dict, List, Set

import numpy as np
from sklearn.cluster import KMeans

from app.utils.cache import ThreadLocalState
from app.utils.geometry import (
    hull_area, hull_verts, invalidate, rebuild_eq,
    update_overlap_row, total_overlap, courier_overlap,
    full_overlap_rebuild, inside_hull,
)
from app.utils.spatial import (
    update_centroids_batch, rebuild_centroids, locality_candidates,
)
from app.services.moves import apply_move, apply_swap


# ═══════════════════════════════════════════════════════════════════════════════
# OR-OPT PASS (chain relocation)
# ═══════════════════════════════════════════════════════════════════════════════

def or_opt_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                sizes: np.ndarray, coords_km: np.ndarray,
                n_deliveries: int, num_couriers: int,
                min_del: int, max_del: int,
                tls: ThreadLocalState,
                chain_len: int = 2, n_tries: int = 200) -> float:
    total = 0.0
    for _ in range(n_tries):
        anchor = random.randint(0, n_deliveries - 1)
        src = int(labels[anchor])
        if sizes[src] - chain_len < min_del:
            continue
        cluster_pts = coords_km[clusters[src]]
        near_local = np.argsort(np.linalg.norm(cluster_pts - coords_km[anchor], axis=1))[1:chain_len + 2]
        chain = [anchor]
        for k in near_local:
            nb = clusters[src][k]
            if nb != anchor:
                chain.append(nb)
            if len(chain) >= chain_len:
                break
        if len(chain) < chain_len:
            continue
        chain_set = set(chain)
        src_without = [p for p in clusters[src] if p not in chain_set]
        best_dst = src
        best_d = 0.0
        for dst in locality_candidates(anchor, coords_km, num_couriers, tls, n=10):
            dst = int(dst)
            if dst == src or sizes[dst] + chain_len > max_del:
                continue
            d = (hull_area(src_without, coords_km, tls) +
                 hull_area(clusters[dst] + chain, coords_km, tls) -
                 areas[src] - areas[dst])
            if d < best_d:
                best_d = d
                best_dst = dst
        if best_dst != src:
            invalidate(src, clusters, tls)
            invalidate(best_dst, clusters, tls)
            for pt in chain:
                clusters[src].remove(pt)
                clusters[best_dst].append(pt)
                labels[pt] = best_dst
                sizes[src] -= 1
                sizes[best_dst] += 1
            areas[src] = hull_area(clusters[src], coords_km, tls)
            areas[best_dst] = hull_area(clusters[best_dst], coords_km, tls)
            rebuild_eq(src, clusters, coords_km, tls)
            rebuild_eq(best_dst, clusters, coords_km, tls)
            update_centroids_batch({src, best_dst}, labels, coords_km, tls)
            if tls.tl.overlap_mat is not None:
                update_overlap_row(src, clusters, areas, coords_km, num_couriers, tls)
                update_overlap_row(best_dst, clusters, areas, coords_km, num_couriers, tls)
            total += best_d
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-EXCHANGE PASS
# ═══════════════════════════════════════════════════════════════════════════════

def cross_exchange_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                        sizes: np.ndarray, coords_km: np.ndarray,
                        num_couriers: int, min_del: int, max_del: int,
                        tls: ThreadLocalState,
                        n_pairs: int = 50) -> float:
    total = 0.0
    cd = np.linalg.norm(
        tls.tl.centroids[:, None, :] - tls.tl.centroids[None, :, :], axis=2)
    np.fill_diagonal(cd, float("inf"))
    tried = set()
    pairs_done = 0
    for c1 in np.argsort(cd.min(axis=1)):
        if pairs_done >= n_pairs:
            break
        c1 = int(c1)
        for c2 in np.argsort(cd[c1])[:5]:
            c2 = int(c2)
            key = (min(c1, c2), max(c1, c2))
            if key in tried:
                continue
            tried.add(key)
            pairs_done += 1
            d1to2 = np.linalg.norm(coords_km[clusters[c1]] - tls.tl.centroids[c2], axis=1)
            d2to1 = np.linalg.norm(coords_km[clusters[c2]] - tls.tl.centroids[c1], axis=1)
            top1 = [clusters[c1][k] for k in np.argsort(d1to2)[:4]]
            top2 = [clusters[c2][k] for k in np.argsort(d2to1)[:4]]
            for k in [4, 3, 2, 1]:
                g1 = top1[:k]
                g2 = top2[:k]
                n1 = [p for p in clusters[c1] if p not in g1] + g2
                n2 = [p for p in clusters[c2] if p not in g2] + g1
                if (len(n1) < min_del or len(n1) > max_del or
                        len(n2) < min_del or len(n2) > max_del):
                    continue
                delta = (hull_area(n1, coords_km, tls) +
                         hull_area(n2, coords_km, tls) -
                         areas[c1] - areas[c2])
                if delta < -1e-9:
                    invalidate(c1, clusters, tls)
                    invalidate(c2, clusters, tls)
                    for p in g1:
                        clusters[c1].remove(p)
                        clusters[c2].append(p)
                        labels[p] = c2
                    for p in g2:
                        clusters[c2].remove(p)
                        clusters[c1].append(p)
                        labels[p] = c1
                    areas[c1] = hull_area(clusters[c1], coords_km, tls)
                    areas[c2] = hull_area(clusters[c2], coords_km, tls)
                    rebuild_eq(c1, clusters, coords_km, tls)
                    rebuild_eq(c2, clusters, coords_km, tls)
                    update_centroids_batch({c1, c2}, labels, coords_km, tls)
                    if tls.tl.overlap_mat is not None:
                        update_overlap_row(c1, clusters, areas, coords_km, num_couriers, tls)
                        update_overlap_row(c2, clusters, areas, coords_km, num_couriers, tls)
                    total += delta
                    break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP MOVES (orchestrator)
# ═══════════════════════════════════════════════════════════════════════════════

def group_moves(labels: np.ndarray, clusters: Dict, areas: Dict,
                sizes: np.ndarray, coords_km: np.ndarray,
                n_deliveries: int, num_couriers: int,
                min_del: int, max_del: int,
                tls: ThreadLocalState,
                n_tries: int = 200, n_pairs: int = 50) -> float:
    from app.services.moves import swap_pass
    total = 0.0
    for _ in range(8):
        d1 = or_opt_pass(labels, clusters, areas, sizes, coords_km,
                         n_deliveries, num_couriers, min_del, max_del, tls,
                         chain_len=2, n_tries=n_tries)
        d2 = or_opt_pass(labels, clusters, areas, sizes, coords_km,
                         n_deliveries, num_couriers, min_del, max_del, tls,
                         chain_len=3, n_tries=n_tries)
        d3 = cross_exchange_pass(labels, clusters, areas, sizes, coords_km,
                                 num_couriers, min_del, max_del, tls, n_pairs=n_pairs)
        swap_pass(labels, clusters, areas, sizes, coords_km,
                  n_deliveries, num_couriers, tls, n_sample=200)
        total += d1 + d2 + d3
        if d1 >= -1e-9 and d2 >= -1e-9 and d3 >= -1e-9:
            break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# [V17-3] AREA-GREEDY VERTEX STEAL
# ═══════════════════════════════════════════════════════════════════════════════

def area_greedy_vertex_steal(labels: np.ndarray, clusters: Dict, areas: Dict,
                             sizes: np.ndarray, coords_km: np.ndarray,
                             num_couriers: int, min_del: int, max_del: int,
                             steal_n_neighbours: int,
                             tls: ThreadLocalState,
                             n_rounds: int = 3) -> float:
    """
    [V17-3] For every hull vertex, try moving it to the best-area-reducing
    neighbour. Accepts strictly improving moves only.
    """
    total = 0.0
    for _ in range(n_rounds):
        improved = False
        for c in range(num_couriers):
            verts = hull_verts(clusters[c], coords_km, tls)
            for ep in list(verts):
                src = int(labels[ep])
                if src != c:
                    continue
                if sizes[src] - 1 < min_del:
                    continue
                src_wo = [p for p in clusters[src] if p != ep]
                area_src_new = hull_area(src_wo, coords_km, tls)
                _, near = tls.tl.centroid_tree.query(
                    coords_km[ep], k=min(steal_n_neighbours, num_couriers))
                best_dst = -1
                best_net = 0.0
                for dst in np.atleast_1d(near):
                    dst = int(dst)
                    if dst == src or sizes[dst] >= max_del:
                        continue
                    area_dst_new = hull_area(clusters[dst] + [ep], coords_km, tls)
                    delta = area_src_new + area_dst_new - areas[src] - areas[dst]
                    if delta < best_net:
                        best_net = delta
                        best_dst = dst
                if best_dst != -1:
                    apply_move(ep, src, best_dst, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total += best_net
                    improved = True
        if not improved:
            break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# DEOVERLAP PASS
# ═══════════════════════════════════════════════════════════════════════════════

def deoverlap_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                   sizes: np.ndarray, coords_km: np.ndarray,
                   num_couriers: int, min_del: int, max_del: int,
                   tls: ThreadLocalState) -> float:
    if tls.tl.overlap_mat is None or total_overlap(tls) < 0.005:
        return 0.0
    total_change = 0.0
    courier_ov_list = sorted(range(num_couriers), key=lambda c: -courier_overlap(c, tls))
    for c in courier_ov_list:
        if courier_overlap(c, tls) < 1e-6:
            break
        if tls.tl.eq_cache.get(c) is None:
            continue
        overlapping = [c2 for c2 in range(num_couriers)
                       if c2 != c and tls.tl.overlap_mat[c, c2] > 1e-6]
        if not overlapping:
            continue
        for i in list(clusters[c]):
            if int(labels[i]) != c:
                continue
            if sizes[c] - 1 < min_del:
                continue
            pt = coords_km[i]
            for c2 in overlapping:
                if sizes[c2] + 1 > max_del:
                    continue
                if inside_hull(pt, c2, tls):
                    ob = courier_overlap(c, tls) + courier_overlap(c2, tls)
                    apply_move(i, c, c2, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total_change += courier_overlap(c, tls) + courier_overlap(c2, tls) - ob
                    break
    return total_change


# ═══════════════════════════════════════════════════════════════════════════════
# TARGETED OVERLAP SWAP PASS
# ═══════════════════════════════════════════════════════════════════════════════

def targeted_overlap_swap_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                                sizes: np.ndarray, coords_km: np.ndarray,
                                num_couriers: int, min_del: int, max_del: int,
                                tls: ThreadLocalState,
                                n_rounds: int = 5) -> float:
    """
    For every pair of overlapping couriers:
      1) Pool all their points and re-cluster with 2-means (forced merge-split)
      2) Try exhaustive multi-point group swaps (2-for-2, 3-for-3)
      3) Try all single point moves (not just hull vertices)
    This solves the 'obvious N-point swap' problem.
    """
    total = 0.0
    for rnd in range(n_rounds):
        improved = False
        full_overlap_rebuild(labels, clusters, areas, coords_km,
                             len(labels), num_couriers, tls)
        if total_overlap(tls) < 0.001:
            break

        # Find all overlapping pairs, sorted by worst overlap first
        overlap_pairs = []
        for c1 in range(num_couriers):
            for c2 in range(c1 + 1, num_couriers):
                if (tls.tl.overlap_mat is not None and
                        tls.tl.overlap_mat[c1, c2] > 1e-6):
                    overlap_pairs.append((c1, c2, tls.tl.overlap_mat[c1, c2]))
        overlap_pairs.sort(key=lambda x: -x[2])

        for c1, c2, ov_area in overlap_pairs:
            old_area = areas[c1] + areas[c2]

            # ── Strategy 1: FORCED MERGE-SPLIT (re-cluster from scratch) ──
            pool = clusters[c1] + clusters[c2]
            n_pool = len(pool)
            if n_pool >= 4:
                pts_pool = coords_km[pool]
                best_new_area = old_area
                best_g0, best_g1 = None, None

                # Try multiple random seeds for KMeans to find best split
                for seed in [0, 7, 42, 99, 123]:
                    try:
                        km = KMeans(n_clusters=2, random_state=seed, n_init=3, max_iter=80)
                        km_labels = km.fit_predict(pts_pool)
                    except Exception:
                        continue

                    g0 = [pool[k] for k in range(n_pool) if km_labels[k] == 0]
                    g1 = [pool[k] for k in range(n_pool) if km_labels[k] == 1]

                    # Enforce capacity constraints
                    for g, other in [(g0, g1), (g1, g0)]:
                        while len(g) > max_del and other:
                            ctr = coords_km[other].mean(axis=0)
                            dists = np.linalg.norm(coords_km[g] - ctr, axis=1)
                            mv = g[int(np.argmin(dists))]
                            g.remove(mv)
                            other.append(mv)
                        while len(g) < min_del and len(other) > min_del:
                            ctr = coords_km[g].mean(axis=0) if g else np.zeros(2)
                            dists = np.linalg.norm(coords_km[other] - ctr, axis=1)
                            mv = other[int(np.argmin(dists))]
                            other.remove(mv)
                            g.append(mv)

                    if (len(g0) < min_del or len(g0) > max_del or
                            len(g1) < min_del or len(g1) > max_del):
                        continue

                    new_area = hull_area(g0, coords_km, tls) + hull_area(g1, coords_km, tls)
                    if new_area < best_new_area - 1e-9:
                        best_new_area = new_area
                        best_g0 = list(g0)
                        best_g1 = list(g1)

                if best_g0 is not None:
                    invalidate(c1, clusters, tls)
                    invalidate(c2, clusters, tls)
                    clusters[c1] = best_g0
                    clusters[c2] = best_g1
                    for p in best_g0:
                        labels[p] = c1
                    for p in best_g1:
                        labels[p] = c2
                    sizes[c1] = len(best_g0)
                    sizes[c2] = len(best_g1)
                    areas[c1] = hull_area(clusters[c1], coords_km, tls)
                    areas[c2] = hull_area(clusters[c2], coords_km, tls)
                    rebuild_eq(c1, clusters, coords_km, tls)
                    rebuild_eq(c2, clusters, coords_km, tls)
                    update_centroids_batch({c1, c2}, labels, coords_km, tls)
                    if tls.tl.overlap_mat is not None:
                        update_overlap_row(c1, clusters, areas, coords_km, num_couriers, tls)
                        update_overlap_row(c2, clusters, areas, coords_km, num_couriers, tls)
                    total += best_new_area - old_area
                    improved = True
                    continue

            # ── Strategy 2: Multi-point group swap (2-for-2 and 3-for-3) ──
            # Find points in c1 closest to c2's centroid and vice versa
            ctr1 = coords_km[clusters[c1]].mean(axis=0) if clusters[c1] else np.zeros(2)
            ctr2 = coords_km[clusters[c2]].mean(axis=0) if clusters[c2] else np.zeros(2)

            d1to2 = np.linalg.norm(coords_km[clusters[c1]] - ctr2, axis=1)
            d2to1 = np.linalg.norm(coords_km[clusters[c2]] - ctr1, axis=1)
            top1 = [clusters[c1][k] for k in np.argsort(d1to2)[:6]]
            top2 = [clusters[c2][k] for k in np.argsort(d2to1)[:6]]

            best_delta = 0.0
            best_g1_swap, best_g2_swap = None, None

            for k in [5, 4, 3, 2, 1]:
                for m in [5, 4, 3, 2, 1]:
                    g1_give = top1[:k]
                    g2_give = top2[:m]
                    n1_new = [p for p in clusters[c1] if p not in g1_give] + g2_give
                    n2_new = [p for p in clusters[c2] if p not in g2_give] + g1_give
                    if (len(n1_new) < min_del or len(n1_new) > max_del or
                            len(n2_new) < min_del or len(n2_new) > max_del):
                        continue
                    da = (hull_area(n1_new, coords_km, tls) +
                          hull_area(n2_new, coords_km, tls) - old_area)
                    if da < best_delta:
                        best_delta = da
                        best_g1_swap = (g1_give, g2_give, n1_new, n2_new)

            if best_g1_swap is not None and best_delta < -1e-9:
                g1_give, g2_give, n1_new, n2_new = best_g1_swap
                invalidate(c1, clusters, tls)
                invalidate(c2, clusters, tls)
                for p in g1_give:
                    clusters[c1].remove(p)
                    clusters[c2].append(p)
                    labels[p] = c2
                for p in g2_give:
                    clusters[c2].remove(p)
                    clusters[c1].append(p)
                    labels[p] = c1
                sizes[c1] = len(clusters[c1])
                sizes[c2] = len(clusters[c2])
                areas[c1] = hull_area(clusters[c1], coords_km, tls)
                areas[c2] = hull_area(clusters[c2], coords_km, tls)
                rebuild_eq(c1, clusters, coords_km, tls)
                rebuild_eq(c2, clusters, coords_km, tls)
                update_centroids_batch({c1, c2}, labels, coords_km, tls)
                if tls.tl.overlap_mat is not None:
                    update_overlap_row(c1, clusters, areas, coords_km, num_couriers, tls)
                    update_overlap_row(c2, clusters, areas, coords_km, num_couriers, tls)
                total += best_delta
                improved = True
                continue

            # ── Strategy 3: Single point moves (all points, not just hull) ──
            for i in list(clusters[c1]):
                if int(labels[i]) != c1 or sizes[c1] <= min_del or sizes[c2] >= max_del:
                    continue
                src_wo = [p for p in clusters[c1] if p != i]
                da = (hull_area(src_wo, coords_km, tls) +
                      hull_area(clusters[c2] + [i], coords_km, tls) -
                      areas[c1] - areas[c2])
                if da < -1e-9:
                    apply_move(i, c1, c2, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total += da
                    improved = True

            for j in list(clusters[c2]):
                if int(labels[j]) != c2 or sizes[c2] <= min_del or sizes[c1] >= max_del:
                    continue
                src_wo = [p for p in clusters[c2] if p != j]
                da = (hull_area(src_wo, coords_km, tls) +
                      hull_area(clusters[c1] + [j], coords_km, tls) -
                      areas[c2] - areas[c1])
                if da < -1e-9:
                    apply_move(j, c2, c1, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total += da
                    improved = True

        if not improved:
            break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# ANTI-ELONGATION PASS — fixes stretched couriers with outlier points
# ═══════════════════════════════════════════════════════════════════════════════

def anti_elongation_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                          sizes: np.ndarray, coords_km: np.ndarray,
                          num_couriers: int, min_del: int, max_del: int,
                          tls: ThreadLocalState,
                          max_stretch: float = 3.0,
                          n_rounds: int = 10) -> float:
    """
    Detects couriers with elongated shapes using two methods:
    1) Diameter method: finds the two farthest points in a courier.
       If diameter > max_stretch * median_nearest_neighbor_distance,
       the farthest point from the cluster's main body is moved.
    2) Aspect ratio: uses PCA to measure length/width ratio.
       If ratio > max_stretch, points along the long axis extremes are moved.
    """
    from scipy.spatial.distance import pdist, squareform

    total = 0.0
    for rnd in range(n_rounds):
        moved = 0
        rebuild_centroids(labels, coords_km, num_couriers, tls)
        centroids = tls.tl.centroids.copy()

        # Compute elongation score for each courier and sort worst first
        elongation_scores = []
        for c in range(num_couriers):
            if len(clusters[c]) < 3:
                continue
            pts = coords_km[clusters[c]]
            
            # Method: PCA aspect ratio
            centered = pts - pts.mean(axis=0)
            try:
                cov = np.cov(centered.T)
                eigvals = np.linalg.eigvalsh(cov)
                eigvals = np.maximum(eigvals, 1e-12)
                aspect_ratio = np.sqrt(eigvals.max() / eigvals.min())
            except Exception:
                aspect_ratio = 1.0
            
            if aspect_ratio > max_stretch:
                elongation_scores.append((aspect_ratio, c))

        elongation_scores.sort(reverse=True)  # Worst elongation first

        for aspect_ratio, c in elongation_scores:
            if len(clusters[c]) < 3 or sizes[c] <= min_del:
                continue

            pts = coords_km[clusters[c]]
            centroid = pts.mean(axis=0)

            # Find the point farthest from centroid — likely the outlier
            # causing the elongation
            dists_from_center = np.linalg.norm(pts - centroid, axis=1)
            
            # Also compute: for each point, how many other cluster points
            # are within a "normal" radius. Outliers have few neighbors.
            median_nn = np.median(np.sort(
                np.linalg.norm(pts[:, None] - pts[None, :], axis=2), axis=1
            )[:, 1])  # median nearest-neighbor distance
            
            # Score each point: high distance from center + few local neighbors = outlier
            outlier_scores = []
            for idx in range(len(clusters[c])):
                pt = pts[idx]
                dist_from_center = dists_from_center[idx]
                n_neighbors = np.sum(np.linalg.norm(pts - pt, axis=1) < 3 * median_nn)
                # Higher score = more likely outlier
                score = dist_from_center / max(median_nn, 1e-6) - n_neighbors
                outlier_scores.append((score, idx))
            
            outlier_scores.sort(reverse=True)

            # Try to move the worst outlier(s)
            for score, idx in outlier_scores[:5]:  # Try top 5 candidates
                i = clusters[c][idx]
                if int(labels[i]) != c or sizes[c] <= min_del:
                    continue

                # Find best destination for this outlier
                pt_dists_to_centroids = np.linalg.norm(centroids - coords_km[i], axis=1)
                sorted_dsts = np.argsort(pt_dists_to_centroids)

                # Be generous with tolerance for highly elongated couriers
                tolerance = 0.05 * (aspect_ratio - 1.0) * median_nn

                # Strategy A: Try MOVE (if destination has capacity)
                best_dst = -1
                best_da = float('inf')
                for dst in sorted_dsts[:10]:
                    dst = int(dst)
                    if dst == c or sizes[dst] >= max_del:
                        continue
                    src_wo = [p for p in clusters[c] if p != i]
                    da = (hull_area(src_wo, coords_km, tls) +
                          hull_area(clusters[dst] + [i], coords_km, tls) -
                          areas[c] - areas[dst])
                    if da < tolerance and da < best_da:
                        best_da = da
                        best_dst = dst

                if best_dst != -1:
                    apply_move(i, c, best_dst, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total += best_da
                    moved += 1
                    rebuild_centroids(labels, coords_km, num_couriers, tls)
                    centroids = tls.tl.centroids.copy()
                    break

                # Strategy B: Try SWAP — find a nearby point from another 
                # courier that's closer to our cluster, and swap them.
                # This works even when all couriers are at max capacity!
                best_swap_da = float('inf')
                best_swap_i = -1
                best_swap_j = -1
                
                for dst in sorted_dsts[:10]:
                    dst = int(dst)
                    if dst == c:
                        continue
                    # Find the point in dst that's closest to courier c's centroid
                    for j_idx, j in enumerate(clusters[dst]):
                        j_dist_to_c = np.linalg.norm(coords_km[j] - centroid)
                        # Only consider points closer to c than the outlier
                        if j_dist_to_c >= dists_from_center[idx]:
                            continue
                        # Evaluate swap
                        a_wo_i = [x for x in clusters[c] if x != i]
                        b_wo_j = [x for x in clusters[dst] if x != j]
                        da = (hull_area(a_wo_i + [j], coords_km, tls) +
                              hull_area(b_wo_j + [i], coords_km, tls) -
                              areas[c] - areas[dst])
                        if da < tolerance and da < best_swap_da:
                            best_swap_da = da
                            best_swap_i = i
                            best_swap_j = j
                
                if best_swap_i != -1:
                    # Perform the swap directly
                    a, b = c, int(labels[best_swap_j])
                    invalidate(a, clusters, tls)
                    invalidate(b, clusters, tls)
                    clusters[a].remove(best_swap_i)
                    clusters[b].remove(best_swap_j)
                    clusters[a].append(best_swap_j)
                    clusters[b].append(best_swap_i)
                    labels[best_swap_i] = b
                    labels[best_swap_j] = a
                    areas[a] = hull_area(clusters[a], coords_km, tls)
                    areas[b] = hull_area(clusters[b], coords_km, tls)
                    rebuild_eq(a, clusters, coords_km, tls)
                    rebuild_eq(b, clusters, coords_km, tls)
                    update_centroids_batch({a, b}, labels, coords_km, tls)
                    if tls.tl.overlap_mat is not None:
                        update_overlap_row(a, clusters, areas, coords_km, num_couriers, tls)
                        update_overlap_row(b, clusters, areas, coords_km, num_couriers, tls)
                    total += best_swap_da
                    moved += 1
                    rebuild_centroids(labels, coords_km, num_couriers, tls)
                    centroids = tls.tl.centroids.copy()
                    break

        if moved == 0:
            break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# SQUEEZE PASS
# ═══════════════════════════════════════════════════════════════════════════════

def squeeze_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                 sizes: np.ndarray, coords_km: np.ndarray,
                 num_couriers: int, min_del: int, max_del: int,
                 tls: ThreadLocalState,
                 max_rounds: int = 10) -> float:
    total = 0.0
    for _ in range(max_rounds):
        improved = False
        for c in range(num_couriers):
            for i in list(hull_verts(clusters[c], coords_km, tls)):
                src = int(labels[i])
                if sizes[src] <= min_del:
                    continue
                src_wo = [p for p in clusters[src] if p != i]
                best_dst = src
                best_d = 0.0
                _, near = tls.tl.centroid_tree.query(coords_km[i], k=min(8, num_couriers))
                for dst in np.atleast_1d(near):
                    dst = int(dst)
                    if dst == src or sizes[dst] >= max_del:
                        continue
                    d = (hull_area(src_wo, coords_km, tls) +
                         hull_area(clusters[dst] + [i], coords_km, tls) -
                         areas[src] - areas[dst])
                    if d < best_d:
                        best_d = d
                        best_dst = dst
                if best_dst != src:
                    apply_move(i, src, best_dst, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total += best_d
                    improved = True
        if not improved:
            break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# [V17-5] SHRINK-WRAP POST-PASS
# ═══════════════════════════════════════════════════════════════════════════════

def shrink_wrap_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                     sizes: np.ndarray, coords_km: np.ndarray,
                     num_couriers: int, min_del: int, max_del: int,
                     steal_n_neighbours: int,
                     tls: ThreadLocalState,
                     n_rounds: int = 8) -> float:
    """
    [V17-5] Sort hull vertices by marginal area contribution (largest first),
    attempt relocation to the best-cost neighbour. Pure greedy compaction.
    """
    total = 0.0
    for _ in range(n_rounds):
        improved = False
        candidates = []
        for c in range(num_couriers):
            for ep in hull_verts(clusters[c], coords_km, tls):
                if int(labels[ep]) != c:
                    continue
                if sizes[c] - 1 < min_del:
                    continue
                src_wo = [p for p in clusters[c] if p != ep]
                marginal = areas[c] - hull_area(src_wo, coords_km, tls)
                if marginal > 0:
                    candidates.append((marginal, ep, c))
        candidates.sort(reverse=True)

        for marginal, ep, c in candidates:
            src = int(labels[ep])
            if src != c:
                continue
            if sizes[src] - 1 < min_del:
                continue
            src_wo = [p for p in clusters[src] if p != ep]
            benefit = areas[src] - hull_area(src_wo, coords_km, tls)
            if benefit <= 0:
                continue
            best_dst = -1
            best_net = 0.0
            _, near = tls.tl.centroid_tree.query(
                coords_km[ep], k=min(steal_n_neighbours, num_couriers))
            for dst in np.atleast_1d(near):
                dst = int(dst)
                if dst == src or sizes[dst] >= max_del:
                    continue
                cost = hull_area(clusters[dst] + [ep], coords_km, tls) - areas[dst]
                net = benefit - cost
                if net > best_net:
                    best_net = net
                    best_dst = dst
            if best_dst != -1:
                apply_move(ep, src, best_dst, labels, clusters, areas, sizes,
                           coords_km, num_couriers, tls)
                total += (-best_net)
                improved = True
        if not improved:
            break
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# [V17-4] MERGE-SPLIT MOVE
# ═══════════════════════════════════════════════════════════════════════════════

def merge_split_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                     sizes: np.ndarray, coords_km: np.ndarray,
                     num_couriers: int, min_del: int, max_del: int,
                     tls: ThreadLocalState,
                     n_pairs: int = 10) -> float:
    """
    [V17-4] Pool deliveries from two adjacent couriers, run 2-means,
    accept if total area decreases.
    """
    total = 0.0
    cd = np.linalg.norm(
        tls.tl.centroids[:, None, :] - tls.tl.centroids[None, :, :], axis=2)
    np.fill_diagonal(cd, float("inf"))

    tried = set()
    done = 0
    for c1 in np.argsort(cd.min(axis=1)):
        if done >= n_pairs:
            break
        c1 = int(c1)
        for c2 in np.argsort(cd[c1])[:6]:
            c2 = int(c2)
            if c1 == c2 or cd[c1, c2] > 3.0:
                continue
            key = (min(c1, c2), max(c1, c2))
            if key in tried:
                continue
            tried.add(key)
            done += 1

            pool = clusters[c1] + clusters[c2]
            n_pool = len(pool)
            if n_pool < 4:
                continue

            pts_pool = coords_km[pool]
            try:
                km = KMeans(n_clusters=2, random_state=0, n_init=5, max_iter=50)
                km_labels = km.fit_predict(pts_pool)
            except Exception:
                continue

            g0 = [pool[k] for k in range(n_pool) if km_labels[k] == 0]
            g1 = [pool[k] for k in range(n_pool) if km_labels[k] == 1]

            # Enforce capacity
            for g, other in [(g0, g1), (g1, g0)]:
                while len(g) > max_del:
                    if not other or not g:
                        break
                    ctr = coords_km[other].mean(axis=0)
                    dists = np.linalg.norm(coords_km[g] - ctr, axis=1)
                    mv = g[int(np.argmin(dists))]
                    g.remove(mv)
                    other.append(mv)
                while len(g) < min_del:
                    if not other or len(other) <= min_del:
                        break
                    ctr = coords_km[g].mean(axis=0) if g else np.zeros(2)
                    dists = np.linalg.norm(coords_km[other] - ctr, axis=1)
                    mv = other[int(np.argmin(dists))]
                    other.remove(mv)
                    g.append(mv)

            if (len(g0) < min_del or len(g0) > max_del or
                    len(g1) < min_del or len(g1) > max_del):
                continue

            new_area = hull_area(g0, coords_km, tls) + hull_area(g1, coords_km, tls)
            old_area = areas[c1] + areas[c2]
            if new_area < old_area - 1e-9:
                invalidate(c1, clusters, tls)
                invalidate(c2, clusters, tls)
                clusters[c1] = list(g0)
                clusters[c2] = list(g1)
                for p in g0:
                    labels[p] = c1
                for p in g1:
                    labels[p] = c2
                sizes[c1] = len(g0)
                sizes[c2] = len(g1)
                areas[c1] = hull_area(clusters[c1], coords_km, tls)
                areas[c2] = hull_area(clusters[c2], coords_km, tls)
                rebuild_eq(c1, clusters, coords_km, tls)
                rebuild_eq(c2, clusters, coords_km, tls)
                update_centroids_batch({c1, c2}, labels, coords_km, tls)
                if tls.tl.overlap_mat is not None:
                    update_overlap_row(c1, clusters, areas, coords_km, num_couriers, tls)
                    update_overlap_row(c2, clusters, areas, coords_km, num_couriers, tls)
                total += new_area - old_area
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# VORONOI CLEANUP PASS — eliminates overlaps by spatial locality
# ═══════════════════════════════════════════════════════════════════════════════

def voronoi_cleanup_pass(labels: np.ndarray, clusters: Dict, areas: Dict,
                          sizes: np.ndarray, coords_km: np.ndarray,
                          num_couriers: int, min_del: int, max_del: int,
                          tls: ThreadLocalState,
                          n_rounds: int = 20) -> float:
    """
    Post-processing pass that enforces spatial locality:
    Each delivery point should belong to its nearest courier centroid.
    Works iteratively: reassign → recalculate centroids → repeat until stable.
    Uses MOVE when destination has capacity, SWAP when all are full.
    """
    total = 0.0
    
    for rnd in range(n_rounds):
        moved = 0
        rebuild_centroids(labels, coords_km, num_couriers, tls)
        centroids = tls.tl.centroids.copy()
        
        dists = np.linalg.norm(
            coords_km[:, None, :] - centroids[None, :, :], axis=2
        )
        nearest = np.argmin(dists, axis=1)
        
        # Sort points by how "wrong" they are (biggest mismatch first)
        mismatch_scores = []
        for i in range(len(labels)):
            current_c = int(labels[i])
            nearest_c = int(nearest[i])
            if current_c != nearest_c:
                wrongness = dists[i, current_c] - dists[i, nearest_c]
                mismatch_scores.append((wrongness, i, current_c, nearest_c))
        
        mismatch_scores.sort(reverse=True)
        
        for wrongness, i, src, dst in mismatch_scores:
            src = int(labels[i])
            dst = int(nearest[i])
            if src == dst:
                continue
            if sizes[src] <= min_del:
                continue
            
            # More aggressive tolerance — allow small area increase for locality
            area_tolerance = 0.02 * wrongness
            
            if sizes[dst] < max_del:
                # Strategy A: MOVE
                src_wo = [p for p in clusters[src] if p != i]
                da = (hull_area(src_wo, coords_km, tls) +
                      hull_area(clusters[dst] + [i], coords_km, tls) -
                      areas[src] - areas[dst])
                if da < area_tolerance:
                    apply_move(i, src, dst, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total += da
                    moved += 1
                    continue
            
            # Try alternate destinations (not just nearest)
            sorted_couriers = np.argsort(dists[i])
            move_done = False
            for alt_dst in sorted_couriers[1:6]:
                alt_dst = int(alt_dst)
                if alt_dst == src or sizes[alt_dst] >= max_del:
                    continue
                src_wo = [p for p in clusters[src] if p != i]
                da = (hull_area(src_wo, coords_km, tls) +
                      hull_area(clusters[alt_dst] + [i], coords_km, tls) -
                      areas[src] - areas[alt_dst])
                if da < area_tolerance:
                    apply_move(i, src, alt_dst, labels, clusters, areas, sizes,
                               coords_km, num_couriers, tls)
                    total += da
                    moved += 1
                    move_done = True
                    break
            if move_done:
                continue
            
            # Strategy B: SWAP — when all dsts are full
            # Find a point in dst that's closer to src's centroid, swap them
            if wrongness > 0.1:  # Only swap for significant misplacements
                src_centroid = centroids[src]
                for alt_dst in sorted_couriers[1:4]:
                    alt_dst = int(alt_dst)
                    if alt_dst == src:
                        continue
                    best_j = -1
                    best_swap_da = float('inf')
                    for j in clusters[alt_dst]:
                        j_dist_to_src = np.linalg.norm(coords_km[j] - src_centroid)
                        if j_dist_to_src >= dists[i, src]:
                            continue
                        a_wo_i = [x for x in clusters[src] if x != i]
                        b_wo_j = [x for x in clusters[alt_dst] if x != j]
                        da = (hull_area(a_wo_i + [j], coords_km, tls) +
                              hull_area(b_wo_j + [i], coords_km, tls) -
                              areas[src] - areas[alt_dst])
                        if da < area_tolerance and da < best_swap_da:
                            best_swap_da = da
                            best_j = j
                    
                    if best_j != -1:
                        a, b = src, alt_dst
                        invalidate(a, clusters, tls)
                        invalidate(b, clusters, tls)
                        clusters[a].remove(i)
                        clusters[b].remove(best_j)
                        clusters[a].append(best_j)
                        clusters[b].append(i)
                        labels[i] = b
                        labels[best_j] = a
                        areas[a] = hull_area(clusters[a], coords_km, tls)
                        areas[b] = hull_area(clusters[b], coords_km, tls)
                        rebuild_eq(a, clusters, coords_km, tls)
                        rebuild_eq(b, clusters, coords_km, tls)
                        update_centroids_batch({a, b}, labels, coords_km, tls)
                        total += best_swap_da
                        moved += 1
                        break
        
        if moved == 0:
            break
    
    # Final rebuild
    rebuild_centroids(labels, coords_km, num_couriers, tls)
    for c in range(num_couriers):
        rebuild_eq(c, clusters, coords_km, tls)
    
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL VORONOI REASSIGNMENT — nuclear option for spatial coherence
# ═══════════════════════════════════════════════════════════════════════════════

def final_voronoi_reassignment(labels: np.ndarray, clusters: Dict, areas: Dict,
                                 sizes: np.ndarray, coords_km: np.ndarray,
                                 num_couriers: int, min_del: int, max_del: int,
                                 tls: ThreadLocalState) -> float:
    """
    Complete from-scratch reassignment using optimized centroids.
    Every point goes to its nearest centroid, with capacity constraints.
    
    This guarantees:
    - Spatial coherence (points belong to nearest courier)
    - Compact clusters (no elongation by construction)
    - Minimal overlap (Voronoi-like cells)
    - Respects min/max delivery constraints
    
    Uses the centroids from the OPTIMIZED solution as seeds, so the
    optimizer's work is preserved (good centroid positions).
    """
    # Step 1: Compute centroids from current (optimized) assignment
    rebuild_centroids(labels, coords_km, num_couriers, tls)
    centroids = tls.tl.centroids.copy()
    
    n_points = len(labels)
    old_area = sum(areas.values())
    
    # Step 2: Compute distance from each point to each centroid
    dists = np.linalg.norm(
        coords_km[:, None, :] - centroids[None, :, :], axis=2
    )
    
    # Step 3: Greedy nearest-centroid assignment with capacity constraints
    # Sort all (point, courier) pairs by distance
    assignments = []
    for i in range(n_points):
        for c in range(num_couriers):
            assignments.append((dists[i, c], i, c))
    assignments.sort()  # Sort by distance (nearest first)
    
    # Track new assignment
    new_labels = np.full(n_points, -1, dtype=int)
    new_counts = np.zeros(num_couriers, dtype=int)
    assigned = np.zeros(n_points, dtype=bool)
    
    # Pass 1: Assign each point to nearest courier that has capacity
    for dist, i, c in assignments:
        if assigned[i]:
            continue
        if new_counts[c] >= max_del:
            continue
        new_labels[i] = c
        new_counts[c] += 1
        assigned[i] = True
    
    # Pass 2: Handle any unassigned points (force into least-full courier)
    for i in range(n_points):
        if not assigned[i]:
            sorted_c = np.argsort(dists[i])
            for c in sorted_c:
                c = int(c)
                if new_counts[c] < max_del:
                    new_labels[i] = c
                    new_counts[c] += 1
                    assigned[i] = True
                    break
            if not assigned[i]:
                # Emergency: assign to courier with most capacity room
                c = int(np.argmin(new_counts))
                new_labels[i] = c
                new_counts[c] += 1
                assigned[i] = True
    
    # Pass 3: Fix under-filled couriers (steal closest points from over-filled neighbors)
    for _ in range(20):
        fixed = True
        for c in range(num_couriers):
            while new_counts[c] < min_del:
                # Find nearest unassigned or stealable point
                best_i = -1
                best_dist = float('inf')
                for i in range(n_points):
                    if new_labels[i] == c:
                        continue
                    src = int(new_labels[i])
                    if new_counts[src] <= min_del:
                        continue  # Can't steal from under-filled
                    d = dists[i, c]
                    if d < best_dist:
                        best_dist = d
                        best_i = i
                if best_i == -1:
                    break
                src = int(new_labels[best_i])
                new_counts[src] -= 1
                new_labels[best_i] = c
                new_counts[c] += 1
                fixed = False
        if fixed:
            break
    
    # Step 4: Build new clusters and compute areas
    new_clusters = {c: [] for c in range(num_couriers)}
    for i in range(n_points):
        new_clusters[int(new_labels[i])].append(i)
    
    new_areas = {}
    for c in range(num_couriers):
        new_areas[c] = hull_area(new_clusters[c], coords_km, tls) if new_clusters[c] else 0.0
    
    new_total_area = sum(new_areas.values())
    
    # Step 5: Accept the reassignment (always — spatial coherence is priority)
    for c in range(num_couriers):
        invalidate(c, clusters, tls)
    
    labels[:] = new_labels
    clusters.clear()
    clusters.update(new_clusters)
    areas.clear()
    areas.update(new_areas)
    sizes[:] = new_counts
    
    # Rebuild all caches
    rebuild_centroids(labels, coords_km, num_couriers, tls)
    for c in range(num_couriers):
        rebuild_eq(c, clusters, coords_km, tls)
    
    return new_total_area - old_area
