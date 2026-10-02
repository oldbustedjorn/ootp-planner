import pandas as pd

from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.roster_snapshot import (
    build_roster_snapshot,
    card_identity,
    compare_snapshots,
    removed_roster_cards,
)


def row(
    name: str,
    *,
    pt_card_id: int | None = None,
    is_variant: bool = False,
) -> pd.Series:
    values = {
        "name": name,
        "card_value": 90,
        "pt_tier": "diamond",
        "pt_year": 2000,
        "pt_type": "Test",
        "is_variant": is_variant,
    }
    if pt_card_id is not None:
        values["pt_card_id"] = pt_card_id
    return pd.Series(values)


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


def test_removed_roster_cards_lists_cards_absent_from_new_roster():
    returning = card_identity(row("Returning Player"))
    departing = card_identity(row("Departing Player"))
    old_snapshot = {
        "Starter SS": returning,
        "Bench 1": departing,
    }
    new_snapshot = {
        "Starter SS": card_identity(row("New Starter")),
        "Bench 1": returning,
    }

    removed = removed_roster_cards(old_snapshot, new_snapshot)

    assert len(removed) == 1
    assert removed[0].name == "Departing Player"
    assert removed[0].previous_roles == ("Bench 1",)
    assert removed[0].card_value == "90"
    assert removed[0].pt_year == "2000"


def test_removed_roster_cards_is_empty_for_first_build():
    new_snapshot = {"Starter SS": card_identity(row("New Starter"))}

    assert removed_roster_cards(None, new_snapshot) == []


def test_snapshot_identity_uses_cid_and_variant():
    normal = card_identity(row("Versioned Card", pt_card_id=86730))
    variant = card_identity(
        row("Versioned Card", pt_card_id=86730, is_variant=True)
    )

    assert normal.endswith("|86730|N")
    assert variant.endswith("|86730|Y")
    assert compare_snapshots(
        {"Starter SS": normal},
        {"Starter SS": variant},
    ) == {"Starter SS": "changed"}


def test_legacy_snapshot_matches_new_snapshot_by_descriptive_identity():
    legacy = "Returning Player|90|diamond|2000|Test"
    current = card_identity(row("Returning Player", pt_card_id=86730))

    assert compare_snapshots(
        {"Starter SS": legacy},
        {"Starter SS": current},
    ) == {"Starter SS": "unchanged"}


def test_removed_roster_card_includes_cid_and_variant():
    departing = card_identity(
        row("Departing Variant", pt_card_id=86730, is_variant=True)
    )

    removed = removed_roster_cards(
        {"Bench 1": departing},
        {"Bench 1": card_identity(row("Replacement", pt_card_id=99999))},
    )

    assert removed[0].pt_card_id == "86730"
    assert removed[0].is_variant is True
