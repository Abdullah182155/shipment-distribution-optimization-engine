"""
JSON export and summary generation — matches the original export_json format.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import numpy as np

from app.utils.cache import ThreadLocalState
from app.utils.geometry import compactness, hull_area, total_overlap
from app.utils.spatial import get_sizes, validate


def build_export_json(results: Dict, baseline_area: float, config: dict,
                      coords_km: np.ndarray, num_couriers: int,
                      min_del: int, max_del: int,
                      tls: ThreadLocalState,
                      weights: dict = None, v17_params: dict = None) -> dict:
    """
    Build the full export dict matching the original export_json output.
    """
    out = {
        "config": {k: str(v) for k, v in config.items()},
        "baseline_km2": float(baseline_area),
        "version": "v17",
        "objective": "pure_area",
        "weights": weights or {},
        "v17_params": v17_params or {},
        "strategies": {},
    }

    for n, d in results.items():
        lb = d["labels"]
        sz = get_sizes(lb, num_couriers)
        c_areas = {c: hull_area(np.where(lb == c)[0].tolist(), coords_km, tls)
                   for c in range(num_couriers)}
        c_clusters = {c: np.where(lb == c)[0].tolist() for c in range(num_couriers)}
        avg_c = float(np.mean([compactness(c_clusters[c], coords_km, tls)
                               for c in range(num_couriers)]))

        couriers = []
        for c in range(num_couriers):
            cpts = coords_km[c_clusters[c]]
            centroid = cpts.mean(axis=0).tolist() if len(cpts) > 0 else [0.0, 0.0]
            couriers.append({
                "courier_id": c + 1,
                "deliveries": c_clusters[c],
                "n_deliveries": len(c_clusters[c]),
                "area_km2": float(c_areas[c]),
                "compactness": float(compactness(c_clusters[c], coords_km, tls)),
                "centroid": centroid,
            })

        out["strategies"][n] = {
            "area_km2": float(d["area"]),
            "reduction_pct": float((baseline_area - d["area"]) / baseline_area * 100),
            "valid": bool(validate(lb, num_couriers, min_del, max_del)),
            "time_s": float(d.get("time", 0)),
            "avg_compact": float(avg_c),
            "overlap_km2": float(d.get("overlap", 0)),
            "workload": {
                "min": int(sz.min()),
                "max": int(sz.max()),
                "mean": float(sz.mean()),
                "std": float(sz.std()),
            },
            "couriers": couriers,
        }

    return out


def save_export_json(export_data: dict, path: str) -> None:
    """Write export dict to file."""
    with open(path, "w") as f:
        json.dump(export_data, f, indent=2)
