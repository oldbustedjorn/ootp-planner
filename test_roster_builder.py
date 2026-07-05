import pandas as pd

from ootp_opt.roster.builder import build_pitcher_roster
from ootp_opt.roster.rules import Ruleset


def test_pitcher_roster_respects_preselected_hitter_names():
    ruleset = Ruleset(
        name="test",
        mode="test",
        hitter_count=1,
        pitcher_count=4,
        dh_enabled=True,
        platoons_allowed=False,
        lineup_fill_order=["SS"],
        rotation_size=1,
        primary_rp_count=1,
        specialist_lhp_count=1,
        long_man_count=1,
        bench_roles=[],
        min_defense_by_position={},
        bench_role_requirements={},
    )
    pitchers = pd.DataFrame(
        [
            {
                "name": "Ace Starter",
                "starter_score_overall": 900,
                "reliever_score_overall": 100,
                "reliever_score_vs_lhb": 100,
            },
            {
                "name": "Top Reliever",
                "starter_score_overall": 100,
                "reliever_score_overall": 900,
                "reliever_score_vs_lhb": 100,
            },
            {
                "name": "Lefty Specialist",
                "starter_score_overall": 100,
                "reliever_score_overall": 100,
                "reliever_score_vs_lhb": 900,
            },
            {
                "name": "Bobby Witt Jr.",
                "starter_score_overall": 800,
                "reliever_score_overall": 800,
                "reliever_score_vs_lhb": 800,
            },
            {
                "name": "Fallback Long Man",
                "starter_score_overall": 200,
                "reliever_score_overall": 100,
                "reliever_score_vs_lhb": 100,
            },
        ]
    )

    roster = build_pitcher_roster(
        pitchers,
        ruleset,
        used_player_names={"bobby witt jr."},
    )

    assert roster.long_man.iloc[0]["name"] == "Fallback Long Man"
    assert "Bobby Witt Jr." not in set(roster.unused_players["name"])
