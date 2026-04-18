"""
Pydantic request / response schemas for every API endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class OptimizationRequest(BaseModel):
    """POST /api/optimize — all tuneable knobs."""

    # fleet
    num_couriers: int = Field(20, ge=2, le=100)
    min_per_courier: int = Field(10, ge=1)
    max_per_courier: int = Field(20, ge=1)
    n_deliveries: int = Field(308, ge=4)
    random_seed: int = Field(42)
    target_date: str = Field("2025-10-15")

    # weights
    alpha: float = Field(0.99, ge=0.0, le=1.0)
    beta: float = Field(0.01, ge=0.0, le=1.0)
    delta: float = Field(0.0, ge=0.0, le=1.0)
    compact_w: float = Field(0.1, ge=0.0)

    # LNS / SA
    lns_iters: int = Field(32, ge=1)
    sa_iters: int = Field(6000, ge=100)
    sa_t_start: float = Field(0.05, gt=0.0)
    sa_cool: float = Field(0.9998, gt=0.0, lt=1.0)
    t_lns_start: float = Field(0.02, gt=0.0)

    # adaptive destroy
    adapt_frac_min: float = Field(0.15)
    adapt_frac_max: float = Field(0.50)
    boredom_kick_every: int = Field(7, ge=1)

    # vertex steal / merge-split
    steal_n_neighbours: int = Field(10, ge=1)
    merge_split_every: int = Field(6, ge=1)
    merge_split_pairs: int = Field(10, ge=1)

    # archive
    archive_k: int = Field(6, ge=1)

    # data file (optional override)
    data_file: Optional[str] = None


class ParameterPreset(BaseModel):
    """Named parameter preset for save/load."""
    name: str
    description: str = ""
    params: OptimizationRequest


class ParameterUpdate(BaseModel):
    """PUT /api/parameters — partial update."""
    num_couriers: Optional[int] = None
    min_per_courier: Optional[int] = None
    max_per_courier: Optional[int] = None
    n_deliveries: Optional[int] = None
    random_seed: Optional[int] = None
    target_date: Optional[str] = None
    alpha: Optional[float] = None
    beta: Optional[float] = None
    delta: Optional[float] = None
    compact_w: Optional[float] = None
    lns_iters: Optional[int] = None
    sa_iters: Optional[int] = None
    adapt_frac_min: Optional[float] = None
    adapt_frac_max: Optional[float] = None
    steal_n_neighbours: Optional[int] = None
    merge_split_every: Optional[int] = None
    merge_split_pairs: Optional[int] = None
    archive_k: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class CourierResult(BaseModel):
    """Per-courier metrics in the final solution."""
    courier_id: int
    deliveries: List[int]
    n_deliveries: int
    area_km2: float
    compactness: float
    hull_vertices: List[List[float]] = Field(default_factory=list,
        description="[[x,y], ...] of hull boundary in km coords")
    centroid: List[float] = Field(default_factory=list,
        description="[x, y] centroid in km coords")


class WorkloadStats(BaseModel):
    min: int
    max: int
    mean: float
    std: float


class StrategyResult(BaseModel):
    area_km2: float
    reduction_pct: float
    valid: bool
    time_s: float
    avg_compact: float
    overlap_km2: float
    workload: WorkloadStats
    couriers: List[CourierResult]


class OptimizationResponse(BaseModel):
    """Full results returned by GET /api/results/{run_id}."""
    run_id: str
    status: str  # "pending" | "running" | "completed" | "failed"
    config: Dict[str, Any] = Field(default_factory=dict)
    baseline_km2: Optional[float] = None
    version: str = "v17"
    objective: str = "pure_area"
    weights: Dict[str, float] = Field(default_factory=dict)
    strategies: Dict[str, StrategyResult] = Field(default_factory=dict)
    convergence_history: List[float] = Field(default_factory=list)
    coords_km: List[List[float]] = Field(default_factory=list,
        description="All delivery point coordinates [[x,y], ...]")
    labels: List[int] = Field(default_factory=list,
        description="Courier assignment per delivery point")
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class RunStatusResponse(BaseModel):
    """GET /api/status/{run_id} — lightweight progress."""
    run_id: str
    status: str
    phase: str = ""
    progress: float = 0.0          # 0..1
    current_iteration: int = 0
    total_iterations: int = 0
    current_area: Optional[float] = None
    best_area: Optional[float] = None
    elapsed_seconds: float = 0.0
    logs: List[str] = Field(default_factory=list)


class RunStartResponse(BaseModel):
    """POST /api/optimize response."""
    run_id: str
    status: str = "pending"
    message: str = "Optimization queued"


class HistoryEntry(BaseModel):
    """GET /api/history item."""
    run_id: str
    status: str
    area_km2: Optional[float] = None
    reduction_pct: Optional[float] = None
    num_couriers: int = 20
    n_deliveries: int = 308
    time_s: Optional[float] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class HistoryResponse(BaseModel):
    runs: List[HistoryEntry]
