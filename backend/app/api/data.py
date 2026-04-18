"""
POST /api/upload        — upload CSV, validate, return metadata
GET  /api/data/info     — get info about currently loaded data
GET  /api/data/dates    — list available dates & their delivery counts
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import DATA_DIR

router = APIRouter(prefix="/api/data", tags=["data"])
logger = logging.getLogger("courier_optimizer")

REQUIRED_COLUMNS = {"latitude", "longitude", "date"}
OPTIONAL_COLUMNS = {"full_address", "delivery_id", "city", "area", "zone"}


def _get_current_csv() -> Path | None:
    """Find the currently loaded CSV in the data directory."""
    csvs = list(DATA_DIR.glob("*.csv"))
    return csvs[0] if csvs else None


@router.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Upload a CSV file, validate required columns, and return metadata.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")

    # Save to data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / file.filename
    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(500, f"Failed to save file: {e}")

    # Validate
    try:
        df = pd.read_csv(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Failed to parse CSV: {e}")

    columns = set(df.columns.str.lower().str.strip())
    df.columns = df.columns.str.lower().str.strip()

    # Check required columns
    missing = REQUIRED_COLUMNS - columns
    if missing:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            422,
            {
                "message": f"Missing required columns: {', '.join(sorted(missing))}",
                "required": sorted(REQUIRED_COLUMNS),
                "found": sorted(columns),
                "missing": sorted(missing),
            },
        )

    # Check for valid lat/lon data
    df_valid = df.dropna(subset=["latitude", "longitude"])
    n_total = len(df)
    n_valid = len(df_valid)
    n_invalid = n_total - n_valid

    # Get available dates
    dates_info = []
    if "date" in df_valid.columns:
        date_counts = df_valid["date"].value_counts().sort_index()
        for date_val, count in date_counts.items():
            dates_info.append({"date": str(date_val), "count": int(count)})

    found_optional = sorted(OPTIONAL_COLUMNS & columns)

    logger.info(f"Uploaded {file.filename}: {n_total} rows, {n_valid} valid, "
                f"{len(dates_info)} dates")

    return {
        "status": "valid",
        "filename": file.filename,
        "total_rows": n_total,
        "valid_rows": n_valid,
        "invalid_rows": n_invalid,
        "columns": sorted(columns),
        "required_columns": sorted(REQUIRED_COLUMNS),
        "optional_columns_found": found_optional,
        "dates": dates_info,
    }


@router.get("/info")
async def get_data_info():
    """Get info about the currently loaded CSV."""
    csv_path = _get_current_csv()
    if not csv_path:
        return {"status": "no_data", "message": "No CSV uploaded yet"}

    try:
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.lower().str.strip()
    except Exception as e:
        return {"status": "error", "message": f"Failed to read CSV: {e}"}

    columns = set(df.columns)
    missing = REQUIRED_COLUMNS - columns
    df_valid = df.dropna(subset=["latitude", "longitude"]) if "latitude" in columns and "longitude" in columns else df

    dates_info = []
    if "date" in df_valid.columns:
        date_counts = df_valid["date"].value_counts().sort_index()
        for date_val, count in date_counts.items():
            dates_info.append({"date": str(date_val), "count": int(count)})

    return {
        "status": "valid" if not missing else "invalid",
        "filename": csv_path.name,
        "total_rows": len(df),
        "valid_rows": len(df_valid),
        "invalid_rows": len(df) - len(df_valid),
        "columns": sorted(columns),
        "missing_columns": sorted(missing),
        "dates": dates_info,
    }


@router.get("/dates")
async def get_dates():
    """List dates and their delivery counts from the currently loaded CSV."""
    csv_path = _get_current_csv()
    if not csv_path:
        raise HTTPException(404, "No CSV uploaded yet")

    try:
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.lower().str.strip()
    except Exception:
        raise HTTPException(500, "Failed to read CSV")

    df_valid = df.dropna(subset=["latitude", "longitude"])
    if "date" not in df_valid.columns:
        raise HTTPException(422, "CSV has no 'date' column")

    date_counts = df_valid["date"].value_counts().sort_index()
    dates = [{"date": str(d), "count": int(c)} for d, c in date_counts.items()]
    return {"dates": dates, "total_valid": len(df_valid)}
