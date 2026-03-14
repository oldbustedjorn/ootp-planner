from __future__ import annotations

from pathlib import Path
from typing import Literal, Any

from ootp_opt.services.shortlist_service import generate_hitter_shortlists
from ootp_opt.export.csv_export import write_csv

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
        blend_cfg = config.get("position_blends", {})

        hitter_weights = HitterRoleWeights(
            contact=hitter_cfg.get("contact", 1.00),
            power=hitter_cfg.get("power", 1.20),
            eye=hitter_cfg.get("eye", 0.85),
            gap_power=hitter_cfg.get("gap_power", 0.55),
            babip=hitter_cfg.get("babip", 0.35),
            avoid_k=hitter_cfg.get("avoid_k", 0.40),

            fld_pos=hitter_cfg.get("fld_pos", 1.00),
            c_framing=hitter_cfg.get("c_framing", 1.20),
            c_blocking=hitter_cfg.get("c_blocking", 0.90),
            c_arm=hitter_cfg.get("c_arm", 0.70),
            if_range=hitter_cfg.get("if_range", 1.10),
            if_error=hitter_cfg.get("if_error", 0.60),
            if_arm=hitter_cfg.get("if_arm", 0.70),
            turn_dp=hitter_cfg.get("turn_dp", 0.60),
            of_range=hitter_cfg.get("of_range", 1.10),
            of_error=hitter_cfg.get("of_error", 0.55),
            of_arm=hitter_cfg.get("of_arm", 0.65),

            min_pos_rating=hitter_cfg.get("min_pos_rating", 1.0),
            defense_scale=hitter_cfg.get("defense_scale", 0.70),
            vs_rhp_weight=hitter_cfg.get("vs_rhp_weight", 0.70),
            vs_lhp_weight=hitter_cfg.get("vs_lhp_weight", 0.30),

            pr_speed=hitter_cfg.get("pr_speed", 1.00),
            pr_baserunning=hitter_cfg.get("pr_baserunning", 0.80),
            pr_stealing_ability=hitter_cfg.get("pr_stealing_ability", 0.70),
            pr_stealing_aggressiveness=hitter_cfg.get("pr_stealing_aggressiveness", 0.40),

            pos_blend={
                pos: tuple(vals)
                for pos, vals in blend_cfg.items()
            } if blend_cfg else {
                "C": (0.90, 1.10),
                "SS": (0.92, 1.05),
                "CF": (0.93, 1.03),
                "2B": (0.94, 1.00),
                "3B": (0.95, 0.98),
                "RF": (0.96, 0.95),
                "LF": (0.97, 0.92),
                "1B": (0.98, 0.80),
            },
        )

        scored = add_hitter_and_position_scores(df, hitter_weights)
        scored = scored.sort_values("batting_score_overall", ascending=False)

        # Also write hitter shortlists during the default rating flow
        output_dir = Path(config.get("paths", {}).get("output_dir", "outputs"))
        shortlist_path = output_dir / "shortlists_hitters.csv"
        shortlists = generate_hitter_shortlists(scored, top_n=15)
        write_csv(shortlists, shortlist_path)

        return scored

    elif profile == "pitchers":
        df = load_pt_pitchers_csv(input_path)

        pitcher_cfg = config.get("pitchers", {})

        pitcher_weights = PitcherRoleWeights(
            vs_rhb_weight=pitcher_cfg.get("vs_rhb_weight", 0.70),
            vs_lhb_weight=pitcher_cfg.get("vs_lhb_weight", 0.30),

            sp_stuff=pitcher_cfg.get("sp_stuff", 1.00),
            sp_movement=pitcher_cfg.get("sp_movement", 0.00),
            sp_pbabip=pitcher_cfg.get("sp_pbabip", 1.30),
            sp_hr_rate=pitcher_cfg.get("sp_hr_rate", 1.20),
            sp_control=pitcher_cfg.get("sp_control", 0.80),

            rp_stuff=pitcher_cfg.get("rp_stuff", 1.30),
            rp_movement=pitcher_cfg.get("rp_movement", 0.00),
            rp_pbabip=pitcher_cfg.get("rp_pbabip", 1.10),
            rp_hr_rate=pitcher_cfg.get("rp_hr_rate", 1.00),
            rp_control=pitcher_cfg.get("rp_control", 0.80),

            stamina=pitcher_cfg.get("stamina", 0.00),
            pitch_count=pitcher_cfg.get("pitch_count", 8.0),
            pitch_threshold=pitcher_cfg.get("pitch_threshold", 60.0),

            starter_min_stamina=pitcher_cfg.get("starter_min_stamina", 60),
            starter_min_good_pitches=pitcher_cfg.get("starter_min_good_pitches", 3),
            starter_stamina_gate_penalty=pitcher_cfg.get("starter_stamina_gate_penalty", 1_000_000),
            starter_pitch_gate_penalty=pitcher_cfg.get("starter_pitch_gate_penalty", 250_000),
        )

        scored = add_pitcher_role_scores(df, pitcher_weights)
        return scored.sort_values("starter_score_overall", ascending=False)

    else:
        raise ValueError(f"Unknown profile: {profile}")