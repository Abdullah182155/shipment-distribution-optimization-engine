"""
LRU cache and thread-local state management.
Direct port of the original LRUCache + _tl pattern, made injectable.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Dict, Optional, Set, Tuple

import numpy as np
from scipy.spatial import cKDTree


class LRUCache:
    """Fixed-size LRU cache using OrderedDict — exact original logic."""

    def __init__(self, maxsize: int) -> None:
        self._d: OrderedDict = OrderedDict()
        self._max: int = maxsize

    def get(self, key, default=None):
        if key not in self._d:
            return default
        self._d.move_to_end(key)
        return self._d[key]

    def __contains__(self, key) -> bool:
        return key in self._d

    def __getitem__(self, key):
        self._d.move_to_end(key)
        return self._d[key]

    def __setitem__(self, key, val) -> None:
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = val
        if len(self._d) > self._max:
            self._d.popitem(last=False)

    def pop(self, key, default=None):
        return self._d.pop(key, default)

    def clear(self) -> None:
        self._d.clear()


class ThreadLocalState:
    """
    Thread-local state wrapped in a class.
    Each worker thread gets its own hull cache, centroids, overlap data, etc.
    """

    def __init__(self, hull_cache_max: int = 8000) -> None:
        self._tl = threading.local()
        self._cache_max = hull_cache_max

    def _init(self) -> None:
        if hasattr(self._tl, "initialised"):
            return
        self._tl.hull_cache = LRUCache(self._cache_max)
        self._tl.vert_cache = LRUCache(self._cache_max)
        self._tl.perim_cache = LRUCache(self._cache_max)
        self._tl.eq_cache: Dict[int, Optional[np.ndarray]] = {}
        self._tl.cluster_radius: Dict[int, float] = {}
        self._tl.centroids: Optional[np.ndarray] = None
        self._tl.centroid_tree: Optional[cKDTree] = None
        self._tl.overlap_mat: Optional[np.ndarray] = None
        self._tl.overlap_point: Optional[np.ndarray] = None
        self._tl.hull_vert_set: Dict[int, Set[int]] = {}
        self._tl.max_diameter: Dict[int, float] = {}
        self._tl.locality_radius: float = 2.0
        self._tl.adapt_compact_thr: float = 0.14
        self._tl.initialised = True

    @property
    def tl(self):
        self._init()
        return self._tl

    def get_caches(self) -> Tuple[LRUCache, LRUCache, LRUCache]:
        self._init()
        return self._tl.hull_cache, self._tl.vert_cache, self._tl.perim_cache

    def clear(self) -> None:
        self._init()
        hc, vc, pc = self.get_caches()
        hc.clear()
        vc.clear()
        pc.clear()
        self._tl.eq_cache.clear()
        self._tl.overlap_mat = None
        self._tl.overlap_point = None
        self._tl.hull_vert_set = {}
        self._tl.max_diameter = {}
        self._tl.cluster_radius = {}
        self._tl.centroid_tree = None


def stable_key(indices) -> tuple:
    """Canonical cache key for a set of point indices."""
    return tuple(sorted(indices))
