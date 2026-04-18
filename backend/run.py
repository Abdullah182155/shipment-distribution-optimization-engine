"""
Uvicorn entry point — run with: python run.py
"""

import os
os.environ["OMP_NUM_THREADS"] = "1"

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
