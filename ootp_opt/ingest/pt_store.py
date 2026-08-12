from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

POSITION_CODE_MAP = {
    1: "P",
    2: "C",
    3: "1B",
    4: "2B",
    5: "3B",
    6: "SS",
    7: "LF",
    8: "CF",
    9: "RF",
    10: "DH",
}


PT_TYPE_CODE_MAP = {
    1: "2026Live",
    2: "NeL",
    3: "RS",
    4: "Leg",
    5: "AS",
    6: "FL",
    7: "Snap",
    8: "UnH",
    9: "HaH",
    10: "VET",
}


STORE_RENAME = {
    "//Card Title": "card_title",
    "Card Title": "card_title",
    "Card ID": "player_id",
    "Card Value": "card_value",
    "Card Type": "pt_type",
    "Card Sub Type": "pt_subtype",
    "Card Series": "pt_series",
    "Year": "pt_year",
    "Team": "pt_card_team",
    "Franchise": "pt_card_franchise",
    "LastName": "last_name",
    "FirstName": "first_name",
    "Bats": "bats",
    "Throws": "throws",
    "Position": "store_position_code",
    "Pitcher Role": "store_pitcher_role",
    "tier": "pt_tier_code",
    "owned": "owned_count",
    "Buy Order High": "buy_order_high",
    "Sell Order Low": "sell_order_low",
    "Last 10 Price": "last_10_price",
    # Hitting
    "BABIP": "babip",
    "Contact": "contact",
    "Gap": "gap_power",
    "Power": "power",
    "Eye": "eye",
    "Avoid Ks": "avoid_k",
    "BABIP vL": "babip_vs_lhp",
    "Contact vL": "contact_vs_lhp",
    "Gap vL": "gap_vs_lhp",
    "Power vL": "power_vs_lhp",
    "Eye vL": "eye_vs_lhp",
    "Avoid K vL": "avoid_k_vs_lhp",
    "BABIP vR": "babip_vs_rhp",
    "Contact vR": "contact_vs_rhp",
    "Gap vR": "gap_vs_rhp",
    "Power vR": "power_vs_rhp",
    "Eye vR": "eye_vs_rhp",
    "Avoid K vR": "avoid_k_vs_rhp",
    # Running
    "Speed": "speed",
    "Stealing": "stealing_ability",
    "Steal Rate": "stealing_aggressiveness",
    "Baserunning": "baserunning",
    "Sac bunt": "sac_bunt",
    "Bunt for hit": "bunt_hit",
    # Pitching
    "Stuff": "stuff",
    "Movement": "movement",
    "Control": "control",
    "pHR": "hr_rate",
    "pBABIP": "pbabip",
    "Stuff vL": "stuff_vs_lhb",
    "Movement vL": "movement_vs_lhb",
    "Control vL": "control_vs_lhb",
    "pHR vL": "hr_rate_vs_lhb",
    "pBABIP vL": "pbabip_vs_lhb",
    "Stuff vR": "stuff_vs_rhb",
    "Movement vR": "movement_vs_rhb",
    "Control vR": "control_vs_rhb",
    "pHR vR": "hr_rate_vs_rhb",
    "pBABIP vR": "pbabip_vs_rhb",
    # Arsenal
    "Fastball": "pitch_fb",
    "Changeup": "pitch_ch",
    "Curveball": "pitch_cb",
    "Slider": "pitch_sl",
    "Sinker": "pitch_si",
    "Splitter": "pitch_sp",
    "Cutter": "pitch_ct",
    "Forkball": "pitch_fo",
    "Circlechange": "pitch_cc",
    "Screwball": "pitch_sc",
    "Knucklecurve": "pitch_kc",
    "Knuckleball": "pitch_kn",
    # Pitching profile
    "Stamina": "stamina",
    "Hold": "hold",
    "GB": "gb_fb",
    "Velocity": "velocity",
    "Arm Slot": "arm_slot",
    # Fielding components
    "CatcherAbil": "c_blocking",
    "CatcherFrame": "c_framing",
    "Catcher Arm": "c_arm",
    "Infield Range": "if_range",
    "Infield Error": "if_error",
    "Infield Arm": "if_arm",
    "DP": "turn_dp",
    "OF Range": "of_range",
    "OF Error": "of_error",
    "OF Arm": "of_arm",
    # Position ratings
    "Pos Rating P": "fld_P",
    "Pos Rating C": "fld_C",
    "Pos Rating 1B": "fld_1B",
    "Pos Rating 2B": "fld_2B",
    "Pos Rating 3B": "fld_3B",
    "Pos Rating SS": "fld_SS",
    "Pos Rating LF": "fld_LF",
    "Pos Rating CF": "fld_CF",
    "Pos Rating RF": "fld_RF",
    # Trainability
    "LearnC": "train_C",
    "Learn1B": "train_1B",
    "Learn2B": "train_2B",
    "Learn3B": "train_3B",
    "LearnSS": "train_SS",
    "LearnLF": "train_LF",
    "LearnCF": "train_CF",
    "LearnRF": "train_RF",
}


TIER_CODE_TO_NAME = {
    0: "iron",
    1: "bronze",
    2: "silver",
    3: "gold",
    4: "diamond",
    5: "perfect",
}


NUMERIC_COLS = [
    "player_id",
    "card_value",
    "pt_year",
    "store_position_code",
    "store_pitcher_role",
    "pt_tier_code",
    "owned_count",
    "buy_order_high",
    "sell_order_low",
    "last_10_price",
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
    "speed",
    "stealing_ability",
    "stealing_aggressiveness",
    "baserunning",
    "sac_bunt",
    "bunt_hit",
    "stuff",
    "movement",
    "control",
    "hr_rate",
    "pbabip",
    "stuff_vs_lhb",
    "movement_vs_lhb",
    "control_vs_lhb",
    "hr_rate_vs_lhb",
    "pbabip_vs_lhb",
    "stuff_vs_rhb",
    "movement_vs_rhb",
    "control_vs_rhb",
    "hr_rate_vs_rhb",
    "pbabip_vs_rhb",
    "pitch_fb",
    "pitch_ch",
    "pitch_cb",
    "pitch_sl",
    "pitch_si",
    "pitch_sp",
    "pitch_ct",
    "pitch_fo",
    "pitch_cc",
    "pitch_sc",
    "pitch_kc",
    "pitch_kn",
    "stamina",
    "hold",
    "gb_fb",
    "fld_P",
    "fld_C",
    "fld_1B",
    "fld_2B",
    "fld_3B",
    "fld_SS",
    "fld_LF",
    "fld_CF",
    "fld_RF",
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
]

INTEGER_COLS = [
    "player_id",
    "card_value",
    "pt_year",
    "pt_type",
    "store_position_code",
    "store_pitcher_role",
    "pt_tier_code",
    "owned_count",
    "buy_order_high",
    "sell_order_low",
    "last_10_price",
]

def load_pt_store_csv(path: str | Path) -> pd.DataFrame:
    df_raw = pd.read_csv(path, index_col=False)
    df_raw.columns = [str(col).strip() for col in df_raw.columns]

    df = df_raw.rename(columns=STORE_RENAME).copy()

    # Preserve raw store-export classification fields for debugging/future rules.
    if "pt_type" in df.columns:
        df["pt_type_raw"] = df["pt_type"]

    if "pt_subtype" in df.columns:
        df["pt_subtype_raw"] = df["pt_subtype"]

    if "pt_series" in df.columns:
        df["pt_series_raw"] = df["pt_series"]

    require_columns(df, ["player_id", "card_title", "store_position_code"])

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df[df["player_id"].notna()]
    df = df[pd.to_numeric(df["player_id"], errors="coerce").fillna(0) > 0].copy()

    coerce_integer_columns(df)

    df["name"] = build_name(df)

    df["store_position"] = (
        df["store_position_code"].astype(int).map(POSITION_CODE_MAP).fillna("")
    )

    if "pt_tier_code" in df.columns:
        df["pt_tier"] = df["pt_tier_code"].astype(int).map(TIER_CODE_TO_NAME).fillna("")
    else:
        df["pt_tier"] = ""

    df["pt_on_active"] = False
    df["pt_title"] = df.get("card_title", "")
    df["is_clubhouse_card"] = (
        df["card_title"]
        .fillna("")
        .astype(str)
        .str.contains("clubhouse", case=False, regex=False)
    )

    df["has_buy_order"] = get_numeric_series(df, "buy_order_high") > 0
    df["has_sell_order"] = get_numeric_series(df, "sell_order_low") > 0

    normalize_pt_type_from_code(df)
    normalize_store_bats_throws(df)

    df["owned_count"] = get_numeric_series(df, "owned_count").astype(int)

    df["is_owned"] = df["owned_count"] > 0

    add_train_ok_columns(df)

    return df


def split_store_hitters_pitchers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "store_position" not in df.columns:
        raise ValueError("Store DataFrame missing normalized column 'store_position'.")

    pitcher_mask = df["store_position"].astype(str).str.upper().eq("P")

    pitchers = df.loc[pitcher_mask].copy()
    hitters = df.loc[~pitcher_mask].copy()

    return hitters, pitchers


def load_pt_store_hitters_pitchers(
    path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = load_pt_store_csv(path)
    return split_store_hitters_pitchers(df)


def build_name(df: pd.DataFrame) -> pd.Series:
    if "first_name" in df.columns:
        first = df["first_name"].astype(str).str.strip()
    else:
        first = pd.Series("", index=df.index)

    if "last_name" in df.columns:
        last = df["last_name"].astype(str).str.strip()
    else:
        last = pd.Series("", index=df.index)

    name = (first + " " + last).str.strip()

    if "card_title" in df.columns:
        fallback = df["card_title"].astype(str).str.strip()
        name = name.where(name.ne(""), fallback)

    return name


def normalize_store_bats_throws(df: pd.DataFrame) -> None:
    # Store export uses numeric handedness in your sample:
    # 1 = R, 2 = L, 3 = S for bats. Throws generally 1 = R, 2 = L.
    if "bats" in df.columns:
        df["bats"] = df["bats"].apply(_decode_bats)

    if "throws" in df.columns:
        df["throws"] = df["throws"].apply(_decode_throws)


def _decode_bats(value: Any) -> str:
    text = str(value).strip().upper()
    if text in {"L", "R", "S"}:
        return text

    try:
        code = int(float(text))
    except ValueError:
        return ""

    return {1: "R", 2: "L", 3: "S"}.get(code, "")


def _decode_throws(value: Any) -> str:
    text = str(value).strip().upper()
    if text in {"L", "R"}:
        return text

    try:
        code = int(float(text))
    except ValueError:
        return ""

    return {1: "R", 2: "L"}.get(code, "")


def add_train_ok_columns(df: pd.DataFrame) -> None:
    new_cols = {}

    for pos in ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]:
        raw_col = f"train_{pos}"
        ok_col = f"{raw_col}_ok"

        if raw_col in df.columns:
            new_cols[ok_col] = pd.to_numeric(df[raw_col], errors="coerce").fillna(0) > 0
        else:
            new_cols[raw_col] = 0
            new_cols[ok_col] = False

    for col_name, values in new_cols.items():
        df[col_name] = values


def require_columns(df: pd.DataFrame, required: list[str]) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"Store export missing required columns after normalization: {missing}\n"
            f"Columns found: {list(df.columns)}"
        )


def get_numeric_series(
    df: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column in df.columns:
        return pd.to_numeric(df[column], errors="coerce").fillna(default)

    return pd.Series(default, index=df.index)


def coerce_integer_columns(df: pd.DataFrame) -> None:
    for col in INTEGER_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)


def normalize_pt_type_from_code(df: pd.DataFrame) -> None:
    if "pt_type_raw" not in df.columns:
        df["pt_type"] = "UNKNOWN"
        return

    codes = pd.to_numeric(df["pt_type_raw"], errors="coerce")
    df["pt_type"] = codes.map(PT_TYPE_CODE_MAP).fillna("UNKNOWN")

    unknown_codes = sorted(codes.loc[df["pt_type"].eq("UNKNOWN")].dropna().unique())
    if unknown_codes:
        print("\nWARNING: Unknown PT card type codes found:")
        for code in unknown_codes[:25]:
            print(f"  {int(code)}")

        if len(unknown_codes) > 25:
            print(f"  ... and {len(unknown_codes) - 25} more")
