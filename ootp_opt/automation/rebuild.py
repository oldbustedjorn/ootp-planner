from __future__ import annotations

from typing import Any


def build_rebuild_delta(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    previous_cards = previous["roster"]["membership"]
    current_cards = current["roster"]["membership"]
    previous_by_key = {card_key(card): card for card in previous_cards}
    current_by_key = {card_key(card): card for card in current_cards}

    removed = [card for card in previous_cards if card_key(card) not in current_by_key]
    added = [card for card in current_cards if card_key(card) not in previous_by_key]
    retained = [card for card in current_cards if card_key(card) in previous_by_key]

    return {
        "schema_version": 1,
        "previous_manifest_id": previous.get("manifest_id"),
        "membership": {
            "remove": removed,
            "add": added,
            "retain": retained,
        },
        "pitching": pitching_delta(previous, current),
        "lineups": {
            split: lineup_delta(previous, current, split)
            for split in ("vs_rhp", "vs_lhp")
        },
    }


def compatible_rebuild_source(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> bool:
    if not previous:
        return False
    previous_source = previous.get("source", {})
    current_source = current.get("source", {})
    previous_preset = previous_source.get("preset_name")
    current_preset = current_source.get("preset_name")
    same_plan = (
        previous_preset == current_preset
        if previous_preset or current_preset
        else previous_source.get("html_report") == current_source.get("html_report")
    )
    return (
        same_plan
        and previous_source.get("build_method") == "optimizer"
    )


def pitching_delta(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    previous_pitching = previous.get("pitching", {})
    current_pitching = current.get("pitching", {})
    old_rotation = {
        entry["order"]: entry for entry in previous_pitching.get("rotation", [])
    }
    new_rotation = current_pitching.get("rotation", [])
    rotation_changes = [
        entry
        for entry in new_rotation
        if assignment_card_key(old_rotation.get(entry["order"]))
        != assignment_card_key(entry)
    ]

    old_bullpen = {
        card_key(entry["card"]): entry
        for entry in previous_pitching.get("bullpen", [])
    }
    bullpen_changes = [
        entry
        for entry in current_pitching.get("bullpen", [])
        if bullpen_signature(old_bullpen.get(card_key(entry["card"])))
        != bullpen_signature(entry)
    ]
    return {
        "rotation_size_changed": len(old_rotation) != len(new_rotation),
        "rotation": rotation_changes,
        "bullpen": bullpen_changes,
        "unchanged_rotation": len(new_rotation) - len(rotation_changes),
        "unchanged_bullpen": len(current_pitching.get("bullpen", []))
        - len(bullpen_changes),
    }


def lineup_delta(
    previous: dict[str, Any],
    current: dict[str, Any],
    split: str,
) -> dict[str, Any]:
    old_starters = previous.get("lineups", {}).get(split, {}).get("starters", [])
    new_starters = current.get("lineups", {}).get(split, {}).get("starters", [])
    old_by_position = {entry["position"]: entry for entry in old_starters}

    old_position_order = [
        entry["position"] for entry in sorted(old_starters, key=batting_order)
    ]
    new_position_order = [
        entry["position"] for entry in sorted(new_starters, key=batting_order)
    ]
    batting_order_changed = old_position_order != new_position_order
    starter_changes = [
        entry
        for entry in new_starters
        if assignment_card_key(old_by_position.get(entry["position"]))
        != assignment_card_key(entry)
    ]

    old_depth = depth_by_target(old_starters)
    new_depth = depth_by_target(new_starters)
    depth_changes = [
        entry
        for target, entry in new_depth.items()
        if depth_signature(old_depth.get(target)) != depth_signature(entry)
    ]

    old_bench = previous.get("bench_actions", {}).get(split, {})
    new_bench = current.get("bench_actions", {}).get(split, {})
    pinch_hitters = changed_ranked_entries(
        old_bench.get("pinch_hitters", []),
        new_bench.get("pinch_hitters", []),
    )
    pinch_runners = changed_ranked_entries(
        old_bench.get("pinch_runners", []),
        new_bench.get("pinch_runners", []),
    )
    return {
        "starters": starter_changes,
        "depth": depth_changes,
        "batting_order_changed": batting_order_changed,
        "batting_order": new_starters if batting_order_changed else [],
        "pinch_hitters": pinch_hitters,
        "pinch_runners": pinch_runners,
        "unchanged_starters": len(new_starters) - len(starter_changes),
        "unchanged_depth": len(new_depth) - len(depth_changes),
    }


def depth_by_target(starters: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for starter in starters:
        for backup in starter.get("depth", []):
            result[(starter["position"], backup["order"])] = {
                "position": starter["position"],
                **backup,
            }
    return result


def changed_ranked_entries(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    previous_by_order = {entry["order"]: entry for entry in previous}
    return [
        entry
        for entry in current
        if assignment_card_key(previous_by_order.get(entry["order"]))
        != assignment_card_key(entry)
    ]


def card_key(card: dict[str, Any]) -> tuple[str, bool]:
    return str(card.get("cid") or ""), bool(card.get("variant", False))


def assignment_card_key(entry: dict[str, Any] | None) -> tuple[str, bool] | None:
    if not entry:
        return None
    card = entry.get("card")
    return card_key(card) if card else None


def bullpen_signature(entry: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not entry:
        return None
    return (
        assignment_card_key(entry),
        entry.get("primary_role"),
        entry.get("usage"),
        entry.get("secondary_role"),
    )


def depth_signature(entry: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not entry:
        return None
    return (
        assignment_card_key(entry),
        entry.get("condition"),
    )


def batting_order(entry: dict[str, Any]) -> int:
    return int(entry["batting_order"])
