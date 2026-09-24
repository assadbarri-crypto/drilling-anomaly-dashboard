"""
3-tier PDF text extraction:
  Tier 1: native text layer (pdfplumber + pymupdf)
  Tier 2: OCR fallback (paddleocr) if text is garbled
  Tier 3: flag for manual review if OCR confidence is too low
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json
import re

import pdfplumber
import pymupdf  # modern name (replaces deprecated `fitz`)
from paddleocr import PaddleOCR

from src.utils import (
    DATA_EXTRACTED,
    DATA_OCR_CACHE,
    is_garbled,
    TEMPLATE_THARJATH,
    TEMPLATE_UNKNOWN,
)

# ----------------------------------------------------------------------
# Lazy-init OCR (heavy — only load when actually needed)
# ----------------------------------------------------------------------
_OCR = None

def _get_ocr():
    global _OCR
    if _OCR is None:
        # use_angle_cls=True handles slightly rotated scans (common in old PDFs)
        _OCR = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _OCR


# ----------------------------------------------------------------------
# Tier 1 — native text extraction
# ----------------------------------------------------------------------
def extract_native(pdf_path: Path) -> str:
    """Extract text using the PDF's own text layer."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    return "\n".join(text_parts)

#-----------------------------------------------------------------------

def extract_native_words(pdf_path: Path) -> list:
    """
    Extract every word with its bounding box on each page.
    Returns: list of pages, each page is a list of word dicts:
      {'text': '10.4', 'x0': 50.0, 'x1': 80.0, 'top': 100.0, 'bottom': 110.0}
    """
    pages_words = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(
                keep_blank_chars=False,
                use_text_flow=False,
                extra_attrs=["size"],
            )
            pages_words.append(words)
    return pages_words

# ----------------------------------------------------------------------
# Tier 2 — OCR fallback
# ----------------------------------------------------------------------
def extract_ocr(pdf_path: Path) -> str:
    """Render each page to an image and OCR it with PaddleOCR."""
    cache_file = DATA_OCR_CACHE / f"{pdf_path.stem}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    ocr = _get_ocr()
    doc = pymupdf.open(pdf_path)
    all_text = []

    for page in doc:
        # 2x zoom → better OCR accuracy on small fonts
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        img_bytes = pix.tobytes("png")

        # PaddleOCR wants a path or numpy array; write temp file
        tmp_img = DATA_OCR_CACHE / f"_tmp_{pdf_path.stem}_{page.number}.png"
        tmp_img.write_bytes(img_bytes)

        result = ocr.ocr(str(tmp_img), cls=True)
        tmp_img.unlink(missing_ok=True)

        if result and result[0]:
            for line in result[0]:
                all_text.append(line[1][0])   # line[1] = (text, confidence)

    doc.close()
    text = "\n".join(all_text)
    cache_file.write_text(text, encoding="utf-8")
    return text


# ----------------------------------------------------------------------
# Template detection
# ----------------------------------------------------------------------
def detect_template(text: str) -> str:
    if "Thar Jath" in text or "PETRONAS" in text.upper():
        return TEMPLATE_THARJATH
    return TEMPLATE_UNKNOWN


# ----------------------------------------------------------------------
# Main entry
# ----------------------------------------------------------------------
def extract_report(pdf_path: Path, force_ocr: bool = False) -> Dict[str, Any]:
    """
    Run the 3-tier pipeline on a single PDF.
    Returns a dict with raw text + metadata for downstream parsing.
    """
    native_text = "" if force_ocr else extract_native(pdf_path)
    used_ocr = False

    if is_garbled(native_text):
        try:
            text = extract_ocr(pdf_path)
            used_ocr = True
        except Exception as e:
            text = native_text
            used_ocr = False
            print(f"  ⚠️  OCR failed for {pdf_path.name}: {e}")
    else:
        text = native_text

    words = extract_native_words(pdf_path)
    
    template = detect_template(text)
    quality  = "ok" if not is_garbled(text) else "low_confidence"

    return {
        "filename":       pdf_path.name,
        "template":       template,
        "used_ocr":       used_ocr,
        "text_quality":   quality,
        "char_count":     len(text),
        "text":           text,
        "words":          words,
    }


# ----------------------------------------------------------------------
# CLI: run on all PDFs, save JSON per report
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from tqdm import tqdm
    from src.utils import list_pdfs

    pdfs = list_pdfs()
    print(f"Found {len(pdfs)} PDFs in DDRs/\n")

    for pdf_path in tqdm(pdfs, desc="Extracting"):
        result = extract_report(pdf_path)
        out_file = DATA_EXTRACTED / f"{pdf_path.stem}.json"
        out_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tqdm.write(
            f"  {pdf_path.name:35s}  "
            f"template={result['template']:10s}  "
            f"ocr={'Y' if result['used_ocr'] else 'N'}  "
            f"quality={result['text_quality']}"
        )

    print(f"\n✅ Extracted text saved to: {DATA_EXTRACTED}")