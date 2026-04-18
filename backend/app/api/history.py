"""
GET /api/history — list of all optimization runs
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.run_state import run_manager
from app.models.schemas import HistoryEntry, HistoryResponse

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history", response_model=HistoryResponse)
async def get_history():
    """List all optimization runs (most recent first)."""
    runs = run_manager.list_runs()
    entries = []
    for run in runs:
        area = None
        reduction = None
        time_s = None
        if run.results:
            area = run.results.get("area")
            ba = run.results.get("baseline_area")
            if ba and area:
                reduction = (ba - area) / ba * 100
            time_s = run.results.get("time")
        entries.append(HistoryEntry(
            run_id=run.run_id,
            status=run.status,
            area_km2=area,
            reduction_pct=reduction,
            num_couriers=run.params.get("num_couriers", 20),
            n_deliveries=run.params.get("n_deliveries", 308),
            time_s=time_s,
            created_at=run.created_at,
            completed_at=run.completed_at,
        ))
    return HistoryResponse(runs=entries)

@router.delete("/history/{run_id}")
async def delete_history(run_id: str):
    """Delete a specific optimization run from history."""
    if run_manager.delete_run(run_id):
        return {"status": "ok", "message": f"Deleted {run_id}"}
    return {"status": "error", "message": "Run not found"}
