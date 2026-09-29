"""
chart_registry.py — catalog of available charts for the dropdown.

Each chart function takes the current well's `filtered` DataFrame
and renders a Plotly chart via Streamlit.
"""
from __future__ import annotations

from typing import Callable, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ----------------------------------------------------------------------
# Helper: find the first existing column from a list
# ----------------------------------------------------------------------
def _pick_col(df: pd.DataFrame, *candidates: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


# ----------------------------------------------------------------------
# Existing charts (unchanged behavior)
# ----------------------------------------------------------------------
def chart_anomaly_distribution(df: pd.DataFrame) -> None:
    if "anomalies" not in df.columns:
        st.info("No anomaly data available.")
        return

    counts: Dict[str, int] = {}
    for a in df["anomalies"]:
        try:
            labels = eval(a) if isinstance(a, str) else a
        except Exception:
            labels = []
        if not isinstance(labels, list):
            continue
        for lbl in labels:
            counts[lbl] = counts.get(lbl, 0) + 1

    if not counts:
        st.info("No anomalies detected.")
        return

    d = pd.DataFrame(counts.items(), columns=["Anomaly", "Count"])
    d = d.sort_values("Count", ascending=True)

    fig = px.bar(d, x="Count", y="Anomaly", orientation="h",
                 color="Count", color_continuous_scale="Reds",
                 title="Anomaly Distribution")
    fig.update_layout(height=380, showlegend=False,
                      coloraxis_showscale=False,
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_depth_vs_time(df: pd.DataFrame) -> None:
    if "date" not in df.columns or "depth_m" not in df.columns:
        st.info("Depth data not available.")
        return
    d = df.dropna(subset=["date", "depth_m"])
    if d.empty:
        st.info("No valid depth data.")
        return
    fig = px.line(d, x="date", y="depth_m", markers=True,
                  title="Depth vs Time",
                  labels={"date": "Date", "depth_m": "Depth (m)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_rop_over_time(df: pd.DataFrame) -> None:
    col = _pick_col(df, "rop_mhr", "avg_pen_rate_mhr", "rop_m_hr")
    if col is None or "date" not in df.columns:
        st.info("ROP data not available.")
        return
    d = df.dropna(subset=["date", col])
    if d.empty:
        st.info("No valid ROP data.")
        return
    fig = px.line(d, x="date", y=col, markers=True,
                  title="ROP over Time",
                  labels={"date": "Date", col: "ROP (m/hr)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_mud_weight(df: pd.DataFrame) -> None:
    if "date" not in df.columns or "mud_weight_ppg" not in df.columns:
        st.info("Mud weight data not available.")
        return
    d = df.dropna(subset=["date", "mud_weight_ppg"])
    if d.empty:
        st.info("No valid mud weight data.")
        return
    fig = px.line(d, x="date", y="mud_weight_ppg", markers=True,
                  title="Mud Weight over Time (ppg)",
                  labels={"date": "Date", "mud_weight_ppg": "MW (ppg)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------
# New charts (from already-parsed fields)
# ----------------------------------------------------------------------
def chart_bit_weight(df: pd.DataFrame) -> None:
    if "date" not in df.columns or "bit_weight_klbs" not in df.columns:
        st.info("Bit weight data not available.")
        return
    d = df.copy()
    # bit_weight_klbs may be a string like '15' or a number
    d["bit_weight_klbs"] = pd.to_numeric(d["bit_weight_klbs"], errors="coerce")
    d = d.dropna(subset=["date", "bit_weight_klbs"])
    if d.empty:
        st.info("No valid bit weight data.")
        return
    fig = px.line(d, x="date", y="bit_weight_klbs", markers=True,
                  title="Bit Weight (WOB) over Time",
                  labels={"date": "Date", "bit_weight_klbs": "WOB (klbs)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_bit_footage(df: pd.DataFrame) -> None:
    if "date" not in df.columns or "bit_footage_m" not in df.columns:
        st.info("Bit footage data not available.")
        return
    d = df.dropna(subset=["date", "bit_footage_m"])
    if d.empty:
        st.info("No valid bit footage data.")
        return
    fig = px.line(d, x="date", y="bit_footage_m", markers=True,
                  title="Bit Footage over Time",
                  labels={"date": "Date", "bit_footage_m": "Footage (m)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_pump_pressure(df: pd.DataFrame) -> None:
    cols = [c for c in df.columns if c.startswith("pump") and c.endswith("_pressure_psi")]
    if "date" not in df.columns or not cols:
        st.info("Pump pressure data not available.")
        return
    d = df.dropna(subset=["date"])
    fig = go.Figure()
    for c in cols:
        d2 = d.dropna(subset=[c])
        if d2.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d2["date"], y=d2[c], mode="lines+markers",
            name=c.replace("_", " "),
        ))
    if not fig.data:
        st.info("No valid pump pressure data.")
        return
    fig.update_layout(title="Pump Pressure over Time",
                      xaxis_title="Date",
                      yaxis_title="Pressure (psi)",
                      height=380,
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_fuel_balance(df: pd.DataFrame) -> None:
    if "date" not in df.columns or "fuel_balance_l" not in df.columns:
        st.info("Fuel balance data not available.")
        return
    d = df.dropna(subset=["date", "fuel_balance_l"])
    if d.empty:
        st.info("No valid fuel balance data.")
        return
    fig = px.line(d, x="date", y="fuel_balance_l", markers=True,
                  title="Fuel Balance over Time",
                  labels={"date": "Date", "fuel_balance_l": "Balance (L)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_depth_progress(df: pd.DataFrame) -> None:
    if "date" not in df.columns or "depth_m" not in df.columns:
        st.info("Depth data not available.")
        return
    d = df.dropna(subset=["date", "depth_m"]).sort_values("date").copy()
    if d.empty:
        st.info("No valid depth data.")
        return
    d["progress_m"] = d["depth_m"].diff()
    d = d.dropna(subset=["progress_m"])
    if d.empty:
        st.info("Not enough depth data to compute daily progress.")
        return
    fig = px.bar(d, x="date", y="progress_m",
                 title="Daily Depth Progress",
                 labels={"date": "Date", "progress_m": "Progress (m)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------
# Phase C placeholders (will populate after parser extension)
# ----------------------------------------------------------------------
def chart_mw_in_out(df: pd.DataFrame) -> None:
    """Plot MW IN and MW OUT on the same axes for comparison."""
    cols_needed = ["mud_weight_in_ppg", "mud_weight_out_ppg"]
    if "date" not in df.columns or not any(c in df.columns for c in cols_needed):
        st.info("MW IN / MW OUT data not available for this well.")
        return

    d = df.dropna(subset=["date"]).copy()
    fig = go.Figure()

    for col, name, color in [
        ("mud_weight_in_ppg",  "MW IN",  "#0d7a7a"),
        ("mud_weight_out_ppg", "MW OUT", "#c0392b"),
    ]:
        if col not in d.columns:
            continue
        d2 = d.dropna(subset=[col])
        if d2.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d2["date"], y=d2[col], mode="lines+markers",
            name=name, line=dict(color=color),
        ))

    if not fig.data:
        st.info("MW IN / MW OUT data not populated.")
        return

    fig.update_layout(title="Mud Weight IN vs OUT (ppg)",
                      xaxis_title="Date",
                      yaxis_title="MW (ppg)",
                      height=380,
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def chart_weight_up_down(df: pd.DataFrame) -> None:
    """Plot Weight Up and Weight Down on the same axes for comparison."""
    cols_needed = ["weight_up_klbs", "weight_down_klbs"]
    if "date" not in df.columns or not any(c in df.columns for c in cols_needed):
        st.info(
            "Weight Up / Down values are not present in the source PDF text layer "
            "and cannot be extracted."
        )
        return
    

    d = df.dropna(subset=["date"]).copy()
    fig = go.Figure()

    for col, name, color in [
        ("weight_up_klbs",   "Weight Up",   "#0d7a7a"),
        ("weight_down_klbs", "Weight Down", "#c0392b"),
    ]:
        if col not in d.columns:
            continue
        d2 = d.dropna(subset=[col])
        if d2.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d2["date"], y=d2[col], mode="lines+markers",
            name=name, line=dict(color=color),
        ))

    if not fig.data:
        st.info("Weight Up / Down data not populated.")
        return

    fig.update_layout(title="Weight Up vs Down (klbs)",
                      xaxis_title="Date",
                      yaxis_title="Weight (klbs)",
                      height=380,
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------
CHART_REGISTRY: Dict[str, Callable[[pd.DataFrame], None]] = {
    "Anomaly Distribution":   chart_anomaly_distribution,
    "Depth vs Time":          chart_depth_vs_time,
    "ROP over Time":          chart_rop_over_time,
    "Mud Weight over Time":   chart_mud_weight,
    "Bit Weight (WOB)":       chart_bit_weight,
    "Bit Footage":            chart_bit_footage,
    "Pump Pressure":          chart_pump_pressure,
    "Fuel Balance":           chart_fuel_balance,
    "Daily Depth Progress":   chart_depth_progress,
    "MW IN vs MW OUT":        chart_mw_in_out,      # populated in Phase C
    "Weight Up vs Down":      chart_weight_up_down, # populated in Phase C
}