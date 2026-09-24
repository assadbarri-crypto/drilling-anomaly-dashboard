"""
Batch-run the field extractor on all 44 reports.
Produces:
  - data/processed/all_reports.csv       (one row per report)
  - data/processed/all_reports.json      (list of dicts)
  - data/processed/field_coverage.csv    (how often each field was populated)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import pandas as pd
from tqdm import tqdm

from src.utils import DATA_EXTRACTED, DATA_PROCESSED
from src.field_extractor import parse_report

# ---------------------------------------------------------------
# Load all extracted reports and parse each one
# ---------------------------------------------------------------
json_files = sorted(DATA_EXTRACTED.glob("*.json"))
print(f"Parsing {len(json_files)} reports...\n")

rows = []
for jf in tqdm(json_files, desc="Parsing"):
    data   = json.loads(jf.read_text(encoding="utf-8"))
    parsed = parse_report(data["text"], data.get("words", []))
    parsed["source_file"] = jf.name
    rows.append(parsed)

df = pd.DataFrame(rows)

# ---------------------------------------------------------------
# Save outputs
# ---------------------------------------------------------------
csv_path  = DATA_PROCESSED / "all_reports.csv"
json_path = DATA_PROCESSED / "all_reports.json"

df.to_csv(csv_path, index=False, encoding="utf-8-sig")
json_path.write_text(
    json.dumps(rows, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

# ---------------------------------------------------------------
# Field coverage report
# ---------------------------------------------------------------
n = len(df)
coverage = []
for col in df.columns:
    if col in ("source_file", "summary", "anomaly_evidence", "surveys",
               "bha_description", "mud_type", "well_name", "rig_name",
               "date_raw", "last_bop_test", "last_kick_drill",
               "bit_serial", "bit_make_type", "bit_jets",
               "bit_weight_klbs", "bit_dull_code", "dp_grade",
               "dp_tj_type"):
        continue  # text columns — handled separately

    non_null = df[col].notna().sum()
    coverage.append({
        "field":         col,
        "populated":     non_null,
        "total":         n,
        "coverage_pct":  round(100 * non_null / n, 1),
    })

cov_df = pd.DataFrame(coverage).sort_values("coverage_pct", ascending=False)
cov_path = DATA_PROCESSED / "field_coverage.csv"
cov_df.to_csv(cov_path, index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------
print(f"\n✅ Wrote {csv_path}")
print(f"✅ Wrote {json_path}")
print(f"✅ Wrote {cov_path}\n")

print("=" * 60)
print("FIELD COVERAGE ACROSS ALL 44 REPORTS")
print("=" * 60)
print(cov_df.to_string(index=False))

# Anomaly summary
print("\n" + "=" * 60)
print("ANOMALY SUMMARY")
print("=" * 60)
anomaly_counts = {}
for a_list in df["anomalies"]:
    if isinstance(a_list, list):
        for a in a_list:
            anomaly_counts[a] = anomaly_counts.get(a, 0) + 1
for a, c in sorted(anomaly_counts.items(), key=lambda x: -x[1]):
    print(f"  {a:20s}  {c:3d} reports")

print(f"\nReports with at least one anomaly: {df['has_anomaly'].sum()} / {n}")