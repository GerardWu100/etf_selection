"""
paths.py
--------
Canonical repository paths shared across pipeline, correlation, and notebook code.

Every stage reads and writes the same root-level ``data/raw`` inputs and keeps
generated artifacts under ``outputs/`` so paths are not re-derived in each module.
"""

from __future__ import annotations

from pathlib import Path

# src/data_pipeline/paths.py -> repository root is two parents up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
SCREEN_CSV = RAW_DATA_DIR / "volume_screen.csv"
PRICE_PARQUET = RAW_DATA_DIR / "daily_close_volume_screened_2016_2025.parquet"
CORRELATION_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "correlation_analysis"
DATA_PIPELINE_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "data_pipeline"
ENV_PATH = PROJECT_ROOT / ".env"
