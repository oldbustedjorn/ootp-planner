import pandas as pd

from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import build_ruleset_from_tournament_preset
from ootp_opt.roster.tier_slot_report import build_tier_slot_rows, tier_slots_satisfied


def test_tier_slot_rows_count_whole_roster_and_normalize_abbreviations():
    hitter_roster = HitterRoster(
        starters_by_position={
            "C": pd.Series({"pt_tier": "Perfect"}),
            "1B": pd.Series({"pt_tier": "Diamond"}),
        },
        bench_players=pd.DataFrame(
            [
                {"pt_tier": "Gold"},
                {"pt_tier": "Gold"},
            ]
        ),
        unused_players=pd.DataFrame(),
    )

    pitcher_roster = PitcherRoster(
        rotation=pd.DataFrame(
            [
                {"pt_tier": "Perfect"},
                {"pt_tier": "Silver"},
            ]
        ),
        bullpen=pd.DataFrame([{"pt_tier": "Bronze"}]),
        lefty_specialist=pd.DataFrame([{"pt_tier": "Iron"}]),
        long_man=pd.DataFrame([{"pt_tier": "Iron"}]),
        unused_players=pd.DataFrame(),
    )

    rows = build_tier_slot_rows(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        tier_slots={
            "P": 2,
            "D": 3,
            "G": 1,
            "S": 1,
            "B": 1,
            "I": 0,
        },
    )

    by_tier = {row.tier: row for row in rows}

    assert by_tier["perfect"].selected_count == 2
    assert by_tier["perfect"].cumulative_selected == 2
    assert by_tier["perfect"].cumulative_slots == 2
    assert by_tier["perfect"].remaining == 0
    assert not by_tier["perfect"].is_over_limit

    assert by_tier["diamond"].selected_count == 1
    assert by_tier["diamond"].cumulative_selected == 3
    assert by_tier["diamond"].cumulative_slots == 5
    assert by_tier["diamond"].remaining == 2
    assert not by_tier["diamond"].is_over_limit

    assert by_tier["gold"].selected_count == 2
    assert by_tier["gold"].cumulative_selected == 5
    assert by_tier["gold"].cumulative_slots == 6
    assert by_tier["gold"].remaining == 1
    assert not by_tier["gold"].is_over_limit

    assert by_tier["iron"].selected_count == 2
    assert by_tier["iron"].cumulative_selected == 9
    assert by_tier["iron"].cumulative_slots is None
    assert by_tier["iron"].remaining is None
    assert not by_tier["iron"].is_over_limit


def test_iron_slots_are_unlimited_even_when_zero_is_configured():
    hitter_roster = HitterRoster(
        starters_by_position={
            "C": pd.Series({"pt_tier": "Iron"}),
            "1B": pd.Series({"pt_tier": "Iron"}),
        },
        bench_players=pd.DataFrame(
            [
                {"pt_tier": "Iron"},
                {"pt_tier": "Iron"},
            ]
        ),
        unused_players=pd.DataFrame(),
    )

    pitcher_roster = PitcherRoster(
        rotation=pd.DataFrame(
            [
                {"pt_tier": "Perfect"},
                {"pt_tier": "Iron"},
            ]
        ),
        bullpen=pd.DataFrame([{"pt_tier": "Iron"}]),
        lefty_specialist=pd.DataFrame([{"pt_tier": "Iron"}]),
        long_man=pd.DataFrame([{"pt_tier": "Iron"}]),
        unused_players=pd.DataFrame(),
    )

    tier_slots = {"P": 1, "D": 1, "G": 0, "S": 0, "B": 0, "I": 0}
    rows = build_tier_slot_rows(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        tier_slots=tier_slots,
    )
    by_tier = {row.tier: row for row in rows}

    assert tier_slots_satisfied(hitter_roster, pitcher_roster, tier_slots)
    assert by_tier["iron"].selected_count == 8
    assert by_tier["iron"].remaining is None
    assert not by_tier["iron"].is_over_limit


def test_tier_slot_rows_flag_cumulative_over_limit():
    hitter_roster = HitterRoster(
        starters_by_position={
            "C": pd.Series({"pt_tier": "Perfect"}),
            "1B": pd.Series({"pt_tier": "Perfect"}),
        },
        bench_players=pd.DataFrame([{"pt_tier": "Diamond"}]),
        unused_players=pd.DataFrame(),
    )

    pitcher_roster = PitcherRoster(
        rotation=pd.DataFrame(),
        bullpen=pd.DataFrame(),
        lefty_specialist=pd.DataFrame(),
        long_man=pd.DataFrame(),
        unused_players=pd.DataFrame(),
    )

    rows = build_tier_slot_rows(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        tier_slots={
            "P": 1,
            "D": 1,
        },
    )

    by_tier = {row.tier: row for row in rows}

    assert by_tier["perfect"].remaining == -1
    assert by_tier["perfect"].is_over_limit

    assert by_tier["diamond"].remaining == -1
    assert by_tier["diamond"].is_over_limit


def test_tournament_preset_can_define_tier_slots():
    cfg = {
        "roster_build_defaults": {},
        "roster_base_profiles": {
            "playoff_pt": {
                "mode": "playoff_pt",
                "hitter_count": 14,
                "pitcher_count": 12,
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
                "rotation_size": 4,
                "primary_rp_count": 6,
                "specialist_lhp_count": 1,
                "long_man_count": 1,
                "bench_roles": ["C", "IF", "OF", "UTIL", "UTIL"],
                "bench_role_requirements": {
                    "C": {"required_positions": ["C"]},
                    "IF": {"required_positions": ["SS", "2B"]},
                    "OF": {"required_positions": ["CF", "LF", "RF"]},
                    "UTIL": {"required_positions_any": ["C", "SS", "CF"]},
                },
            },
        },
        "tournament_presets": {
            "slot_test": {
                "base_profile": "playoff_pt",
                "tier_slots": {
                    "P": 2,
                    "D": 1,
                    "G": 1,
                },
            },
        },
    }

    ruleset = build_ruleset_from_tournament_preset(cfg, "slot_test")

    assert ruleset.tier_slots == {"P": 2, "D": 1, "G": 1}
