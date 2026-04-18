"""
Main optimization orchestrator — hybrid pipeline + multi-start.
Sections 23–24 from the original script, made async-friendly with progress callbacks.
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from app.utils.cache import ThreadLocalState
from app.utils.geometry import (
    hull_area, rebuild_eq, compactness, raw_area,
    rebuild_overlap_matrix, rebuild_overlap_flags,
    full_overlap_rebuild, total_overlap,
)
from app.utils.spatial import (
    rebuild_centroids, compute_locality_radius,
    get_sizes, validate, build_clusters, build_areas,
)
from app.services.moves import (
    full_cost, greedy_pass, swap_pass, converge,
    update_adaptive_compact_threshold,
)
from app.services.advanced_moves import (
    area_greedy_vertex_steal, deoverlap_pass, squeeze_pass,
    shrink_wrap_pass, merge_split_pass, group_moves,
    or_opt_pass, cross_exchange_pass, targeted_overlap_swap_pass,
    voronoi_cleanup_pass, anti_elongation_pass,
    final_voronoi_reassignment,
)
from app.services.lns import (
    AdaptiveDestroy, SolutionArchive, Metrics, lns_iteration,
)
from app.services.sa import sa_polish
from app.services.initializers import (
    init_kmeans, init_compact, init_hexgrid, init_random_perturb,
)

logger = logging.getLogger("courier_optimizer")


class OptimizationContext:
    """Holds all state for one optimization run — replaces all globals."""

    def __init__(self, coords_km: np.ndarray, num_couriers: int,
                 min_del: int, max_del: int, params: dict,
                 progress_cb: Optional[Callable] = None):
        self.coords_km = coords_km
        self.n_deliveries = len(coords_km)
        self.num_couriers = num_couriers
        self.min_del = min_del
        self.max_del = max_del
        self.params = params
        self.progress_cb = progress_cb
        self.tls = ThreadLocalState(hull_cache_max=params.get("hull_cache_max", 8000))
        
        # Inject weights into ThreadLocalState for fast access in geometry functions
        self.tls.tl.alpha = params.get("alpha", 1.0)
        self.tls.tl.beta = params.get("beta", 0.01)
        self.tls.tl.delta = params.get("delta", 0.0)

    def report(self, **kwargs):
        if self.progress_cb:
            self.progress_cb(**kwargs)


def hybrid_pipeline(ctx: OptimizationContext,
                    labels_init: np.ndarray,
                    initial_frac: float = 0.20,
                    lns_iters: int = 32,
                    T_lns_start: float = 0.02,
                    sa_iters: int = 6_000,
                    label: str = "") -> Tuple[np.ndarray, float, List[float]]:
    """Full optimization pipeline for one variant."""
    p = ctx.params
    coords_km = ctx.coords_km
    n_del = ctx.n_deliveries
    nc = ctx.num_couriers
    mn, mx = ctx.min_del, ctx.max_del
    tls = ctx.tls
    steal_k = p.get("steal_n_neighbours", 10)
    merge_pairs = p.get("merge_split_pairs", 10)
    merge_every = p.get("merge_split_every", 6)
    archive_cross_every = p.get("archive_crossover_every", 6)
    locality_fac = p.get("locality_r_fac", 1.2)
    compact_k = p.get("compact_adapt_k", 0.20)

    tls.clear()
    labels = labels_init.copy()
    clusters = build_clusters(labels, nc)
    areas = build_areas(clusters, coords_km, tls)
    sizes = get_sizes(labels, nc)
    rebuild_centroids(labels, coords_km, nc, tls)
    compute_locality_radius(labels, coords_km, nc, locality_fac, tls)
    update_adaptive_compact_threshold(clusters, coords_km, nc, compact_k, tls)
    for c in range(nc):
        rebuild_eq(c, clusters, coords_km, tls)

    metrics = Metrics()
    adapt = AdaptiveDestroy(
        initial_frac=initial_frac,
        adapt_window=p.get("adapt_window", 10),
        adapt_target_low=p.get("adapt_target_low", 0.20),
        adapt_target_high=p.get("adapt_target_high", 0.55),
        adapt_step=p.get("adapt_step", 0.02),
        adapt_frac_min=p.get("adapt_frac_min", 0.15),
        adapt_frac_max=p.get("adapt_frac_max", 0.50),
        boredom_kick_every=p.get("boredom_kick_every", 7),
    )
    archive = SolutionArchive(
        archive_k=p.get("archive_k", 6),
        archive_min_div=p.get("archive_min_div", 0.05),
        archive_div_weight=p.get("archive_div_weight", 0.30),
    )

    # Initial convergence
    converge(labels, clusters, areas, sizes, coords_km, n_del, nc, mn, mx, tls)
    area_greedy_vertex_steal(labels, clusters, areas, sizes, coords_km,
                             nc, mn, mx, steal_k, tls, n_rounds=5)
    logger.info(f"[{label}] After converge+steal: {sum(areas.values()):.4f} km²")

    full_overlap_rebuild(labels, clusters, areas, coords_km, n_del, nc, tls)
    for _ in range(5):
        if deoverlap_pass(labels, clusters, areas, sizes, coords_km,
                          nc, mn, mx, tls) >= -1e-6:
            break

    group_moves(labels, clusters, areas, sizes, coords_km, n_del, nc, mn, mx, tls)
    area_greedy_vertex_steal(labels, clusters, areas, sizes, coords_km,
                             nc, mn, mx, steal_k, tls, n_rounds=5)
    merge_split_pass(labels, clusters, areas, sizes, coords_km,
                     nc, mn, mx, tls, n_pairs=merge_pairs)

    full_overlap_rebuild(labels, clusters, areas, coords_km, n_del, nc, tls)
    compute_locality_radius(labels, coords_km, nc, locality_fac, tls)
    update_adaptive_compact_threshold(clusters, coords_km, nc, compact_k, tls)
    archive.try_add(full_cost(areas, clusters, coords_km, tls), labels)

    # LNS
    lns_accepted = 0
    no_improve = 0
    T_cur = T_lns_start
    max_dry = max(6, lns_iters // 3)

    for lns_round in range(lns_iters):
        # Archive crossover
        if (lns_round > 0 and lns_round % archive_cross_every == 0
                and archive.size() >= 2):
            child = archive.crossover(coords_km, nc, mn, mx, tls)
            if child is not None:
                c_clust = build_clusters(child, nc)
                c_areas = build_areas(c_clust, coords_km, tls)
                c_cost = full_cost(c_areas, c_clust, coords_km, tls)
                if c_cost < full_cost(areas, clusters, coords_km, tls):
                    np.copyto(labels, child)
                    for c in range(nc):
                        clusters[c] = c_clust[c]
                        areas[c] = c_areas[c]
                    np.copyto(sizes, get_sizes(child, nc))
                    rebuild_centroids(labels, coords_km, nc, tls)
                    for c in range(nc):
                        rebuild_eq(c, clusters, coords_km, tls)
                    full_overlap_rebuild(labels, clusters, areas, coords_km, n_del, nc, tls)
                    compute_locality_radius(labels, coords_km, nc, locality_fac, tls)
                    update_adaptive_compact_threshold(clusters, coords_km, nc, compact_k, tls)

        # Periodic merge-split
        if lns_round > 0 and lns_round % merge_every == 0:
            saved = merge_split_pass(labels, clusters, areas, sizes, coords_km,
                                     nc, mn, mx, tls, n_pairs=merge_pairs)
            if saved < -1e-9:
                rebuild_centroids(labels, coords_km, nc, tls)
                full_overlap_rebuild(labels, clusters, areas, coords_km, n_del, nc, tls)

        T_cur = max(0.001, T_cur * 0.93)
        d = lns_iteration(labels, clusters, areas, sizes, coords_km,
                          n_del, nc, mn, mx, tls,
                          destroy_frac=adapt.frac,
                          T_accept=T_cur,
                          metrics=metrics,
                          it=lns_round,
                          adapt=adapt,
                          archive=archive,
                          steal_n_neighbours=steal_k)

        if lns_round % 4 == 0:
            compute_locality_radius(labels, coords_km, nc, locality_fac, tls)
            update_adaptive_compact_threshold(clusters, coords_km, nc, compact_k, tls)

        if d < -1e-9:
            lns_accepted += 1
            no_improve = 0
            if lns_accepted % 3 == 0:
                or_opt_pass(labels, clusters, areas, sizes, coords_km,
                            n_del, nc, mn, mx, tls, chain_len=2, n_tries=150)
                cross_exchange_pass(labels, clusters, areas, sizes, coords_km,
                                    nc, mn, mx, tls, n_pairs=30)
                area_greedy_vertex_steal(labels, clusters, areas, sizes, coords_km,
                                         nc, mn, mx, steal_k, tls, n_rounds=2)
            # Periodic anti-elongation inside LNS
            if lns_round % 8 == 7:
                anti_elongation_pass(labels, clusters, areas, sizes, coords_km,
                                      nc, mn, mx, tls, max_stretch=2.0, n_rounds=3)
        else:
            no_improve += 1
            if no_improve >= max_dry and total_overlap(tls) < 0.01:
                logger.info(f"[{label}] Early LNS exit at round {lns_round}")
                break

        # Progress
        ctx.report(phase=f"LNS ({label})", iteration=lns_round,
                   total=lns_iters, area=sum(areas.values()),
                   best=archive.best_cost() if archive.size() > 0 else sum(areas.values()))

    logger.info(f"[{label}] After LNS ×{lns_round + 1}: area={sum(areas.values()):.4f}")

    group_moves(labels, clusters, areas, sizes, coords_km, n_del, nc, mn, mx, tls)
    full_overlap_rebuild(labels, clusters, areas, coords_km, n_del, nc, tls)
    for _ in range(5):
        if deoverlap_pass(labels, clusters, areas, sizes, coords_km,
                          nc, mn, mx, tls) >= -1e-6:
            break

    shrink_wrap_pass(labels, clusters, areas, sizes, coords_km,
                     nc, mn, mx, steal_k, tls, n_rounds=10)
    squeeze_pass(labels, clusters, areas, sizes, coords_km,
                 nc, mn, mx, tls, max_rounds=8)
    area_greedy_vertex_steal(labels, clusters, areas, sizes, coords_km,
                             nc, mn, mx, steal_k, tls, n_rounds=5)

    # Anti-elongation before mergesplit
    anti_elongation_pass(labels, clusters, areas, sizes, coords_km,
                          nc, mn, mx, tls, max_stretch=2.0, n_rounds=5)

    merge_split_pass(labels, clusters, areas, sizes, coords_km,
                     nc, mn, mx, tls, n_pairs=merge_pairs * 2)

    # SA
    ctx.report(phase=f"SA ({label})", iteration=0, total=sa_iters, area=sum(areas.values()))
    best_l, best_a, hist = sa_polish(
        labels, clusters, areas, sizes, coords_km,
        n_del, nc, mn, mx, steal_k, tls,
        iters=sa_iters,
        T_start=p.get("sa_t_start", 0.05),
        cool=p.get("sa_cool", 0.9998),
        progress_cb=lambda **kw: ctx.report(**kw),
    )

    arch_best_l = archive.best_labels()
    if arch_best_l is not None:
        arch_c = build_clusters(arch_best_l, nc)
        arch_a = build_areas(arch_c, coords_km, tls)
        arch_cost = sum(arch_a.values())
        if arch_cost < best_a:
            best_l = arch_best_l
            best_a = arch_cost

    # Final repair
    rebuild_centroids(best_l, coords_km, nc, tls)
    c2 = build_clusters(best_l, nc)
    a2 = build_areas(c2, coords_km, tls)
    s2 = get_sizes(best_l, nc)
    for c in range(nc):
        rebuild_eq(c, c2, coords_km, tls)
    rebuild_overlap_matrix(c2, a2, coords_km, nc, tls)
    rebuild_overlap_flags(best_l, c2, coords_km, n_del, nc, tls)
    compute_locality_radius(best_l, coords_km, nc, locality_fac, tls)
    update_adaptive_compact_threshold(c2, coords_km, nc, compact_k, tls)

    for _ in range(3):
        if deoverlap_pass(best_l, c2, a2, s2, coords_km, nc, mn, mx, tls) >= -1e-6:
            break
    shrink_wrap_pass(best_l, c2, a2, s2, coords_km, nc, mn, mx, steal_k, tls, n_rounds=6)
    squeeze_pass(best_l, c2, a2, s2, coords_km, nc, mn, mx, tls, max_rounds=5)
    area_greedy_vertex_steal(best_l, c2, a2, s2, coords_km, nc, mn, mx, steal_k, tls, n_rounds=5)
    merge_split_pass(best_l, c2, a2, s2, coords_km, nc, mn, mx, tls, n_pairs=merge_pairs * 2)
    for _ in range(2):
        greedy_pass(best_l, c2, a2, s2, coords_km, n_del, nc, mn, mx, tls, hull_only=True)
        greedy_pass(best_l, c2, a2, s2, coords_km, n_del, nc, mn, mx, tls, hull_only=False)

    # ═══ NUCLEAR CLEANUP: Voronoi from-scratch reassignment ═══
    # Uses optimized centroids, assigns every point to nearest centroid.
    # Guarantees spatial coherence + compact shapes + minimal overlap.
    final_voronoi_reassignment(best_l, c2, a2, s2, coords_km, nc, mn, mx, tls)

    # Post-reassignment: fix boundary overlaps + area tightening
    rebuild_overlap_matrix(c2, a2, coords_km, nc, tls)
    rebuild_overlap_flags(best_l, c2, coords_km, n_del, nc, tls)
    for _ in range(3):
        if deoverlap_pass(best_l, c2, a2, s2, coords_km, nc, mn, mx, tls) >= -1e-6:
            break
    targeted_overlap_swap_pass(best_l, c2, a2, s2, coords_km, nc, mn, mx, tls, n_rounds=5)
    area_greedy_vertex_steal(best_l, c2, a2, s2, coords_km, nc, mn, mx, steal_k, tls, n_rounds=3)
    squeeze_pass(best_l, c2, a2, s2, coords_km, nc, mn, mx, tls, max_rounds=3)
    for _ in range(2):
        greedy_pass(best_l, c2, a2, s2, coords_km, n_del, nc, mn, mx, tls, hull_only=True)
        greedy_pass(best_l, c2, a2, s2, coords_km, n_del, nc, mn, mx, tls, hull_only=False)

    best_a_final = sum(a2.values())
    return best_l, best_a_final, hist + metrics.cost


def run_optimization(coords_km: np.ndarray, params: dict,
                     progress_cb: Optional[Callable] = None) -> Dict[str, Any]:
    """
    Top-level optimization entry point. Runs multi-start hybrid pipeline.
    Returns dict with results, labels, areas, history.
    """
    nc = params.get("num_couriers", 20)
    mn = params.get("min_per_courier", 10)
    mx = params.get("max_per_courier", 20)
    seed = params.get("random_seed", 42)
    lns_n = params.get("lns_iters", 32)
    sa_n = params.get("sa_iters", 6000)

    np.random.seed(seed)
    random.seed(seed)

    ctx = OptimizationContext(coords_km, nc, mn, mx, params, progress_cb)

    if progress_cb:
        progress_cb(phase="Initializing", iteration=0, total=4, area=0, best=0)

    # Create initial solutions
    ctx.tls.clear()
    l_km = init_kmeans(coords_km, nc, mn, mx, seed=42)
    ctx.tls.clear()
    l_cp = init_compact(coords_km, nc, mn, mx, seed=42)
    ctx.tls.clear()
    l_hx = init_hexgrid(coords_km, nc, mn, mx, seed=42)

    rebuild_centroids(l_cp, coords_km, nc, ctx.tls)
    compute_locality_radius(l_cp, coords_km, nc, params.get("locality_r_fac", 1.2), ctx.tls)

    a_km = sum(hull_area(np.where(l_km == c)[0].tolist(), coords_km, ctx.tls) for c in range(nc))
    a_cp = sum(hull_area(np.where(l_cp == c)[0].tolist(), coords_km, ctx.tls) for c in range(nc))
    a_hx = sum(hull_area(np.where(l_hx == c)[0].tolist(), coords_km, ctx.tls) for c in range(nc))

    best_a = min(a_km, a_cp, a_hx)
    if best_a == a_km:
        base_l = l_km
    elif best_a == a_cp:
        base_l = l_cp
    else:
        base_l = l_hx

    rebuild_centroids(base_l, coords_km, nc, ctx.tls)
    compute_locality_radius(base_l, coords_km, nc, params.get("locality_r_fac", 1.2), ctx.tls)
    l_p30 = init_random_perturb(base_l, coords_km, nc, mn, mx, ctx.tls, frac=0.30, seed=123)
    ctx.tls.clear()

    variants = [
        ("Compact  v17", l_cp.copy(), 0.18, lns_n),
        ("KMeans   v17", l_km.copy(), 0.22, lns_n),
        ("HexGrid  v17", l_hx.copy(), 0.18, max(lns_n - 2, 8)),
        ("Perturb30 v17", l_p30, 0.20, max(lns_n - 2, 8)),
    ]

    gbest_l = base_l.copy()
    gbest_a = float("inf")
    gbest_name = ""
    ghist: List[float] = []
    variant_scores: Dict[str, float] = {}
    t0 = time.time()

    if progress_cb:
        progress_cb(phase="Running variants", iteration=0, total=len(variants), area=0, best=0)

    # Run variants (sequentially for simplicity in web context — avoids thread-local issues)
    for vi, (name, init_l, frac, lns_count) in enumerate(variants):
        np.random.seed(hash(name) % (2 ** 31))
        random.seed(hash(name) % (2 ** 31))

        variant_ctx = OptimizationContext(coords_km, nc, mn, mx, params, progress_cb)
        rebuild_centroids(init_l, coords_km, nc, variant_ctx.tls)

        l, a, h = hybrid_pipeline(
            variant_ctx, init_l,
            initial_frac=frac,
            lns_iters=lns_count,
            T_lns_start=params.get("t_lns_start", 0.02),
            sa_iters=sa_n,
            label=name,
        )
        ghist.extend(h)
        variant_scores[name] = float(a)
        if a < gbest_a:
            gbest_a = a
            gbest_l = l.copy()
            gbest_name = name
            logger.info(f"*** New best [{name}]: {gbest_a:.4f} km² ***")

        if progress_cb:
            progress_cb(phase=f"Variant {vi + 1}/{len(variants)}", iteration=vi + 1,
                        total=len(variants), area=gbest_a, best=gbest_a)

    # Compute final metrics
    final_tls = ThreadLocalState()
    rebuild_centroids(gbest_l, coords_km, nc, final_tls)
    fc = build_clusters(gbest_l, nc)
    fa = build_areas(fc, coords_km, final_tls)
    for c in range(nc):
        rebuild_eq(c, fc, coords_km, final_tls)
    rebuild_overlap_matrix(fc, fa, coords_km, nc, final_tls)
    final_overlap = total_overlap(final_tls)
    baseline_area = raw_area(coords_km)

    # Build per-courier results
    from scipy.spatial import ConvexHull
    courier_results = []
    for c in range(nc):
        pts = coords_km[fc[c]]
        centroid = pts.mean(axis=0).tolist() if len(pts) > 0 else [0.0, 0.0]
        hull_pts = []
        if len(pts) >= 3:
            try:
                h = ConvexHull(pts)
                hull_pts = pts[h.vertices].tolist()
            except Exception:
                pass
        courier_results.append({
            "courier_id": c + 1,
            "deliveries": fc[c],
            "n_deliveries": len(fc[c]),
            "area_km2": float(fa[c]),
            "compactness": float(compactness(fc[c], coords_km, final_tls)),
            "hull_vertices": hull_pts,
            "centroid": centroid,
        })

    elapsed = time.time() - t0
    sz = get_sizes(gbest_l, nc)

    return {
        "labels": gbest_l,
        "area": gbest_a,
        "baseline_area": baseline_area,
        "overlap": final_overlap,
        "time": elapsed,
        "history": ghist,
        "valid": validate(gbest_l, nc, mn, mx),
        "coords_km": coords_km.tolist(),
        "couriers": courier_results,
        "workload": {
            "min": int(sz.min()),
            "max": int(sz.max()),
            "mean": float(sz.mean()),
            "std": float(sz.std()),
        },
        "avg_compact": float(np.mean([compactness(fc[c], coords_km, final_tls)
                                       for c in range(nc)])),
        "winning_strategy": gbest_name,
        "variant_scores": variant_scores,
    }
