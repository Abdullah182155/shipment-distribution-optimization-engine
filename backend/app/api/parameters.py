"""
GET  /api/parameters — current defaults
PUT  /api/parameters — update defaults
GET  /api/parameters/presets — list saved presets
POST /api/parameters/presets — save preset
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import PRESETS_DIR, settings
from app.models.schemas import OptimizationRequest, ParameterPreset, ParameterUpdate

router = APIRouter(prefix="/api/parameters", tags=["parameters"])


def _ensure_presets_dir():
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
async def get_parameters():
    """Get current default parameters."""
    return OptimizationRequest(
        num_couriers=settings.num_couriers,
        min_per_courier=settings.min_per_courier,
        max_per_courier=settings.max_per_courier,
        n_deliveries=settings.n_deliveries,
        random_seed=settings.random_seed,
        target_date=settings.target_date,
        alpha=settings.alpha,
        beta=settings.beta,
        delta=settings.delta,
        compact_w=settings.compact_w,
        lns_iters=settings.lns_iters,
        sa_iters=settings.sa_iters,
        sa_t_start=settings.sa_t_start,
        sa_cool=settings.sa_cool,
        t_lns_start=settings.t_lns_start,
        adapt_frac_min=settings.adapt_frac_min,
        adapt_frac_max=settings.adapt_frac_max,
        boredom_kick_every=settings.boredom_kick_every,
        steal_n_neighbours=settings.steal_n_neighbours,
        merge_split_every=settings.merge_split_every,
        merge_split_pairs=settings.merge_split_pairs,
        archive_k=settings.archive_k,
    )


@router.put("")
async def update_parameters(update: ParameterUpdate):
    """Update default parameters (in-memory only)."""
    updates = update.model_dump(exclude_none=True)
    for key, val in updates.items():
        if hasattr(settings, key):
            object.__setattr__(settings, key, val)
    return {"status": "ok", "updated": list(updates.keys())}


@router.get("/presets")
async def list_presets():
    """List all saved parameter presets."""
    _ensure_presets_dir()
    presets = []
    for f in PRESETS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            presets.append({
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "filename": f.name,
            })
        except Exception:
            pass
    return {"presets": presets}


@router.post("/presets")
async def save_preset(preset: ParameterPreset):
    """Save a parameter preset to disk."""
    _ensure_presets_dir()
    filename = preset.name.lower().replace(" ", "_") + ".json"
    path = PRESETS_DIR / filename
    data = {
        "name": preset.name,
        "description": preset.description,
        "params": preset.params.model_dump(),
    }
    path.write_text(json.dumps(data, indent=2))
    return {"status": "saved", "filename": filename}


@router.get("/presets/{name}")
async def get_preset(name: str):
    """Load a specific preset."""
    _ensure_presets_dir()
    filename = name.lower().replace(" ", "_") + ".json"
    path = PRESETS_DIR / filename
    if not path.exists():
        raise HTTPException(404, f"Preset '{name}' not found")
    data = json.loads(path.read_text())
    return data
