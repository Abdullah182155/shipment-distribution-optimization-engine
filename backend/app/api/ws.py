"""
WebSocket endpoint for live progress streaming.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.run_state import run_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{run_id}")
async def websocket_progress(websocket: WebSocket, run_id: str):
    """Stream live progress updates for an optimization run."""
    await websocket.accept()

    run = run_manager.get_run(run_id)
    if not run:
        await websocket.send_json({"error": f"Run {run_id} not found"})
        await websocket.close()
        return

    last_log_count = 0
    try:
        while run.status in ("pending", "running"):
            logs = run.progress.logs
            new_logs = logs[last_log_count:]
            last_log_count = len(logs)

            data = {
                "run_id": run_id,
                "status": run.status,
                "phase": run.progress.phase,
                "progress": round(run.progress.progress, 4),
                "current_iteration": run.progress.current_iteration,
                "total_iterations": run.progress.total_iterations,
                "current_area": run.progress.current_area,
                "best_area": run.progress.best_area,
                "elapsed_seconds": round(run.elapsed_seconds(), 1),
                "new_logs": new_logs,
            }
            await websocket.send_json(data)
            await asyncio.sleep(1.0)

        # Send final state
        await websocket.send_json({
            "run_id": run_id,
            "status": run.status,
            "phase": "completed" if run.status == "completed" else run.progress.phase,
            "progress": 1.0 if run.status == "completed" else run.progress.progress,
            "best_area": run.progress.best_area,
            "elapsed_seconds": round(run.elapsed_seconds(), 1),
            "final": True,
        })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
