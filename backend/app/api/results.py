"""
GET /api/results/{run_id} — full results
GET /api/download/json/{run_id} — downloadable JSON
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.models.run_state import run_manager
from app.models.schemas import OptimizationResponse

router = APIRouter(prefix="/api", tags=["results"])


@router.get("/results/{run_id}")
async def get_results(run_id: str):
    """Get full results for a completed run."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    if run.status == "running":
        return {"run_id": run_id, "status": "running", "message": "Still running..."}
    if run.status == "failed":
        return {"run_id": run_id, "status": "failed", "error": run.error}
    if run.status == "pending":
        return {"run_id": run_id, "status": "pending"}

    r = run.results
    if not r:
        raise HTTPException(500, "Results missing for completed run")

    return {
        "run_id": run_id,
        "status": "completed",
        "config": run.params,
        "baseline_km2": r.get("baseline_area", 0),
        "version": "v17",
        "objective": "pure_area",
        "weights": {
            "alpha": run.params.get("alpha", 0.99),
            "beta": run.params.get("beta", 0.01),
            "gamma": run.params.get("gamma", 0.0),
            "delta": run.params.get("delta", 0.0),
        },
        "area_km2": r["area"],
        "reduction_pct": ((r["baseline_area"] - r["area"]) / r["baseline_area"] * 100)
                          if r.get("baseline_area") else 0,
        "overlap_km2": r.get("overlap", 0),
        "avg_compact": r.get("avg_compact", 0),
        "valid": r.get("valid", False),
        "time_s": r.get("time", 0),
        "workload": r.get("workload", {}),
        "couriers": r.get("couriers", []),
        "convergence_history": r.get("history", []),
        "coords_km": r.get("coords_km", []),
        "center_lat": r.get("center_lat"),
        "center_lon": r.get("center_lon"),
        "labels": r["labels"].tolist() if hasattr(r["labels"], "tolist") else r["labels"],
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/download/json/{run_id}")
async def download_json(run_id: str):
    """Download results as JSON file."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    if run.status != "completed" or not run.results:
        raise HTTPException(400, "Run not completed yet")

    # Build the export JSON matching the original format
    r = run.results
    export = {
        "config": {k: str(v) for k, v in run.params.items()},
        "baseline_km2": r.get("baseline_area", 0),
        "version": "v17",
        "objective": "pure_area",
        "weights": {
            "ALPHA": run.params.get("alpha", 0.99),
            "BETA": run.params.get("beta", 0.01),
            "GAMMA": run.params.get("gamma", 0.0),
            "DELTA": run.params.get("delta", 0.0),
        },
        "strategies": {
            "Multi-Start Hybrid v17": {
                "area_km2": r["area"],
                "reduction_pct": ((r["baseline_area"] - r["area"]) / r["baseline_area"] * 100)
                                  if r.get("baseline_area") else 0,
                "valid": r.get("valid", False),
                "time_s": r.get("time", 0),
                "avg_compact": r.get("avg_compact", 0),
                "overlap_km2": r.get("overlap", 0),
                "workload": r.get("workload", {}),
                "couriers": r.get("couriers", []),
            }
        },
    }

    content = json.dumps(export, indent=2, default=str)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=optimization_{run_id}.json"},
    )
