"""
Simulated Annealing polish — Section 21 from the original script.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

import numpy as np

from app.utils.cache import ThreadLocalState
from app.utils.geometry import hull_area
from app.utils.spatial import locality_candidates
from app.services.moves import (
    move_delta, apply_move, apply_swap, full_cost,
)
from app.services.advanced_moves import area_greedy_vertex_steal


def sa_polish(labels: np.ndarray, clusters: Dict, areas: Dict,
              sizes: np.ndarray, coords_km: np.ndarray,
              n_deliveries: int, num_couriers: int,
              min_del: int, max_del: int,
              steal_n_neighbours: int,
              tls: ThreadLocalState,
              iters: int = 6_000,
              T_start: float = 0.05,
              cool: float = 0.9998,
              progress_cb=None) -> Tuple[np.ndarray, float, List[float]]:
    """
    SA with move and swap operators, periodic vertex steal.
    Returns (best_labels, best_area, history).
    """
    cur = full_cost(areas, clusters, coords_km, tls)
    best_l = labels.copy()
    best_a = cur
    hist: List[float] = []
    T = T_start
    cent = tls.tl.centroids

    for it in range(iters):
        if random.random() < 0.50:
            # Swap
            i = random.randint(0, n_deliveries - 1)
            j = random.randint(0, n_deliveries - 1)
            if i == j or labels[i] == labels[j]:
                T *= cool
                continue
            a, b = int(labels[i]), int(labels[j])
            a_without_i = [x for x in clusters[a] if x != i]
            b_without_j = [x for x in clusters[b] if x != j]
            delta = (hull_area(a_without_i + [j], coords_km, tls) +
                     hull_area(b_without_j + [i], coords_km, tls) -
                     areas[a] - areas[b])
            T_eff = T
            if delta < 0 or random.random() < math.exp(-delta / max(T_eff, 1e-10)):
                apply_swap(i, j, labels, clusters, areas, sizes,
                           coords_km, num_couriers, tls)
                cur += delta
        else:
            # Move
            i = random.randint(0, n_deliveries - 1)
            src = int(labels[i])
            if sizes[src] - 1 < min_del:
                T *= cool
                continue
            cands = locality_candidates(i, coords_km, num_couriers, tls, n=15)
            if not cands:
                T *= cool
                continue
            dst = int(random.choice(cands))
            if dst == src or sizes[dst] + 1 > max_del:
                T *= cool
                continue
            delta = move_delta(i, src, dst, clusters, areas, labels, coords_km, tls)
            T_eff = T
            if delta < 0 or random.random() < math.exp(-delta / max(T_eff, 1e-10)):
                apply_move(i, src, dst, labels, clusters, areas, sizes,
                           coords_km, num_couriers, tls)
                cur += delta
        T *= cool
        if cur < best_a - 1e-9:
            best_a = cur
            best_l = labels.copy()
            hist.append(best_a)

        # Periodic vertex steal
        if it % 500 == 499:
            area_greedy_vertex_steal(labels, clusters, areas, sizes, coords_km,
                                     num_couriers, min_del, max_del,
                                     steal_n_neighbours, tls, n_rounds=1)

        # Progress callback
        if progress_cb and it % 200 == 0:
            progress_cb(phase="SA", iteration=it, total=iters, area=cur, best=best_a)

    return best_l, best_a, hist
