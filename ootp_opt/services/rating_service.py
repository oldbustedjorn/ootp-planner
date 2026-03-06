from __future__ import annotations
from ootp_opt.domain.rating import add_hitter_and_position_scores, HitterRoleWeights

from pathlib import Path
from typing import Literal

import pandas as pd

from ootp_opt.domain.rating import (
    RatingWeights,
    PitcherRatingWeights,
    rate_hitters_basic,
    rate_pitchers_basic,
    add_pitcher_role_scores,
    PitcherRoleWeights,
)

from ootp_opt.ingest.pt_hitters import load_pt_cards_csv
from ootp_opt.ingest.pt_pitchers import load_pt_pitchers_csv


Profile = Literal["hitters", "pitchers"]


def rate_cards_service(input_path: Path, profile: Profile = "hitters") -> pd.DataFrame:
    """End-to-end: ingest → rate → sort."""

    if profile == "hitters":
        df = load_pt_cards_csv(input_path)
        scored = add_hitter_and_position_scores(df, HitterRoleWeights())
        # Default sort: overall bat (you can switch to a position column anytime)
        return scored.sort_values("hitter_score_overall", ascending=False)

    elif profile == "pitchers":
        df = load_pt_pitchers_csv(input_path)

        # Add starter / reliever role scores
        scored = add_pitcher_role_scores(df, PitcherRoleWeights())

        # Default sort: starter overall (easiest for rotation building)
        return scored.sort_values("starter_score_overall", ascending=False)

    else:
        raise ValueError(f"Unknown profile: {profile}")