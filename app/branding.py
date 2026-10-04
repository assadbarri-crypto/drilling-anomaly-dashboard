"""
branding.py — renders the header with optional logo + names.

Controlled by config/wells.yaml → branding.show_logo / show_well_name.
There is NO viewer-facing toggle. Admin flips the config and redeploys.
"""
from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

# Ensure project root is importable (needed on Streamlit Cloud)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config_loader import load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def render_header(well_display_name: str | None = None) -> None:
    """
    Render dashboard header.

    well_display_name: pass the currently-selected well, or None to hide.
    """
    cfg = load_config()
    b = cfg.branding

    # Layout: logo column (optional) + title column
    logo_col, title_col = st.columns([1, 4]) if b.show_logo else (None, None)

    if b.show_logo:
        with logo_col:
            logo = b.logo_path
            if logo.exists():
                st.image(str(logo), width=160)
            else:
                st.caption("[logo not found]")

    with (title_col if title_col is not None else st.container()):
        st.title("🛢️ Drilling Report Anomaly Dashboard")

        # Subtitle composed from what's enabled
        parts = []
        if b.show_well_name and well_display_name:
            parts.append(well_display_name)
        if b.show_client_name and b.client_name:
            parts.append(b.client_name)
        if parts:
            st.caption(" — ".join(parts))
        # If nothing enabled, render no caption at all


def render_sidebar_brand(well_display_name: str | None = None) -> None:
    """Sidebar brand block (optional)."""
    cfg = load_config()
    b = cfg.branding
    if not b.show_logo:
        st.sidebar.title("🛢️ Drilling Dashboard")
    else:
        logo = b.logo_path
        if logo.exists():
            st.sidebar.image(str(logo), use_container_width=True)
        st.sidebar.title("Drilling Dashboard")

    if b.show_well_name and well_display_name:
        st.sidebar.caption(well_display_name)
    st.sidebar.divider()