"""
Data loading and caching for the dashboard.
"""
from pathlib import Path
from functools import lru_cache
import json
import re
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CSV_PATH = PROCESSED_DIR / "all_reports.csv"
JSON_PATH = PROCESSED_DIR / "all_reports.json"


def _parse_date(date_raw):
    """
    Parse a date string. Handles:
      '24 September 2004'  -> full date
      '24 September'       -> infer year 2004
    """
    if not isinstance(date_raw, str) or not date_raw.strip():
        return pd.NaT

    s = date_raw.strip()

    # Try full date with long month
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass

    # Partial: "24 September" -> assume 2004
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s*$", s)
    if m:
        day, month = m.group(1), m.group(2)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return pd.to_datetime(f"{day} {month} 2004", format=fmt)
            except Exception:
                pass

    return pd.NaT


@lru_cache(maxsize=1)
def load_reports() -> pd.DataFrame:
    """Load all reports as a DataFrame."""
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

    # Parse dates with fallback
    df["date"] = df["date_raw"].apply(_parse_date)

    # Sort: date first, then report_no as fallback
    df = df.sort_values(["date", "report_no"], na_position="last").reset_index(drop=True)
    return df


@lru_cache(maxsize=1)
def load_reports_json() -> list:
    """Load raw JSON (has list fields like anomalies, surveys)."""
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def get_anomaly_counts(df: pd.DataFrame) -> dict:
    """Count occurrences of each anomaly label across all reports."""
    counts = {}
    for a_list in df["anomalies"]:
        try:
            labels = eval(a_list) if isinstance(a_list, str) else a_list
        except Exception:
            labels = []
        if not isinstance(labels, list):
            continue
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
    return counts