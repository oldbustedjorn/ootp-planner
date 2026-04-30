from __future__ import annotations

import pandas as pd

from ootp_opt.roster.rules import Ruleset


TIER_ORDER = {
    "iron": 0,
    "bronze": 1,
    "silver": 2,
    "gold": 3,
    "diamond": 4,
    "perfect": 5,
}


def filter_eligible_hitters(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    return filter_eligible_players(df, ruleset)


def filter_eligible_pitchers(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    return filter_eligible_players(df, ruleset)


def filter_eligible_players(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    filtered = df.copy()

    filtered = apply_tier_filter(filtered, ruleset)
    filtered = apply_card_value_filter(filtered, ruleset)
    filtered = apply_live_filter(filtered, ruleset)
    filtered = apply_card_year_filter(filtered, ruleset)

    return filtered.copy()


def apply_tier_filter(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    if ruleset.tier_min is None and ruleset.tier_max is None:
        return df

    if "pt_tier" not in df.columns:
        raise ValueError("Cannot apply tier filter: missing column 'pt_tier'.")

    min_rank = tier_rank(ruleset.tier_min) if ruleset.tier_min else None
    max_rank = tier_rank(ruleset.tier_max) if ruleset.tier_max else None

    def allowed(tier: object) -> bool:
        rank = tier_rank(str(tier))
        if min_rank is not None and rank < min_rank:
            return False
        if max_rank is not None and rank > max_rank:
            return False
        return True

    return df.loc[df["pt_tier"].apply(allowed)].copy()


def apply_card_value_filter(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    if ruleset.card_value_min is None and ruleset.card_value_max is None:
        return df

    if "card_value" not in df.columns:
        raise ValueError("Cannot apply card value filter: missing column 'card_value'.")

    values = pd.to_numeric(df["card_value"], errors="coerce")
    mask = pd.Series(True, index=df.index)

    if ruleset.card_value_min is not None:
        mask &= values >= ruleset.card_value_min

    if ruleset.card_value_max is not None:
        mask &= values <= ruleset.card_value_max

    return df.loc[mask].copy()


def apply_live_filter(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    mode = ruleset.live_mode.lower()

    if mode == "all":
        return df

    if "pt_type" not in df.columns:
        raise ValueError("Cannot apply live filter: missing column 'pt_type'.")

    is_live = df["pt_type"].astype(str).str.lower().str.contains("live", na=False)

    if mode == "live":
        return df.loc[is_live].copy()

    if mode == "non_live":
        return df.loc[~is_live].copy()

    raise ValueError(
        f"Unknown live_mode '{ruleset.live_mode}'. Expected 'all', 'live', or 'non_live'."
    )


def apply_card_year_filter(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    if ruleset.card_year_min is None and ruleset.card_year_max is None:
        return df

    if "pt_year" not in df.columns:
        raise ValueError("Cannot apply card year filter: missing column 'pt_year'.")

    years = pd.to_numeric(df["pt_year"], errors="coerce")
    mask = pd.Series(True, index=df.index)

    if ruleset.card_year_min is not None:
        mask &= years >= ruleset.card_year_min

    if ruleset.card_year_max is not None:
        mask &= years <= ruleset.card_year_max

    return df.loc[mask].copy()


def tier_rank(tier: str) -> int:
    normalized = str(tier).strip().lower()

    if normalized not in TIER_ORDER:
        raise ValueError(
            f"Unknown card tier '{tier}'. Expected one of: {list(TIER_ORDER.keys())}"
        )

    return TIER_ORDER[normalized]