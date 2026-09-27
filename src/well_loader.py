"""
well_loader.py — loads per-well data (drilling reports + survey).

Reuses the config from config_loader. Does NOT import Streamlit,
so it can be tested from CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config_loader import Config, Well, load_config


@dataclass
class WellData:
    well: Well
    reports: pd.DataFrame
    survey: Optional[pd.DataFrame]   # None for vertical wells

    @property
    def has_survey(self) -> bool:
        return self.survey is not None and not self.survey.empty


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    return pd.read_csv(path)


def load_well(well: Well) -> WellData:
    reports = _read_csv(well.data_path)

    survey = None
    if well.is_deviated and well.survey_path is not None:
        if well.survey_path.exists():
            survey = _read_csv(well.survey_path)
        else:
            # Deviated well but survey file missing — warn, don't crash
            print(f"[warn] Survey file missing for {well.id}: {well.survey_path}")

    return WellData(well=well, reports=reports, survey=survey)


def load_all_wells(config: Optional[Config] = None) -> dict[str, WellData]:
    cfg = config or load_config()
    result: dict[str, WellData] = {}
    for w in cfg.wells:
        try:
            result[w.id] = load_well(w)
        except FileNotFoundError as e:
            print(f"[warn] Skipping {w.id}: {e}")
    return result


# ---------- Quick self-test ----------
if __name__ == "__main__":
    cfg = load_config()
    print(f"Config loaded. Wells: {cfg.well_ids()}\n")

    for w in cfg.wells:
        print(f"--- {w.id} ({w.type}) ---")
        print(f"    data_path:   {w.data_path}")
        print(f"    exists:      {w.data_path.exists()}")
        if w.is_deviated:
            print(f"    survey_path: {w.survey_path}")
            print(f"    survey exists: {w.survey_path and w.survey_path.exists()}")
        print()