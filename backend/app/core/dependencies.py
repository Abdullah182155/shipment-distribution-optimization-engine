"""
FastAPI dependency injection — provides settings, run manager, etc.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import OptimizerSettings


@lru_cache
def get_settings() -> OptimizerSettings:
    return OptimizerSettings()
