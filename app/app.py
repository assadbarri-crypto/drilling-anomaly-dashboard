"""
Drilling Report Anomaly Dashboard — main Streamlit app.
"""
import sys
from pathlib import Path

# Ensure project root is importable (needed on Streamlit Cloud)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd

from components import field_row
from chart_registry import CHART_REGISTRY

from data_loader import get_anomaly_counts
from well_data_loader import load_well_data
from branding import render_header, render_sidebar_brand
from trajectory import render_trajectory
from src.config_loader import load_config
from background import render_background

st.set_page_config(
    page_title="Drilling Report Anomaly Dashboard",
    page_icon="🛢️",
    layout="wide",
)

# ---- Global style overrides ----
st.markdown(
    """
    <style>
    /* ============ HEADER TITLE ============ */
    h1 {
        color: #1a4d8f !important;
        font-weight: 700 !important;
    }
    [data-testid="stCaptionContainer"] {
        color: #4a7eb8 !important;
        font-size: 1.05rem !important;
    }

    /* ============ SECTION HEADERS ============ */
    h2, h3 {
        color: #1a4d8f !important;
    }

    /* ============ GLOBAL OVERVIEW KPIs (RED) ============ */
    [data-testid="stMetricLabel"] {
        color: #c0392b !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
    }
    [data-testid="stMetricValue"] {
        color: #c0392b !important;
        font-weight: 700 !important;
        font-size: 2rem !important;
    }

    /* ============ REPORTS TABLE (BLUE) ============ */
    div[data-testid="stDataFrame"] th,
    div[data-testid="stDataFrame"] th div,
    div[data-testid="stDataFrame"] thead tr th {
        color: #1a4d8f !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        text-align: center !important;
    }
    div[data-testid="stDataFrame"] td,
    div[data-testid="stDataFrame"] td div {
        color: #1a4d8f !important;
        font-size: 1rem !important;
        text-align: center !important;
        justify-content: center !important;
    }
    div[data-testid="stDataFrame"] td div,
    div[data-testid="stDataFrame"] th div {
        display: flex !important;
        justify-content: center !important;
        text-align: center !important;
    }

    /* ============ REPORT DETAIL — LABELS (BLUE) ============ */
    [data-testid="stMarkdownContainer"] p strong {
        color: #1a4d8f !important;
        font-size: 1.15rem !important;
        font-weight: 700 !important;
    }
    /* ============ REPORT DETAIL — VALUES (RED) ============ */
    [data-testid="stMarkdownContainer"] p {
        color: #c0392b !important;
        font-size: 1.15rem !important;
    }

    /* ============ TAB LABELS ============ */
    button[data-baseweb="tab"] {
        color: #1a4d8f !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #c0392b !important;
    }

    /* ============ ANOMALIES/SUMMARY SUBHEADERS (RED) ============ */
    [data-testid="stMarkdownContainer"] h3 {
        color: #c0392b !important;
        font-size: 1.3rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------
# Config + well selector
# ----------------------------------------------------------------
CONFIG = load_config()
render_background()

st.sidebar.title("🛢️ Drilling Dashboard")
st.sidebar.divider()
st.sidebar.subheader("Well")

def _display(w):
    return CONFIG.branding.display_name_for(w.id, w.display_name)

well_options = {w.id: _display(w) for w in CONFIG.wells}
default_well = CONFIG.default_well_id if CONFIG.default_well_id in well_options else list(well_options)[0]

selected_well_id = st.sidebar.selectbox(
    "Select well",
    options=list(well_options.keys()),
    format_func=lambda k: well_options[k],
    index=list(well_options.keys()).index(default_well),
)

st.sidebar.divider()

# Load selected well
bundle = load_well_data(selected_well_id)
well = bundle["well"]
df = bundle["reports"]
survey = bundle["survey"]
planned_curve = bundle.get("planned_curve")

# Expose planned curve for the depth-vs-time chart
st.session_state["current_planned_curve"] = planned_curve

# ----------------------------------------------------------------
# Sidebar — filters
# ----------------------------------------------------------------
with st.sidebar:
    #st.title("🛢️ Drilling Dashboard")
    #st.caption("Thar Jath #11 — DDR Analysis")
    st.divider()

    st.subheader("Filters")

    valid_dates = df["date"].dropna()
    if len(valid_dates) == 0:
        st.error("No valid dates in dataset.")
        st.stop()

    date_min = valid_dates.min().date()
    date_max = valid_dates.max().date()

    date_range = st.date_input(
        "Date range",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
    )

    # Collect unique anomaly labels
    all_labels = set()
    for lst in df["anomalies"]:
        try:
            labels = eval(lst) if isinstance(lst, str) else lst
        except Exception:
            labels = []
        if isinstance(labels, list):
            for lbl in labels:
                if lbl != "no_anomaly":
                    all_labels.add(lbl)
    all_labels = sorted(all_labels)

    selected_labels = st.multiselect(
        "Filter by anomaly",
        options=all_labels,
        default=[],
        help="Leave empty to include all reports",
    )

    st.divider()
    st.caption(f"Loaded {len(df)} reports")

# ----------------------------------------------------------------
# Apply filters
# ----------------------------------------------------------------
filtered = df.copy()

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[
        (filtered["date"].dt.date >= start) &
        (filtered["date"].dt.date <= end)
    ]

if selected_labels:
    def has_selected(a_list):
        try:
            labels = eval(a_list) if isinstance(a_list, str) else a_list
        except Exception:
            labels = []
        if not isinstance(labels, list):
            return False
        return any(lbl in selected_labels for lbl in labels)
    filtered = filtered[filtered["anomalies"].apply(has_selected)]

# ----------------------------------------------------------------
# Header (branding-controlled)
# ----------------------------------------------------------------
render_header(CONFIG.branding.display_name_for(well.id, well.display_name))

# ----------------------------------------------------------------
# KPIs
# ----------------------------------------------------------------
st.subheader("Global Overview")

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.metric("Reports", len(filtered))

with k2:
    anom_count = int(filtered["has_anomaly"].sum())
    st.metric("Anomalies", anom_count)

with k3:
    valid = filtered["date"].dropna()
    latest = valid.max() if len(valid) else pd.NaT
    st.metric("Latest date", latest.strftime("%Y-%m-%d") if pd.notna(latest) else "—")

with k4:
    if not filtered.empty:
        last_row = filtered.sort_values("date", na_position="first").iloc[-1]
        depth = last_row.get("depth_m")
        st.metric("Current depth (m)", f"{depth:,.0f}" if pd.notna(depth) else "—")
    else:
        st.metric("Current depth (m)", "—")

st.divider()

# ----------------------------------------------------------------
# Trajectory (deviated wells only)
# ----------------------------------------------------------------
if well.is_deviated and survey is not None:
    render_trajectory(survey)
    st.divider()

# ----------------------------------------------------------------
# Charts — user-selectable
# ----------------------------------------------------------------
st.subheader("Charts")

default_charts = [
    "Anomaly Distribution",
    "Depth vs Time",
    "Mud Weight over Time",
]

selected_charts = st.multiselect(
    "Select charts to display",
    options=list(CHART_REGISTRY.keys()),
    default=default_charts,
    help="Pick any number of charts — layout adjusts automatically.",
)

if not selected_charts:
    st.info("No charts selected. Choose at least one from the dropdown above.")
else:
    # 2-column grid layout
    for i in range(0, len(selected_charts), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(selected_charts):
                break
            label = selected_charts[idx]
            with col:
                CHART_REGISTRY[label](filtered)

st.divider()

# ----------------------------------------------------------------
# Report table
# ----------------------------------------------------------------
st.subheader("Reports")

if filtered.empty:
    st.info("No reports match the current filters.")
    st.stop()

# Pick the ROP column that exists
rop_col = None
for candidate in ("rop_mhr", "avg_pen_rate_mhr", "rop_m_hr"):
    if candidate in filtered.columns:
        rop_col = candidate
        break

base_cols = ["date", "report_no", "depth_m", "mud_weight_ppg",
             "has_anomaly", "anomalies"]
if rop_col:
    base_cols.insert(3, rop_col)

display = filtered[base_cols].copy()
display["date"] = display["date"].dt.strftime("%Y-%m-%d")

rename_map = {
    "date": "Date",
    "report_no": "Report #",
    "depth_m": "Depth (m)",
    "mud_weight_ppg": "MW (ppg)",
    "has_anomaly": "Anomaly?",
    "anomalies": "Labels",
}
if rop_col:
    rename_map[rop_col] = "ROP (m/hr)"

display = display.rename(columns=rename_map)

    # --- Format numeric columns ---
    # Report # : integer, no decimals
if "Report #" in display.columns:
    display["Report #"] = display["Report #"].apply(
        lambda x: f"{int(x)}" if pd.notna(x) else ""
    )
# Depth (m) : 0 decimals if integer, else 2
if "Depth (m)" in display.columns:
    display["Depth (m)"] = display["Depth (m)"].apply(
        lambda x: f"{x:,.0f}" if pd.notna(x) else ""
    )
# ROP (m/hr) : 2 decimals
if "ROP (m/hr)" in display.columns:
    display["ROP (m/hr)"] = display["ROP (m/hr)"].apply(
         lambda x: f"{x:.2f}" if pd.notna(x) else ""
    )
    # MW (ppg) : 2 decimals
if "MW (ppg)" in display.columns:
    display["MW (ppg)"] = display["MW (ppg)"].apply(
        lambda x: f"{x:.2f}" if pd.notna(x) else ""
    )

    # --- Inject CSS to force center alignment (Streamlit overrides pandas) ---
    st.markdown(
        """
        <style>
        div[data-testid="stDataFrame"] td,
        div[data-testid="stDataFrame"] th {
            text-align: center !important;
        }
        div[data-testid="stDataFrame"] td div,
        div[data-testid="stDataFrame"] th div {
            justify-content: center !important;
            text-align: center !important;
            display: flex !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # --- Render centered on the page ---
    _left, _center, _right = st.columns([1, 20, 1])
    with _center:
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
        )

st.divider()

# ----------------------------------------------------------------
# Report detail
# ----------------------------------------------------------------
st.subheader("Report Detail")

# Column name differs between wells: old TJ-11 CSV used 'source_file',
# new TJ-5/TJ-8 CSVs use 'filename'. Pick whichever exists.
file_col = None
for candidate in ("filename", "source_file"):
    if candidate in filtered.columns:
        file_col = candidate
        break

if file_col is None:
    st.warning("No file identifier column found — cannot show report detail.")
    st.stop()

# --- Anonymize filenames for display ---
def _mask_filename(filename: str, well_id: str, real_well_name: str) -> str:
    """Replace real well identifiers inside a filename with the anonymized name."""
    if not filename:
        return filename
    if not CONFIG.branding.anonymize_wells:
        return filename
    masked_name = CONFIG.branding.display_name_for(well_id, real_well_name)
    # Build a list of common variants of the well id to replace
    variants = [
        well_id,                                       # TharJath5
        well_id.replace("TharJath", "TharJath_"),      # TharJath_5
        well_id.replace("TharJath", "Thar Jath-"),     # Thar Jath-5
        well_id.replace("TharJath", "Thar Jath "),     # Thar Jath 5
    ]
    out = filename
    for v in variants:
        out = out.replace(v, masked_name)
    return out

options = [
    _mask_filename(f, well.id, well.display_name)
    for f in filtered[file_col].tolist()
]

# Map masked display names back to the real filename for row lookup
_options_map = dict(zip(options, filtered[file_col].tolist()))

if options:
    selected_file = st.selectbox("Select a report", options=options)
    real_file = _options_map.get(selected_file, selected_file)
    row = filtered[filtered[file_col] == real_file].iloc[0]

    # Build tab list dynamically based on config
    show_anomalies = CONFIG.branding.show_report_anomalies

    if show_anomalies:
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 General", "🛠️ Drilling", "💧 Mud & Hydraulics", "⚠️ Anomalies"
        ])
    else:
        tab1, tab2, tab3 = st.tabs([
            "📋 General", "🛠️ Drilling", "💧 Mud & Hydraulics"
        ])
        tab4 = None

    # ----------------------------------------------------------------
    # FALLBACK — Full tab hiding (kept for reference, disabled)
    # ----------------------------------------------------------------
    # If you want to hide the entire Anomalies tab in the future
    # (instead of masking its text), uncomment the block below and
    # comment out the block above:
    #
    # tab1, tab2, tab3 = st.tabs([
    #     "📋 General", "🛠️ Drilling", "💧 Mud & Hydraulics"
    # ])
    # tab4 = None

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            field_row(
                "Well",
                CONFIG.branding.display_name_for(well.id, row.get("well_name")),
            )
            field_row(
                "Rig",
                CONFIG.branding.display_rig_name(row.get("rig_name")),
            )
            field_row("Date", row.get("date_raw"))
            field_row("Report No", row.get("report_no"))
            field_row("Days w/o LTA", row.get("days_without_lta"))
        with col2:
            field_row("POB — Expat", row.get("pob_expat"))
            field_row("POB — Staff", row.get("pob_staff"))
            field_row("POB — Non-staff", row.get("pob_non_staff"))
            field_row("POB — Total", row.get("pob_total"))
            field_row("Last BOP Test", row.get("last_bop_test"))
            field_row("Last Kick Drill", row.get("last_kick_drill"))
        col3, col4 = st.columns(2)
        with col3:
            field_row("Deepest Casing Size (in)", row.get("deepest_casing_size_in"))
            field_row("Deepest Casing Depth (m)", row.get("deepest_casing_depth_m"))
        with col4:
            field_row("Fuel Balance (L)", row.get("fuel_balance_l"))
            field_row("Fuel Cumulative (L)", row.get("fuel_cumulative_l"))

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            field_row("Depth (m)", row.get("depth_m"))
            field_row("Footage (m)", row.get("footage_m"))
            rop_val = None
            for candidate in ("rop_mhr", "avg_pen_rate_mhr", "rop_m_hr"):
                if candidate in row.index and pd.notna(row.get(candidate)):
                    rop_val = row.get(candidate)
                    break
            field_row("ROP (m/hr)", rop_val)
            field_row("Bit Size (in)", row.get("bit_size_in"))
            field_row("Bit Make/Type", row.get("bit_make_type"))
            field_row("Bit Serial", row.get("bit_serial"))
            field_row("Bit Jets", row.get("bit_jets"))
        with col2:
            field_row("Bit Depth Out (m)", row.get("bit_depth_out_m"))
            field_row("Bit Footage (m)", row.get("bit_footage_m"))
            field_row("Bit Weight (klbs)", row.get("bit_weight_klbs"))
            field_row("Bit RPM", row.get("bit_rpm"))
            field_row("Bit Dull Code", row.get("bit_dull_code"))
            field_row("MW IN (ppg)", row.get("mud_weight_in_ppg"))
            field_row("MW OUT (ppg)", row.get("mud_weight_out_ppg"))

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            field_row("Mud Weight (ppg)", row.get("mud_weight_ppg"))
            field_row("Funnel Visc (sec/qt)", row.get("funnel_viscosity_s"))
            field_row("PV (cp)", row.get("plastic_viscosity"))
            field_row("YP (lb/100ft²)", row.get("yield_point"))
            field_row("Gels", row.get("gels"))
            field_row("pH", row.get("ph"))
            field_row("MBT", row.get("mbt"))
            field_row("Oil/Water", row.get("oil_water_ratio"))
            field_row("Chlorides (ppm)", row.get("chlorides_ppm"))
            field_row("Sand (%)", row.get("sand_pct"))
            field_row("Solids (%)", row.get("solids_pct"))
            field_row("Mud Type", row.get("mud_type"))
            field_row("Mud Cost Daily ($)", row.get("mud_cost_daily_usd"))
            field_row("Mud Cost Cumulative ($)", row.get("mud_cost_cumulative_usd"))
        with col2:
            field_row("Pump 1 Make/Model", f"{row.get('pump1_make')} / {row.get('pump1_model')}")
            field_row("Pump 1 SPM / GPM", f"{row.get('pump1_spm')} / {row.get('pump1_gpm')}")
            field_row("Pump 2 Make/Model", f"{row.get('pump2_make')} / {row.get('pump2_model')}")
            field_row("Pump 2 SPM / GPM", f"{row.get('pump2_spm')} / {row.get('pump2_gpm')}")
            field_row("Pump 2 Pressure (psi)", row.get("pump2_pressure_psi"))
            field_row("Pump 3 Make/Model", f"{row.get('pump3_make')} / {row.get('pump3_model')}")
            field_row("Annular Vel DP (ft/min)", row.get("annular_velocity_dp_ftmin"))
            field_row("Annular Vel DC (ft/min)", row.get("annular_velocity_dc_ftmin"))
            field_row("Nozzle Velocity (fps)", row.get("nozzle_velocity_fps"))
            field_row("Bit Pressure Drop (psi)", row.get("bit_pressure_drop_psi"))
            field_row("Hydraulic HP", row.get("hydraulic_hp"))

    if tab4 is not None:
        with tab4:
            st.markdown("### Anomaly labels")
            try:
                labels = eval(row["anomalies"]) if isinstance(row["anomalies"], str) else row["anomalies"]
            except Exception:
                labels = []
            if labels and labels != ["no_anomaly"]:
                for lbl in labels:
                    st.error(f"⚠️ {lbl}")
            else:
                st.success("✅ No anomalies detected")

            # ---- Mask confidential terms in narrative text ----
            evidence_raw = row.get("anomaly_evidence", "—")
            summary_raw  = row.get("summary", "—")

            evidence_masked = CONFIG.branding.mask_text(
                str(evidence_raw) if pd.notna(evidence_raw) else "—",
                well_id=well.id,
                real_well_name=row.get("well_name", ""),
            )
            summary_masked = CONFIG.branding.mask_text(
                str(summary_raw) if pd.notna(summary_raw) else "—",
                well_id=well.id,
                real_well_name=row.get("well_name", ""),
            )

            st.markdown("### Evidence")
            st.info(evidence_masked)

            st.markdown("### Summary of Operations")
            st.write(summary_masked)

    # ----------------------------------------------------------------
    # FALLBACK — Unmasked version (kept for reference, disabled)
    # ----------------------------------------------------------------
    # If you ever need to show raw text (e.g., internal testing),
    # uncomment the block below and comment out the masked block above:
    #
    # if tab4 is not None:
    #     with tab4:
    #         st.markdown("### Anomaly labels")
    #         try:
    #             labels = eval(row["anomalies"]) if isinstance(row["anomalies"], str) else row["anomalies"]
    #         except Exception:
    #             labels = []
    #         if labels and labels != ["no_anomaly"]:
    #             for lbl in labels:
    #                 st.error(f"⚠️ {lbl}")
    #         else:
    #             st.success("✅ No anomalies detected")
    #
    #         st.markdown("### Evidence")
    #         st.info(row.get("anomaly_evidence", "—"))
    #
    #         st.markdown("### Summary of Operations")
    #         st.write(row.get("summary", "—"))

# ----------------------------------------------------------------
# Footer
# ----------------------------------------------------------------
st.caption(f"Built with Streamlit • Data source: {CONFIG.branding.display_name_for(well.id, well.display_name)}")