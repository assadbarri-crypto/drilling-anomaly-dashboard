"""
well_data_loader.py — load any well's data based on wells.yaml.

Handles:
  - Different date formats (TJ-11 uses 'date_raw', TJ-5/TJ-8 use ISO 'date')
  - Survey CSVs with messy multi-row headers and Latin-1 encoding
  - Per-well caching
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config_loader import load_config, Config, Well


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG = load_config()


# ----------------------------------------------------------------------
# Date parsing (unified for all wells)
# ----------------------------------------------------------------------
def _parse_date_any(s) -> pd.Timestamp:
    """
    Parse dates from multiple sources:
      - ISO:       '2004-05-21'
      - Full:      '21 May 2004', '24 September 2004'
      - Partial:   '24 September'  (assume year from context — fallback 2004)
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return pd.NaT
    s = str(s).strip()
    if not s:
        return pd.NaT

    # Already ISO?
    try:
        return pd.to_datetime(s, format="%Y-%m-%d")
    except Exception:
        pass

    # Full date with month name
    for fmt in ("%d %B %Y", "%d %b %Y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass

    # Partial: "24 September"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s*$", s)
    if m:
        day, month = m.group(1), m.group(2)
        for year in (2003, 2004):  # try likely years
            for fmt in ("%d %B %Y", "%d %b %Y"):
                try:
                    return pd.to_datetime(f"{day} {month} {year}", format=fmt)
                except Exception:
                    pass

    return pd.to_datetime(s, errors="coerce")


# ----------------------------------------------------------------------
# Reports (drilling_reports.csv)
# ----------------------------------------------------------------------
def _load_reports_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Reports CSV not found: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")

    # Normalize date column — pick whichever exists
    if "date" in df.columns:
        df["date"] = df["date"].apply(_parse_date_any)
    elif "date_raw" in df.columns:
        df["date"] = df["date_raw"].apply(_parse_date_any)
    else:
        df["date"] = pd.NaT

    # Normalize anomalies column — ensure it's a Python list
    if "anomalies" in df.columns:
        df["anomalies"] = df["anomalies"].apply(_ensure_list)

    # Make sure has_anomaly is bool
    if "has_anomaly" in df.columns:
        df["has_anomaly"] = df["has_anomaly"].fillna(False).astype(bool)
    else:
        df["has_anomaly"] = df["anomalies"].apply(
            lambda a: bool(a) and a != ["no_anomaly"]
        )

    df = df.sort_values("date", na_position="last").reset_index(drop=True)
    return df


def _ensure_list(v):
    """Convert a stringified list / list / NaN into a Python list."""
    if isinstance(v, list):
        return v
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    s = str(v).strip()
    if not s:
        return []
    # Try literal eval-style parse
    try:
        parsed = eval(s, {"__builtins__": {}}, {})
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    # Comma-separated fallback
    return [p.strip() for p in s.split(",") if p.strip()]


# ----------------------------------------------------------------------
# Survey (survey.csv) — messy multi-row header, Latin-1 encoded
# ----------------------------------------------------------------------
def _load_survey_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None

    try:
        raw = pd.read_csv(
            path,
            encoding="latin-1",
            header=None,
            dtype=str,
            engine="python",
            on_bad_lines="skip",
        )
    except Exception:
        return None

    if raw.empty:
        return None

    # Find the header row: contains 'Inclination' and 'Azimuth'
    header_idx = None
    for i, row in raw.iterrows():
        joined = " ".join(str(x) for x in row.tolist() if pd.notna(x))
        if "Inclination" in joined and "Azimuth" in joined and "Measured" in joined:
            header_idx = i
            break

    if header_idx is None:
        return None

    # Two header rows: header row + units row → skip both
    df = raw.iloc[header_idx + 2:].copy()
    df.columns = [
        "comments", "md", "inclination", "azimuth", "tvd",
        "vs", "ns", "ew", "closure", "closure_az", "dls", "tool_face",
    ] + [f"extra_{i}" for i in range(max(0, len(df.columns) - 12))]

    # Coerce numeric columns
    numeric_cols = ["md", "inclination", "azimuth", "tvd", "vs",
                    "ns", "ew", "closure", "closure_az", "dls"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows without MD
    df = df.dropna(subset=["md"]).reset_index(drop=True)
    return df


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
@lru_cache(maxsize=8)
def load_well_data(well_id: str) -> dict:
    """
    Load and cache a well's data.

    Returns a dict:
      {
        'well':     Well (from config),
        'reports':  pd.DataFrame,
        'survey':   pd.DataFrame | None,
      }
    """
    well = CONFIG.get_well(well_id)
    reports = _load_reports_csv(well.data_path)

    survey = None
    if well.is_deviated and well.survey_path is not None:
        survey = _load_survey_csv(well.survey_path)

    return {"well": well, "reports": reports, "survey": survey}


def clear_cache():
    load_well_data.cache_clear()