"""
Core configuration — Pydantic Settings for all optimization parameters.
Maps every CONFIG / weight / LNS / SA / archive constant from the original script.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


# ── paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # courier-optimizer/
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
PRESETS_DIR = DATA_DIR / "presets"


class OptimizerSettings(BaseSettings):
    """All tuneable parameters — loaded from .env, overridable via API."""

    # ── data ──────────────────────────────────────────────────────────────
    data_file: str = Field("address_extraction_results.csv", description="CSV filename inside data/")
    output_dir: str = Field("./data/output", description="Output directory for results")
    target_date: str = Field("2025-10-15", description="Date filter for deliveries")

    # ── fleet ─────────────────────────────────────────────────────────────
    num_couriers: int = Field(20, ge=2, le=100)
    min_per_courier: int = Field(10, ge=1)
    max_per_courier: int = Field(20, ge=1)
    n_deliveries: int = Field(308, ge=4)
    random_seed: int = Field(42)

    # ── objective weights [V17-1] ─────────────────────────────────────────
    alpha: float = Field(1.0, ge=0.0, le=1.0, description="Area weight")
    beta: float = Field(0.0, ge=0.0, le=1.0, description="Overlap weight")
    delta: float = Field(0.0, ge=0.0, le=1.0, description="Compactness penalty")

    # ── compact [V17-7] ──────────────────────────────────────────────────
    compact_w: float = Field(0.1, ge=0.0)
    compact_adapt_k: float = Field(0.20, ge=0.0)

    # ── LNS ──────────────────────────────────────────────────────────────
    locality_r_fac: float = Field(1.2, ge=0.1)
    overlap_w: float = Field(0.1, ge=0.0)

    # ── adaptive destroy [V17-6] ─────────────────────────────────────────
    adapt_window: int = Field(10, ge=1)
    adapt_target_low: float = Field(0.20)
    adapt_target_high: float = Field(0.55)
    adapt_step: float = Field(0.02)
    adapt_frac_min: float = Field(0.15)
    adapt_frac_max: float = Field(0.65)
    boredom_kick_every: int = Field(5, ge=1)

    # ── solution archive ─────────────────────────────────────────────────
    archive_k: int = Field(6, ge=1)
    archive_div_weight: float = Field(0.30)
    archive_crossover_every: int = Field(6, ge=1)
    archive_min_div: float = Field(0.05)

    # ── vertex steal [V17-3] ─────────────────────────────────────────────
    steal_n_neighbours: int = Field(10, ge=1)

    # ── merge-split [V17-4] ──────────────────────────────────────────────
    merge_split_every: int = Field(15, ge=1)
    merge_split_pairs: int = Field(2, ge=1)

    # ── pipeline tuning ──────────────────────────────────────────────────
    lns_iters: int = Field(64, ge=1, description="LNS iterations per variant")
    sa_iters: int = Field(15000, ge=100, description="SA iterations")
    sa_t_start: float = Field(0.05, gt=0.0)
    sa_cool: float = Field(0.9998, gt=0.0, lt=1.0)
    t_lns_start: float = Field(0.02, gt=0.0)

    # ── hull cache ───────────────────────────────────────────────────────
    hull_cache_max: int = Field(12000, ge=100)

    # ── debug ────────────────────────────────────────────────────────────
    debug: bool = Field(False)

    # ── server ───────────────────────────────────────────────────────────
    host: str = Field("0.0.0.0")
    port: int = Field(8000)
    cors_origins: str = Field("http://localhost:5173,http://localhost:3000")

    model_config = {"env_prefix": "COURIER_", "env_file": ".env", "extra": "ignore"}

    def to_config_dict(self) -> dict:
        """Return the subset matching the original CONFIG dict."""
        return {
            "data_file": self.data_file,
            "output_dir": self.output_dir,
            "target_date": self.target_date,
            "num_couriers": self.num_couriers,
            "min_per_courier": self.min_per_courier,
            "max_per_courier": self.max_per_courier,
            "n_deliveries": self.n_deliveries,
            "random_seed": self.random_seed,
        }


# Singleton — created once at startup
settings = OptimizerSettings()
