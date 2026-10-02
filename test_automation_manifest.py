from pathlib import Path

import pandas as pd
import pytest

from ootp_opt.automation.checkpoint import (
    initialize_checkpoint,
    load_checkpoint,
    update_phase,
)
from ootp_opt.automation.manifest import (
    build_automation_manifest,
    load_manifest,
    validate_manifest,
    write_manifest,
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
