"""
background.py — injects a faded background image via CSS.

Controlled by config/wells.yaml → branding.show_background.
There is NO viewer-facing toggle. Admin flips the config and redeploys.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config_loader import load_config


def _img_to_base64(path: Path) -> str:
    """Read an image and return base64-encoded bytes."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def render_background() -> None:
    """Inject CSS that places the background image behind the app."""
    cfg = load_config()
    b = cfg.branding

    if not b.show_background:
        return
    if not b.background_path.exists():
        return

    try:
        b64 = _img_to_base64(b.background_path)
    except Exception:
        return

    opacity = max(0.0, min(1.0, b.background_opacity))

    # Streamlit's main content is inside [data-testid="stAppViewContainer"].
    # We layer the image with a very low opacity so it does not disturb
    # reading of the charts and tables.
    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: url("data:image/jpeg;base64,{b64}");
            background-size: cover;
            background-position: center center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }}
        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            inset: 0;
            background: rgba(255, 255, 255, {1.0 - opacity});
            pointer-events: none;
            z-index: 0;
        }}
        [data-testid="stAppViewContainer"] > section {{
            position: relative;
            z-index: 1;
        }}
        [data-testid="stHeader"] {{
            background: transparent;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )