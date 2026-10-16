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

def parse_date_from_ddr(date_raw: str, default_year: int = 2003) -> str | None:
    """
    Parse a date from the PDF's date_raw field.
    Handles:
        '18 September 2003'  →  2003-09-18
        '22 June'            →  2003-06-22  (uses default_year)
        '22-Jun-03'          →  2003-06-22
        '22 June 2003 Drilling'  →  2003-06-22  (strips trailing text)
    """
    if not date_raw or not isinstance(date_raw, str):
        return None

    s = date_raw.strip()

    # Strip trailing non-date words
    s = re.sub(r"\s+(Drilling|Rig|Report|Well|Field)\b.*$", "",
               s, flags=re.IGNORECASE)
    s = re.sub(r"\s*#\s*\d+\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Try explicit year formats first
    for fmt in ("%d %B %Y", "%d %b %Y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return pd.to_datetime(s, format=fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    # Partial date with year like "September 2003" — no day, skip
    m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", s)
    if m:
        # No day — can't produce a real date. Return None.
        return None

    # Partial date like "22 June" — no year. Use default_year.
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)$", s)
    if m:
        day, month = m.group(1), m.group(2)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return pd.to_datetime(
                    f"{day} {month} {default_year}", format=fmt
                ).strftime("%Y-%m-%d")
            except Exception:
                pass

    # Try pandas fallback
    try:
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return None
    
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

            # Date: try filename first (existing wells), then fall back to
            # the date_raw field extracted from the PDF content
            date_from_filename = parse_date_from_filename(pdf.name)
            if date_from_filename:
                parsed["date"] = date_from_filename
            else:
                date_from_pdf = parsed.get("date_raw", "")
                parsed["date"] = parse_date_from_ddr(date_from_pdf)

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

    # ----------------------------------------------------------------
    # Data-quality pass: fix impossible depth jumps
    # ----------------------------------------------------------------
    df = _clean_depth_typos(df)

    df.to_csv(output_csv, index=False)
    print(f"\n✅ Wrote {len(df)} rows → {output_csv}")
    print(f"   Columns: {len(df.columns)}")
    print(f"   Dates parsed: {df['date'].notna().sum()} / {len(df)}")


# ----------------------------------------------------------------------
# Data-quality helpers
# ----------------------------------------------------------------------
def _clean_depth_typos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect and correct depth typos.

    Rule: within a well, depth should generally increase over time.
    If any report has a depth LARGER than its neighbors AND the drop
    is more than 200 m, it's likely a typo. Replace it with the next
    valid depth (or 0 if no subsequent valid depth exists).

    Also handles the reverse: a single value that's much SMALLER than
    neighbors gets flagged as a typo.
    """
    if "depth_m" not in df.columns or len(df) < 2:
        return df

    df = df.sort_values("date", na_position="last").reset_index(drop=True)
    depth = df["depth_m"].copy().astype(float)
    fixed = 0

    for i in range(len(df)):
        current = depth.iloc[i]
        if pd.isna(current):
            continue

        # Look for neighbors on both sides
        prev_valid = depth.iloc[:i].dropna()
        next_valid = depth.iloc[i + 1:].dropna()

        # ---- Case A: current is HIGHER than next by > 200 m ----
        # (typo producing an unusually large depth)
        if not next_valid.empty:
            next_val = next_valid.iloc[0]
            if current - next_val > 200:
                # Rule 1: row 0 with anomalous depth → assume rig-move day → 0
                if i == 0:
                    replacement = 0.0
                    print(f"   ⚠️  Fixed depth typo at row 0: "
                          f"{current} m → 0.0 m (first report assumed rig-move)")
                else:
                    # Rule 2: mid-sequence typo → use next valid depth
                    replacement = next_val
                    print(f"   ⚠️  Fixed depth typo at row {i}: "
                          f"{current} m → {replacement} m (jump forward)")
                depth.iloc[i] = replacement
                fixed += 1
                continue

        # ---- Case B: current is LOWER than prev by > 200 m ----
        # (typo producing an unusually small depth mid-sequence)
        if not prev_valid.empty:
            prev_val = prev_valid.iloc[-1]
            if prev_val - current > 200:
                # Use the next valid value if available, else prev
                replacement = next_val if not next_valid.empty else prev_val
                print(f"   ⚠️  Fixed depth typo at row {i}: "
                      f"{current} m → {replacement} m (drop)")
                depth.iloc[i] = replacement
                fixed += 1
                continue

    # ----------------------------------------------------------------
    # Fill leading NaNs with 0 (rig-move / pre-spud days)
    # Strategy: find the FIRST row with depth > 0 (actual drilling).
    # Any NaN BEFORE that row is a rig-move day → set to 0.
    # ----------------------------------------------------------------
    # Find first non-zero, non-NaN depth
    first_drilled_idx = None
    for i in range(len(depth)):
        v = depth.iloc[i]
        if pd.notna(v) and v > 0:
            first_drilled_idx = i
            break

    filled_count = 0
    if first_drilled_idx is not None and first_drilled_idx > 0:
        # All rows before the first drilled row should be 0 (or already 0)
        for i in range(first_drilled_idx):
            if pd.isna(depth.iloc[i]):
                depth.iloc[i] = 0.0
                filled_count += 1

    if filled_count > 0:
        print(f"   ✅ Filled {filled_count} leading rig-move day(s) with 0 m")

    df["depth_m"] = depth

    if fixed > 0:
        print(f"   ✅ Corrected {fixed} depth typo(s)")

    return df


if __name__ == "__main__":
    main()