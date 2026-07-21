import pandas as pd

from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.roster_snapshot import (
    build_roster_snapshot,
    card_identity,
    compare_snapshots,
)


def row(name: str) -> pd.Series:
    return pd.Series(
        {
            "name": name,
            "card_value": 90,
            "pt_tier": "diamond",
            "pt_year": 2000,
            "pt_type": "Test",
        }
    )


def test_pooled_members_remain_unchanged_when_their_order_changes():
    bench_a = card_identity(row("Bench A"))
    bench_b = card_identity(row("Bench B"))
    reliever_a = card_identity(row("Reliever A"))
    reliever_b = card_identity(row("Reliever B"))
    old_snapshot = {
        "Bench 1": bench_a,
        "Bench 2": bench_b,
        "RP1": reliever_a,
        "RP2": reliever_b,
    }
    new_snapshot = {
        "Bench 1": bench_b,
        "Bench 2": bench_a,
        "Middle Relief 1": reliever_b,
        "Middle Relief 2": reliever_a,
    }

    statuses = compare_snapshots(old_snapshot, new_snapshot)

    assert set(statuses.values()) == {"unchanged"}


def test_new_pool_member_is_changed_without_relabeling_other_members():
    old_snapshot = {
        "RP1": card_identity(row("Returning Reliever")),
        "RP2": card_identity(row("Departing Reliever")),
    }
    new_snapshot = {
        "Middle Relief 1": card_identity(row("New Reliever")),
        "Middle Relief 2": card_identity(row("Returning Reliever")),
    }

    statuses = compare_snapshots(old_snapshot, new_snapshot)

    assert statuses["Middle Relief 1"] == "changed"
    assert statuses["Middle Relief 2"] == "unchanged"


def test_rotation_comparison_remains_order_sensitive():
    starter_a = card_identity(row("Starter A"))
    starter_b = card_identity(row("Starter B"))
    old_snapshot = {"SP1": starter_a, "SP2": starter_b}
    new_snapshot = {"SP1": starter_b, "SP2": starter_a}

    statuses = compare_snapshots(old_snapshot, new_snapshot)

    assert statuses == {"SP1": "changed", "SP2": "changed"}


def test_new_snapshot_uses_middle_and_long_relief_names():
    hitter_roster = HitterRoster(
        starters_by_position={"DH": row("Starter")},
        bench_players=pd.DataFrame([row("Bench")]),
        unused_players=pd.DataFrame(),
    )
    pitcher_roster = PitcherRoster(
        rotation=pd.DataFrame([row("Starter Pitcher")]),
        bullpen=pd.DataFrame([row("Middle Reliever")]),
        lefty_specialist=pd.DataFrame([row("Specialist")]),
        long_man=pd.DataFrame([row("Long Reliever")]),
        unused_players=pd.DataFrame(),
    )

    snapshot = build_roster_snapshot(hitter_roster, pitcher_roster)

    assert "Middle Relief 1" in snapshot
    assert "Long Relief 1" in snapshot
    assert "RP1" not in snapshot
    assert "Long Man 1" not in snapshot
