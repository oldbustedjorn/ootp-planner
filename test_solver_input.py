from dataclasses import replace

import pandas as pd
import pytest

from ootp_opt.config import load_config
from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PERSON_KEY_COLUMN,
    PT_CARD_IDENTITY_SCHEMA,
    attach_candidate_identities,
)
from ootp_opt.optimization.candidate_matrices import build_candidate_matrices
from ootp_opt.optimization.solver_input import build_solver_input
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.services.candidate_service import resolve_build_context


def build_solver_fixture(*, constrained=True):
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")
    if constrained:
        ruleset = replace(
            ruleset,
            point_cap_total=1580,
            variant_limit=2,
            tier_slots={"P": 1, "D": 2, "G": 0, "S": 1, "B": 0},
        )
    context = resolve_build_context(cfg, ruleset)

    tiers = ["perfect", "diamond", "gold", "silver", "bronze", "iron"]
    hitter_rows = []
    pitcher_rows = []
    for index in range(30):
        name = "Shared Player" if index in {0, 1} else f"Player {index}"
        metadata = {
            "name": name,
            "pt_year": 2000 + index,
            "card_value": 100 - index,
            "pt_type": "Test",
            "pt_series": "Solver",
            "pt_tier": tiers[index % len(tiers)],
            "is_variant": index in {0, 4, 8},
        }
        hitter = {
            **metadata,
            "batting_score_vs_rhp": 100.0 + index,
            "batting_score_vs_lhp": 90.0 + index,
            "pinch_run_score": 80.0 + index,
        }
        for position in ruleset.min_defense_by_position:
            hitter[f"fld_{position}"] = 100.0
        for slot in ruleset.slot_plan.lineup_slots:
            if slot.position != "DH":
                hitter[slot.score_column] = 100.0 + index
        hitter_rows.append(hitter)
        pitcher_rows.append(
            {
                **metadata,
                "starter_score_overall": 200.0 + index,
                "reliever_score_overall": 190.0 + index,
                "reliever_score_vs_lhb": 180.0 + index,
            }
        )

    hitters = attach_candidate_identities(
        pd.DataFrame(hitter_rows),
        PT_CARD_IDENTITY_SCHEMA,
    )
    pitchers = attach_candidate_identities(
        pd.DataFrame(pitcher_rows),
        PT_CARD_IDENTITY_SCHEMA,
    )
    matrices = build_candidate_matrices(
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
        ruleset=ruleset,
    )
    solver_input = build_solver_input(
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
        ruleset=ruleset,
        scoring_config=context.scoring_config,
        matrices=matrices,
    )
    return cfg, ruleset, hitters, pitchers, matrices, solver_input


def test_solver_input_unifies_hitter_and_pitcher_records_by_candidate_id():
    _, _, hitters, pitchers, _, solver_input = build_solver_fixture()

    assert set(hitters[CANDIDATE_ID_COLUMN]) == set(pitchers[CANDIDATE_ID_COLUMN])
    assert solver_input.candidate_count == 30
    assert solver_input.candidates["can_hit"].all()
    assert solver_input.candidates["can_pitch"].all()


def test_solver_input_exposes_person_cap_variant_and_side_vectors():
    _, _, _, _, _, solver_input = build_solver_fixture()

    assert solver_input.person_count == 29
    assert solver_input.duplicate_person_group_count == 1
    assert solver_input.limits.hitter_count == 13
    assert solver_input.limits.pitcher_count == 13
    assert solver_input.limits.point_cap_total == 1580
    assert solver_input.limits.variant_limit == 2

    card_values = solver_input.candidate_vector("card_value")
    variant_flags = solver_input.candidate_vector("is_variant")
    assert set(card_values) == set(range(71, 101))
    assert int(variant_flags.sum()) == 3


def test_solver_input_contains_split_lineup_and_coverage_requirements():
    _, _, _, _, _, solver_input = build_solver_fixture()

    assert len(solver_input.lineup_requirements) == 18
    assert set(solver_input.lineup_requirements["required_count"]) == {1}
    assert solver_input.lineup_split_weights == {"vs_rhp": 0.7, "vs_lhp": 0.3}
    assert set(
        solver_input.lineup_requirements.loc[
            solver_input.lineup_requirements["split"].eq("vs_rhp"),
            "objective_weight",
        ]
    ) == {0.7}
    assert len(solver_input.coverage_requirements) == 16
    assert set(solver_input.coverage_requirements["minimum_bench_players"]) == {1}
    assert len(solver_input.pitcher_group_requirements) == 4
    assert (
        solver_input.pitcher_group_requirements.set_index("group_key").loc[
            "middle_relief", "required_count"
        ]
        == 6
    )


def test_tier_limits_are_cumulative_and_iron_is_unlimited():
    _, _, _, _, _, solver_input = build_solver_fixture()

    limits = solver_input.tier_limits.set_index("threshold_tier")["max_selected"]
    assert limits.to_dict() == {
        "perfect": 1,
        "diamond": 3,
        "gold": 3,
        "silver": 4,
        "bronze": 4,
    }

    candidate = solver_input.candidates.iloc[0]
    memberships = solver_input.tier_limit_membership.loc[
        solver_input.tier_limit_membership[CANDIDATE_ID_COLUMN].eq(
            candidate[CANDIDATE_ID_COLUMN]
        ),
        "threshold_tier",
    ]
    if candidate["tier"] == "perfect":
        assert set(memberships) == {
            "perfect",
            "diamond",
            "gold",
            "silver",
            "bronze",
        }

    iron_ids = set(
        solver_input.candidates.loc[
            solver_input.candidates["tier"].eq("iron"), CANDIDATE_ID_COLUMN
        ]
    )
    assert iron_ids.isdisjoint(solver_input.tier_limit_membership[CANDIDATE_ID_COLUMN])


def test_inactive_tier_rules_create_no_tier_constraint_edges():
    _, _, _, _, _, solver_input = build_solver_fixture(constrained=False)

    assert solver_input.tier_limits.empty
    assert solver_input.tier_limit_membership.empty
    assert solver_input.limits.point_cap_total is None
    assert solver_input.limits.variant_limit is None


def test_active_point_cap_requires_card_value_metadata():
    _, ruleset, hitters, pitchers, matrices, _ = build_solver_fixture()
    hitters = hitters.drop(columns=["card_value"])

    with pytest.raises(ValueError, match="point cap requires"):
        build_solver_input(
            eligible_hitters=hitters,
            eligible_pitchers=pitchers,
            ruleset=ruleset,
            scoring_config=load_config("config.toml"),
            matrices=matrices,
        )


def test_solver_input_rejects_inconsistent_shared_card_metadata():
    _, ruleset, hitters, pitchers, matrices, _ = build_solver_fixture()
    shared_id = hitters.iloc[0][CANDIDATE_ID_COLUMN]
    pitcher_index = pitchers.index[pitchers[CANDIDATE_ID_COLUMN].eq(shared_id)][0]
    pitchers.loc[pitcher_index, "card_value"] += 1

    with pytest.raises(ValueError, match="inconsistent card_value"):
        build_solver_input(
            eligible_hitters=hitters,
            eligible_pitchers=pitchers,
            ruleset=ruleset,
            scoring_config=load_config("config.toml"),
            matrices=matrices,
        )


def test_person_membership_preserves_alternate_cards_for_one_person():
    _, _, _, _, _, solver_input = build_solver_fixture()
    shared_people = solver_input.person_membership.groupby(PERSON_KEY_COLUMN).filter(
        lambda group: len(group) > 1
    )

    assert shared_people[PERSON_KEY_COLUMN].nunique() == 1
    assert shared_people[CANDIDATE_ID_COLUMN].nunique() == 2
