import pandas as pd
import pytest

from ootp_opt.domain.rating import (
    HitterRoleWeights,
    PitcherRoleWeights,
    add_hitter_and_position_scores,
    add_pitcher_role_scores,
)
from ootp_opt.domain.scoring_environment import (
    apply_scoring_environment_to_config,
    resolve_scoring_environment,
)
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.services.rating_service import build_pitcher_weights


def sample_config():
    return {
        "roster": {"default_base_profile": "standard_pt"},
        "roster_build_defaults": {"scoring_environment": "auto"},
        "roster_base_profiles": {
            "standard_pt": sample_profile("standard_pt"),
            "playoff_pt": sample_profile("playoff_pt"),
        },
        "scoring_environments": {
            "gold": {
                "hitters": {
                    "power_midpoint": 92,
                    "avoid_k_midpoint": 95,
                    "babip_midpoint": 97,
                    "gap_midpoint": 90,
                    "eye_midpoint": 97,
                },
                "pitchers": {
                    "vs_rhb_weight": 0.60,
                    "vs_lhb_weight": 0.40,
                    "rp_stuff_midpoint": 95,
                    "hra_midpoint": 92,
                    "pbabip_midpoint": 97,
                    "control_midpoint": 97,
                    "control_floor": 55,
                    "control_floor_penalty": 2.5,
                }
            },
            "open": {
                "pitchers": {
                    "vs_rhb_weight": 0.50,
                    "vs_lhb_weight": 0.50,
                    "rp_stuff_midpoint": 115,
                }
            },
        },
    }


def sample_profile(mode: str):
    return {
        "mode": mode,
        "hitter_count": 2,
        "pitcher_count": 12,
        "dh_enabled": True,
        "platoons_allowed": False,
        "lineup_fill_order": ["C"],
        "rotation_size": 4,
        "primary_rp_count": 6,
        "specialist_lhp_count": 1,
        "long_man_count": 1,
        "bench_roles": ["UTIL"],
        "bench_role_requirements": {
            "UTIL": {
                "required_positions": [],
                "required_positions_any": ["C"],
                "preferred_positions": ["C"],
            }
        },
    }


def test_auto_scoring_environment_uses_tier_max():
    cfg = sample_config()
    ruleset = build_ruleset_from_base_profile(
        cfg,
        "playoff_pt",
        overrides={"tier_max": "gold"},
    )

    environment = resolve_scoring_environment(cfg, ruleset)

    assert environment.name == "gold"
    assert environment.source == "auto"


def test_standard_pt_auto_scoring_environment_uses_open():
    cfg = sample_config()
    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    environment = resolve_scoring_environment(cfg, ruleset)

    assert environment.name == "open"


def test_explicit_scoring_environment_overrides_auto():
    cfg = sample_config()
    ruleset = build_ruleset_from_base_profile(
        cfg,
        "playoff_pt",
        overrides={"tier_max": "gold", "scoring_environment": "open"},
    )

    environment = resolve_scoring_environment(cfg, ruleset)

    assert environment.name == "open"
    assert environment.source == "explicit"


def test_apply_scoring_environment_updates_pitcher_config_without_mutating_base():
    cfg = sample_config()
    ruleset = build_ruleset_from_base_profile(
        cfg,
        "playoff_pt",
        overrides={"tier_max": "gold"},
    )
    environment = resolve_scoring_environment(cfg, ruleset)

    adjusted = apply_scoring_environment_to_config(cfg, environment)

    assert adjusted["pitchers"]["rp_stuff_midpoint"] == 95
    assert adjusted["pitchers"]["hra_midpoint"] == 92
    assert adjusted["pitchers"]["pbabip_midpoint"] == 97
    assert adjusted["pitchers"]["control_midpoint"] == 97
    assert adjusted["pitchers"]["control_floor"] == 55
    assert adjusted["pitchers"]["control_floor_penalty"] == 2.5
    assert adjusted["hitters"]["power_midpoint"] == 92
    assert adjusted["hitters"]["avoid_k_midpoint"] == 95
    assert adjusted["hitters"]["babip_midpoint"] == 97
    assert adjusted["hitters"]["gap_midpoint"] == 90
    assert adjusted["hitters"]["eye_midpoint"] == 97
    assert "pitchers" not in cfg
    assert "hitters" not in cfg


def test_unknown_scoring_environment_has_useful_error():
    cfg = sample_config()
    ruleset = build_ruleset_from_base_profile(
        cfg,
        "playoff_pt",
        overrides={"scoring_environment": "missing"},
    )

    with pytest.raises(ValueError, match="Scoring environment 'missing' not found"):
        resolve_scoring_environment(cfg, ruleset)


def test_higher_stuff_midpoint_increases_elite_stuff_separation():
    pitchers = pd.DataFrame(
        [
            pitcher("Elite Stuff", stuff=140),
            pitcher("Good Stuff", stuff=116),
        ]
    )

    low_env = add_pitcher_role_scores(
        pitchers,
        PitcherRoleWeights(
            use_nonlinear_transforms=True,
            rp_stuff=1.0,
            rp_stuff_midpoint=91,
            rp_pbabip=0.0,
            rp_hr_rate=0.0,
            rp_control=0.0,
        ),
    )
    high_env = add_pitcher_role_scores(
        pitchers,
        PitcherRoleWeights(
            use_nonlinear_transforms=True,
            rp_stuff=1.0,
            rp_stuff_midpoint=115,
            rp_pbabip=0.0,
            rp_hr_rate=0.0,
            rp_control=0.0,
        ),
    )

    assert score_gap(high_env) > score_gap(low_env)


def test_environment_midpoints_shift_other_pitcher_component_curves():
    pitchers = pd.DataFrame(
        [
            pitcher(
                "High Components",
                stuff=100,
                hr_rate=120,
                pbabip=120,
                control=120,
            ),
            pitcher(
                "Average Components",
                stuff=100,
                hr_rate=95,
                pbabip=95,
                control=95,
            ),
        ]
    )

    low_env = add_pitcher_role_scores(
        pitchers,
        PitcherRoleWeights(
            use_nonlinear_transforms=True,
            rp_stuff=0.0,
            rp_pbabip=1.0,
            rp_hr_rate=1.0,
            rp_control=1.0,
            rp_pbabip_midpoint=87,
            rp_hr_rate_midpoint=72,
            rp_control_midpoint=82,
        ),
    )
    high_env = add_pitcher_role_scores(
        pitchers,
        PitcherRoleWeights(
            use_nonlinear_transforms=True,
            rp_stuff=0.0,
            rp_pbabip=1.0,
            rp_hr_rate=1.0,
            rp_control=1.0,
            rp_pbabip_midpoint=122,
            rp_hr_rate_midpoint=108,
            rp_control_midpoint=105,
        ),
    )

    assert component_score_gap(high_env) > component_score_gap(low_env)


def test_generic_pitcher_environment_midpoints_are_reference_only_by_default():
    weights = build_pitcher_weights(
        {
            "pitchers": {
                "hra_midpoint": 120,
                "pbabip_midpoint": 120,
                "control_midpoint": 120,
            }
        }
    )

    assert weights.rp_hr_rate_midpoint is None
    assert weights.rp_pbabip_midpoint is None
    assert weights.rp_control_midpoint is None
    assert weights.sp_hr_rate_midpoint is None
    assert weights.sp_pbabip_midpoint is None
    assert weights.sp_control_midpoint is None


def test_pitcher_control_floor_penalizes_low_control():
    pitchers = pd.DataFrame(
        [
            pitcher("Adequate Control", stuff=100, control=60),
            pitcher("Low Control", stuff=100, control=45),
        ]
    )

    scored = add_pitcher_role_scores(
        pitchers,
        PitcherRoleWeights(
            use_nonlinear_transforms=True,
            rp_stuff=0.0,
            rp_pbabip=0.0,
            rp_hr_rate=0.0,
            rp_control=0.0,
            rp_control_floor=55,
            rp_control_floor_penalty=2.5,
        ),
    )

    by_name = scored.set_index("name")
    assert (
        by_name.loc["Adequate Control", "reliever_score_overall"]
        - by_name.loc["Low Control", "reliever_score_overall"]
    ) == pytest.approx(25.0)


def test_hitter_environment_midpoints_shift_component_curves():
    hitters = pd.DataFrame(
        [
            hitter("High Components", 125),
            hitter("Average Components", 95),
        ]
    )

    low_env = add_hitter_and_position_scores(
        hitters,
        HitterRoleWeights(
            use_nonlinear_transforms=True,
            power=1.0,
            eye=1.0,
            gap_power=1.0,
            babip=1.0,
            avoid_k=1.0,
            power_midpoint=70,
            eye_midpoint=70,
            gap_midpoint=70,
            babip_midpoint=70,
            avoid_k_midpoint=70,
            min_pos_rating=0.0,
        ),
    )
    high_env = add_hitter_and_position_scores(
        hitters,
        HitterRoleWeights(
            use_nonlinear_transforms=True,
            power=1.0,
            eye=1.0,
            gap_power=1.0,
            babip=1.0,
            avoid_k=1.0,
            power_midpoint=110,
            eye_midpoint=110,
            gap_midpoint=110,
            babip_midpoint=110,
            avoid_k_midpoint=110,
            min_pos_rating=0.0,
        ),
    )

    assert hitter_score_gap(high_env) > hitter_score_gap(low_env)


def pitcher(
    name: str,
    stuff: int,
    hr_rate: int = 100,
    pbabip: int = 100,
    control: int = 100,
):
    return {
        "name": name,
        "stuff_vs_lhb": stuff,
        "stuff_vs_rhb": stuff,
        "movement_vs_lhb": 100,
        "movement_vs_rhb": 100,
        "control_vs_lhb": control,
        "control_vs_rhb": control,
        "pbabip_vs_lhb": pbabip,
        "pbabip_vs_rhb": pbabip,
        "hr_rate_vs_lhb": hr_rate,
        "hr_rate_vs_rhb": hr_rate,
        "stamina": 25,
    }


def hitter(name: str, rating: int):
    return {
        "name": name,
        "contact": rating,
        "power": rating,
        "eye": rating,
        "gap_power": rating,
        "babip": rating,
        "avoid_k": rating,
        "contact_vs_lhp": rating,
        "power_vs_lhp": rating,
        "eye_vs_lhp": rating,
        "gap_vs_lhp": rating,
        "babip_vs_lhp": rating,
        "avoid_k_vs_lhp": rating,
        "contact_vs_rhp": rating,
        "power_vs_rhp": rating,
        "eye_vs_rhp": rating,
        "gap_vs_rhp": rating,
        "babip_vs_rhp": rating,
        "avoid_k_vs_rhp": rating,
        "speed": 0,
        "baserunning": 0,
        "stealing_ability": 0,
        "stealing_aggressiveness": 0,
    }


def score_gap(scored: pd.DataFrame) -> float:
    by_name = scored.set_index("name")
    return (
        by_name.loc["Elite Stuff", "reliever_score_overall"]
        - by_name.loc["Good Stuff", "reliever_score_overall"]
    )


def component_score_gap(scored: pd.DataFrame) -> float:
    by_name = scored.set_index("name")
    return (
        by_name.loc["High Components", "reliever_score_overall"]
        - by_name.loc["Average Components", "reliever_score_overall"]
    )


def hitter_score_gap(scored: pd.DataFrame) -> float:
    by_name = scored.set_index("name")
    return (
        by_name.loc["High Components", "batting_score_overall"]
        - by_name.loc["Average Components", "batting_score_overall"]
    )
