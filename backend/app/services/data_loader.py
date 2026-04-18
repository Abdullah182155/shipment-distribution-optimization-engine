"""
Data loader — reads CSV file, filters by date, builds km-projected coordinates.
Replaces the global `load_data()` from the original script.
Handles case-insensitive column names and optional columns gracefully.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class DeliveryData:
    """Structured output from data loading — no globals needed."""
    df: pd.DataFrame                  # full delivery dataframe
    coords_km: np.ndarray             # (N, 2) projected coordinates
    n_deliveries: int
    center_lat: float
    center_lon: float


def load_data(csv_path: str, target_date: str, n_deliveries: int,
              random_seed: int) -> DeliveryData:
    """
    Load deliveries from CSV, filter by date, project to km coordinates.
    Handles case-insensitive column names. Uses all matching rows from the
    selected date if n_deliveries >= actual count, otherwise samples.
    """
    np.random.seed(random_seed)

    df = pd.read_csv(csv_path)
    # Normalize column names to lowercase
    df.columns = df.columns.str.lower().str.strip()

    df_valid = df.dropna(subset=["latitude", "longitude"]).copy()
    df_target = df_valid[df_valid["date"] == target_date].reset_index(drop=True)

    if len(df_target) == 0:
        # Try matching date as string more flexibly
        df_valid["date"] = df_valid["date"].astype(str).str.strip()
        df_target = df_valid[df_valid["date"] == str(target_date).strip()].reset_index(drop=True)

    if len(df_target) == 0:
        raise ValueError(f"No deliveries found for date '{target_date}'. "
                         f"Available dates: {sorted(df_valid['date'].unique().tolist())}")

    N = n_deliveries
    actual_count = len(df_target)

    if N >= actual_count:
        # Use all deliveries, sample with replacement if needed to reach N
        idx = np.random.choice(actual_count, size=N, replace=True)
    else:
        # Subsample without replacement
        idx = np.random.choice(actual_count, size=N, replace=False)

    # Select columns — handle missing "full_address" gracefully
    available_cols = ["latitude", "longitude"]
    if "full_address" in df_target.columns:
        available_cols = ["full_address"] + available_cols

    dl = df_target.iloc[idx][available_cols].copy().reset_index(drop=True)
    dl["delivery_id"] = range(1, N + 1)

    if "full_address" not in dl.columns:
        dl["full_address"] = [f"Point-{i}" for i in range(1, N + 1)]

    dl["latitude"] += np.random.normal(0, 0.0002, N)
    dl["longitude"] += np.random.normal(0, 0.0002, N)

    clat = dl["latitude"].mean()
    clon = dl["longitude"].mean()
    R = 6371.0

    coords_km = np.array([
        (R * math.radians(r.longitude - clon) * math.cos(math.radians(clat)),
         R * math.radians(r.latitude - clat))
        for _, r in dl.iterrows()
    ])
    # Tiny jitter to avoid degenerate convex hulls
    coords_km += np.random.uniform(-1e-8, 1e-8, coords_km.shape)

    return DeliveryData(
        df=dl,
        coords_km=coords_km,
        n_deliveries=len(dl),
        center_lat=clat,
        center_lon=clon,
    )
