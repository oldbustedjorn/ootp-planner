from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd

# -----------------------------
# OOTP 26 – PT Pitchers Export Schema
# -----------------------------

OOTP26_PITCHER_REQUIRED = [
    "ID",
    "First Name",
    "Last Name",
    "T",
    "STU",
    "MOV",
    "CON",
    "PBABIP",
]

OOTP26_PITCHER_RENAME: Dict[str, str] = {
    # Identity
    "ID": "player_id",
    "First Name": "first_name",
    "Last Name": "last_name",
    "B": "bats",
    "T": "throws",

    # Core pitching ratings
    "STU": "stuff",
    "MOV": "movement",
    "CON": "control",
    "PBABIP": "pbabip",
    "HRR": "hr_rate",
    "HRA": "hr_rate",

    # Splits vs LHB
    "STU vL": "stuff_vs_lhb",
    "MOV vL": "movement_vs_lhb",
    "CON vL": "control_vs_lhb",
    "PBABIP vL": "pbabip_vs_lhb",
    "HRR vL": "hr_rate_vs_lhb",
    "HRA vL": "hr_rate_vs_lhb",

    # Splits vs RHB
    "STU vR": "stuff_vs_rhb",
    "MOV vR": "movement_vs_rhb",
    "CON vR": "control_vs_rhb",
    "PBABIP vR": "pbabip_vs_rhb",
    "HRR vR": "hr_rate_vs_rhb",
    "HRA vR": "hr_rate_vs_rhb",

    # Pitch arsenal
    "FB": "pitch_fb",
    "CH": "pitch_ch",
    "CB": "pitch_cb",
    "SL": "pitch_sl",
    "SI": "pitch_si",
    "SP": "pitch_sp",
    "CT": "pitch_ct",
    "FO": "pitch_fo",
    "CC": "pitch_cc",
    "SC": "pitch_sc",
    "KC": "pitch_kc",
    "KN": "pitch_kn",

    # Pitching profile
    "PIT": "pitches",     # "Pitches" in UI
    "G/F": "gb_fb",       # Ground/Fly
    "VELO": "velocity",
    "Slot": "arm_slot",
    "PT": "type",         # "Type" in UI (pitcher type)
    "STM": "stamina",
    "HLD": "hold",

    # PT metadata
    "ACT": "pt_on_active",
    "CTM": "pt_card_team",
    "CFR": "pt_card_franchise",
    "CYear": "pt_year",
    "CEra": "pt_era",
    "CType": "pt_type",
    "ST": "pt_subtype",
    "CTier": "pt_tier",
    "CTitle": "pt_title",
    "SER": "pt_series",
}


def _rename_duplicate_p_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename pitcher fielding columns into explicit current vs potential names.

    Supports both:
      - OOTP 26 style duplicate columns that pandas mangles to P / P.1
      - OOTP 27 style explicit suffixes P / P_1
    """
    rename_map: Dict[str, str] = {}

    if "P" in df.columns:
        rename_map["P"] = "fld_P"

    if "P.1" in df.columns:
        rename_map["P.1"] = "pot_P"
    elif "P_1" in df.columns:
        rename_map["P_1"] = "pot_P"

    return df.rename(columns=rename_map)


def load_pt_pitchers_csv(path: Path) -> pd.DataFrame:
    """Load an OOTP26 pitchers PT export and normalize key columns."""
    df_raw = pd.read_csv(path)

    missing = [c for c in OOTP26_PITCHER_REQUIRED if c not in df_raw.columns]
    if missing:
        raise ValueError(
            f"OOTP26 pitchers export missing expected columns: {missing}\n"
            f"Columns found: {list(df_raw.columns)}"
        )
    if "HRR" not in df_raw.columns and "HRA" not in df_raw.columns:
        raise ValueError(
            "Pitchers export is missing both HRR and HRA columns.\n"
            f"Columns found: {list(df_raw.columns)}"
        )
        
    df = df_raw.rename(columns=OOTP26_PITCHER_RENAME)
    df = _rename_duplicate_p_columns(df)

    df["name"] = df["first_name"].astype(str) + " " + df["last_name"].astype(str)

    # Coerce numeric columns we know we’ll use
    numeric_cols: List[str] = [
        "stuff", "movement", "control", "pbabip", "hr_rate",
        "stuff_vs_lhb", "movement_vs_lhb", "control_vs_lhb", "pbabip_vs_lhb", "hr_rate_vs_lhb",
        "stuff_vs_rhb", "movement_vs_rhb", "control_vs_rhb", "pbabip_vs_rhb", "hr_rate_vs_rhb",
        # Arsenal
        "pitch_fb", "pitch_ch", "pitch_cb", "pitch_sl", "pitch_si", "pitch_sp",
        "pitch_ct", "pitch_fo", "pitch_cc", "pitch_sc", "pitch_kc", "pitch_kn",
        # Profile
        "pitches", "velocity", "stamina", "hold",
        # Fielding
        "fld_P", "pot_P",
        # PT year
        "pt_year",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df