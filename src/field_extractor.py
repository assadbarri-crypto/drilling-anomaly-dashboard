"""
Field extractor for Petronas Carigali IADC-style daily drilling reports.

Uses coordinate-based extraction for grid sections (mud, bit, time, pumps,
surveys, general info) and regex for narrative sections (summary, anomalies,
fuel). All grid extractors are layout-aware: they derive column anchors from
the header row of each table, so they work across TJ-5, TJ-8 and TJ-11.
"""
from __future__ import annotations

import re
from typing import Dict, Any, List, Optional

from src.grid_extractor import (
    words_to_rows,
    find_header_row,
    anchor_x,
    value_at_anchor,
    value_range_at_anchor,
)


# ======================================================================
# HELPERS
# ======================================================================
def _num(s) -> Optional[float]:
    """Parse a number from a string like '10.4', '1,260', '17 ½'."""
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "-", "UTS", "N/A", "n/a"):
        return None
    s = s.replace(",", "")
    s = s.replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
    try:
        cleaned = re.sub(r"[^\d.\-]", "", s)
        if cleaned in ("", "-", "."):
            return None
        return float(cleaned)
    except ValueError:
        return None


def _word_near_x(row: List[Dict], x_target: float, tol: float = 8.0) -> Optional[str]:
    """Return text of the word whose x0 is closest to x_target (within tol)."""
    best, best_dist = None, 1e9
    for w in row:
        d = abs(w["x0"] - x_target)
        if d < best_dist and d <= tol:
            best, best_dist = w, d
    return best["text"] if best else None


def _words_in_x_range(row: List[Dict], x_min: float, x_max: float) -> List[str]:
    return [w["text"] for w in row if x_min <= w["x0"] <= x_max]


def _join_x_range(row: List[Dict], x_min: float, x_max: float,
                  sep: str = " ") -> Optional[str]:
    parts = _words_in_x_range(row, x_min, x_max)
    return sep.join(parts) if parts else None


def _find_row(rows: List[List[Dict]], *keywords: str) -> Optional[List[Dict]]:
    for row in rows:
        text = " ".join(w["text"] for w in row).lower()
        if all(k.lower() in text for k in keywords):
            return row
    return None


# ======================================================================
# HEADER
# ======================================================================
def extract_header_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    well_row = _find_row(rows, "Thar", "Jath")
    if well_row:
        # Well name words all sit left of x=150 (Sudan starts around 196+)
        well_parts = [w["text"] for w in well_row if w["x0"] < 150]
        out["well_name"] = " ".join(well_parts)

        depth_words = [w for w in well_row if 380 <= w["x0"] <= 430]
        if depth_words:
            out["depth_m"] = _num(depth_words[0]["text"])

        foot_words = [w for w in well_row if 440 <= w["x0"] <= 490]
        if foot_words:
            out["footage_m"] = _num(foot_words[0]["text"])

    rig_row = _find_row(rows, "ZPEB")
    if rig_row:
        out["rig_name"] = " ".join(w["text"] for w in rig_row)

    date_row = _find_row(rows, "OILFIELD", "UNITS")
    if date_row:
        date_words = [w["text"] for w in date_row if 420 <= w["x0"] <= 540]
        date_text = " ".join(date_words)
        date_text = re.sub(r"\s+\d+\s*$", "", date_text).strip()
        out["date_raw"] = date_text

        nums = [w["text"] for w in date_row if w["text"].isdigit() and w["x0"] > 530]
        if nums:
            out["report_no"] = _num(nums[-1])

    return out


# ======================================================================
# GENERAL INFO (safety, POB, casing)
# ======================================================================
def extract_general_info_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    """
    Layout-aware general info extraction.
    Finds the label, then reads the first numeric/date value to its right.
    """
    out: Dict[str, Any] = {}

    def _value_after_label(row: List[Dict], label_words: List[str],
                           numeric_only: bool = True) -> Optional[str]:
        label_x = None
        for w in row:
            for lw in label_words:
                if lw.lower() in w["text"].lower():
                    label_x = w["x1"]
                    break
        if label_x is None:
            return None

        for c in [w for w in row if w["x0"] > label_x + 2]:
            t = c["text"].strip()
            if not t:
                continue
            if numeric_only:
                if _num(t) is not None:
                    return t
            else:
                if any(ch.isdigit() for ch in t):
                    return t
        return None

    for row in rows:
        if not row:
            continue
        joined = " ".join(w["text"] for w in row).upper()

        if "DAYS" in joined and "LOST" in joined and "ACCIDENT" in joined:
            v = _value_after_label(row, ["Accident", "LTA"])
            if v is not None:
                out["days_without_lta"] = _num(v)

        if "LAST" in joined and "BOP" in joined and "last_bop_test" not in out:
            v = _value_after_label(row, ["Test"], numeric_only=False)
            if v:
                out["last_bop_test"] = v

        if "LAST" in joined and "KICK" in joined:
            v = _value_after_label(row, ["Drill"], numeric_only=False)
            if v:
                out["last_kick_drill"] = v

        if "EXPATRIATES" in joined:
            v = _value_after_label(row, ["EXPATRIATES"])
            if v is not None:
                out["pob_expat"] = _num(v)

        if ("STAFF" in joined and "NON-STAFF" not in joined
                and "PERSONNEL" not in joined and "PROPOSED" not in joined):
            v = _value_after_label(row, ["STAFF"])
            if v is not None:
                out["pob_staff"] = _num(v)

        if "NON-STAFF" in joined or "NON STAFF" in joined:
            v = _value_after_label(row, ["NON-STAFF", "NON STAFF"])
            if v is not None:
                out["pob_non_staff"] = _num(v)

        if "TOTAL" in joined and "PERSONNEL" in joined:
            v = _value_after_label(row, ["PERSONNEL"])
            if v is not None:
                out["pob_total"] = _num(v)

    # Deepest casing: size + depth are on the STAFF row
    for row in rows[:25]:
        joined = " ".join(w["text"] for w in row).upper()
        if "STAFF" in joined and "NON-STAFF" not in joined and "PROPOSED" not in joined:
            size_str = None
            size_idx = None
            for i, w in enumerate(row):
                if "/" in w["text"] and '"' in w["text"]:
                    if i > 0 and row[i - 1]["text"].isdigit():
                        size_str = row[i - 1]["text"] + " " + w["text"]
                        size_idx = i
                    else:
                        size_str = w["text"]
                        size_idx = i
                    break
                if "." in w["text"] and '"' in w["text"]:
                    size_str = w["text"]
                    size_idx = i
                    break

            if size_str:
                out["deepest_casing_size_in"] = size_str
                if size_idx is not None:
                    for w2 in row[size_idx + 1:]:
                        n = _num(w2["text"])
                        if n is not None and n >= 100:
                            out["deepest_casing_depth_m"] = n
                            break
            break

    # ---- ROP fallback: TJ-8 layout ----
    # Label row contains 'AVG PEN. RATE (m/hr)'.
    # The row immediately below contains the actual value, e.g. '4.60 m/hr'.
    # Only fires if ROP not already found by the header extractor.
    if "avg_pen_rate_mhr" not in out:
        for r_idx, row in enumerate(rows[:25]):
            joined = " ".join(w["text"] for w in row).upper()
            # Find the label row: contains both 'PEN' and 'RATE'
            if "PEN" not in joined or "RATE" not in joined:
                continue
            # The data row is the one right after it
            if r_idx + 1 >= len(rows):
                continue
            data_row = rows[r_idx + 1]
            # In the data row, find 'm/hr' and read the number just before it
            mhr_idx = None
            for i, w in enumerate(data_row):
                if "M/HR" in w["text"].upper().replace(" ", ""):
                    mhr_idx = i
                    break
            if mhr_idx is None or mhr_idx == 0:
                continue
            prev = data_row[mhr_idx - 1]
            n = _num(prev["text"])
            if n is not None and 0 < n < 100:
                out["avg_pen_rate_mhr"] = n
                break

    return out

# ======================================================================
# GENERAL INFO MUD WEIGHTS (MW IN / MW OUT)
# ======================================================================
def extract_general_info_mud_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    """
    Extract MW IN and MW OUT from the GENERAL INFORMATION section.

    Layout: header row with labels, then data row right below.
    MW values sit in the same X-range as their 'MUD WT IN' / 'MUD WT OUT' labels.

    Note: gas readings and weights are also present in the header but their
    numeric values are NOT in the PDF text layer (source limitation), so they
    cannot be extracted.
    """
    out: Dict[str, Any] = {}

    # Locate the header row
    header = None
    header_idx = None
    for i, row in enumerate(rows):
        joined = " ".join(w["text"] for w in row).upper()
        if ("BACKGROUND" in joined and "BOTTOMS" in joined
                and "MUD" in joined and "WEIGHT" in joined):
            header = row
            header_idx = i
            break

    if header is None or header_idx + 1 >= len(rows):
        return out

    data_row = rows[header_idx + 1]
    if not data_row:
        return out

    # Find the two MUD label X positions
    mud_positions = [w["x0"] for w in header if "MUD" in w["text"].upper()]
    a_mw_in  = mud_positions[0] if len(mud_positions) > 0 else None
    a_mw_out = mud_positions[1] if len(mud_positions) > 1 else None

    def _value_after(anchor_x, width: float = 60.0):
        if anchor_x is None:
            return None
        for w in data_row:
            if anchor_x - 5 <= w["x0"] <= anchor_x + width:
                n = _num(w["text"])
                if n is not None:
                    return n
        return None

    v = _value_after(a_mw_in, width=30)
    if v is not None:
        out["mud_weight_in_ppg"] = v

    v = _value_after(a_mw_out, width=30)
    if v is not None:
        out["mud_weight_out_ppg"] = v

    return out

# ======================================================================
# MUD PROPERTIES (layout-aware)
# ======================================================================
def extract_mud_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    """
    Layout-aware mud properties extraction.
    Reads the MUD PROPERTIES header row to derive column anchors,
    then reads values from the row below.
    """
    out: Dict[str, Any] = {}

    # Locate header row (contains all these distinctive tokens)
    header = None
    for row in rows:
        joined = " ".join(w["text"] for w in row).upper()
        if ("WT" in joined and "VIS" in joined
                and "GELS" in joined and "CHLORIDES" in joined):
            header = row
            break

    if header is None:
        return out

    def _find_x(*tokens) -> Optional[float]:
        for t in tokens:
            for w in header:
                if t.upper() in w["text"].upper():
                    return w["x0"]
        return None

    a_mw   = _find_x("WT", "WT.")
    a_vis  = _find_x("VIS")
    a_pv   = _find_x("PV")
    a_yp   = _find_x("YP")
    a_gels = _find_x("GELS")
    a_api  = _find_x("API")
    a_chl  = _find_x("CHLORIDES")
    a_sand = _find_x("SAND")
    a_sol  = _find_x("SOLIDS")

    # Locate values row (contains 'ppm')
    header_idx = rows.index(header)
    values_row = None
    for r in rows[header_idx + 1: header_idx + 4]:
        if any(w["text"] == "ppm" for w in r):
            values_row = r
            break

    if values_row is None:
        return out

    def _val(anchor, tol_right=25):
        if anchor is None:
            return None
        for w in values_row:
            if anchor - 8 <= w["x0"] <= anchor + tol_right:
                n = _num(w["text"])
                if n is not None:
                    return n
        return None

    v = _val(a_mw)
    if v is not None:
        out["mud_weight_ppg"] = v

    v = _val(a_vis)
    if v is not None:
        out["funnel_viscosity_s"] = v

    v = _val(a_pv)
    if v is not None:
        out["plastic_viscosity"] = v

    v = _val(a_yp)
    if v is not None:
        out["yield_point"] = v

    v = _val(a_gels)
    if v is not None:
        out["gels"] = v

    v = _val(a_api)
    if v is not None:
        out["api_wl"] = v

    v = _val(a_chl, tol_right=50)
    if v is not None:
        out["chlorides_ppm"] = v

    v = _val(a_sand)
    if v is not None:
        out["sand_pct"] = v

    v = _val(a_sol)
    if v is not None:
        out["solids_pct"] = v

    # Row below values: MBT / Oil-Water / pH / mud type
    try:
        row_below = rows[rows.index(values_row) + 2]
    except (ValueError, IndexError):
        return out

    a_mbt = a_ow = a_ph = None
    for w in row_below:
        t = w["text"].upper()
        if "MBT" in t and a_mbt is None:
            a_mbt = w["x1"]
        if "OIL" in t and "WATER" in t and a_ow is None:
            a_ow = w["x1"]
        if t == "PH" and a_ph is None:
            a_ph = w["x1"]

    def _val_after(start_x, tol_right=25):
        if start_x is None:
            return None
        for w in row_below:
            if start_x < w["x0"] <= start_x + tol_right:
                n = _num(w["text"])
                if n is not None:
                    return n
        return None

    v = _val_after(a_mbt)
    if v is not None:
        out["mbt"] = v
    v = _val_after(a_ow)
    if v is not None:
        out["oil_water_ratio"] = v
    v = _val_after(a_ph)
    if v is not None:
        out["ph"] = v

    for i, w in enumerate(row_below):
        if "USED" in w["text"].upper():
            parts = [row_below[j]["text"] for j in range(i + 1, len(row_below))]
            if parts:
                out["mud_type"] = " ".join(parts)[:80]
            break

    # Mud cost row
    for r in rows[rows.index(row_below) + 1:
                    rows.index(row_below) + 4]:
        joined = " ".join(w["text"] for w in r).upper()
        if "DAILY" in joined and "CUMULATIVE" in joined:
            continue
        nums = [_num(w["text"]) for w in r if _num(w["text"]) is not None]
        nums = [n for n in nums if n > 0]
        if nums:
            if "mud_cost_daily_usd" not in out:
                out["mud_cost_daily_usd"] = nums[0]
            if len(nums) > 1 and "mud_cost_cumulative_usd" not in out:
                out["mud_cost_cumulative_usd"] = nums[-1]
            break

    return out


# ======================================================================
# SURVEYS
# ======================================================================
def extract_surveys_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    survey_row = None
    for row in rows:
        text = " ".join(w["text"] for w in row)
        if "deg" in text and "m" in text and "DEPTH" not in text and "HYDRAULIC" not in text:
            if any("/" in w["text"] for w in row):
                survey_row = row
                break
    if not survey_row:
        return {"surveys": []}

    merged: List[Dict] = []
    for w in survey_row:
        if merged and (w["x0"] - merged[-1]["x1"]) < 5:
            merged[-1] = {**merged[-1],
                          "text": merged[-1]["text"] + w["text"],
                          "x1": w["x1"]}
        else:
            merged.append(dict(w))

    groups = [(70, 220), (220, 380), (380, 580)]
    surveys = []
    for xmin, xmax in groups:
        group = [w for w in merged if xmin <= w["x0"] <= xmax]
        if not group:
            continue
        text = " ".join(w["text"] for w in group)
        md = re.search(r"(\d+)\s*m", text)
        ang = re.search(r"([\d/]+)\s*deg", text)
        if md:
            surveys.append({
                "md_m":  _num(md.group(1)),
                "angle": ang.group(1) if ang else None,
            })
    return {"surveys": surveys}


# ======================================================================
# BIT RECORD
# ======================================================================
def extract_bit_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    header = find_header_row(rows, "BIT", "RUN", "SIZE", "SERIAL")
    if header is None:
        return out

    a_size    = anchor_x(header, "SIZE")
    a_serial  = anchor_x(header, "SERIAL")
    a_make    = anchor_x(header, "MAKE")
    a_jets    = anchor_x(header, "JETS")
    a_depth   = anchor_x(header, "DEPTH")
    a_footage = anchor_x(header, "FOOTAGE")
    a_wt      = anchor_x(header, "WT")
    a_rpm     = anchor_x(header, "RPM")
    a_dull    = anchor_x(header, "DULL") or anchor_x(header, "API")

    header_idx = rows.index(header)
    data_rows = []
    for r in rows[header_idx + 1:header_idx + 6]:
        if not r:
            continue
        joined = " ".join(w["text"] for w in r).upper()
        if joined.replace(":", "").strip() in ("CURRENT",):
            continue
        if not any(w["text"][0].isdigit() for w in r if w["text"]):
            continue

        REJECT = ("D.P.", "DP.", "GRADE", "T.J.", "BHA",
                  "STRING WEIGHT", "DRILL STRING")
        if any(kw in joined for kw in REJECT):
            continue

        anchors = [a_size, a_serial, a_make, a_jets,
                   a_depth, a_footage, a_wt, a_rpm]
        hits = sum(1 for a in anchors
                   if a is not None
                   and value_at_anchor(r, a, tol_right=30) is not None)
        if hits < 5:
            continue

        if a_size is not None:
            size_words = [w for w in r
                          if a_size - 8 <= w["x0"] <= a_size + 40]
            if size_words:
                size_str = size_words[0]["text"]
                if "." in size_str and len(size_str.split(".")[-1]) > 1:
                    continue
                if not re.match(r"^\d+[½¼¾]?$", size_str):
                    if not (size_str.replace(".", "").isdigit()
                            and float(size_str) < 30):
                        continue

        data_rows.append(r)

    if not data_rows:
        return out

    data = data_rows[-1]

    out["bit_size_in"]     = _num(value_range_at_anchor(data, a_size, sep=""))
    out["bit_serial"]      = value_at_anchor(data, a_serial)
    out["bit_make_type"]   = value_range_at_anchor(data, a_make, tol_right=60)
    out["bit_jets"]        = value_range_at_anchor(data, a_jets, tol_right=40)
    out["bit_depth_out_m"] = _num(value_at_anchor(data, a_depth))
    out["bit_footage_m"]   = _num(value_at_anchor(data, a_footage))
    out["bit_weight_klbs"] = value_at_anchor(data, a_wt)
    out["bit_rpm"]         = _num(value_at_anchor(data, a_rpm))
    out["bit_dull_code"]   = value_range_at_anchor(data, a_dull, tol_right=30, sep="")

    return out


# ======================================================================
# PUMPS + HYDRAULICS
# ======================================================================
def extract_pumps_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    header = find_header_row(rows, "PUMP", "MAKE", "STROKE", "LINER")
    if header is None:
        return out

    a_make     = anchor_x(header, "MAKE")
    a_model    = anchor_x(header, "MODEL")
    a_stroke   = anchor_x(header, "STROKE")
    a_liner    = anchor_x(header, "LINER")
    a_rate     = anchor_x(header, "RATE")
    a_volume   = anchor_x(header, "VOLUME")
    a_pressure = anchor_x(header, "PRESSURE")
    a_kill     = anchor_x(header, "KILL")

    header_idx = rows.index(header)

    pump_rows = []
    for r in rows[header_idx + 1:header_idx + 8]:
        if not r:
            continue
        first = r[0]["text"]
        joined = " ".join(w["text"] for w in r)
        if first not in ("1", "2", "3", "4"):
            continue
        if not ("T-" in joined or "BPMP" in joined or "F-" in joined or "F -" in joined):
            continue
        anchors = [a_make, a_stroke, a_liner, a_rate, a_pressure]
        hits = sum(1 for a in anchors
                   if a is not None
                   and value_at_anchor(r, a, tol_right=30) is not None)
        if hits >= 2:
            pump_rows.append(r)

    for row in pump_rows:
        n = row[0]["text"]

        make = value_range_at_anchor(row, a_make, tol_right=40)
        if make:
            out[f"pump{n}_make"] = make

        model = value_range_at_anchor(row, a_model, tol_right=30)
        if model:
            out[f"pump{n}_model"] = model

        stroke = value_at_anchor(row, a_stroke)
        if stroke:
            out[f"pump{n}_stroke_in"] = _num(stroke)

        if a_liner is not None:
            liner_parts = []
            for w in row:
                if a_liner - 8 <= w["x0"] <= a_liner + 25:
                    if _num(w["text"]) is not None:
                        liner_parts.append(w["text"])
            if liner_parts:
                out[f"pump{n}_liner_in"] = " ".join(liner_parts)

        a_volume_use = a_volume if a_volume is not None else (a_pressure or 1e9)
        if a_rate is not None:
            candidates = [w for w in row
                          if a_rate - 8 <= w["x0"] <= a_volume_use - 5]
            nums = [w for w in candidates if _num(w["text"]) is not None]
            if len(nums) >= 2:
                out[f"pump{n}_spm"] = _num(nums[0]["text"])
                out[f"pump{n}_gpm"] = _num(nums[1]["text"])
            elif len(nums) == 1:
                out[f"pump{n}_spm"] = _num(nums[0]["text"])

        if a_pressure is not None:
            a_kill_use = a_kill if a_kill is not None else (a_pressure + 1e9)
            candidates = [w for w in row
                          if a_pressure - 8 <= w["x0"] <= a_kill_use - 5]
            nums = [w for w in candidates if _num(w["text"]) is not None]
            if nums:
                out[f"pump{n}_pressure_psi"] = _num(nums[0]["text"])

        if a_kill is not None:
            kill_candidates = [w for w in row
                               if a_kill <= w["x0"] <= a_kill + 150]
            kill_nums = [w for w in kill_candidates
                         if _num(w["text"]) is not None]
            if kill_nums:
                out[f"pump{n}_kill_rate_psi"] = _num(kill_nums[-1]["text"])

    # Annular velocity row
    for row in rows:
        text = " ".join(w["text"] for w in row).upper()
        if "FT/MIN" in text and "FPS" in text:
            v = _word_near_x(row, 143, tol=15)
            if v: out["annular_velocity_dp_ftmin"] = _num(v)
            v = _word_near_x(row, 256, tol=15)
            if v: out["annular_velocity_dc_ftmin"] = _num(v)
            v = _word_near_x(row, 322, tol=15)
            if v: out["nozzle_velocity_fps"] = _num(v)
            v = _word_near_x(row, 380, tol=15)
            if v: out["bit_pressure_drop_psi"] = _num(v)
            v = _word_near_x(row, 449, tol=15)
            if v: out["hydraulic_hp"] = _num(v)
            break

    return out


# ======================================================================
# TIME BREAKDOWN
# ======================================================================
def extract_time_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    header = find_header_row(rows, "DRILLING", "TRIPS", "CIRC", "OTHERS")
    if header is None:
        return out

    a_drill   = anchor_x(header, "DRILLING")
    a_trips   = anchor_x(header, "TRIPS")
    a_circ    = anchor_x(header, "CIRC")
    a_rig     = anchor_x(header, "RIG") or anchor_x(header, "REPAIR")
    a_logging = anchor_x(header, "LOGGING")
    a_coring  = anchor_x(header, "CORING") or anchor_x(header, "CORE")
    a_others  = anchor_x(header, "OTHERS")
    a_total   = anchor_x(header, "TOTAL")

    header_idx = rows.index(header)
    daily_row = None
    cumm_row = None

    for r_idx, r in enumerate(rows[header_idx + 1: header_idx + 10],
                               start=header_idx + 1):
        if not r:
            continue
        joined = " ".join(w["text"] for w in r).upper()

        if "CUMM" in joined and "DRILLING" in joined:
            continue
        if "CUMM" in joined:
            continue

        is_daily = False

        if a_total is not None:
            candidates = [w for w in r if abs(w["x0"] - a_total) < 40]
            for c in candidates:
                v = _num(c["text"])
                if v is not None and 20.0 <= v <= 25.0:
                    is_daily = True
                    break

        if not is_daily:
            anchors = [a_drill, a_trips, a_circ, a_others]
            hits = sum(1 for a in anchors
                       if a is not None
                       and value_at_anchor(r, a, tol_right=50) is not None)
            if hits >= 2:
                is_daily = True

        if is_daily:
            daily_row = r

    if cumm_row is None:
        for i, r in enumerate(rows[header_idx + 1: header_idx + 10],
                              start=header_idx + 1):
            joined = " ".join(w["text"] for w in r).upper()
            if "CUMM" in joined and "DRILLING" in joined:
                if i + 1 < len(rows):
                    cumm_row = rows[i + 1]
                break

    if daily_row is None:
        return out

    def _extract_into(row, suffix):
        if row is None:
            return
        for key, anchor in [("drilling", a_drill),
                            ("trips", a_trips),
                            ("circ_ream", a_circ),
                            ("rig_repairs", a_rig),
                            ("logging", a_logging),
                            ("coring_dst", a_coring),
                            ("others", a_others),
                            ("total", a_total)]:
            if anchor is None:
                continue
            v = value_at_anchor(row, anchor, tol_right=50)
            if v is not None:
                num = _num(v)
                if num is not None:
                    out[f"time_{key}_{suffix}_hrs"] = num

    _extract_into(daily_row, "daily")
    _extract_into(cumm_row, "cumm")
    return out


# ======================================================================
# SUMMARY
# ======================================================================
def extract_summary(text: str) -> str:
    """
    Extract the SUMMARY OF OPERATIONS narrative.
    Strips trailing AFE numbers and meta-fields that get concatenated
    by pdfplumber's reading order.
    Handles both compact codes ('040406') and spaced codes ('04 03 02').
    """
    m = re.search(
        r"SUMMARY OF OPERATIONS.*?\n(.+?)(?=AFE COST|DRY HOLE|ESTIMATED COST)",
        text, re.S | re.I,
    )
    if not m:
        return ""

    s = re.sub(r"\s+", " ", m.group(1)).strip()

    # --- Strip AFE codes in various formats ---

    # 1. AFE label + code
    s = re.sub(r"\bAFE\s*No\.?\s*:?\s*\d{4,8}\b", "", s, flags=re.IGNORECASE)

    # 2. Compact code at end: "040406"
    s = re.sub(r"\s+\d{4,8}\s*$", "", s)

    # 3. Spaced 3-group code at end: "04 03 02"
    s = re.sub(r"\s+\d{2}\s+\d{2}\s+\d{2}\s*$", "", s)

    # 4. Spaced 2-group code at end: "04 03"
    s = re.sub(r"\s+\d{2}\s+\d{2}\s*$", "", s)

    # 5. Any trailing numeric token(s) after a comma or period
    s = re.sub(r"[,\.]\s*\d[\d\s]{2,}$", "", s)

    # Cleanup: remove double spaces
    s = re.sub(r"\s{2,}", " ", s).strip()

    return s[:500]


# ======================================================================
# ANOMALIES
# ======================================================================
ANOMALY_KEYWORDS = {
    "lost_circulation": [r"lost circulation", r"\bloss(es)?\b",
                         r"unable to circulate", r"partial loss", r"total loss"],
    "stuck_pipe":       [r"stuck", r"pipe stuck", r"stuck string"],
    "pack_off":         [r"pack(ed)?[- ]?off", r"packing off"],
    "well_kick":        [
        r"well[\s-]?kick",
        r"\bkick\b(?!\s*[-]?off)",
        r"influx",
        r"shut[- ]in",
        r"gain\s+\d+",
        r"flow\s+check",
    ],
    "equipment_failure": [r"failure", r"breakdown", r"malfunction",
                          r"rupture", r"\bleak\b"],
    "tight_hole":       [r"tight hole", r"overpull", r"over pull",
                         r"\bdrag\b", r"ream(ing)?"],
    "cementing_issue":  [r"cement", r"float (shoe|collar)",
                         r"plug (bump|set)", r"displace", r"top plug"],
}


def extract_anomalies(text: str) -> Dict[str, Any]:
    haystack = ""

    m = re.search(r"HOURS & REMARKS(.+?)(?=FUEL|$)", text, re.S | re.I)
    if m:
        haystack += m.group(1)

    m = re.search(
        r"SUMMARY OF OPERATIONS.*?\n(.+?)(?=AFE COST|ESTIMATED COST)",
        text, re.S | re.I,
    )
    if m:
        haystack += "\n" + m.group(1)

    haystack_l = haystack.lower()

    found, evidence = [], []
    for label, patterns in ANOMALY_KEYWORDS.items():
        for pat in patterns:
            for m in re.finditer(pat, haystack_l):
                s = max(0, m.start() - 40)
                e = min(len(haystack_l), m.end() + 40)
                evidence.append(haystack_l[s:e].replace("\n", " ").strip())
                if label not in found:
                    found.append(label)

    return {
        "anomalies":        found if found else ["no_anomaly"],
        "has_anomaly":      bool(found),
        "anomaly_evidence": " | ".join(evidence[:5]),
    }


# ======================================================================
# FUEL
# ======================================================================
def extract_fuel(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    patterns = {
        "fuel_daily_l":      r"Daily Fuel Consumption:\s*([\d,]+)\s*L",
        "fuel_cumulative_l": r"Fuel Consumed to Date:\s*([\d,]+)\s*L",
        "fuel_balance_l":    r"Fuel Balance on Hand:\s*([\d,]+)\s*L",
        "fuel_received_l":   r"Fuel Received:\s*([\d,]+)\s*L",
    }
    for field, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            out[field] = _num(m.group(1))
    return out


# ======================================================================
# MASTER
# ======================================================================
def parse_report(raw_text: str, words_pages: List[List[Dict]]) -> Dict[str, Any]:
    text = re.sub(r"\(cid:\d+\)", "", raw_text)
    page0_rows = words_to_rows(words_pages[0]) if words_pages else []

    parsed: Dict[str, Any] = {}
    parsed.update(extract_header_from_rows(page0_rows))
    parsed.update(extract_general_info_from_rows(page0_rows))
    parsed.update(extract_general_info_mud_from_rows(page0_rows))
    parsed.update(extract_mud_from_rows(page0_rows))
    parsed.update(extract_surveys_from_rows(page0_rows))
    parsed.update(extract_bit_from_rows(page0_rows))
    parsed.update(extract_pumps_from_rows(page0_rows))
    parsed.update(extract_time_from_rows(page0_rows))
    parsed["summary"] = extract_summary(text)
    parsed.update(extract_anomalies(text))
    parsed.update(extract_fuel(text))
    return parsed


# ======================================================================
# CLI
# ======================================================================
if __name__ == "__main__":
    import json
    from src.utils import DATA_EXTRACTED

    sample = DATA_EXTRACTED / "09_TharJath_11.json"
    data = json.loads(sample.read_text(encoding="utf-8"))
    parsed = parse_report(data["text"], data["words"])
    print(json.dumps(parsed, indent=2, ensure_ascii=False))