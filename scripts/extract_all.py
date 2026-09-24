"""
Fast audit: for each PDF, report whether its text layer is usable
or if OCR is needed. Does NOT run OCR (keeps it fast).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import list_pdfs, is_garbled
from src.parser import extract_native

pdfs = list_pdfs()
print(f"Auditing {len(pdfs)} PDFs (native text layer only)...\n")

good, bad = [], []
for pdf_path in pdfs:
    try:
        text = extract_native(pdf_path)
        if is_garbled(text):
            bad.append(pdf_path.name)
        else:
            good.append(pdf_path.name)
    except Exception as e:
        bad.append(f"{pdf_path.name}  (error: {e})")

print(f"✅ Good text layer   : {len(good)}")
for n in good:
    print(f"     {n}")

print(f"\n❌ Garbled / needs OCR: {len(bad)}")
for n in bad:
    print(f"     {n}")