"""
Run state manager with disk persistence.
Tracks active and completed optimization runs.
Saves completed runs to disk so history survives server restarts.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from app.core.config import BASE_DIR

logger = logging.getLogger("courier_optimizer")

# ── Persistent storage directory ──
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class RunProgress:
    """Mutable progress state for a running optimization."""
    phase: str = "queued"
    progress: float = 0.0            # 0..1
    current_iteration: int = 0
    total_iterations: int = 0
    current_area: Optional[float] = None
    best_area: Optional[float] = None
    logs: List[str] = field(default_factory=list)
    _max_logs: int = 200

    def log(self, msg: str) -> None:
        self.logs.append(msg)
        if len(self.logs) > self._max_logs:
            self.logs = self.logs[-self._max_logs:]

    def update(self, phase: str = None, progress: float = None,
               iteration: int = None, total: int = None,
               area: float = None, best: float = None) -> None:
        if phase is not None:
            self.phase = phase
        if progress is not None:
            self.progress = progress
        if iteration is not None:
            self.current_iteration = iteration
        if total is not None:
            self.total_iterations = total
        if area is not None:
            self.current_area = area
        if best is not None:
            self.best_area = best


@dataclass
class RunState:
    """Complete state for one optimization run."""
    run_id: str
    status: str = "pending"          # pending | running | completed | failed
    params: Dict[str, Any] = field(default_factory=dict)
    progress: RunProgress = field(default_factory=RunProgress)

    # Results (populated on completion)
    results: Optional[Dict[str, Any]] = None
    labels: Optional[np.ndarray] = None
    coords_km: Optional[np.ndarray] = None
    baseline_area: Optional[float] = None
    convergence_history: List[float] = field(default_factory=list)

    # Center coordinates (from data loader)
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    # WebSocket subscribers
    _ws_callbacks: List[Callable] = field(default_factory=list, repr=False)

    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    async def notify_ws(self, data: dict) -> None:
        """Notify all WebSocket subscribers."""
        for cb in list(self._ws_callbacks):
            try:
                await cb(data)
            except Exception:
                self._ws_callbacks.remove(cb)

    # ── Serialization ──

    def to_disk_dict(self) -> dict:
        """Serialize to a JSON-safe dict for disk storage."""
        r = self.results or {}
        return {
            "run_id": self.run_id,
            "status": self.status,
            "params": self.params,
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "baseline_area": self.baseline_area,
            "convergence_history": self.convergence_history,
            "results": {
                "area": r.get("area"),
                "baseline_area": r.get("baseline_area"),
                "overlap": r.get("overlap"),
                "time": r.get("time"),
                "valid": r.get("valid"),
                "avg_compact": r.get("avg_compact"),
                "workload": r.get("workload"),
                "center_lat": r.get("center_lat"),
                "center_lon": r.get("center_lon"),
                "couriers": r.get("couriers", []),
                "coords_km": r.get("coords_km", []),
                "labels": r["labels"].tolist() if isinstance(r.get("labels"), np.ndarray) else r.get("labels", []),
                "history": r.get("history", []),
            } if r else None,
        }

    @classmethod
    def from_disk_dict(cls, data: dict) -> RunState:
        """Reconstruct a RunState from a saved dict."""
        run = cls(
            run_id=data["run_id"],
            status=data.get("status", "completed"),
            params=data.get("params", {}),
        )
        # Center coordinates
        run.center_lat = data.get("center_lat")
        run.center_lon = data.get("center_lon")

        # Timestamps
        for ts_field in ("created_at", "started_at", "completed_at"):
            if data.get(ts_field):
                try:
                    setattr(run, ts_field, datetime.fromisoformat(data[ts_field]))
                except Exception:
                    pass

        run.error = data.get("error")
        run.baseline_area = data.get("baseline_area")
        run.convergence_history = data.get("convergence_history", [])

        # Results
        r = data.get("results")
        if r:
            labels = r.get("labels", [])
            if isinstance(labels, list):
                labels = np.array(labels)
            run.results = r
            run.results["labels"] = labels
            run.labels = labels
            # Ensure center coords propagate into results
            if not r.get("center_lat") and run.center_lat:
                run.results["center_lat"] = run.center_lat
                run.results["center_lon"] = run.center_lon

        # Mark progress as complete for loaded runs
        run.progress = RunProgress(phase="completed", progress=1.0)

        return run


class RunManager:
    """Thread-safe run store with automatic disk persistence."""

    def __init__(self) -> None:
        self._runs: Dict[str, RunState] = {}
        self._lock = threading.Lock()
        self._load_from_disk()

    # ── Disk I/O ──

    def _load_from_disk(self) -> None:
        """Load all saved runs from the runs/ directory on startup."""
        count = 0
        for f in sorted(RUNS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                run = RunState.from_disk_dict(data)
                self._runs[run.run_id] = run
                count += 1
            except Exception as e:
                logger.warning(f"Failed to load run {f.name}: {e}")
        if count:
            logger.info(f"Loaded {count} saved runs from {RUNS_DIR}")

    def _save_to_disk(self, run: RunState) -> None:
        """Save a completed/failed run to disk."""
        if run.status not in ("completed", "failed"):
            return
        try:
            path = RUNS_DIR / f"{run.run_id}.json"
            data = run.to_disk_dict()
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            logger.info(f"Saved run {run.run_id} to {path.name}")
        except Exception as e:
            logger.error(f"Failed to save run {run.run_id}: {e}")

    # ── CRUD ──

    def create_run(self, params: dict) -> RunState:
        run_id = str(uuid.uuid4())[:8]
        run = RunState(run_id=run_id, params=params)
        with self._lock:
            self._runs[run_id] = run
        return run

    def complete_run(self, run: RunState) -> None:
        """Mark a run as done and persist to disk."""
        self._save_to_disk(run)

    def get_run(self, run_id: str) -> Optional[RunState]:
        return self._runs.get(run_id)

    def list_runs(self) -> List[RunState]:
        with self._lock:
            return sorted(self._runs.values(),
                          key=lambda r: r.created_at, reverse=True)

    def get_latest(self) -> Optional[RunState]:
        runs = self.list_runs()
        return runs[0] if runs else None

    def delete_run(self, run_id: str) -> bool:
        """Delete a run from memory and disk."""
        with self._lock:
            run = self._runs.pop(run_id, None)
        if run:
            path = RUNS_DIR / f"{run_id}.json"
            path.unlink(missing_ok=True)
            return True
        return False


# Singleton
run_manager = RunManager()
