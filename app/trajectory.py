"""
trajectory.py — trajectory charts for deviated wells.

Renders only when the well is deviated and a survey DataFrame is available.
Includes:
  - 3D trajectory (MD → TVD, NS, EW)
  - Inclination vs MD
  - Azimuth vs MD
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows with MD and all needed columns."""
    needed = ["md", "inclination", "azimuth"]
    return df.dropna(subset=needed).copy()


def render_trajectory(survey: pd.DataFrame | None) -> None:
    """Render the full trajectory section."""
    if survey is None or survey.empty:
        return

    df = _clean(survey)
    if df.empty:
        st.info("No usable trajectory data.")
        return

    st.subheader("🛰️ Well Trajectory")

    # ---------- 3D trajectory ----------
    if {"tvd", "ns", "ew"}.issubset(df.columns):
        d3 = df.dropna(subset=["tvd", "ns", "ew"])
        if not d3.empty:
            fig = go.Figure(
                data=[
                    go.Scatter3d(
                        x=d3["ew"], y=d3["ns"], z=-d3["tvd"],
                        mode="lines+markers",
                        line=dict(
                            color=d3["md"],
                            colorscale="Viridis",
                            width=6,
                            colorbar=dict(
                                title="MD (m)",
                                x=1.05,
                                thickness=15,
                            ),
                        ),
                        marker=dict(size=3, color=d3["md"],
                                    colorscale="Viridis"),
                        text=[f"MD {md:.0f} m" for md in d3["md"]],
                        hovertemplate=(
                            "EW %{x:.0f} m<br>NS %{y:.0f} m<br>"
                            "TVD %{z:.0f} m<br>%{text}<extra></extra>"
                        ),
                    )
                ]
            )
            fig.update_layout(
                scene=dict(
                    xaxis_title="East (m)",
                    yaxis_title="North (m)",
                    zaxis_title="TVD (m, negated)",
                    aspectmode="data",
                    camera=dict(
                        eye=dict(x=1.6, y=1.6, z=1.1),
                    ),
                ),
                height=720,
                margin=dict(l=0, r=0, t=40, b=10),
                title="3D Well Path",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ---------- Inclination + Azimuth ----------
    c1, c2 = st.columns(2)

    with c1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["md"], y=df["inclination"],
            mode="lines+markers",
            line=dict(color="#0d7a7a"),
            name="Inclination",
        ))
        fig.update_layout(
            title="Inclination vs MD",
            xaxis_title="MD (m)",
            yaxis_title="Inclination (°)",
            height=350,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["md"], y=df["azimuth"],
            mode="lines+markers",
            line=dict(color="#c0392b"),
            name="Azimuth",
        ))
        fig.update_layout(
            title="Azimuth vs MD",
            xaxis_title="MD (m)",
            yaxis_title="Azimuth (°)",
            height=350,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)