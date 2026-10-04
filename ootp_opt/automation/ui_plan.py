from __future__ import annotations

import json
from typing import Any


UI_PLAN_SCHEMA_VERSION = 2
UI_PLAN_SECTIONS = ("sync", "pitching", "vs_rhp", "vs_lhp")
FAST_SYNC_BATCH_SIZE = 7


def build_ui_plan(manifest: dict[str, Any], section: str) -> dict[str, Any]:
    if section not in UI_PLAN_SECTIONS:
        raise ValueError(f"Unknown UI plan section: {section}")

    base = {
        "schema_version": UI_PLAN_SCHEMA_VERSION,
        "manifest_id": manifest["manifest_id"],
        "section": section,
    }
    if section == "sync":
        return {**base, **sync_plan(manifest)}
    if section == "pitching":
        return {**base, **pitching_plan(manifest)}
    return {**base, **lineup_plan(manifest, section)}


def compact_ui_plan(manifest: dict[str, Any], section: str) -> str:
    return json.dumps(build_ui_plan(manifest, section), separators=(",", ":"))


def sync_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    membership = manifest["roster"]["membership"]
    variants = [card for card in membership if card["variant"]]
    standards = [card for card in membership if not card["variant"]]
    roster = manifest["roster"]
    return {
        "passes": [
            sync_pass(True, variants),
            sync_pass(False, standards),
        ],
        "expected": {
            "total": roster["expected_total"],
            "hitters": roster["expected_hitters"],
            "pitchers": roster["expected_pitchers"],
            "variants": len(variants),
        },
    }


def sync_pass(variant: bool, cards: list[dict[str, Any]]) -> dict[str, Any]:
    fast_cards = [
        sync_card(card) for card in cards if card.get("owned_cid_copy_count") == 1
    ]
    inspect_cards = [
        sync_card(card) for card in cards if card.get("owned_cid_copy_count") != 1
    ]
    return {
        "variant": variant,
        "fast_batches": list(chunked(fast_cards, FAST_SYNC_BATCH_SIZE)),
        "inspect": inspect_cards,
    }


def pitching_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    pitching = manifest["pitching"]
    return {
        "rotation": [
            [entry["order"], entry["card"]["cid"], entry["card"]["name"]]
            for entry in pitching["rotation"]
        ],
        "bullpen": [
            [
                entry["card"]["cid"],
                entry["card"]["name"],
                entry["primary_role"],
                entry["usage"],
                entry["secondary_role"],
            ]
            for entry in pitching["bullpen"]
        ],
    }


def lineup_plan(manifest: dict[str, Any], split: str) -> dict[str, Any]:
    starters: list[list[Any]] = []
    depth: list[list[Any]] = []
    for entry in manifest["lineups"][split]["starters"]:
        card = entry["card"]
        starters.append(
            [entry["batting_order"], entry["position"], card["cid"], card["name"]]
        )
        for backup in entry["depth"]:
            backup_card = backup["card"]
            depth.append(
                [
                    entry["position"],
                    backup["order"],
                    backup_card["cid"],
                    backup_card["name"],
                    backup["condition"],
                ]
            )

    bench = manifest["bench_actions"][split]
    return {
        "starters": starters,
        "depth": depth,
        "pinch_hitters": ranked_names(bench["pinch_hitters"]),
        "pinch_runners": ranked_names(bench["pinch_runners"]),
    }


def sync_card(card: dict[str, Any]) -> list[Any]:
    return [
        card["candidate_id"],
        card["cid"],
        card["name"],
        card["player_type"],
        card.get("owned_cid_copy_count"),
    ]


def chunked(cards: list[list[Any]], size: int) -> list[list[list[Any]]]:
    return [cards[index : index + size] for index in range(0, len(cards), size)]


def ranked_names(entries: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [entry["order"], entry["card"]["cid"], entry["card"]["name"]]
        for entry in entries
    ]
