import pandas as pd
import pytest

from ootp_opt.config import load_config
from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PT_CARD_IDENTITY_SCHEMA,
    attach_candidate_identities,
)
from ootp_opt.optimization.candidate_matrices import build_candidate_matrices
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.services.candidate_service import CandidatePool, resolve_build_context


def build_inputs():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    hitter_rows = [
        hitter_row("Versatile", ruleset, score=100.0, defense=100.0),
        hitter_row("Weak SS", ruleset, score=200.0, defense=100.0, ss=84.0),
        hitter_row("DH Only", ruleset, score=300.0, defense=0.0),
    ]
    pitcher_rows = [
        {
            "name": f"Pitcher {index}",
            "starter_score_overall": 100.0 + index,
            "reliever_score_overall": 200.0 + index,
            "reliever_score_vs_lhb": 300.0 + index,
        }
        for index in range(13)
    ]
    hitters = attach_candidate_identities(
        pd.DataFrame(hitter_rows),
        PT_CARD_IDENTITY_SCHEMA,
    )
    pitchers = attach_candidate_identities(
        pd.DataFrame(pitcher_rows),
        PT_CARD_IDENTITY_SCHEMA,
    )
    return ruleset, hitters, pitchers


def hitter_row(
    name,
    ruleset,
    *,
    score,
    defense,
    ss=None,
):
    row = {
        "name": name,
        "batting_score_vs_rhp": score + 1.0,
        "batting_score_vs_lhp": score + 2.0,
        "pinch_run_score": score + 3.0,
    }
    for position in ruleset.min_defense_by_position:
        row[f"fld_{position}"] = defense
    if ss is not None:
        row["fld_SS"] = ss
    for slot in ruleset.slot_plan.lineup_slots:
        if slot.position != "DH":
            row[slot.score_column] = score + (1.0 if slot.split == "vs_rhp" else 2.0)
    return row


def test_matrices_use_position_thresholds_for_assignment_and_coverage_capability():
    ruleset, hitters, pitchers = build_inputs()

    matrices = build_candidate_matrices(
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
        ruleset=ruleset,
    )

    ss_capable = matrices.capable_hitters("SS")
    assert set(ss_capable["name"]) == {"Versatile"}
    assert ss_capable.iloc[0]["minimum_rating"] == 85.0

    ss_rhp = matrices.hitters_for_slot("vs_rhp_ss")
    assert set(ss_rhp["name"]) == {"Versatile"}
    assert ss_rhp.iloc[0]["score"] == 101.0


def test_dh_assignment_uses_split_batting_without_defensive_eligibility():
    ruleset, hitters, pitchers = build_inputs()

    matrices = build_candidate_matrices(
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
        ruleset=ruleset,
    )

    dh_rhp = matrices.hitters_for_slot("vs_rhp_dh")
    assert set(dh_rhp["name"]) == {"Versatile", "Weak SS", "DH Only"}
    dh_only = dh_rhp.loc[dh_rhp["name"].eq("DH Only")].iloc[0]
    assert dh_only["score"] == 301.0
    assert "DH" not in set(matrices.hitter_position_capability["position"])


def test_hitter_utilities_are_candidate_values_not_bench_assignments():
    ruleset, hitters, pitchers = build_inputs()

    matrices = build_candidate_matrices(
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
        ruleset=ruleset,
    )

    utility = matrices.hitter_utilities.loc[
        matrices.hitter_utilities["name"].eq("Versatile")
    ].iloc[0]
    assert utility["batting_score_vs_rhp"] == 101.0
    assert utility["batting_score_vs_lhp"] == 102.0
    assert utility["pinch_run_score"] == 103.0
    assert not any(
        "bench" in column
        for frame in (
            matrices.hitter_position_capability,
            matrices.hitter_assignments,
            matrices.hitter_utilities,
        )
        for column in frame.columns
    )


def test_pitcher_role_edges_preserve_current_role_scores():
    ruleset, hitters, pitchers = build_inputs()

    matrices = build_candidate_matrices(
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
        ruleset=ruleset,
    )

    assert len(matrices.pitchers_for_group("rotation")) == 13
    assert len(matrices.pitchers_for_group("middle_relief")) == 13
    specialist = matrices.pitchers_for_group("lefty_specialist")
    assert specialist.loc[specialist["name"].eq("Pitcher 0"), "score"].iloc[0] == 300.0


def test_matrix_builder_reports_missing_score_columns_with_slot_context():
    ruleset, hitters, pitchers = build_inputs()
    hitters = hitters.drop(columns=["score_SS_vs_rhp"])

    with pytest.raises(ValueError, match="lineup slot vs_rhp_ss"):
        build_candidate_matrices(
            eligible_hitters=hitters,
            eligible_pitchers=pitchers,
            ruleset=ruleset,
        )


def test_matrix_builder_rejects_duplicate_candidate_ids():
    ruleset, hitters, pitchers = build_inputs()
    hitters.loc[1, CANDIDATE_ID_COLUMN] = hitters.loc[0, CANDIDATE_ID_COLUMN]

    with pytest.raises(ValueError, match="duplicate candidate IDs"):
        build_candidate_matrices(
            eligible_hitters=hitters,
            eligible_pitchers=pitchers,
            ruleset=ruleset,
        )


def test_candidate_pool_exposes_matrices_without_eagerly_changing_selection():
    ruleset, hitters, pitchers = build_inputs()
    context = resolve_build_context(load_config("config.toml"), ruleset)
    pool = CandidatePool(
        source="owned",
        context=context,
        identity_schema=PT_CARD_IDENTITY_SCHEMA,
        scored_hitters=hitters,
        scored_pitchers=pitchers,
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
    )

    matrices = pool.build_matrices()

    assert matrices.hitter_assignment_count == 36
    assert matrices.position_capability_count == 15
    assert matrices.pitcher_assignment_count == 52
