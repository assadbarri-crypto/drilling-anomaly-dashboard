"""
config_loader.py — loads config/wells.yaml and exposes typed accessors.

Reusable across the app. No Streamlit import — pure Python so it can be
tested from the command line.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


# ---------- Resolve project root regardless of cwd ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "wells.yaml"


@dataclass(frozen=True)
class Well:
    id: str
    display_name: str
    type: str                   # "vertical" | "deviated"
    field: str
    country: str
    data_path: Path
    survey_path: Optional[Path]

    @property
    def is_deviated(self) -> bool:
        return self.type.lower() == "deviated"


@dataclass(frozen=True)
class Branding:
    show_logo: bool
    show_well_name: bool
    client_name: str
    logo_path: Path


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
        )
        for w in raw.get("wells", [])
    ]

    b = raw.get("branding", {})
    branding = Branding(
        show_logo=bool(b.get("show_logo", False)),
        show_well_name=bool(b.get("show_well_name", False)),
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