"""Test coordinate extraction on Report 9."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from src.utils import DATA_EXTRACTED
from src.grid_extractor import words_to_rows, row_texts

# Load Report 9
data = json.loads((DATA_EXTRACTED / "09_TharJath_11.json").read_text(encoding="utf-8"))
page0_words = data["words"][0]   # first page

print(f"Total words on page: {len(page0_words)}\n")

# Group into rows
rows = words_to_rows(page0_words)
print(f"Grouped into {len(rows)} rows\n")

# Print first 60 rows so we can see the layout
print("=" * 100)
print("ROW-BY-ROW VIEW OF REPORT 9 (first page)")
print("=" * 100)
for i, row in enumerate(rows[:60]):
    text = " | ".join(f"{w['text']}@{int(w['x0'])}" for w in row)
    print(f"{i:03d}  {text}")