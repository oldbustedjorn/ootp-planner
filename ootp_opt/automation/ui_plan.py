from __future__ import annotations

import json
from typing import Any

from ootp_opt.automation.manifest import SCHEMA_VERSION as MANIFEST_SCHEMA_VERSION


AUTOMATION_CONTRACT_VERSION = 13
UI_PLAN_SCHEMA_VERSION = 15
UI_PLAN_SECTIONS = ("sync", "pitching", "vs_rhp", "vs_lhp")
FAST_SYNC_BATCH_SIZE = 7


def automation_status() -> dict[str, Any]:
    return {
        "automation_contract_version": AUTOMATION_CONTRACT_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "ui_plan_schema_version": UI_PLAN_SCHEMA_VERSION,
        "features": {
            "cid_copy_counts": True,
            "direct_split_lineups": True,
            "single_calibration_batching": True,
            "target_family_calibration": True,
            "checkpoint_repair_gate": True,
            "targeted_repair_retries": True,
            "split_pinch_calibration": True,
            "distinct_repair_strategies": True,
            "in_place_assignment_pause": True,
            "drag_capability_preflight": True,
            "drag_gesture_fail_fast": True,
            "context_menu_lineup_assignment": False,
            "context_menu_isolated_repair_only": True,
            "lower_pane_drag_sources": True,
            "upper_list_drag_disabled": False,
            "failed_preflight_manual_handoff": True,
            "windows_held_drag": True,
            "upper_pitcher_list_drag": True,
            "player_name_drag_source": True,
            "local_assignment_captures": True,
            "native_drag_batches": True,
            "card_subtype_constraints": True,
            "delta_rebuilds": True,
            "targeted_assignment_updates": True,
            "depth_before_batting_order": True,
            "rebuild_lineup_clear_disabled": True,
        },
    }


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


def require_cid_copy_counts(manifest: dict[str, Any]) -> None:
    missing = [
        card["candidate_id"]
        for card in manifest["roster"]["membership"]
        if not isinstance(card.get("owned_cid_copy_count"), int)
        or card["owned_cid_copy_count"] < 1
    ]
    if missing:
        raise ValueError(
            "Manifest is missing CID-wide inventory counts for "
            f"{len(missing)} selected cards. The planner service may predate the "
            "fast-sync code; restart the repository planner and rebuild this new "
            "roster before creating its OOTP roster."
        )


def sync_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    rebuild = manifest.get("rebuild")
    if rebuild:
        membership = rebuild["membership"]
        added = membership["add"]
        variants = [card for card in added if card["variant"]]
        standards = [card for card in added if not card["variant"]]
        return {
            "mode": "rebuild",
            "remove": [rebuild_sync_card(card) for card in membership["remove"]],
            "add": [rebuild_sync_card(card) for card in added],
            "add_passes": [
                sync_pass(True, variants),
                sync_pass(False, standards),
            ],
            "retained": len(membership["retain"]),
            "expected": sync_expected(manifest),
            "required_sequence": [
                "open_manage_cards_once",
                "remove_exact_cards",
                "add_exact_cards",
                "verify_roster_totals",
            ],
        }

    membership = manifest["roster"]["membership"]
    variants = [card for card in membership if card["variant"]]
    standards = [card for card in membership if not card["variant"]]
    return {
        "mode": "full",
        "passes": [
            sync_pass(True, variants),
            sync_pass(False, standards),
        ],
        "expected": sync_expected(manifest),
    }


def sync_expected(manifest: dict[str, Any]) -> dict[str, Any]:
    roster = manifest["roster"]
    membership = roster["membership"]
    return {
        "total": roster["expected_total"],
        "hitters": roster["expected_hitters"],
        "pitchers": roster["expected_pitchers"],
        "variants": sum(bool(card["variant"]) for card in membership),
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
    rebuild = manifest.get("rebuild", {}).get("pitching")
    pitching = rebuild or manifest["pitching"]
    return {
        "mode": "rebuild" if rebuild else "full",
        "execution": pitching_execution_contract(
            len(manifest["pitching"]["rotation"]),
            rebuild=rebuild,
        ),
        "rotation_size_changed": bool(rebuild and rebuild["rotation_size_changed"]),
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
        "unchanged": {
            "rotation": rebuild["unchanged_rotation"] if rebuild else 0,
            "bullpen": rebuild["unchanged_bullpen"] if rebuild else 0,
        },
    }


def lineup_plan(manifest: dict[str, Any], split: str) -> dict[str, Any]:
    rebuild = manifest.get("rebuild", {}).get("lineups", {}).get(split)
    starter_sequence: list[list[Any]] = []
    depth: list[list[Any]] = []
    starters = (
        rebuild["starters"]
        if rebuild
        else manifest["lineups"][split]["starters"]
    )
    for entry in starters:
        card = entry["card"]
        starter_sequence.append(
            [entry["batting_order"], entry["position"], card["cid"], card["name"]]
        )
        for backup in ([] if rebuild else entry["depth"]):
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

    if rebuild:
        depth = [
            [
                entry["position"],
                entry["order"],
                entry["card"]["cid"],
                entry["card"]["name"],
                entry["condition"],
            ]
            for entry in rebuild["depth"]
        ]

    bench = manifest["bench_actions"][split]
    batting_order_changed = bool(
        rebuild
        and rebuild.get(
            "batting_order_changed",
            rebuild.get("rebuild_starters", False),
        )
    )
    batting_order_entries = (
        rebuild.get("batting_order", rebuild["starters"])
        if batting_order_changed
        else []
    )
    return {
        "mode": "rebuild" if rebuild else "full",
        "execution": lineup_execution_contract(split, rebuild=rebuild),
        "starter_strategy": (
            "replace_changed_position_slots" if rebuild else "build_all_starters"
        ),
        "starter_sequence": sorted(starter_sequence, key=lambda entry: entry[0]),
        "depth": depth,
        "batting_order_strategy": (
            "reorder_after_depth_chart_updates"
            if batting_order_changed
            else "preserve_existing_order"
            if rebuild
            else "established_by_starter_insertion"
        ),
        "batting_order": [
            [entry["batting_order"], entry["card"]["cid"], entry["card"]["name"]]
            for entry in sorted(batting_order_entries, key=lambda entry: entry["batting_order"])
        ],
        "pinch_hitters": ranked_names(
            rebuild["pinch_hitters"] if rebuild else bench["pinch_hitters"]
        ),
        "pinch_runners": ranked_names(
            rebuild["pinch_runners"] if rebuild else bench["pinch_runners"]
        ),
        "unchanged": {
            "starters": rebuild["unchanged_starters"] if rebuild else 0,
            "depth": rebuild["unchanged_depth"] if rebuild else 0,
        },
    }


def assignment_execution_contract() -> dict[str, Any]:
    return {
        "lock_source_coordinate_for_screen": True,
        "intermediate_state_reads": False,
        "verify_after_complete_section": True,
        "upper_list_drag_allowed": True,
        "context_menu_assignment_method": "isolated_repair_only",
        "context_menu_requires_fresh_screenshot": True,
        "drag_input_method": "windows_sendinput_held_drag",
        "drag_command": (
            ".\\.venv\\Scripts\\python.exe -m "
            "ootp_opt.automation.windows_drag drag"
        ),
        "drag_batch_command": (
            ".\\.venv\\Scripts\\python.exe -m "
            "ootp_opt.automation.windows_drag batch"
        ),
        "drag_batch_required_for_multiple": True,
        "drag_requires_unsandboxed_gui_input": True,
        "drag_requires_fresh_screenshot": True,
        "drag_source_zone": "player_name_text",
        "drag_preflight_required": True,
        "drag_preflight_max_attempts": 2,
        "drag_preflight_counts_as_assignment": True,
        "drag_failure_signals": [
            "target_unchanged",
            "player_profile_opened",
        ],
        "drag_failure_behavior": "checkpoint_and_pause_before_repair",
        "coordinate_repairs_after_gesture_failure": False,
        "post_drop_wait_ms": 450,
        "caller_post_drop_wait_ms": 0,
        "drag_hold_ms": 400,
        "drag_move_ms": 1000,
        "drag_settle_ms": 300,
        "drag_steps": 30,
        "max_repair_batches": 3,
        "max_attempts_per_discrepancy": 2,
        "repair_gate_command": (
            "repair-attempt --item <target> --strategy <distinct-strategy>"
        ),
        "repair_only_confirmed_mismatches": True,
        "repair_requires_strategy_change": True,
        "must_complete_before_next_section": True,
        "blocked_section_behavior": "checkpoint_and_pause_in_place",
        "save_partial_roster_on_block": False,
    }


def pitching_execution_contract(
    rotation_size: int,
    *,
    rebuild: dict[str, Any] | None = None,
) -> dict[str, Any]:
    required_sequence = [
        "configure_rotation_size",
        "preflight_rotation_drag_capability",
        "assign_remaining_rotation",
        "verify_rotation_before_bullpen_menus",
        "map_bullpen_menus_once",
        "assign_bullpen",
        "verify_section",
    ]
    if rebuild:
        required_sequence = []
        if rebuild["rotation_size_changed"]:
            required_sequence.append("configure_rotation_size")
        if rebuild["rotation"]:
            required_sequence.extend(
                [
                    "preflight_rotation_drag_capability",
                    "assign_remaining_rotation",
                    "verify_rotation_before_bullpen_menus",
                ]
            )
        if rebuild["bullpen"]:
            required_sequence.extend(
                ["map_bullpen_menus_once", "assign_bullpen"]
            )
        required_sequence.append("verify_section")
    return {
        **assignment_execution_contract(),
        "upper_list_drag_allowed": True,
        "rotation_size": rotation_size,
        "preserve_unchanged_assignments": bool(rebuild),
        "calibration_families": ["rotation_drop"],
        "rotation_source_order": [
            "upper_pitcher_name",
            "current_bullpen_name",
            "current_rotation_name",
        ],
        "remap_bullpen_before_rotation_repair": True,
        "required_sequence": required_sequence,
    }


def lineup_execution_contract(
    split: str,
    *,
    rebuild: dict[str, Any] | None = None,
) -> dict[str, Any]:
    required_sequence = [
        "preflight_starter_direct_drag",
        "assign_remaining_starters_by_direct_drag",
        "assign_depth_by_direct_drag",
        "calibrate_pinch_hitter_list",
        "assign_remaining_pinch_hitters",
        "wait_for_pinch_family_transition",
        "calibrate_pinch_runner_list",
        "assign_remaining_pinch_runners",
        "verify_section",
    ]
    if rebuild:
        required_sequence = []
        if rebuild["starters"]:
            required_sequence.extend(
                [
                    "preflight_starter_direct_drag",
                    "assign_remaining_starters_by_direct_drag",
                ]
            )
        if rebuild["depth"]:
            required_sequence.append("assign_depth_by_direct_drag")
        if rebuild.get("batting_order_changed", rebuild.get("rebuild_starters", False)):
            required_sequence.append("reorder_batting_order_after_depth_chart")
        if rebuild["pinch_hitters"]:
            required_sequence.extend(
                ["calibrate_pinch_hitter_list", "assign_remaining_pinch_hitters"]
            )
        if rebuild["pinch_runners"]:
            if rebuild["pinch_hitters"]:
                required_sequence.append("wait_for_pinch_family_transition")
            required_sequence.extend(
                ["calibrate_pinch_runner_list", "assign_remaining_pinch_runners"]
            )
        required_sequence.append("verify_section")
    return {
        **assignment_execution_contract(),
        "drag_source_zone": "upper_player_name",
        "calibration_families": [
            "starter_direct_drag",
            "depth_direct_drag",
            "pinch_hitter_list",
            "pinch_runner_list",
        ],
        "starter_assignment_method": "direct_drag_to_position_in_batting_order",
        "starter_position_method": "set_by_position_drop",
        "depth_assignment_method": "direct_drag_to_depth_slot",
        "pinch_source_zone": "upper_player_name",
        "pinch_requires_lower_pane_anchor": False,
        "lineup_drag_source_zones": [
            "player_name_text_center",
            "player_name_text_right_half",
        ],
        "failed_preflight_behavior": "checkpoint_and_single_manual_handoff",
        "manual_handoff_scope": "all_remaining_lineup_assignments",
        "context_menu_max_isolated_repairs": 1,
        "calibration_counts_as_first_assignment": False,
        "pinch_family_transition_delay_ms": 800,
        "target_drop_zone": "interior_cell_center",
        "repair_target_shift_inward_min_px": 40,
        "reuse_calibration_from": "vs_rhp" if split == "vs_lhp" else None,
        "preserve_unchanged_assignments": bool(rebuild),
        "never_clear_lineup_during_rebuild": bool(rebuild),
        "never_clear_depth_during_rebuild": bool(rebuild),
        "required_sequence": required_sequence,
    }


def sync_card(card: dict[str, Any]) -> list[Any]:
    return [
        card["candidate_id"],
        card["cid"],
        card["name"],
        card["player_type"],
        card.get("owned_cid_copy_count"),
    ]


def rebuild_sync_card(card: dict[str, Any]) -> list[Any]:
    return [
        card["candidate_id"],
        card["cid"],
        card["name"],
        card["player_type"],
        bool(card["variant"]),
        card.get("owned_cid_copy_count"),
    ]


def chunked(cards: list[list[Any]], size: int) -> list[list[list[Any]]]:
    return [cards[index : index + size] for index in range(0, len(cards), size)]


def ranked_names(entries: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [entry["order"], entry["card"]["cid"], entry["card"]["name"]]
        for entry in entries
    ]
