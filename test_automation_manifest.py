from pathlib import Path
import sys

import pandas as pd
import pytest

from ootp_opt.automation.checkpoint import (
    format_checkpoint_summary,
    initialize_checkpoint,
    load_checkpoint,
    update_phase,
)
from manage_roster_automation import format_actions, main as automation_main
from ootp_opt.automation.manifest import (
    build_automation_manifest,
    load_manifest,
    validate_manifest,
    write_manifest,
)
from ootp_opt.automation.ui_plan import (
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


def test_manifest_round_trip_and_tamper_detection(tmp_path: Path):
    path = tmp_path / "roster.automation.json"
    write_manifest(path, build_manifest())

    loaded = load_manifest(path)
    assert loaded["manifest_id"] == loaded["fingerprint"][:16]

    loaded["roster"]["name"] = "Tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        validate_manifest(loaded)


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
    assert len(pitching["bullpen"]) == 8
    assert len(lineup["starter_sequence"]) == 9
    assert [entry[0] for entry in lineup["starter_sequence"]] == list(range(1, 10))
    assert lineup["depth"]
    assert "\n" not in encoded


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
