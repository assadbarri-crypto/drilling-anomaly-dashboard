"""
parse_well.py — Batch-parse all PDFs in a folder for ONE well.

Reuses the existing 3-stage pipeline:
    parser.extract_report  →  grid_extractor.words_to_rows  →  field_extractor.parse_report

Usage (from project root):
    python scripts/parse_well.py --well TJ05 --input "D:\...\DDRs TJ05" --output "data\wells\TharJath5\drilling_reports.csv"
    python scripts/parse_well.py --well TJ08 --input "D:\...\DDRs TJ08" --output "data\wells\TharJath8\drilling_reports.csv"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

# Make sure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parser import extract_report                      # noqa: E402
from src.field_extractor import parse_report               # noqa: E402
from src.utils import list_pdfs_in, extracted_dir_for      # noqa: E402


# ----------------------------------------------------------------------
# Filename → date parsing (handles TJ-5 and TJ-8 naming variants)
# ----------------------------------------------------------------------
_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "april": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}

def parse_date_from_filename(name: str) -> str | None:
    """
    Extract ISO date from filenames like:
        12_TharJath5_15_Oct_2003.pdf
        33_TharJath8_21_MAY_2004.pdf
        03_TharJath8_21_APRIL_2004.pdf
    Returns 'YYYY-MM-DD' or None.
    """
    stem = Path(name).stem
    m = re.search(r"(\d{1,2})[_\-\s]+([A-Za-z]+)[_\-\s]+(\d{4})", stem)
    if not m:
        return None
    day, month_raw, year = m.groups()
    month = _MONTHS.get(month_raw.lower())
    if not month:
        return None
    return f"{year}-{month}-{int(day):02d}"


# ----------------------------------------------------------------------
# Normalizer for the output CSV — keeps a stable schema across wells
# ----------------------------------------------------------------------
def flatten_for_csv(parsed: dict) -> dict:
    """Turn the nested 'surveys' list into a compact string so CSV stays tabular."""
    row = dict(parsed)
    surveys = row.pop("surveys", None)
    if isinstance(surveys, list):
        row["surveys_json"] = json.dumps(surveys, ensure_ascii=False)
    return row


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Parse all PDFs for one well.")
    ap.add_argument("--well",   required=True, help="Well id (e.g., TJ05)")
    ap.add_argument("--input",  required=True, help="Folder containing PDFs")
    ap.add_argument("--output", required=True, help="Output CSV path")
    args = ap.parse_args()

    input_dir = Path(args.input)
    output_csv = Path(args.output)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    extracted_dir = extracted_dir_for(args.well)

    pdfs = list_pdfs_in(input_dir)
    print(f"\n📂 {args.well}: found {len(pdfs)} PDFs in {input_dir}\n")

    rows: list[dict] = []

    for i, pdf in enumerate(pdfs, 1):
        tag = f"[{i:>2}/{len(pdfs)}]"
        try:
            # Stage 1 — extract text + coordinates
            raw = extract_report(pdf)

            # Save raw JSON (per-well folder)
            raw_out = extracted_dir / f"{pdf.stem}.json"
            raw_out.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Stages 2 & 3 — rows + fields
            parsed = parse_report(raw["text"], raw["words"])

            # Metadata
            parsed["filename"] = pdf.name
            parsed["well_id"] = args.well
            parsed["date"] = parse_date_from_filename(pdf.name)
            parsed["used_ocr"] = raw.get("used_ocr", False)
            parsed["text_quality"] = raw.get("text_quality", "unknown")

            rows.append(flatten_for_csv(parsed))

            status = "OCR" if raw.get("used_ocr") else "TXT"
            print(f"  {tag} {pdf.name:40s}  {status}  date={parsed['date']}")

        except Exception as e:
            print(f"  {tag} {pdf.name:40s}  ❌ FAILED: {e}")
            rows.append({
                "filename": pdf.name,
                "well_id": args.well,
                "date": parse_date_from_filename(pdf.name),
                "parse_error": str(e),
            })

    # Build dataframe with stable column order — union of keys, sorted
    df = pd.DataFrame(rows)
    if "date" in df.columns:
        cols = ["well_id", "filename", "date"] + [
            c for c in df.columns if c not in ("well_id", "filename", "date")
        ]
        df = df[cols]
    df = df.sort_values("date", na_position="last").reset_index(drop=True)

    df.to_csv(output_csv, index=False)
    print(f"\n✅ Wrote {len(df)} rows → {output_csv}")
    print(f"   Columns: {len(df.columns)}")
    print(f"   Dates parsed: {df['date'].notna().sum()} / {len(df)}\n")


if __name__ == "__main__":
    main()