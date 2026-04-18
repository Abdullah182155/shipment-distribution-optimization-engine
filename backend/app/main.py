"""
FastAPI application entry point.
Mounts all routers, configures CORS, sets up logging.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import DATA_DIR, LOGS_DIR, PRESETS_DIR, settings
from app.api import optimize, results, parameters, history, ws, data

# ── Logging ──────────────────────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
PRESETS_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "output").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "app.log"),
    ],
)
logger = logging.getLogger("courier_optimizer")

# ── App ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Courier Optimizer v17",
    description="Pure area minimization engine with LNS + SA + advanced geometric moves",
    version="1.0.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────
app.include_router(optimize.router)
app.include_router(results.router)
app.include_router(parameters.router)
app.include_router(history.router)
app.include_router(data.router)
app.include_router(ws.router)


# ── Health ───────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "v17"}


@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("COURIER OPTIMIZER v17 — starting up")
    logger.info(f"  Data dir: {DATA_DIR}")
    logger.info(f"  Logs dir: {LOGS_DIR}")
    logger.info(f"  CORS origins: {origins}")
    logger.info("=" * 60)
