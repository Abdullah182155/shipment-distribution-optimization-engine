"""
LNS iteration + Adaptive Destroy + Solution Archive + Metrics.
Sections 18–20 from the original script.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from app.utils.cache import ThreadLocalState
from app.utils.geometry import (
    hull_area, rebuild_eq, invalidate, compactness,
    full_overlap_rebuild, total_overlap, hull_vert_set_cached,
)
from app.utils.spatial import (
    rebuild_centroids, update_centroids_batch, compute_locality_radius,
    locality_candidates, get_sizes, validate, build_clusters, build_areas,
)
from app.services.moves import (
    full_cost, greedy_pass, swap_pass, move_delta, apply_move,
    update_adaptive_compact_threshold,
)
from app.services.advanced_moves import (
    area_greedy_vertex_steal, deoverlap_pass,
)
from app.services.rebalance import rebalance


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Metrics:
    iterations: List[int] = field(default_factory=list)
    total_area: List[float] = field(default_factory=list)
    avg_compact: List[float] = field(default_factory=list)
    total_overlap: List[float] = field(default_factory=list)
    cost: List[float] = field(default_factory=list)
    destroy_frac: List[float] = field(default_factory=list)

    def record(self, it: int, area: float, compact: float,
               overlap: float, cost_val: float, dfrac: float = 0.0) -> None:
        self.iterations.append(it)
        self.total_area.append(area)
        self.avg_compact.append(compact)
        self.total_overlap.append(overlap)
        self.cost.append(cost_val)
        self.destroy_frac.append(dfrac)


# ═══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE DESTROY CONTROLLER [V17-6]
# ═══════════════════════════════════════════════════════════════════════════════

class AdaptiveDestroy:
    def __init__(self, initial_frac: float = 0.20,
                 adapt_window: int = 10,
                 adapt_target_low: float = 0.20,
                 adapt_target_high: float = 0.55,
                 adapt_step: float = 0.02,
                 adapt_frac_min: float = 0.15,
                 adapt_frac_max: float = 0.50,
                 boredom_kick_every: int = 7) -> None:
        self.frac = initial_frac
        self._history: List[int] = []
        self._no_improve: int = 0
        self._kicked: bool = False
        # Params
        self._window = adapt_window
        self._target_low = adapt_target_low
        self._target_high = adapt_target_high
        self._step = adapt_step
        self._frac_min = adapt_frac_min
        self._frac_max = adapt_frac_max
        self._kick_every = boredom_kick_every

    def record(self, accepted: bool) -> None:
        self._history.append(1 if accepted else 0)
        if len(self._history) > self._window:
            self._history.pop(0)
        if accepted:
            self._no_improve = 0
            self._kicked = False
        else:
            self._no_improve += 1

    def update(self) -> float:
        if len(self._history) < self._window:
            return self.frac
        rate = float(sum(self._history)) / len(self._history)
        if rate < self._target_low:
            self.frac = min(self.frac + self._step, self._frac_max)
        elif rate > self._target_high:
            self.frac = max(self.frac - self._step, self._frac_min)
        if self._no_improve >= self._kick_every and not self._kicked:
            self.frac = min(self.frac * 2.0, self._frac_max)
            self._kicked = True
        return self.frac

    @property
    def accept_rate(self) -> float:
        if not self._history:
            return 0.0
        return float(sum(self._history)) / len(self._history)


# ═══════════════════════════════════════════════════════════════════════════════
# SOLUTION ARCHIVE
# ═══════════════════════════════════════════════════════════════════════════════

class SolutionArchive:
    def __init__(self, archive_k: int = 6, archive_min_div: float = 0.05,
                 archive_div_weight: float = 0.30) -> None:
        self._pool: List[Tuple[float, np.ndarray]] = []
        self._k = archive_k
        self._min_div = archive_min_div
        self._div_weight = archive_div_weight

    def _hamming(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.mean(a != b))

    def try_add(self, cost: float, labels: np.ndarray) -> bool:
        labs = labels.copy()
        for _, existing in self._pool:
            if self._hamming(labs, existing) < self._min_div:
                return False
        self._pool.append((cost, labs))
        self._pool.sort(key=lambda x: x[0])
        if len(self._pool) > self._k:
            self._pool.pop()
        return True

    def crossover(self, coords_km: np.ndarray, num_couriers: int,
                  min_del: int, max_del: int,
                  tls: ThreadLocalState) -> Optional[np.ndarray]:
        if len(self._pool) < 2:
            return None
        best_score = -float("inf")
        p1_idx = p2_idx = 0
        for i in range(len(self._pool)):
            for j in range(i + 1, len(self._pool)):
                c1, l1 = self._pool[i]
                c2, l2 = self._pool[j]
                div = self._hamming(l1, l2)
                score = -0.5 * (c1 + c2) + self._div_weight * div
                if score > best_score:
                    best_score = score
                    p1_idx, p2_idx = i, j
        _, labels_a = self._pool[p1_idx]
        _, labels_b = self._pool[p2_idx]
        child = labels_a.copy()
        for c in range(num_couriers):
            pts_a = np.where(labels_a == c)[0]
            pts_b = np.where(labels_b == c)[0]
            if hull_area(pts_b.tolist(), coords_km, tls) < hull_area(pts_a.tolist(), coords_km, tls):
                for i in pts_a:
                    child[i] = labels_b[i]
        child = rebalance(child, coords_km, num_couriers, min_del, max_del)
        if not validate(child, num_couriers, min_del, max_del):
            return None
        # Polish child
        rebuild_centroids(child, coords_km, num_couriers, tls)
        c2_clust = build_clusters(child, num_couriers)
        c2_areas = build_areas(c2_clust, coords_km, tls)
        c2_sizes = get_sizes(child, num_couriers)
        for c in range(num_couriers):
            rebuild_eq(c, c2_clust, coords_km, tls)
        for _ in range(2):
            area_greedy_vertex_steal(child, c2_clust, c2_areas, c2_sizes, coords_km,
                                     num_couriers, min_del, max_del, 10, tls, n_rounds=1)
            greedy_pass(child, c2_clust, c2_areas, c2_sizes, coords_km,
                        len(child), num_couriers, min_del, max_del, tls, hull_only=True)
        return child

    def best_cost(self) -> float:
        return self._pool[0][0] if self._pool else float("inf")

    def best_labels(self) -> Optional[np.ndarray]:
        return self._pool[0][1].copy() if self._pool else None

    def size(self) -> int:
        return len(self._pool)


# ═══════════════════════════════════════════════════════════════════════════════
# LNS ITERATION [V17: pure area, no elongation]
# ═══════════════════════════════════════════════════════════════════════════════

def lns_iteration(labels: np.ndarray, clusters: Dict, areas: Dict,
                  sizes: np.ndarray, coords_km: np.ndarray,
                  n_deliveries: int, num_couriers: int,
                  min_del: int, max_del: int,
                  tls: ThreadLocalState,
                  destroy_frac: float = 0.20,
                  T_accept: float = 0.0,
                  metrics: Optional[Metrics] = None,
                  it: int = 0,
                  adapt: Optional[AdaptiveDestroy] = None,
                  archive: Optional[SolutionArchive] = None,
                  steal_n_neighbours: int = 10,
                  debug: bool = False) -> float:
    cost_before = full_cost(areas, clusters, coords_km, tls)

    base_n = max(8, int(n_deliveries * destroy_frac))
    n_destroy = base_n

    # Score deliveries by marginal area contribution
    scores = np.zeros(n_deliveries)
    for c in range(num_couriers):
        if not clusters[c]:
            continue
        verts_set = hull_vert_set_cached(c, clusters, coords_km, tls)
        for i in clusters[c]:
            s = areas[c] * 0.5
            if i in verts_set:
                without = [p for p in clusters[c] if p != i]
                s += max(areas[c] - hull_area(without, coords_km, tls), 0.0)
            scores[i] = s

    n_greedy = int(n_destroy * 0.75)
    n_random = n_destroy - n_greedy
    top_bad = np.argsort(-scores)[:n_greedy * 3]
    w = scores[top_bad]
    wsum = w.sum()
    if wsum > 1e-9:
        chosen_g = np.random.choice(top_bad, size=min(n_greedy, len(top_bad)),
                                    replace=False, p=w / wsum)
    else:
        chosen_g = top_bad[:n_greedy]
    chosen_r = np.random.choice(n_deliveries, size=n_random, replace=False)
    destroyed = list(set(chosen_g.tolist() + chosen_r.tolist()))[:n_destroy]

    sizes_after = sizes.copy()
    for i in destroyed:
        sizes_after[int(labels[i])] -= 1
    final_destroyed = []
    for i in destroyed:
        c = int(labels[i])
        if sizes_after[c] >= min_del:
            final_destroyed.append(i)
        else:
            sizes_after[c] += 1
    destroyed = final_destroyed
    if not destroyed:
        return 0.0

    # Backup
    labels_bak = labels.copy()
    clusters_bak = {c: list(v) for c, v in clusters.items()}
    areas_bak = dict(areas)
    sizes_bak = sizes.copy()
    om_bak = tls.tl.overlap_mat.copy() if tls.tl.overlap_mat is not None else None
    op_bak = tls.tl.overlap_point.copy() if tls.tl.overlap_point is not None else None

    # Destroy
    affected: Set[int] = set()
    for i in destroyed:
        c = int(labels[i])
        affected.add(c)
        invalidate(c, clusters, tls)
        clusters[c].remove(i)
        sizes[c] -= 1
        labels[i] = -1
    for c in affected:
        areas[c] = hull_area(clusters[c], coords_km, tls)
    update_centroids_batch(affected, labels, coords_km, tls)

    # Regret-based repair
    cost_table: Dict[int, List[Tuple[float, int]]] = {}
    for i in destroyed:
        costs = []
        for c in locality_candidates(i, coords_km, num_couriers, tls, n=18):
            c = int(c)
            if sizes[c] >= max_del:
                continue
            area_cost = hull_area(clusters[c] + [i], coords_km, tls) - areas[c]
            costs.append((area_cost, c))
        costs.sort()
        cost_table[i] = costs

    remaining = list(destroyed)
    while remaining:
        best_reg = -float("inf")
        i_ins = remaining[0]
        c_ins = -1
        for i in remaining:
            costs = [(cst, c) for cst, c in cost_table[i] if sizes[c] < max_del]
            if not costs:
                _, idx_arr = tls.tl.centroid_tree.query(coords_km[i], k=num_couriers)
                for c in np.atleast_1d(idx_arr):
                    if sizes[int(c)] < max_del:
                        i_ins = i
                        c_ins = int(c)
                        best_reg = float("inf")
                        break
                if c_ins != -1:
                    break
                continue
            regret = (costs[2][0] - costs[0][0] if len(costs) >= 3 else
                      (costs[1][0] - costs[0][0] if len(costs) == 2 else 0.0))
            if regret > best_reg:
                best_reg = regret
                i_ins = i
                c_ins = costs[0][1]

        if c_ins == -1:
            c_ins = int(np.argmin(sizes))
        invalidate(c_ins, clusters, tls)
        clusters[c_ins].append(i_ins)
        labels[i_ins] = c_ins
        sizes[c_ins] += 1
        areas[c_ins] = hull_area(clusters[c_ins], coords_km, tls)
        rebuild_eq(c_ins, clusters, coords_km, tls)
        update_centroids_batch({c_ins}, labels, coords_km, tls)
        remaining.remove(i_ins)
        for j in remaining:
            new_costs = []
            for c in locality_candidates(j, coords_km, num_couriers, tls, n=18):
                c = int(c)
                if sizes[c] >= max_del:
                    continue
                area_cost = hull_area(clusters[c] + [j], coords_km, tls) - areas[c]
                new_costs.append((area_cost, c))
            new_costs.sort()
            if new_costs:
                cost_table[j] = new_costs

    if not validate(labels, num_couriers, min_del, max_del):
        lr = rebalance(labels, coords_km, num_couriers, min_del, max_del)
        for c in range(num_couriers):
            clusters[c] = np.where(lr == c)[0].tolist()
            areas[c] = hull_area(clusters[c], coords_km, tls)
        np.copyto(sizes, get_sizes(lr, num_couriers))
        np.copyto(labels, lr)
        rebuild_centroids(labels, coords_km, num_couriers, tls)

    full_overlap_rebuild(labels, clusters, areas, coords_km, n_deliveries, num_couriers, tls)
    for _ in range(3):
        if deoverlap_pass(labels, clusters, areas, sizes, coords_km,
                          num_couriers, min_del, max_del, tls) >= -1e-6:
            break
    area_greedy_vertex_steal(labels, clusters, areas, sizes, coords_km,
                             num_couriers, min_del, max_del, steal_n_neighbours,
                             tls, n_rounds=2)
    for _ in range(3):
        d1 = greedy_pass(labels, clusters, areas, sizes, coords_km,
                         n_deliveries, num_couriers, min_del, max_del, tls, hull_only=True)
        d2 = greedy_pass(labels, clusters, areas, sizes, coords_km,
                         n_deliveries, num_couriers, min_del, max_del, tls, hull_only=False)
        swap_pass(labels, clusters, areas, sizes, coords_km,
                  n_deliveries, num_couriers, tls, n_sample=120)
        if d1 >= -1e-9 and d2 >= -1e-9:
            break

    cost_after = full_cost(areas, clusters, coords_km, tls)
    delta = cost_after - cost_before
    accepted = delta < -1e-9
    if not accepted and T_accept > 0 and delta >= 0:
        accepted = random.random() < math.exp(-delta / T_accept)

    if adapt is not None:
        adapt.record(accepted)
        adapt.update()

    if not accepted:
        np.copyto(labels, labels_bak)
        for c in range(num_couriers):
            clusters[c] = clusters_bak[c]
            areas[c] = areas_bak[c]
        np.copyto(sizes, sizes_bak)
        for c in affected:
            rebuild_eq(c, clusters, coords_km, tls)
        rebuild_centroids(labels, coords_km, num_couriers, tls)
        if om_bak is not None:
            tls.tl.overlap_mat = om_bak
        if op_bak is not None:
            tls.tl.overlap_point = op_bak
        return 0.0

    if archive is not None:
        archive.try_add(cost_after, labels)

    if metrics is not None:
        area_total = sum(areas.values())
        avg_c = float(np.mean([compactness(clusters[c], coords_km, tls)
                               for c in range(num_couriers)]))
        dfrac = adapt.frac if adapt is not None else destroy_frac
        metrics.record(it, area_total, avg_c, total_overlap(tls), cost_after, dfrac)

    return delta
