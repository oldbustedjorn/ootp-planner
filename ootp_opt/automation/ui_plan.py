from __future__ import annotations

import json
from typing import Any


UI_PLAN_SCHEMA_VERSION = 1
UI_PLAN_SECTIONS = ("sync", "pitching", "vs_rhp", "vs_lhp")


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
    variants = [sync_card(card) for card in membership if card["variant"]]
    standards = [sync_card(card) for card in membership if not card["variant"]]
    roster = manifest["roster"]
    return {
        "passes": [
            {"variant": True, "cards": variants},
            {"variant": False, "cards": standards},
        ],
        "expected": {
            "total": roster["expected_total"],
            "hitters": roster["expected_hitters"],
            "pitchers": roster["expected_pitchers"],
            "variants": len(variants),
        },
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
    ]


def ranked_names(entries: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [entry["order"], entry["card"]["cid"], entry["card"]["name"]]
        for entry in entries
    ]
