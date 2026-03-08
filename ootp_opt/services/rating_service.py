from __future__ import annotations

from pathlib import Path
from typing import Literal, Any

from ootp_opt.services.shortlist_service import generate_hitter_shortlists

import pandas as pd

from ootp_opt.domain.rating import (
    RatingWeights,
    PitcherRatingWeights,
    rate_hitters_basic,
    rate_pitchers_basic,
    add_pitcher_role_scores,
    PitcherRoleWeights,
    add_hitter_and_position_scores,
    HitterRoleWeights,
)
from ootp_opt.ingest.pt_hitters import load_pt_cards_csv
from ootp_opt.ingest.pt_pitchers import load_pt_pitchers_csv

Profile = Literal["hitters", "pitchers"]


def rate_cards_service(
    input_path: Path,
    profile: Profile = "hitters",
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    config = config or {}

    if profile == "hitters":
        df = load_pt_cards_csv(input_path)

        hitter_cfg = config.get("hitters", {})
        hitter_weights = HitterRoleWeights(
            defense_scale=hitter_cfg.get("defense_scale", 0.70),
            vs_rhp_weight=hitter_cfg.get("vs_rhp_weight", 0.70),
            vs_lhp_weight=hitter_cfg.get("vs_lhp_weight", 0.30),
        )

        scored = add_hitter_and_position_scores(df, hitter_weights)
        shortlists = generate_hitter_shortlists(scored)

        shortlist_path = Path(config.get("paths", {}).get("output_dir", "outputs")) / "shortlists_hitters.csv"
        shortlists.to_csv(shortlist_path, index=False)

        return scored.sort_values("hitter_score_overall", ascending=False)

    elif profile == "pitchers":
        df = load_pt_pitchers_csv(input_path)

        pitcher_cfg = config.get("pitchers", {})
        pitcher_weights = PitcherRoleWeights(
            starter_min_stamina=pitcher_cfg.get("starter_min_stamina", 60),
            starter_min_good_pitches=pitcher_cfg.get("starter_min_good_pitches", 3),
            starter_stamina_gate_penalty=pitcher_cfg.get("starter_stamina_gate_penalty", 1_000_000),
            starter_pitch_gate_penalty=pitcher_cfg.get("starter_pitch_gate_penalty", 250_000),
            vs_rhb_weight=pitcher_cfg.get("vs_rhb_weight", 0.70),
            vs_lhb_weight=pitcher_cfg.get("vs_lhb_weight", 0.30),
        )

        scored = add_pitcher_role_scores(df, pitcher_weights)
        return scored.sort_values("starter_score_overall", ascending=False)

    else:
        raise ValueError(f"Unknown profile: {profile}")