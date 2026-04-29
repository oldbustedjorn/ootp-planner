from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd


# -----------------------------
# OOTP 26 – PT Hitters Export Schema
# -----------------------------

# Columns we expect in OOTP26 hitters export.
OOTP26_HITTER_REQUIRED = [
    "ID",
    "First Name",
    "Last Name",
    "B",
    "T",
    "BABIP",
    "CON",
    "GAP",
    "POW",
    "EYE",
    "K's",
]

# Base mapping from raw CSV column → normalized internal name.
# We keep this explicit for robustness (year-to-year changes can be handled
# by adding a new profile/mapping rather than spaghetti conditionals).
OOTP26_HITTER_RENAME: Dict[str, str] = {
    # Identity
    "ID": "player_id",
    "First Name": "first_name",
    "Last Name": "last_name",
    "B": "bats",
    "T": "throws",
    # Core batting ratings
    "BABIP": "babip",
    "CON": "contact",
    "GAP": "gap_power",
    "POW": "power",
    "EYE": "eye",
    "K's": "avoid_k",
    # Splits vs LHP
    "BA vL": "babip_vs_lhp",  # NOTE: this is BABIP vs LHP (UI label), not batting average
    "CON vL": "contact_vs_lhp",
    "GAP vL": "gap_vs_lhp",
    "POW vL": "power_vs_lhp",
    "EYE vL": "eye_vs_lhp",
    "K vL": "avoid_k_vs_lhp",
    # Splits vs RHP
    "BA vR": "babip_vs_rhp",  # NOTE: this is BABIP vs RHP (UI label), not batting average
    "CON vR": "contact_vs_rhp",
    "GAP vR": "gap_vs_rhp",
    "POW vR": "power_vs_rhp",
    "EYE vR": "eye_vs_rhp",
    "K vR": "avoid_k_vs_rhp",
    # Bunting / tendencies
    "BUN": "sac_bunt",
    "BFH": "bunt_hit",
    "BBT": "bb_type",
    "GBT": "gb_tendency",
    "FBT": "fb_tendency",
    # Catcher / fielding component ratings
    "C ABI": "c_blocking",
    "C FRM": "c_framing",
    "C ARM": "c_arm",
    "IF RNG": "if_range",
    "IF ERR": "if_error",
    "IF ARM": "if_arm",
    "TDP": "turn_dp",
    "OF RNG": "of_range",
    "OF ERR": "of_error",
    "OF ARM": "of_arm",
    # Running
    "SPE": "speed",
    "STE": "stealing_ability",
    "SR": "stealing_aggressiveness",
    "RUN": "baserunning",
    # PT metadata (as exported)
    "ACT": "pt_on_active",
    "CTM": "pt_card_team",
    "CFR": "pt_card_franchise",
    "CYear": "pt_year",
    "CVAL": "card_value",
    "CEra": "pt_era",
    "CType": "pt_type",
    "ST": "pt_subtype",
    "CTier": "pt_tier",
    "CTitle": "pt_title",
    "SER": "pt_series",
}

# Positions appear twice in your export:
#   P, C, 1B, ... RF      -> fielding at position (current)
#   P.1, C.1, 1B.1, ...   -> fielding potential at position
POSITION_COLS: List[str] = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]

# Trainability flags (from your note):
# T2..T9 correspond to whether the position can be trained.
# Based on the PT Info tab: Train C, 1B, 2B, 3B, SS, LF, CF, RF.
TRAIN_MAP: Dict[str, str] = {
    "T2": "train_C",
    "T3": "train_1B",
    "T4": "train_2B",
    "T5": "train_3B",
    "T6": "train_SS",
    "T7": "train_LF",
    "T8": "train_CF",
    "T9": "train_RF",
}


def _coerce_yes_no_to_bool(series: pd.Series) -> pd.Series:
    """Convert common yes/no encodings to booleans."""
    s = series.astype(str).str.strip().str.upper()
    return s.isin(["Y", "YES", "TRUE", "T", "1"])


def _rename_fielding_position_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename fielding position columns into explicit current vs potential names.

    Supports both:
      - OOTP 26 style duplicate columns that pandas mangles to .1
        e.g. P, C, 1B ... and P.1, C.1, 1B.1 ...
      - OOTP 27 style explicit suffixes
        e.g. P, C, 1B ... and P_1, C_1, 1B_1 ...
    """
    rename_map: Dict[str, str] = {}

    for pos in POSITION_COLS:
        cur = pos
        pot_dot = f"{pos}.1"  # old pandas-mangled duplicate style
        pot_us = f"{pos}_1"  # new OOTP 27 explicit style

        if cur in df.columns:
            rename_map[cur] = f"fld_{pos}"

        if pot_dot in df.columns:
            rename_map[pot_dot] = f"pot_{pos}"
        elif pot_us in df.columns:
            rename_map[pot_us] = f"pot_{pos}"

    return df.rename(columns=rename_map)


def load_pt_cards_csv(path: Path) -> pd.DataFrame:
    """Load an OOTP26 hitters PT export and normalize key columns.

    What you get back:
      - All original columns (unless renamed for normalization)
      - Stable normalized columns for downstream logic
      - Explicit fielding columns: fld_* and pot_*
      - Trainability columns: train_* and train_*_ok (bool)
      - Computed: name
    """
    df_raw = pd.read_csv(path)

    # Validate required core columns
    missing = [col for col in OOTP26_HITTER_REQUIRED if col not in df_raw.columns]
    if missing:
        raise ValueError(
            f"OOTP26 hitters export missing expected columns: {missing}\n"
            f"Columns found: {list(df_raw.columns)}"
        )

    # 1) Rename known columns to normalized names
    df = df_raw.rename(columns=OOTP26_HITTER_RENAME)

    # 2) Rename duplicate position columns into explicit current vs potential
    df = _rename_fielding_position_columns(df)

    # 3) Compute stable full name
    df["name"] = df["first_name"].astype(str) + " " + df["last_name"].astype(str)

    # 4) Normalize trainability flags
    # Keep the raw T2..T9 columns if present, but also add normalized train_* names.
    for raw_col, norm_col in TRAIN_MAP.items():
        if raw_col in df.columns:
            df[norm_col] = df[raw_col]
            df[f"{norm_col}_ok"] = _coerce_yes_no_to_bool(df[raw_col])
        else:
            # If not present, create safe defaults
            df[norm_col] = ""
            df[f"{norm_col}_ok"] = False

    # 5) Ensure numeric ratings are numeric (important for scoring)
    numeric_cols: Iterable[str] = [
        # Batting
        "babip",
        "contact",
        "gap_power",
        "power",
        "eye",
        "avoid_k",
        "babip_vs_lhp",
        "contact_vs_lhp",
        "gap_vs_lhp",
        "power_vs_lhp",
        "eye_vs_lhp",
        "avoid_k_vs_lhp",
        "babip_vs_rhp",
        "contact_vs_rhp",
        "gap_vs_rhp",
        "power_vs_rhp",
        "eye_vs_rhp",
        "avoid_k_vs_rhp",
        # Fielding components
        "c_blocking",
        "c_framing",
        "c_arm",
        "if_range",
        "if_error",
        "if_arm",
        "turn_dp",
        "of_range",
        "of_error",
        "of_arm",
        # Fielding at position / potential (now explicit)
        *[f"fld_{p}" for p in POSITION_COLS],
        *[f"pot_{p}" for p in POSITION_COLS],
        # Running
        "speed",
        "stealing_ability",
        "stealing_aggressiveness",
        "baserunning",
        # PT year sometimes comes through numeric
        "pt_year",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df
