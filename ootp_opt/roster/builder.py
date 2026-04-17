from __future__ import annotations

import pandas as pd

from ootp_opt.roster.models import PitcherRoster
from ootp_opt.roster.rules import Ruleset


def select_top_n(
    df: pd.DataFrame,
    score_col: str,
    n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if score_col not in df.columns:
        raise ValueError(f"Missing required score column: {score_col}")

    selected = df.sort_values(score_col, ascending=False).head(n).copy()

    remaining = df.drop(index=selected.index).copy()
    return selected, remaining


def build_pitcher_roster(df: pd.DataFrame, ruleset: Ruleset) -> PitcherRoster:
    remaining = df.copy()

    rotation, remaining = select_top_n(
        remaining,
        score_col="starter_score_overall",
        n=ruleset.rotation_size,
    )

    bullpen, remaining = select_top_n(
        remaining,
        score_col="reliever_score_overall",
        n=ruleset.primary_rp_count,
    )

    lefty_specialist, remaining = select_top_n(
        remaining,
        score_col="reliever_score_vs_lhb",
        n=ruleset.specialist_lhp_count,
    )

    long_man, remaining = select_top_n(
        remaining,
        score_col="starter_score_overall",
        n=ruleset.long_man_count,
    )

    return PitcherRoster(
        rotation=rotation,
        bullpen=bullpen,
        lefty_specialist=lefty_specialist,
        long_man=long_man,
        unused_players=remaining,
    )
