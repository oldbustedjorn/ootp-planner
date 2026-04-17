from __future__ import annotations

import pandas as pd

from ootp_opt.roster.rules import Ruleset


def filter_eligible_hitters(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    return df.copy()


def filter_eligible_pitchers(df: pd.DataFrame, ruleset: Ruleset) -> pd.DataFrame:
    return df.copy()


def summarize_pool(df):
    return {
        "count": len(df),
        "columns": list(df.columns),
    }
