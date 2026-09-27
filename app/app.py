"""
Drilling Report Anomaly Dashboard — main Streamlit app.
"""
import streamlit as st
import pandas as pd

from components import (
    anomaly_bar_chart,
    depth_vs_time_chart,
    rop_over_time_chart,
    mud_weight_chart,
    field_row,
)
from data_loader import get_anomaly_counts
from well_data_loader import load_well_data
from branding import render_header, render_sidebar_brand
from trajectory import render_trajectory
from src.config_loader import load_config

st.set_page_config(
    page_title="Drilling Report Anomaly Dashboard",
    page_icon="🛢️",
    layout="wide",
)

# ----------------------------------------------------------------
# Config + well selector
# ----------------------------------------------------------------
CONFIG = load_config()

st.sidebar.title("🛢️ Drilling Dashboard")
st.sidebar.divider()
st.sidebar.subheader("Well")

well_options = {w.id: w.display_name for w in CONFIG.wells}
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
render_header(well.display_name)

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
# Charts — Row 1
# ----------------------------------------------------------------
c1, c2 = st.columns(2)

with c1:
    anomaly_counts = get_anomaly_counts(filtered)
    anomaly_bar_chart(anomaly_counts)

with c2:
    depth_vs_time_chart(filtered)

# ----------------------------------------------------------------
# Charts — Row 2
# ----------------------------------------------------------------
c3, c4 = st.columns(2)
with c3:
    rop_over_time_chart(filtered)
with c4:
    mud_weight_chart(filtered)

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
st.dataframe(display, use_container_width=True, hide_index=True)

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

options = filtered[file_col].tolist()
if options:
    selected_file = st.selectbox("Select a report", options=options)
    row = filtered[filtered[file_col] == selected_file].iloc[0]

    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 General", "🛠️ Drilling", "💧 Mud & Hydraulics", "⚠️ Anomalies"
    ])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            field_row("Well", row.get("well_name"))
            field_row("Rig", row.get("rig_name"))
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

        st.markdown("### Evidence")
        st.info(row.get("anomaly_evidence", "—"))

        st.markdown("### Summary of Operations")
        st.write(row.get("summary", "—"))

# ----------------------------------------------------------------
# Footer
# ----------------------------------------------------------------
st.caption(f"Built with Streamlit • Data source: {well.display_name}")