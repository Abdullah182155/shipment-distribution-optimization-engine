"""
POST /api/optimize — start optimization
GET  /api/status/{run_id} — get run progress
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.config import DATA_DIR, settings
from app.models.run_state import RunState, run_manager
from app.models.schemas import (
    OptimizationRequest, RunStartResponse, RunStatusResponse,
)
from app.services.data_loader import load_data
from app.services.optimizer import run_optimization

router = APIRouter(prefix="/api", tags=["optimize"])
logger = logging.getLogger("courier_optimizer")

_executor = ThreadPoolExecutor(max_workers=2)


def _run_in_thread(run: RunState):
    """Execute the optimization synchronously in a background thread."""
    try:
        run.status = "running"
        run.started_at = datetime.utcnow()
        run.progress.phase = "loading_data"

        params = run.params
        data_file = params.get("data_file")
        if not data_file:
            data_file = settings.data_file
        csv_path = DATA_DIR / data_file
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        data = load_data(
            csv_path=str(csv_path),
            target_date=params.get("target_date", settings.target_date),
            n_deliveries=params.get("n_deliveries", settings.n_deliveries),
            random_seed=params.get("random_seed", settings.random_seed),
        )

        run.coords_km = data.coords_km
        run.center_lat = data.center_lat
        run.center_lon = data.center_lon
        run.progress.log(f"Loaded {data.n_deliveries} deliveries (center: {data.center_lat:.4f}, {data.center_lon:.4f})")

        def progress_cb(phase="", iteration=0, total=0, area=0, best=0, **kw):
            run.progress.update(
                phase=phase,
                iteration=iteration,
                total=total,
                area=area,
                best=best,
            )
            if total > 0:
                run.progress.progress = min(iteration / max(total, 1), 1.0)
            run.progress.log(f"[{phase}] iter={iteration}/{total} area={area:.4f}")

        results = run_optimization(
            coords_km=data.coords_km,
            params=params,
            progress_cb=progress_cb,
        )

        # Inject actual center lat/lon into results for map visualization
        results["center_lat"] = data.center_lat
        results["center_lon"] = data.center_lon

        run.results = results
        run.labels = results["labels"]
        run.baseline_area = results["baseline_area"]
        run.convergence_history = results.get("history", [])
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.progress.update(phase="completed", progress=1.0)
        run.progress.log(f"Optimization complete: {results['area']:.4f} km²")
        logger.info(f"Run {run.run_id} completed: {results['area']:.4f} km²")
        
        # Save to disk
        run_manager.complete_run(run)

    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        run.completed_at = datetime.utcnow()
        run.progress.log(f"ERROR: {e}")
        logger.exception(f"Run {run.run_id} failed")
        
        # Save to disk
        run_manager.complete_run(run)


@router.post("/optimize", response_model=RunStartResponse)
async def start_optimization(request: OptimizationRequest):
    """Start a new optimization run in the background."""
    params = request.model_dump()

    data_file = params.get("data_file")
    if not data_file:
        data_file = settings.data_file
    csv_path = DATA_DIR / data_file
    if not csv_path.exists():
        raise HTTPException(404, f"Data file not found: {csv_path.name}. "
                                  f"Place CSV in {DATA_DIR}/")

    run = run_manager.create_run(params)
    logger.info(f"Created run {run.run_id} with params: couriers={params['num_couriers']}, "
                f"deliveries={params['n_deliveries']}")

    # Run in background thread
    _executor.submit(_run_in_thread, run)

    return RunStartResponse(run_id=run.run_id, status="pending",
                            message="Optimization started")


@router.get("/status/{run_id}", response_model=RunStatusResponse)
async def get_status(run_id: str):
    """Get progress for a running or completed optimization."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    return RunStatusResponse(
        run_id=run.run_id,
        status=run.status,
        phase=run.progress.phase,
        progress=run.progress.progress,
        current_iteration=run.progress.current_iteration,
        total_iterations=run.progress.total_iterations,
        current_area=run.progress.current_area,
        best_area=run.progress.best_area,
        elapsed_seconds=run.elapsed_seconds(),
        logs=run.progress.logs[-50:],
    )


@router.get("/status")
async def get_latest_status():
    """Get status of the most recent run."""
    run = run_manager.get_latest()
    if not run:
        return {"status": "no_runs", "message": "No optimization runs yet"}
    return RunStatusResponse(
        run_id=run.run_id,
        status=run.status,
        phase=run.progress.phase,
        progress=run.progress.progress,
        current_iteration=run.progress.current_iteration,
        total_iterations=run.progress.total_iterations,
        current_area=run.progress.current_area,
        best_area=run.progress.best_area,
        elapsed_seconds=run.elapsed_seconds(),
        logs=run.progress.logs[-50:],
    )
