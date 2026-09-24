"""
Reusable UI components for the dashboard.
"""
import streamlit as st
import plotly.express as px
import pandas as pd


def kpi_card(label: str, value: str, delta: str = None):
    """Render a single KPI card."""
    st.metric(label=label, value=value, delta=delta)


def anomaly_bar_chart(anomaly_counts: dict):
    """Horizontal bar chart of anomaly types."""
    if not anomaly_counts:
        st.info("No anomalies detected.")
        return

    df = pd.DataFrame(
        list(anomaly_counts.items()),
        columns=["Anomaly", "Count"],
    ).sort_values("Count", ascending=True)

    fig = px.bar(
        df, x="Count", y="Anomaly", orientation="h",
        color="Count", color_continuous_scale="Reds",
        title="Anomaly Distribution",
    )
    fig.update_layout(
        showlegend=False,
        height=320,
        margin=dict(l=10, r=10, t=40, b=10),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def depth_vs_time_chart(df: pd.DataFrame):
    """Line chart: depth over time."""
    if df.empty:
        return
    if "date" not in df.columns or "depth_m" not in df.columns:
        st.info("Depth data not available.")
        return
    dff = df.dropna(subset=["date", "depth_m"])
    if dff.empty:
        st.info("No valid depth/date data.")
        return
    fig = px.line(
        dff, x="date", y="depth_m", markers=True,
        title="Depth vs Time",
        labels={"date": "Date", "depth_m": "Depth (m)"},
    )
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def rop_over_time_chart(df: pd.DataFrame):
    """Line chart: ROP over time. Tolerates multiple column names."""
    if df.empty:
        return

    # Try multiple possible column names — pick whichever exists
    col = None
    for candidate in ("rop_mhr", "avg_pen_rate_mhr", "rop_m_hr"):
        if candidate in df.columns:
            col = candidate
            break

    if col is None:
        st.info("ROP data not available.")
        return

    if "date" not in df.columns:
        st.info("Date data not available.")
        return

    dff = df.dropna(subset=["date", col])
    if dff.empty:
        st.info("No valid ROP/date data.")
        return

    fig = px.line(
        dff, x="date", y=col, markers=True,
        title="ROP over Time",
        labels={"date": "Date", col: "ROP (m/hr)"},
    )
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def mud_weight_chart(df: pd.DataFrame):
    """Mud weight over time."""
    if df.empty:
        return
    if "mud_weight_ppg" not in df.columns or "date" not in df.columns:
        st.info("Mud weight data not available.")
        return
    dff = df.dropna(subset=["date", "mud_weight_ppg"])
    if dff.empty:
        st.info("No valid mud/date data.")
        return
    fig = px.line(
        dff, x="date", y="mud_weight_ppg", markers=True,
        title="Mud Weight over Time (ppg)",
        labels={"date": "Date", "mud_weight_ppg": "MW (ppg)"},
    )
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def field_row(label: str, value):
    """Render one label-value row for the detail panel."""
    if value is None:
        value_str = "—"
    elif isinstance(value, float) and pd.isna(value):
        value_str = "—"
    elif isinstance(value, float):
        value_str = f"{value:,.2f}".rstrip("0").rstrip(".")
    else:
        value_str = str(value)
    st.markdown(f"**{label}:** {value_str}")