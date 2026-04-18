"""
Cluster initialisers — KMeans, compact, hex-grid, random-perturb.
Section 22 from the original script.
"""

from __future__ import annotations

import math
import random

import numpy as np
from sklearn.cluster import KMeans

from app.utils.cache import ThreadLocalState
from app.utils.spatial import rebuild_centroids, compute_locality_radius, locality_candidates
from app.services.rebalance import rebalance


def init_kmeans(coords_km: np.ndarray, num_couriers: int,
                min_del: int, max_del: int, seed: int = 42) -> np.ndarray:
    km = KMeans(n_clusters=num_couriers, random_state=seed, n_init=30)
    return rebalance(km.fit_predict(coords_km), coords_km, num_couriers, min_del, max_del)


def init_compact(coords_km: np.ndarray, num_couriers: int,
                 min_del: int, max_del: int, seed: int = 42) -> np.ndarray:
    n = len(coords_km)
    km = KMeans(n_clusters=num_couriers, random_state=seed, n_init=30)
    km.fit(coords_km)
    sc = km.cluster_centers_
    labels = np.full(n, -1, dtype=int)
    sizes = np.zeros(num_couriers, dtype=int)
    dn = np.min(np.linalg.norm(coords_km[:, None, :] - sc[None, :, :], axis=2), axis=1)
    for i in np.argsort(dn):
        d2c = np.linalg.norm(sc - coords_km[i], axis=1)
        for c in np.argsort(d2c):
            if sizes[c] < max_del:
                labels[i] = c
                sizes[c] += 1
                break
    for i in np.where(labels == -1)[0]:
        c = int(np.argmin(sizes))
        labels[i] = c
        sizes[c] += 1
    return rebalance(labels, coords_km, num_couriers, min_del, max_del)


def init_greedy_compact(coords_km: np.ndarray, num_couriers: int,
                        min_del: int, max_del: int, seed: int = 42) -> np.ndarray:
    n = len(coords_km)
    np.random.seed(seed)
    random.seed(seed)
    km = KMeans(n_clusters=num_couriers, random_state=seed, n_init=10)
    km.fit(coords_km)
    sc = km.cluster_centers_.copy()
    labels = np.full(n, -1, dtype=int)
    sizes = np.zeros(num_couriers, dtype=int)
    d_nearest = np.min(np.linalg.norm(coords_km[:, None, :] - sc[None, :, :], axis=2), axis=1)
    for i in np.argsort(d_nearest):
        d2c = np.linalg.norm(sc - coords_km[i], axis=1)
        assigned = False
        for c in np.argsort(d2c):
            if sizes[c] >= max_del:
                continue
            labels[i] = c
            sizes[c] += 1
            assigned = True
            break
        if not assigned:
            c = int(np.argmin(sizes))
            labels[i] = c
            sizes[c] += 1
    return rebalance(labels, coords_km, num_couriers, min_del, max_del)


def init_hexgrid(coords_km: np.ndarray, num_couriers: int,
                 min_del: int, max_del: int, seed: int = 42) -> np.ndarray:
    n = len(coords_km)
    np.random.seed(seed)
    random.seed(seed)
    xmin, xmax = coords_km[:, 0].min(), coords_km[:, 0].max()
    ymin, ymax = coords_km[:, 1].min(), coords_km[:, 1].max()
    area_per = ((xmax - xmin) * (ymax - ymin)) / num_couriers
    hex_r = math.sqrt(2.0 * area_per / (3.0 * math.sqrt(3.0)))
    dx = hex_r * math.sqrt(3.0)
    dy = hex_r * 1.5
    pts_hex = []
    row = 0
    y = ymin
    while y <= ymax + dy and len(pts_hex) < num_couriers * 4:
        x_off = (dx / 2.0) if row % 2 == 1 else 0.0
        x = xmin + x_off
        while x <= xmax + dx and len(pts_hex) < num_couriers * 4:
            pts_hex.append([x, y])
            x += dx
        y += dy
        row += 1
    pts_hex = np.array(pts_hex)
    ctr = coords_km.mean(axis=0)
    dists = np.linalg.norm(pts_hex - ctr, axis=1)
    seeds_pts = pts_hex[np.argsort(dists)[:num_couriers]]
    labels = np.full(n, -1, dtype=int)
    sizes = np.zeros(num_couriers, dtype=int)
    dmat = np.linalg.norm(coords_km[:, None, :] - seeds_pts[None, :, :], axis=2)
    for i in np.argsort(dmat.min(axis=1)):
        for c in np.argsort(dmat[i]):
            if sizes[c] < max_del:
                labels[i] = c
                sizes[c] += 1
                break
    for i in np.where(labels == -1)[0]:
        c = int(np.argmin(sizes))
        labels[i] = c
        sizes[c] += 1
    return rebalance(labels, coords_km, num_couriers, min_del, max_del)


def init_random_perturb(base_labels: np.ndarray, coords_km: np.ndarray,
                        num_couriers: int, min_del: int, max_del: int,
                        tls: ThreadLocalState,
                        frac: float = 0.30, seed: int = 0) -> np.ndarray:
    n = len(coords_km)
    random.seed(seed)
    np.random.seed(seed)
    labels = base_labels.copy()
    sizes = np.bincount(labels.clip(min=0), minlength=num_couriers)
    rebuild_centroids(labels, coords_km, num_couriers, tls)
    for i in random.sample(range(n), int(n * frac)):
        src = int(labels[i])
        if sizes[src] - 1 < min_del:
            continue
        for dst in locality_candidates(i, coords_km, num_couriers, tls, n=6):
            dst = int(dst)
            if dst != src and sizes[dst] + 1 <= max_del:
                labels[i] = dst
                sizes[src] -= 1
                sizes[dst] += 1
                break
    return rebalance(labels, coords_km, num_couriers, min_del, max_del)
