"""
Field extractor for Petronas Carigali IADC-style daily drilling reports.

Uses COORDINATE-BASED extraction for grid sections (mud, bit, time,
pumps, surveys, general info) and REGEX for narrative sections
(summary, anomalies, fuel).
"""
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional

from src.grid_extractor import words_to_rows


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
        well_parts = [w["text"] for w in well_row if w["x0"] < 200]
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
        # Remove trailing report number from date text
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
    out: Dict[str, Any] = {}

    # Row with DAYS w/o Lost Time Accident
    row20 = _find_row(rows, "DAYS", "Lost", "Time", "Accident")
    if row20:
        v = _word_near_x(row20, 185, tol=15)
        if v:
            out["days_without_lta"] = _num(v)
        v = _word_near_x(row20, 390, tol=8)
        if v:
            out["pob_total"] = _num(v)
        v = _word_near_x(row20, 504, tol=8)
        if v:
            out["avg_pen_rate_mhr"] = _num(v)

    # Expatriates
    row17 = _find_row(rows, "EXPATRIATES")
    if row17:
        v = _word_near_x(row17, 392, tol=8)
        if v:
            out["pob_expat"] = _num(v)

    # Scan rows for STAFF, NON-STAFF, casing, BOP
    for row in rows[:25]:
        text = " ".join(w["text"] for w in row)
        text_l = text.lower()

        # STAFF but not NON-STAFF
        if "staff" in text_l and "non-staff" not in text_l and "proposed" not in text_l:
            v = _word_near_x(row, 392, tol=8)
            if v:
                out["pob_staff"] = _num(v)
            # Deepest casing on same row: 20" 21 m 2110 psi
            v = _word_near_x(row, 420, tol=12)
            if v:
                out["deepest_casing_size_in"] = _num(v)
            v = _word_near_x(row, 455, tol=12)
            if v:
                out["deepest_casing_depth_m"] = _num(v)

        if "non-staff" in text_l:
            v = _word_near_x(row, 392, tol=8)
            if v:
                out["pob_non_staff"] = _num(v)

        if "last bop test" in text_l:
            v = _word_near_x(row, 270, tol=25)
            if v and any(c.isdigit() for c in v):
                out["last_bop_test"] = v

        if "last kick drill" in text_l:
            v = _word_near_x(row, 270, tol=25)
            if v and any(c.isdigit() for c in v):
                out["last_kick_drill"] = v

    return out


# ======================================================================
# MUD
# ======================================================================
def extract_mud_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # Find the mud-values row (contains "ppm")
    mud_row = None
    for row in rows:
        if any(w["text"] == "ppm" for w in row):
            mud_row = row
            break
    if not mud_row:
        return out

    anchors = {
        "mud_weight_ppg":     79,
        "funnel_viscosity_s": 113,
        "plastic_viscosity":  143,
        "yield_point":        171,
        "gels":               204,
        "api_wl":             238,
        "chlorides_ppm":      335,
        "sand_pct":           391,
        "solids_pct":         422,
    }
    for field, x in anchors.items():
        v = _word_near_x(mud_row, x, tol=12)
        if v:
            out[field] = _num(v)

    # MBT / Oil-Water / pH / mud type row (2 rows below mud row)
    try:
        idx = rows.index(mud_row)
        row_below = rows[idx + 2]
    except (ValueError, IndexError):
        return out

    mbt = _word_near_x(row_below, 81, tol=12)
    if mbt:
        out["mbt"] = _num(mbt)
    ph = _word_near_x(row_below, 140, tol=12)
    if ph:
        out["ph"] = _num(ph)
    ow = _word_near_x(row_below, 164, tol=12)
    if ow:
        out["oil_water_ratio"] = _num(ow)

    mud_type = _join_x_range(row_below, 170, 280)
    if mud_type:
        out["mud_type"] = mud_type

    # Mud cost row (next row after row_below)
    try:
        cost_row = rows[rows.index(row_below) + 1]
        daily = _join_x_range(cost_row, 440, 480, sep="")
        cumm  = _join_x_range(cost_row, 520, 570, sep="")
        if daily:
            out["mud_cost_daily_usd"] = _num(daily)
        if cumm:
            out["mud_cost_cumulative_usd"] = _num(cumm)
    except (ValueError, IndexError):
        pass

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

    # Merge adjacent words with tiny x-gap (e.g. "3" + "73" -> "373")
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

    bit_row = None
    for row in rows:
        text = " ".join(w["text"] for w in row)
        if "HTC" in text or "3x22" in text:
            bit_row = row
            break
    if not bit_row:
        return out

    size_parts = _words_in_x_range(bit_row, 100, 132)
    if size_parts:
        size_str = "".join(size_parts)
        out["bit_size_in"] = _num(size_str)

    serial = _word_near_x(bit_row, 139, tol=15)
    if serial and serial.isdigit():
        out["bit_serial"] = serial

    make = _join_x_range(bit_row, 190, 250)
    if make:
        out["bit_make_type"] = make

    jets = _join_x_range(bit_row, 245, 330)
    if jets:
        out["bit_jets"] = jets

    v = _word_near_x(bit_row, 356, tol=12)
    if v:
        out["bit_depth_out_m"] = _num(v)

    v = _word_near_x(bit_row, 405, tol=12)
    if v:
        out["bit_footage_m"] = _num(v)

    wt = _join_x_range(bit_row, 435, 460)
    if wt:
        out["bit_weight_klbs"] = wt

    v = _word_near_x(bit_row, 478, tol=12)
    if v:
        out["bit_rpm"] = _num(v)

    dull = _join_x_range(bit_row, 520, 560, sep="")
    if dull:
        out["bit_dull_code"] = dull

    return out


# ======================================================================
# PUMPS + HYDRAULICS
# ======================================================================
def extract_pumps_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    pump_rows = []
    for row in rows:
        if not row:
            continue
        first = row[0]["text"]
        joined = " ".join(w["text"] for w in row)
        if first in ("1", "2", "3", "4") and ("T-" in joined or "BPMP" in joined):
            pump_rows.append(row)

    for row in pump_rows[:3]:
        n = row[0]["text"]
        out[f"pump{n}_make"]  = _word_near_x(row, 83, tol=8)
        out[f"pump{n}_model"] = _word_near_x(row, 105, tol=8)

        stroke = _word_near_x(row, 157, tol=12)
        if stroke:
            out[f"pump{n}_stroke_in"] = _num(stroke)

        liner = _join_x_range(row, 190, 225, sep=" ")
        if liner:
            out[f"pump{n}_liner_in"] = liner

        v = _word_near_x(row, 256, tol=12)
        if v:
            out[f"pump{n}_spm"] = _num(v)

        v = _word_near_x(row, 306, tol=12)
        if v:
            out[f"pump{n}_gpm"] = _num(v)

        v = _word_near_x(row, 362, tol=12)
        if v and v.isdigit():
            out[f"pump{n}_pressure_psi"] = _num(v)

    # Velocity row
    vel_row = None
    for row in rows:
        text = " ".join(w["text"] for w in row)
        if "FT/MIN" in text and "FPS" in text:
            vel_row = row
            break
    if vel_row:
        v = _word_near_x(vel_row, 143, tol=12)
        if v:
            out["annular_velocity_dp_ftmin"] = _num(v)
        v = _word_near_x(vel_row, 256, tol=12)
        if v:
            out["annular_velocity_dc_ftmin"] = _num(v)
        v = _word_near_x(vel_row, 322, tol=12)
        if v:
            out["nozzle_velocity_fps"] = _num(v)
        v = _word_near_x(vel_row, 380, tol=12)
        if v:
            out["bit_pressure_drop_psi"] = _num(v)
        v = _word_near_x(vel_row, 449, tol=12)
        if v:
            out["hydraulic_hp"] = _num(v)

    return out


# ======================================================================
# TIME BREAKDOWN
# ======================================================================
def extract_time_from_rows(rows: List[List[Dict]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    daily_row = None
    cumm_row = None

    for row in rows:
        texts = [w["text"] for w in row]
        if texts.count("HRS") < 3:
            continue

        # Count numeric tokens (excluding x-position dupes)
        numeric_tokens = [t for t in texts if re.match(r"^\d+\.\d+$", t)]

        # The daily row has a total near x~510 that equals ~24
        # The cumm row has larger numbers
        total_words = [w for w in row if 490 <= w["x0"] <= 540]
        if not total_words:
            continue

        try:
            total_val = float(total_words[0]["text"])
        except ValueError:
            continue

        if 23.5 <= total_val <= 24.5:
            daily_row = row
        elif total_val > 24.5:
            cumm_row = row

    if daily_row:
        v = _word_near_x(daily_row, 84, tol=15)
        if v: out["time_drilling_daily_hrs"] = _num(v)
        v = _word_near_x(daily_row, 147, tol=15)
        if v: out["time_trips_daily_hrs"] = _num(v)
        v = _word_near_x(daily_row, 198, tol=15)
        if v: out["time_circ_ream_daily_hrs"] = _num(v)
        v = _word_near_x(daily_row, 245, tol=15)  # rig repairs
        if v: out["time_rig_repairs_daily_hrs"] = _num(v)
        v = _word_near_x(daily_row, 297, tol=15)  # logging
        if v: out["time_logging_daily_hrs"] = _num(v)
        v = _word_near_x(daily_row, 345, tol=15)  # coring
        if v: out["time_coring_dst_daily_hrs"] = _num(v)
        v = _word_near_x(daily_row, 432, tol=15)  # others
        if v: out["time_others_daily_hrs"] = _num(v)
        v = _word_near_x(daily_row, 511, tol=15)
        if v: out["time_total_daily_hrs"] = _num(v)

    if cumm_row:
        v = _word_near_x(cumm_row, 84, tol=15)
        if v: out["time_drilling_cumm_hrs"] = _num(v)
        v = _word_near_x(cumm_row, 147, tol=15)
        if v: out["time_trips_cumm_hrs"] = _num(v)
        v = _word_near_x(cumm_row, 198, tol=15)
        if v: out["time_circ_ream_cumm_hrs"] = _num(v)
        v = _word_near_x(cumm_row, 245, tol=15)
        if v: out["time_rig_repairs_cumm_hrs"] = _num(v)
        v = _word_near_x(cumm_row, 297, tol=15)
        if v: out["time_logging_cumm_hrs"] = _num(v)
        v = _word_near_x(cumm_row, 345, tol=15)
        if v: out["time_coring_dst_cumm_hrs"] = _num(v)
        v = _word_near_x(cumm_row, 428, tol=15)
        if v: out["time_others_cumm_hrs"] = _num(v)
        v = _word_near_x(cumm_row, 509, tol=15)
        if v: out["time_total_cumm_hrs"] = _num(v)

    return out


# ======================================================================
# SUMMARY
# ======================================================================
def extract_summary(text: str) -> str:
    m = re.search(
        r"SUMMARY OF OPERATIONS.*?\n(.+?)(?=AFE COST|DRY HOLE|ESTIMATED COST)",
        text, re.S | re.I,
    )
    if m:
        s = re.sub(r"\s+", " ", m.group(1)).strip()
        return s[:500]
    return ""


# ======================================================================
# ANOMALIES (only scan remarks + summary)
# ======================================================================
ANOMALY_KEYWORDS = {
    "lost_circulation": [r"lost circulation", r"\bloss(es)?\b",
                         r"unable to circulate", r"partial loss", r"total loss"],
    "stuck_pipe":       [r"stuck", r"pipe stuck", r"stuck string"],
    "pack_off":         [r"pack(ed)?[- ]?off", r"packing off"],
    "well_kick":        [
    r"well[\s-]?kick",
    r"\bkick\b(?!\s*[-]?off)",     # "kick" but NOT "kick off"
    r"influx",
    r"shut[- ]in",
    r"gain\s+\d+",                  # "gain 10 bbls" — classic kick indicator
    r"flow\s+check",
                        ],
    "equipment_failure":[r"failure", r"breakdown", r"malfunction",
                         r"rupture", r"\bleak\b"],
    "tight_hole":       [r"tight hole", r"overpull", r"over pull",
                         r"\bdrag\b", r"ream(ing)?"],
    "cementing_issue":  [r"cement", r"float (shoe|collar)",
                         r"plug (bump|set)", r"displace", r"top plug"],
}


def extract_anomalies(text: str) -> Dict[str, Any]:
    haystack = ""

    # Remarks section
    m = re.search(r"HOURS & REMARKS(.+?)(?=FUEL|$)", text, re.S | re.I)
    if m:
        haystack += m.group(1)

    # Summary section
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