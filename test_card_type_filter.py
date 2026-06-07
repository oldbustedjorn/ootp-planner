import pandas as pd

from ootp_opt.roster.eligibility import filter_eligible_players
from ootp_opt.roster.rules import build_ruleset_from_base_profile


def base_config() -> dict:
    return {
        "roster_build_defaults": {
            "live_mode": "all",
            "allowed_card_types": [],
            "excluded_card_types": [],
        },
        "roster": {
            "default_base_profile": "standard_pt",
        },
        "roster_base_profiles": {
            "standard_pt": {
                "mode": "standard_pt",
                "hitter_count": 13,
                "pitcher_count": 13,
                "dh_enabled": True,
                "platoons_allowed": False,
                "lineup_fill_order": [
                    "C",
                    "SS",
                    "CF",
                    "2B",
                    "3B",
                    "LF",
                    "RF",
                    "1B",
                    "DH",
                ],
                "rotation_size": 5,
                "primary_rp_count": 6,
                "specialist_lhp_count": 1,
                "long_man_count": 1,
                "bench_roles": ["C", "IF", "OF", "UTIL"],
                "bench_role_requirements": {
                    "C": {"required_positions": ["C"]},
                    "IF": {"required_positions": ["SS", "2B"]},
                    "OF": {"required_positions": ["CF", "LF", "RF"]},
                    "UTIL": {"required_positions_any": ["C", "SS", "CF"]},
                },
            }
        },
    }


def sample_cards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"name": "A", "pt_type": "Live", "pt_tier": "gold"},
            {"name": "B", "pt_type": "Historical Legend", "pt_tier": "gold"},
            {"name": "C", "pt_type": "Future Legend", "pt_tier": "gold"},
        ]
    )


def test_allowed_card_types_filter_exact_pt_type_values():
    ruleset = build_ruleset_from_base_profile(
        base_config(),
        "standard_pt",
        overrides={"allowed_card_types": ["historical legend", "future legend"]},
    )

    filtered = filter_eligible_players(sample_cards(), ruleset)

    assert filtered["name"].tolist() == ["B", "C"]


def test_excluded_card_types_filter_exact_pt_type_values():
    ruleset = build_ruleset_from_base_profile(
        base_config(),
        "standard_pt",
        overrides={"excluded_card_types": ["live"]},
    )

    filtered = filter_eligible_players(sample_cards(), ruleset)

    assert filtered["name"].tolist() == ["B", "C"]


def test_allowed_and_excluded_card_types_can_be_combined():
    ruleset = build_ruleset_from_base_profile(
        base_config(),
        "standard_pt",
        overrides={
            "allowed_card_types": ["live", "historical legend", "future legend"],
            "excluded_card_types": ["future legend"],
        },
    )

    filtered = filter_eligible_players(sample_cards(), ruleset)

    assert filtered["name"].tolist() == ["A", "B"]
