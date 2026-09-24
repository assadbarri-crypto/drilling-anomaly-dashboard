"""
Shared configuration and helpers for the drilling report pipeline.
"""
from pathlib import Path

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# PDFs live OUTSIDE the project (one level up, in DDRs/)
DDRS_DIR          = PROJECT_ROOT.parent / "DDRs"
DATA_EXTRACTED    = PROJECT_ROOT / "data" / "extracted"
DATA_PROCESSED    = PROJECT_ROOT / "data" / "processed"
DATA_OCR_CACHE    = PROJECT_ROOT / "data" / "ocr_cache"

for p in (DATA_EXTRACTED, DATA_PROCESSED, DATA_OCR_CACHE):
    p.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------
# Report template identifiers
# ----------------------------------------------------------------------
TEMPLATE_THARJATH = "tharjath"   # Petronas Carigali IADC-style (2004)
TEMPLATE_GODA     = "goda"       # Geoservices / Woodside (2021)
TEMPLATE_UNKNOWN  = "unknown"

# ----------------------------------------------------------------------
# Anomaly labels we will detect (client requirement #9)
# ----------------------------------------------------------------------
ANOMALY_LABELS = [
    "lost_circulation",
    "stuck_pipe",
    "pack_off",
    "well_kick",
    "equipment_failure",
    "tight_hole",
    "cementing_issue",
    "no_anomaly",
]

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def list_pdfs() -> list[Path]:
    """Return all PDFs in DDRs/, sorted by numeric prefix."""
    if not DDRS_DIR.exists():
        raise FileNotFoundError(f"DDRs folder not found: {DDRS_DIR}")
    pdfs = [p for p in DDRS_DIR.glob("*.pdf")]
    pdfs.sort(key=lambda p: p.name)
    return pdfs


def is_garbled(text: str, min_tokens: int = 20,
               max_unique_ratio: float = 0.20,
               max_digit_ratio: float = 0.70) -> bool:
    """
    Heuristic: detect a broken text layer (like '1 1 1 1 ...').
    Returns True if the text looks garbled and needs OCR.
    """
    if not text:
        return True
    tokens = text.split()
    if len(tokens) < min_tokens:
        return True
    unique_ratio = len(set(tokens)) / len(tokens)
    digit_ratio  = sum(t.isdigit() for t in tokens) / len(tokens)
    return unique_ratio < max_unique_ratio or digit_ratio > max_digit_ratio