"""
config_loader.py — loads config/wells.yaml and exposes typed accessors.

Reusable across the app. No Streamlit import — pure Python so it can be
tested from the command line.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

import yaml


# ---------- Resolve project root regardless of cwd ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "wells.yaml"


@dataclass(frozen=True)
class Well:
    id: str
    display_name: str
    type: str
    field: str
    country: str
    data_path: Path
    survey_path: Optional[Path]
    planned_curve_path: Optional[Path]

    @property
    def is_deviated(self) -> bool:
        return self.type.lower() == "deviated"


@dataclass(frozen=True)
class Branding:
    show_logo: bool
    show_well_name: bool
    show_client_name: bool
    anonymize_wells: bool
    anonymized_names: dict
    show_rig_name: bool
    rig_name_masked: str
    show_report_anomalies: bool        # ← NEW
    show_background: bool
    background_path: Path
    background_opacity: float
    client_name: str
    logo_path: Path

    def display_name_for(self, well_id: str, real_name: str) -> str:
        """Return the display name for a well, respecting anonymization."""
        if not self.anonymize_wells:
            return real_name
        return self.anonymized_names.get(well_id, real_name)

    def display_rig_name(self, real_rig_name) -> str:
        """Return the rig name to display, respecting masking."""
        if self.show_rig_name:
            return real_rig_name or self.rig_name_masked
        return self.rig_name_masked

    def mask_text(self, text: str, well_id: str = "",
                  real_well_name: str = "") -> str:
        """
        Mask confidential terms in free-form text (narratives, evidence).
        Replaces well name variants and rig name patterns with anonymized values.
        Typo-tolerant and zero-pad-tolerant.
        """
        if not text or not isinstance(text, str):
            return text

        out = text

        # --- Mask well name variants ---
        if self.anonymize_wells and well_id:
            masked_well = self.display_name_for(well_id, real_well_name)

            # Extract the well number (e.g. "5" from "TharJath5")
            m = re.search(r"(\d+)$", well_id)
            well_num = m.group(1) if m else ""

            # --- Pattern 1: "Thar ... Jath [zeros] <num>" (well's own number) ---
            # This catches "Thar Jath 8" first, so we don't double-replace later
            if well_num:
                thar_jath_numbered_re = re.compile(
                    r"Thar[\s\.\-_#]*Jath[\s\.\-_#]*0*"
                    + re.escape(well_num) + r"\b",
                    re.IGNORECASE,
                )
                out = thar_jath_numbered_re.sub(masked_well, out)

            # --- Pattern 2: ANY remaining "Thar ... Jath" (typo-tolerant) ---
            # Matches: Thar Jath, TharJath, Thar-Jath, Thar.Jath, "Thar Jath #"
            # and anything that follows (numbers, codes, punctuation)
            thar_jath_re = re.compile(
                r"Thar[\s\.\-_#]*Jath",
                re.IGNORECASE,
            )
            out = thar_jath_re.sub(masked_well, out)

            # --- Pattern 3: "TJ [zeros] <num>" ---
            # Matches: TJ-5, TJ 5, TJ5, TJ-05, TJ05, TJ_005, etc.
            if well_num:
                tj_re = re.compile(
                    r"\bTJ[\s\.\-_#]*0*" + re.escape(well_num) + r"\b",
                    re.IGNORECASE,
                )
                out = tj_re.sub(masked_well, out)

        # --- Mask rig name patterns ---
        if not self.show_rig_name:
            out = re.sub(
                r"(?i)\bZPEB[\s\.\-_]*Rig[\s\.\-_]*\d+\b",
                self.rig_name_masked, out,
            )
            out = re.sub(
                r"(?i)\bZPEB[\s\.\-_]*\d+\b",
                self.rig_name_masked, out,
            )
            out = re.sub(
                r"(?i)\bRig[\s\.\-_]*\d{2,}\b",
                self.rig_name_masked, out,
            )

        return out

@dataclass(frozen=True)
class Config:
    wells: list[Well]
    branding: Branding
    default_well_id: str

    def get_well(self, well_id: str) -> Well:
        for w in self.wells:
            if w.id == well_id:
                return w
        raise KeyError(f"Well id '{well_id}' not found in wells.yaml")

    def well_ids(self) -> list[str]:
        return [w.id for w in self.wells]


def _resolve(rel: Optional[str]) -> Optional[Path]:
    if rel is None:
        return None
    p = Path(rel)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def load_config(config_path: Path = CONFIG_PATH) -> Config:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    wells = [
        Well(
            id=w["id"],
            display_name=w["display_name"],
            type=w["type"],
            field=w.get("field", ""),
            country=w.get("country", ""),
            data_path=_resolve(w["data_path"]),
            survey_path=_resolve(w.get("survey_path")),
            planned_curve_path=_resolve(w.get("planned_curve_path")),
        )
        for w in raw.get("wells", [])
    ]

    b = raw.get("branding", {})
    branding = Branding(
        show_logo=bool(b.get("show_logo", False)),
        show_well_name=bool(b.get("show_well_name", False)),
        show_client_name=bool(b.get("show_client_name", True)),
        anonymize_wells=bool(b.get("anonymize_wells", False)),
        anonymized_names=dict(b.get("anonymized_names", {}) or {}),
        show_rig_name=bool(b.get("show_rig_name", True)),
        rig_name_masked=b.get("rig_name_masked", "XXXX"),
        show_report_anomalies=bool(b.get("show_report_anomalies", True)),
        show_background=bool(b.get("show_background", False)),
        background_path=_resolve(b.get("background_path",
                                       "assets/rig_background.jpg")),
        background_opacity=float(b.get("background_opacity", 0.18)),
        client_name=b.get("client_name", ""),
        logo_path=_resolve(b.get("logo_path", "assets/petronas_carigali_logo.png")),
    )

    default_well_id = raw.get("ui", {}).get(
        "default_well_id", wells[0].id if wells else ""
    )

    return Config(wells=wells, branding=branding, default_well_id=default_well_id)


# ---------- Quick self-test ----------
if __name__ == "__main__":
    cfg = load_config()
    print(f"Loaded {len(cfg.wells)} wells:")
    for w in cfg.wells:
        print(f"  - {w.id:15s} type={w.type:9s} data={w.data_path}")
    print(f"Branding: logo={cfg.branding.show_logo}, "
          f"well_name={cfg.branding.show_well_name}")
    print(f"Default well: {cfg.default_well_id}")