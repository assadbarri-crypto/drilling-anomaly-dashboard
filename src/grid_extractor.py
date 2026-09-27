"""
Coordinate-based extraction for grid sections that pdfplumber concatenates
in flat text (mud row, hydraulics, bit, time breakdown, assembly, POB).
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional


# ======================================================================
# CORE HELPERS
# ======================================================================
def words_to_rows(words: List[Dict], y_tolerance: float = 3.0) -> List[List[Dict]]:
    """
    Group words into rows by vertical position.
    Words within `y_tolerance` of each other are on the same row.
    Each row is sorted left-to-right by x0.
    """
    if not words:
        return []

    # Sort words by vertical position, then horizontal
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))

    rows: List[List[Dict]] = []
    current_row: List[Dict] = []
    current_y: Optional[float] = None

    for w in sorted_words:
        if current_y is None or abs(w["top"] - current_y) <= y_tolerance:
            current_row.append(w)
            # use average top as the row's y
            current_y = sum(x["top"] for x in current_row) / len(current_row)
        else:
            rows.append(sorted(current_row, key=lambda x: x["x0"]))
            current_row = [w]
            current_y = w["top"]

    if current_row:
        rows.append(sorted(current_row, key=lambda x: x["x0"]))

    return rows


def find_row_containing(rows: List[List[Dict]], *keywords: str,
                        case_sensitive: bool = False) -> Optional[List[Dict]]:
    """Return the first row whose text contains ALL given keywords."""
    for row in rows:
        row_text = " ".join(w["text"] for w in row)
        if not case_sensitive:
            row_text = row_text.lower()
            check = [k.lower() for k in keywords]
        else:
            check = list(keywords)
        if all(k in row_text for k in check):
            return row
    return None


def find_row_after(rows: List[List[Dict]], anchor_row: List[Dict],
                   skip: int = 1) -> Optional[List[Dict]]:
    """Return the row `skip` positions after the anchor row."""
    try:
        idx = rows.index(anchor_row)
        return rows[idx + skip] if idx + skip < len(rows) else None
    except ValueError:
        return None


def row_texts(rows: List[List[Dict]]) -> List[str]:
    """Debug helper: return each row as a space-joined string."""
    return [" ".join(w["text"] for w in row) for row in rows]


def words_in_y_range(rows: List[List[Dict]],
                     top: float, bottom: float) -> List[Dict]:
    """Return all words whose 'top' falls in [top, bottom]."""
    out = []
    for row in rows:
        for w in row:
            if top <= w["top"] <= bottom:
                out.append(w)
    return out


# ======================================================================
# COLUMN PICKING
# ======================================================================
def pick_by_x_range(row: List[Dict],
                    x_min: float, x_max: float) -> Optional[str]:
    """Return the text of the word whose center-x is inside [x_min, x_max]."""
    for w in row:
        center = (w["x0"] + w["x1"]) / 2
        if x_min <= center <= x_max:
            return w["text"]
    return None


def pick_columns(row: List[Dict], columns: List[tuple]) -> List[Optional[str]]:
    """
    `columns` is a list of (x_min, x_max) tuples.
    Returns one value per column (or None if nothing found).
    """
    return [pick_by_x_range(row, xmin, xmax) for (xmin, xmax) in columns]

# ======================================================================
# LAYOUT-AWARE ANCHORS (added for multi-well support, Session 3)
# ======================================================================
def find_header_row(rows: List[List[Dict]], *keywords: str) -> Optional[List[Dict]]:
    """
    Return the row containing ALL given keywords (case-insensitive).
    Used to find section headers like ('BIT', 'RUN', 'SIZE', 'SERIAL').
    """
    check = [k.upper() for k in keywords]
    for row in rows:
        texts = [w["text"].upper() for w in row]
        row_upper = " ".join(texts)
        if all(k in row_upper for k in check):
            return row
    return None


def anchor_x(header_row: List[Dict], token: str,
             exact: bool = False) -> Optional[float]:
    """
    Return the x0 of the header word matching `token`.
    If exact=False, matches token as a substring (case-insensitive).
    """
    token_u = token.upper()
    for w in header_row:
        t = w["text"].upper()
        if (t == token_u) if exact else (token_u in t):
            return w["x0"]
    return None


def value_at_anchor(data_row: List[Dict], anchor: Optional[float],
                    tol_left: float = 8.0, tol_right: float = 25.0
                    ) -> Optional[str]:
    """
    Return the first word in data_row whose x0 is within
    [anchor - tol_left, anchor + tol_right].

    Data values usually sit slightly RIGHT of the header text,
    hence the asymmetric tolerance.
    """
    if anchor is None:
        return None
    for w in data_row:
        if anchor - tol_left <= w["x0"] <= anchor + tol_right:
            return w["text"]
    return None


def value_range_at_anchor(data_row: List[Dict], anchor: Optional[float],
                          tol_left: float = 8.0, tol_right: float = 40.0,
                          sep: str = " ") -> Optional[str]:
    """
    Like value_at_anchor, but joins all words in the x-window.
    Useful for multi-word values (e.g., '6 2/3', 'G-105').
    """
    if anchor is None:
        return None
    parts = [w["text"] for w in data_row
             if anchor - tol_left <= w["x0"] <= anchor + tol_right]
    return sep.join(parts) if parts else None