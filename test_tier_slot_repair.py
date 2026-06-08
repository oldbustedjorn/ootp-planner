import pandas as pd

from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset
from ootp_opt.roster.tier_slot_repair import repair_roster_to_tier_slots
from ootp_opt.roster.tier_slot_report import tier_slots_satisfied


def test_tier_slot_repair_demotes_card_to_satisfy_rollover_slots():
    hitter_roster = HitterRoster(
        starters_by_position={},
        bench_players=pd.DataFrame(),
        unused_players=pd.DataFrame(),
    )
    pitcher_roster = PitcherRoster(
        rotation=pd.DataFrame(
            [
                {
                    "name": "Perfect Ace",
                    "pt_tier": "Perfect",
                    "starter_score_overall": 500.0,
                },
                {
                    "name": "Perfect Two",
                    "pt_tier": "Perfect",
                    "starter_score_overall": 490.0,
                },
            ]
        ),
        bullpen=pd.DataFrame(),
        lefty_specialist=pd.DataFrame(),
        long_man=pd.DataFrame(),
        unused_players=pd.DataFrame(),
    )
    eligible_pitchers = pd.DataFrame(
        [
            {
                "name": "Perfect Ace",
                "pt_tier": "Perfect",
                "starter_score_overall": 500.0,
            },
            {
                "name": "Perfect Two",
                "pt_tier": "Perfect",
                "starter_score_overall": 490.0,
            },
            {
                "name": "Gold Replacement",
                "pt_tier": "Gold",
                "starter_score_overall": 480.0,
            },
        ]
    )
    ruleset = build_ruleset(tier_slots={"P": 1, "D": 0, "G": 2})

    result = repair_roster_to_tier_slots(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        eligible_hitters=pd.DataFrame(),
        eligible_pitchers=eligible_pitchers,
        ruleset=ruleset,
    )

    assert result.success
    assert len(result.steps) == 1
    assert result.steps[0].old_tier == "perfect"
    assert result.steps[0].new_tier == "gold"
    assert tier_slots_satisfied(
        result.hitter_roster,
        result.pitcher_roster,
        ruleset.tier_slots,
    )


def build_ruleset(tier_slots: dict[str, int]) -> Ruleset:
    return Ruleset(
        name="test",
        mode="playoff_pt",
        hitter_count=0,
        pitcher_count=2,
        dh_enabled=True,
        platoons_allowed=False,
        lineup_fill_order=["C"],
        rotation_size=2,
        primary_rp_count=0,
        specialist_lhp_count=0,
        long_man_count=0,
        bench_roles=["UTIL"],
        min_defense_by_position={},
        bench_role_requirements={},
        tier_slots=tier_slots,
    )
