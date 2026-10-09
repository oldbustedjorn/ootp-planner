from pathlib import Path
import json
import sys

import pandas as pd
import pytest

from ootp_opt.automation.checkpoint import (
    format_checkpoint_summary,
    initialize_checkpoint,
    load_checkpoint,
    record_assignment_repair,
    update_phase,
)
from manage_roster_automation import (
    check_service,
    format_actions,
    main as automation_main,
)
from ootp_opt.automation.manifest import (
    archive_manifest_revision,
    build_automation_manifest,
    load_manifest,
    validate_manifest,
    write_manifest,
)
from ootp_opt.automation.ui_plan import (
    automation_status,
    build_ui_plan,
    compact_ui_plan,
    require_cid_copy_counts,
)
from ootp_opt.config import load_config
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import build_ruleset_from_base_profile


POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]


def hitter(index: int) -> pd.Series:
    row = {
        "candidate_id": f"hitter-{index}",
        "pt_card_id": 1000 + index,
        "source_record_id": 5000 + index,
        "name": f"Hitter {index}",
        "is_variant": index % 2 == 0,
        "owned_copy_count": 1,
        "owned_cid_copy_count": 1,
        "card_value": 80 + index,
        "pt_year": 1990 + index,
        "pt_type": "Historical All-Star",
        "bats": "L" if index % 2 else "R",
        "batting_score_overall": 200.0 - index,
        "batting_score_vs_rhp": 210.0 - index,
        "batting_score_vs_lhp": 190.0 - index,
        "pinch_run_score": 100.0 - index,
    }
    for position in POSITIONS:
        if position != "DH":
            row[f"fld_{position}"] = 100.0
            row[f"score_{position}_overall"] = 200.0 - index
            row[f"score_{position}_vs_rhp"] = 210.0 - index
            row[f"score_{position}_vs_lhp"] = 190.0 - index
    return pd.Series(row)


def pitcher(index: int) -> dict:
    return {
        "candidate_id": f"pitcher-{index}",
        "pt_card_id": 2000 + index,
        "source_record_id": 6000 + index,
        "name": f"Pitcher {index}",
        "is_variant": False,
        "owned_copy_count": 1,
        "owned_cid_copy_count": 1,
        "card_value": 85 + index,
        "pt_year": 1980 + index,
        "pt_type": "Historical All-Star",
        "throws": "L" if index % 2 else "R",
        "starter_score_overall": 300.0 - index,
        "reliever_score_overall": 250.0 - index,
        "reliever_score_vs_lhb": 240.0 - index,
        "is_long_secondary": False,
    }


def build_rosters() -> tuple[HitterRoster, PitcherRoster]:
    hitters = [hitter(index) for index in range(13)]
    starters = {
        position: hitters[index] for index, position in enumerate(POSITIONS)
    }
    bench = pd.DataFrame([row.to_dict() for row in hitters[9:]])
    hitter_roster = HitterRoster(
        starters_by_position=starters,
        bench_players=bench,
        unused_players=pd.DataFrame(),
        starters_by_split={"vs_rhp": starters, "vs_lhp": starters},
        bench_by_split={"vs_rhp": bench, "vs_lhp": bench},
    )

    pitchers = pd.DataFrame([pitcher(index) for index in range(13)])
    pitcher_roster = PitcherRoster(
        rotation=pitchers.iloc[:5].copy(),
        bullpen=pitchers.iloc[5:11].copy(),
        lefty_specialist=pitchers.iloc[11:12].copy(),
        long_man=pitchers.iloc[12:13].copy(),
        unused_players=pd.DataFrame(),
    )
    return hitter_roster, pitcher_roster


def build_manifest() -> dict:
    ruleset = build_ruleset_from_base_profile(load_config("config.toml"), "standard_pt")
    hitter_roster, pitcher_roster = build_rosters()
    return build_automation_manifest(
        ruleset=ruleset,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        html_output="outputs/test.html",
        roster_name="Automation Test",
        preset_name="automation_test",
        base_profile=None,
        config_path="config.toml",
    )


def test_manifest_contains_membership_assignments_and_stable_cids():
    manifest = build_manifest()

    assert manifest["source"]["build_method"] == "optimizer"
    assert manifest["roster"]["name"] == "Automation Test"
    assert len(manifest["roster"]["membership"]) == 26
    assert manifest["roster"]["membership"][0]["cid"] == "1000"
    assert len(manifest["pitching"]["rotation"]) == 5
    assert len(manifest["pitching"]["bullpen"]) == 8
    assert len(manifest["lineups"]["vs_rhp"]["starters"]) == 9
    assert manifest["lineups"]["vs_rhp"]["starters"][0]["depth"]
    assert manifest["tournament"]["excluded_card_subtypes"] == []


def test_manifest_round_trip_and_tamper_detection(tmp_path: Path):
    path = tmp_path / "roster.automation.json"
    write_manifest(path, build_manifest())

    loaded = load_manifest(path)
    assert loaded["manifest_id"] == loaded["fingerprint"][:16]

    loaded["roster"]["name"] = "Tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        validate_manifest(loaded)


def test_manifest_revision_archives_previous_manifest_and_snapshot(tmp_path: Path):
    manifest_path = tmp_path / "roster.automation.json"
    snapshot_path = tmp_path / "roster.snapshot.json"
    manifest = build_manifest()
    write_manifest(manifest_path, manifest)
    snapshot_path.write_text('{"version":1}\n', encoding="utf-8")

    artifacts = archive_manifest_revision(
        manifest_path,
        snapshot_path,
        manifest,
    )

    assert load_manifest(artifacts["manifest"])["manifest_id"] == manifest["manifest_id"]
    assert Path(artifacts["snapshot"]).read_text(encoding="utf-8") == '{"version":1}\n'


def test_manifest_embeds_rebuild_delta_from_previous_revision():
    previous = build_manifest()
    ruleset = build_ruleset_from_base_profile(load_config("config.toml"), "standard_pt")
    hitter_roster, pitcher_roster = build_rosters()

    current = build_automation_manifest(
        ruleset=ruleset,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        html_output="outputs/test.html",
        roster_name="Automation Test",
        preset_name="automation_test",
        base_profile=None,
        config_path="config.toml",
        previous_manifest=previous,
        previous_artifacts={"manifest": "outputs/history/old.json"},
    )

    assert current["rebuild"]["previous_manifest_id"] == previous["manifest_id"]
    assert current["rebuild"]["membership"]["add"] == []
    assert len(current["rebuild"]["membership"]["retain"]) == 26
    assert current["rebuild"]["previous_artifacts"]["manifest"].endswith("old.json")
    validate_manifest(current)


def test_checkpoint_tracks_resumable_phase_results(tmp_path: Path):
    manifest_path = tmp_path / "roster.automation.json"
    checkpoint_path = tmp_path / "roster.checkpoint.json"
    write_manifest(manifest_path, build_manifest())

    checkpoint = initialize_checkpoint(manifest_path, checkpoint_path)
    assert checkpoint["phases"]["plan"]["status"] == "complete"
    assert checkpoint["phases"]["sync"]["status"] == "pending"

    update_phase(
        checkpoint_path,
        "sync",
        "failed",
        completed=["hitter-1"],
        missing=["hitter-2"],
        notes=["Card was not visible after filtering."],
    )
    loaded = load_checkpoint(checkpoint_path)
    assert loaded["phases"]["sync"]["completed"] == ["hitter-1"]
    assert loaded["phases"]["sync"]["missing"] == ["hitter-2"]

    update_phase(
        checkpoint_path,
        "sync",
        "complete",
        completed=["hitter-2"],
    )
    loaded = load_checkpoint(checkpoint_path)
    assert loaded["phases"]["sync"]["completed"] == ["hitter-1", "hitter-2"]
    assert loaded["phases"]["sync"]["missing"] == []


def test_checkpoint_enforces_bounded_targeted_assignment_repairs(tmp_path: Path):
    manifest_path = tmp_path / "roster.automation.json"
    checkpoint_path = tmp_path / "roster.checkpoint.json"
    write_manifest(manifest_path, build_manifest())
    initialize_checkpoint(manifest_path, checkpoint_path)
    update_phase(checkpoint_path, "assign", "in_progress")

    checkpoint = record_assignment_repair(
        checkpoint_path,
        "vs_rhp",
        ["pinch_runner:1"],
        "initial_interior_target",
    )

    assert checkpoint["assignment_repairs"]["vs_rhp"] == 1
    assert checkpoint["assignment_repairs"]["pitching"] == 0
    assert checkpoint["assignment_repair_items"]["vs_rhp"] == {
        "pinch_runner:1": 1
    }
    assert checkpoint["assignment_repair_strategies"]["vs_rhp"] == {
        "pinch_runner:1": ["initial_interior_target"]
    }

    with pytest.raises(ValueError, match="Repair strategy already used"):
        record_assignment_repair(
            checkpoint_path,
            "vs_rhp",
            ["pinch_runner:1"],
            "initial_interior_target",
        )

    checkpoint = record_assignment_repair(
        checkpoint_path,
        "vs_rhp",
        ["pinch_runner:1"],
        "inward_recentered_target",
    )
    assert checkpoint["assignment_repair_items"]["vs_rhp"]["pinch_runner:1"] == 2

    with pytest.raises(ValueError, match="Repair attempt limit reached"):
        record_assignment_repair(
            checkpoint_path,
            "vs_rhp",
            ["pinch_runner:1"],
            "alternate_source_row",
        )

    checkpoint = record_assignment_repair(
        checkpoint_path, "vs_rhp", ["depth:CF:1"], "inward_depth_target"
    )
    assert checkpoint["assignment_repairs"]["vs_rhp"] == 3
    with pytest.raises(ValueError, match="Repair batch limit reached"):
        record_assignment_repair(
            checkpoint_path, "vs_rhp", ["depth:SS:1"], "inward_depth_target"
        )


def test_checkpoint_repair_requires_active_assignment_phase(tmp_path: Path):
    manifest_path = tmp_path / "roster.automation.json"
    checkpoint_path = tmp_path / "roster.checkpoint.json"
    write_manifest(manifest_path, build_manifest())
    initialize_checkpoint(manifest_path, checkpoint_path)

    with pytest.raises(ValueError, match="must be in_progress"):
        record_assignment_repair(
            checkpoint_path, "pitching", ["rotation:1"], "bullpen_row_source"
        )


def test_checkpoint_rejects_replaced_manifest(tmp_path: Path):
    manifest_path = tmp_path / "roster.automation.json"
    checkpoint_path = tmp_path / "roster.checkpoint.json"
    manifest = build_manifest()
    write_manifest(manifest_path, manifest)
    initialize_checkpoint(manifest_path, checkpoint_path)

    manifest["roster"]["name"] = "Replacement"
    manifest["fingerprint"] = ""
    from ootp_opt.automation.manifest import manifest_fingerprint

    manifest["fingerprint"] = manifest_fingerprint(manifest)
    manifest["manifest_id"] = manifest["fingerprint"][:16]
    write_manifest(manifest_path, manifest)

    with pytest.raises(ValueError, match="different manifest revision"):
        load_checkpoint(checkpoint_path)


def test_compact_checkpoint_summary_identifies_next_phase(tmp_path: Path):
    manifest_path = tmp_path / "roster.automation.json"
    checkpoint_path = tmp_path / "roster.checkpoint.json"
    write_manifest(manifest_path, build_manifest())
    checkpoint = initialize_checkpoint(manifest_path, checkpoint_path)

    summary = format_checkpoint_summary(checkpoint)

    assert "plan: complete" in summary
    assert "sync: pending" in summary
    assert "Next phase: sync" in summary
    assert "Assignment repairs: pitching=0 vs_rhp=0 vs_lhp=0" in summary
    assert "hitter-1" not in summary


def test_action_views_are_compact_and_phase_specific():
    manifest = build_manifest()

    sync = format_actions(manifest, "sync")
    pitching = format_actions(manifest, "pitching")
    lineup = format_actions(manifest, "vs_rhp")

    assert sync.count("\n") == 26
    assert "1000\tY\thitter\tHitter 0" in sync
    assert "ROTATION" in pitching
    assert "BULLPEN" in pitching
    assert "LINEUP vs_rhp" in lineup
    assert "PINCH HITTERS" in lineup
    assert "PINCH RUNNERS" in lineup


def test_sync_ui_plan_separates_exact_variants_into_first_pass():
    manifest = build_manifest()

    plan = build_ui_plan(manifest, "sync")

    assert plan["section"] == "sync"
    assert plan["expected"] == {
        "total": 26,
        "hitters": 13,
        "pitchers": 13,
        "variants": 7,
    }
    assert plan["passes"][0]["variant"] is True
    assert plan["passes"][1]["variant"] is False
    variant_cards = [
        card for batch in plan["passes"][0]["fast_batches"] for card in batch
    ]
    assert all(card[0].startswith("hitter-") for card in variant_cards)
    assert all(
        int(card[0].split("-")[-1]) % 2 == 0
        for card in variant_cards
    )
    assert all(len(batch) <= 7 for batch in plan["passes"][1]["fast_batches"])
    assert plan["passes"][0]["inspect"] == []


def test_sync_ui_plan_inspects_cid_duplicates_and_unknown_old_manifests():
    manifest = build_manifest()
    manifest["roster"]["membership"][0]["owned_cid_copy_count"] = 2
    manifest["roster"]["membership"][1].pop("owned_cid_copy_count")

    plan = build_ui_plan(manifest, "sync")
    inspect_cards = [card for sync_pass in plan["passes"] for card in sync_pass["inspect"]]

    assert {card[0] for card in inspect_cards} == {"hitter-0", "hitter-1"}
    assert inspect_cards[0][-1] in {2, None}


def test_new_sync_plan_requires_cid_wide_inventory_counts():
    manifest = build_manifest()
    require_cid_copy_counts(manifest)

    manifest["roster"]["membership"][0].pop("owned_cid_copy_count")

    with pytest.raises(ValueError, match="restart the repository planner"):
        require_cid_copy_counts(manifest)


def test_assignment_ui_plans_are_compact_and_directly_executable():
    manifest = build_manifest()

    pitching = build_ui_plan(manifest, "pitching")
    lineup = build_ui_plan(manifest, "vs_rhp")
    encoded = compact_ui_plan(manifest, "vs_rhp")

    assert pitching["rotation"][0] == [1, "2000", "Pitcher 0"]
    assert pitching["execution"]["rotation_size"] == 5
    assert pitching["execution"]["required_sequence"][0] == "configure_rotation_size"
    assert pitching["execution"]["required_sequence"][1] == (
        "preflight_rotation_drag_capability"
    )
    assert pitching["execution"]["calibration_families"] == ["rotation_drop"]
    assert pitching["execution"]["intermediate_state_reads"] is False
    assert pitching["execution"]["max_repair_batches"] == 3
    assert pitching["execution"]["max_attempts_per_discrepancy"] == 2
    assert pitching["execution"]["repair_only_confirmed_mismatches"] is True
    assert pitching["execution"]["repair_requires_strategy_change"] is True
    assert pitching["execution"]["blocked_section_behavior"] == (
        "checkpoint_and_pause_in_place"
    )
    assert pitching["execution"]["save_partial_roster_on_block"] is False
    assert pitching["execution"]["drag_input_method"] == (
        "windows_sendinput_held_drag"
    )
    assert pitching["execution"]["drag_requires_unsandboxed_gui_input"] is True
    assert pitching["execution"]["drag_batch_required_for_multiple"] is True
    assert pitching["execution"]["drag_hold_ms"] == 400
    assert pitching["execution"]["drag_move_ms"] == 1000
    assert pitching["execution"]["drag_settle_ms"] == 300
    assert pitching["execution"]["drag_steps"] == 30
    assert pitching["execution"]["drag_requires_fresh_screenshot"] is True
    assert pitching["execution"]["drag_source_zone"] == "player_name_text"
    assert pitching["execution"]["upper_list_drag_allowed"] is True
    assert pitching["execution"]["context_menu_assignment_method"] == (
        "isolated_repair_only"
    )
    assert pitching["execution"]["drag_preflight_required"] is True
    assert pitching["execution"]["drag_preflight_max_attempts"] == 2
    assert pitching["execution"]["drag_preflight_counts_as_assignment"] is True
    assert pitching["execution"]["drag_failure_signals"] == [
        "target_unchanged",
        "player_profile_opened",
    ]
    assert pitching["execution"]["drag_failure_behavior"] == (
        "checkpoint_and_pause_before_repair"
    )
    assert pitching["execution"]["coordinate_repairs_after_gesture_failure"] is False
    assert pitching["execution"]["post_drop_wait_ms"] == 450
    assert pitching["execution"]["caller_post_drop_wait_ms"] == 0
    assert pitching["execution"]["rotation_source_order"] == [
        "upper_pitcher_name",
        "current_bullpen_name",
        "current_rotation_name",
    ]
    assert pitching["execution"]["remap_bullpen_before_rotation_repair"] is True
    assert "verify_rotation_before_bullpen_menus" in (
        pitching["execution"]["required_sequence"]
    )
    assert lineup["execution"]["calibration_families"] == [
        "starter_direct_drag",
        "depth_direct_drag",
        "pinch_hitter_list",
        "pinch_runner_list",
    ]
    assert lineup["execution"]["starter_assignment_method"] == (
        "direct_drag_to_position_in_batting_order"
    )
    assert lineup["execution"]["depth_assignment_method"] == (
        "direct_drag_to_depth_slot"
    )
    assert lineup["execution"]["drag_source_zone"] == "upper_player_name"
    assert lineup["execution"]["pinch_source_zone"] == "upper_player_name"
    assert lineup["execution"]["pinch_requires_lower_pane_anchor"] is False
    assert lineup["execution"]["lineup_drag_source_zones"] == [
        "player_name_text_center",
        "player_name_text_right_half",
    ]
    assert lineup["execution"]["failed_preflight_behavior"] == (
        "checkpoint_and_single_manual_handoff"
    )
    assert lineup["execution"]["manual_handoff_scope"] == (
        "all_remaining_lineup_assignments"
    )
    assert lineup["execution"]["context_menu_max_isolated_repairs"] == 1
    assert lineup["execution"]["calibration_counts_as_first_assignment"] is False
    assert lineup["execution"]["pinch_family_transition_delay_ms"] == 800
    assert lineup["execution"]["target_drop_zone"] == "interior_cell_center"
    assert lineup["execution"]["repair_target_shift_inward_min_px"] == 40
    assert lineup["execution"]["reuse_calibration_from"] is None
    assert lineup["execution"]["required_sequence"][0] == (
        "preflight_starter_direct_drag"
    )
    assert len(pitching["bullpen"]) == 8
    assert len(lineup["starter_sequence"]) == 9
    assert [entry[0] for entry in lineup["starter_sequence"]] == list(range(1, 10))
    assert lineup["depth"]
    assert "\n" not in encoded

    versus_left = build_ui_plan(manifest, "vs_lhp")
    assert versus_left["execution"]["reuse_calibration_from"] == "vs_rhp"


def test_automation_status_describes_current_planner_contract():
    status = automation_status()

    assert status["automation_contract_version"] == 13
    assert status["ui_plan_schema_version"] == 15
    assert status["features"]["cid_copy_counts"] is True
    assert status["features"]["single_calibration_batching"] is True
    assert status["features"]["target_family_calibration"] is True
    assert status["features"]["checkpoint_repair_gate"] is True
    assert status["features"]["targeted_repair_retries"] is True
    assert status["features"]["split_pinch_calibration"] is True
    assert status["features"]["distinct_repair_strategies"] is True
    assert status["features"]["in_place_assignment_pause"] is True
    assert status["features"]["drag_capability_preflight"] is True
    assert status["features"]["drag_gesture_fail_fast"] is True
    assert status["features"]["context_menu_lineup_assignment"] is False
    assert status["features"]["context_menu_isolated_repair_only"] is True
    assert status["features"]["lower_pane_drag_sources"] is True
    assert status["features"]["upper_list_drag_disabled"] is False
    assert status["features"]["failed_preflight_manual_handoff"] is True
    assert status["features"]["windows_held_drag"] is True
    assert status["features"]["upper_pitcher_list_drag"] is True
    assert status["features"]["player_name_drag_source"] is True
    assert status["features"]["local_assignment_captures"] is True
    assert status["features"]["native_drag_batches"] is True
    assert status["features"]["card_subtype_constraints"] is True
    assert status["features"]["delta_rebuilds"] is True
    assert status["features"]["targeted_assignment_updates"] is True
    assert status["features"]["depth_before_batting_order"] is True
    assert status["features"]["rebuild_lineup_clear_disabled"] is True


def test_service_check_accepts_exact_running_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(automation_status()).encode("utf-8")

    monkeypatch.setattr("manage_roster_automation.urlopen", lambda *_args, **_kwargs: Response())

    check_service("http://127.0.0.1:8765/automation-status")

    assert "Planner automation service ready" in capsys.readouterr().out


def test_service_check_rejects_stale_running_contract(
    monkeypatch: pytest.MonkeyPatch,
):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"automation_contract_version":0}'

    monkeypatch.setattr("manage_roster_automation.urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(RuntimeError, match="stale or incompatible"):
        check_service("http://127.0.0.1:8765/automation-status")


def test_cli_complete_all_records_manifest_membership_compactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    manifest_path = tmp_path / "roster.automation.json"
    checkpoint_path = tmp_path / "roster.checkpoint.json"
    write_manifest(manifest_path, build_manifest())
    initialize_checkpoint(manifest_path, checkpoint_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manage_roster_automation.py",
            "phase",
            str(checkpoint_path),
            "sync",
            "complete",
            "--complete-all",
        ],
    )

    automation_main()

    output = capsys.readouterr().out
    checkpoint = load_checkpoint(checkpoint_path)
    assert len(checkpoint["phases"]["sync"]["completed"]) == 26
    assert "completed=26" in output
    assert "ootp-pt:card" not in output


def test_cli_repair_attempt_records_exact_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    manifest_path = tmp_path / "roster.automation.json"
    checkpoint_path = tmp_path / "roster.checkpoint.json"
    write_manifest(manifest_path, build_manifest())
    initialize_checkpoint(manifest_path, checkpoint_path)
    update_phase(checkpoint_path, "assign", "in_progress")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manage_roster_automation.py",
            "repair-attempt",
            str(checkpoint_path),
            "vs_rhp",
            "--item",
            "pinch_runner:1",
            "--item",
            "depth:CF:1",
            "--strategy",
            "inward_recentered_target",
        ],
    )

    automation_main()

    output = capsys.readouterr().out
    checkpoint = load_checkpoint(checkpoint_path)
    assert checkpoint["assignment_repairs"]["vs_rhp"] == 1
    assert checkpoint["assignment_repair_items"]["vs_rhp"] == {
        "pinch_runner:1": 1,
        "depth:CF:1": 1,
    }
    assert checkpoint["assignment_repair_strategies"]["vs_rhp"] == {
        "pinch_runner:1": ["inward_recentered_target"],
        "depth:CF:1": ["inward_recentered_target"],
    }
    assert "items=pinch_runner:1,depth:CF:1" in output
    assert "strategy=inward_recentered_target" in output
