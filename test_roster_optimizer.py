from dataclasses import replace

import pandas as pd

from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PERSON_KEY_COLUMN,
)
from ootp_opt.optimization.candidate_matrices import CandidateMatrices
from ootp_opt.optimization.roster_optimizer import (
    OptimizerSettings,
    build_optimization_model,
    solve_roster_optimization,
)
from ootp_opt.optimization.solver_input import SolverInput, SolverLimits


def test_optimizer_default_values_selected_bench_players():
    assert OptimizerSettings().bench_utility_weight == 0.10


def build_optimizer_fixture() -> SolverInput:
    hitter_specs = {
        "h1": ("catcher_right", "Catcher Right", {"C"}, 120.0, 80.0),
        "h2": ("shortstop", "Shortstop", {"SS"}, 100.0, 100.0),
        "h3": ("catcher_left", "Catcher Left", {"C"}, 80.0, 120.0),
        "h4": ("utility", "Utility", {"C", "SS"}, 70.0, 70.0),
        "h5": ("extra", "Extra Hitter", {"C"}, 60.0, 60.0),
    }
    pitcher_specs = {
        "p1": ("pitcher_shared", "Pitcher Base", 100.0, 95.0),
        "p2": ("pitcher_two", "Pitcher Two", 90.0, 110.0),
        "p3": ("pitcher_shared", "Pitcher Variant", 120.0, 105.0),
    }

    candidate_rows = []
    capability_rows = []
    hitter_assignment_rows = []
    utility_rows = []
    for candidate_id, (
        person_key,
        name,
        positions,
        score_r,
        score_l,
    ) in hitter_specs.items():
        candidate_rows.append(
            candidate_row(candidate_id, person_key, name, can_hit=True)
        )
        utility_rows.append(
            {
                CANDIDATE_ID_COLUMN: candidate_id,
                PERSON_KEY_COLUMN: person_key,
                "name": name,
                "batting_score_vs_rhp": score_r,
                "batting_score_vs_lhp": score_l,
                "pinch_run_score": 50.0,
            }
        )
        for position in positions:
            capability_rows.append(
                {
                    CANDIDATE_ID_COLUMN: candidate_id,
                    PERSON_KEY_COLUMN: person_key,
                    "name": name,
                    "position": position,
                    "defense_rating": 100.0,
                    "minimum_rating": 80.0,
                }
            )
            for split, suffix, score in (
                ("vs_rhp", "r", score_r),
                ("vs_lhp", "l", score_l),
            ):
                hitter_assignment_rows.append(
                    {
                        CANDIDATE_ID_COLUMN: candidate_id,
                        PERSON_KEY_COLUMN: person_key,
                        "name": name,
                        "slot_key": f"{position.lower()}_{suffix}",
                        "split": split,
                        "position": position,
                        "score": score,
                    }
                )

    pitcher_assignment_rows = []
    for candidate_id, (
        person_key,
        name,
        rotation_score,
        middle_score,
    ) in pitcher_specs.items():
        candidate_rows.append(
            candidate_row(candidate_id, person_key, name, can_pitch=True)
        )
        for group_key, label, score in (
            ("rotation", "Rotation", rotation_score),
            ("middle_relief", "Middle Relief", middle_score),
        ):
            pitcher_assignment_rows.append(
                {
                    CANDIDATE_ID_COLUMN: candidate_id,
                    PERSON_KEY_COLUMN: person_key,
                    "name": name,
                    "group_key": group_key,
                    "group_label": label,
                    "score": score,
                }
            )

    candidates = pd.DataFrame(candidate_rows)
    lineup_requirements = pd.DataFrame(
        [
            {
                "slot_key": f"{position.lower()}_{suffix}",
                "split": split,
                "position": position,
                "required_count": 1,
                "objective_weight": weight,
            }
            for split, suffix, weight in (
                ("vs_rhp", "r", 0.7),
                ("vs_lhp", "l", 0.3),
            )
            for position in ("C", "SS")
        ]
    )
    coverage_requirements = pd.DataFrame(
        [
            {
                "requirement_key": f"{position.lower()}_{suffix}_backup",
                "split": split,
                "position": position,
                "minimum_bench_players": 1,
            }
            for split, suffix in (("vs_rhp", "r"), ("vs_lhp", "l"))
            for position in ("C", "SS")
        ]
    )
    matrices = CandidateMatrices(
        hitter_position_capability=pd.DataFrame(capability_rows),
        hitter_assignments=pd.DataFrame(hitter_assignment_rows),
        hitter_utilities=pd.DataFrame(utility_rows),
        pitcher_assignments=pd.DataFrame(pitcher_assignment_rows),
    )
    return SolverInput(
        candidates=candidates,
        person_membership=candidates[[CANDIDATE_ID_COLUMN, PERSON_KEY_COLUMN]].copy(),
        tier_limit_membership=pd.DataFrame(
            columns=[CANDIDATE_ID_COLUMN, "threshold_tier"]
        ),
        lineup_requirements=lineup_requirements,
        pitcher_group_requirements=pd.DataFrame(
            [
                {
                    "group_key": "rotation",
                    "group_label": "Rotation",
                    "required_count": 1,
                },
                {
                    "group_key": "middle_relief",
                    "group_label": "Middle Relief",
                    "required_count": 1,
                },
            ]
        ),
        coverage_requirements=coverage_requirements,
        tier_limits=pd.DataFrame(columns=["threshold_tier", "max_selected"]),
        lineup_split_weights={"vs_rhp": 0.7, "vs_lhp": 0.3},
        limits=SolverLimits(
            hitter_count=4,
            pitcher_count=2,
            point_cap_total=None,
            variant_limit=None,
        ),
        matrices=matrices,
    )


def candidate_row(
    candidate_id: str,
    person_key: str,
    name: str,
    *,
    can_hit: bool = False,
    can_pitch: bool = False,
) -> dict:
    return {
        CANDIDATE_ID_COLUMN: candidate_id,
        PERSON_KEY_COLUMN: person_key,
        "name": name,
        "card_value": 50,
        "tier": "iron",
        "tier_rank": 0,
        "is_variant": False,
        "can_hit": can_hit,
        "can_pitch": can_pitch,
    }


def deterministic_settings() -> OptimizerSettings:
    return OptimizerSettings(time_limit_seconds=5.0, num_workers=1)


def test_optimizer_fills_split_lineups_roster_and_pitcher_groups():
    solver_input = build_optimizer_fixture()

    solution = solve_roster_optimization(solver_input, deterministic_settings())

    assert solution.is_optimal
    assert len(solution.selected_hitter_ids) == 4
    assert len(solution.selected_pitcher_ids) == 2
    assert set(solution.hitter_assignments["slot_key"]) == {
        "c_r",
        "ss_r",
        "c_l",
        "ss_l",
    }
    assert solution.pitcher_assignments.groupby("group_key").size().to_dict() == {
        "middle_relief": 1,
        "rotation": 1,
    }


def test_optimizer_uses_platoon_and_derives_versatile_bench_coverage():
    solver_input = build_optimizer_fixture()

    solution = solve_roster_optimization(solver_input, deterministic_settings())

    catchers = solution.hitter_assignments.loc[
        solution.hitter_assignments["position"].eq("C")
    ].set_index("split")[CANDIDATE_ID_COLUMN]
    assert catchers.to_dict() == {"vs_rhp": "h1", "vs_lhp": "h3"}
    assert "h4" in solution.selected_hitter_ids
    assert set(
        solution.bench_assignments.loc[
            solution.bench_assignments[CANDIDATE_ID_COLUMN].eq("h4"), "split"
        ]
    ) == {"vs_rhp", "vs_lhp"}


def test_optimizer_prevents_alternate_cards_for_one_person():
    solver_input = build_optimizer_fixture()

    solution = solve_roster_optimization(solver_input, deterministic_settings())

    assert not {"p1", "p3"}.issubset(solution.selected_pitcher_ids)
    assert "p3" in solution.selected_pitcher_ids


def test_optimizer_enforces_zero_variant_limit_and_point_cap():
    solver_input = build_optimizer_fixture()
    candidates = solver_input.candidates.copy()
    candidates.loc[candidates[CANDIDATE_ID_COLUMN].eq("p3"), "is_variant"] = True
    candidates.loc[candidates[CANDIDATE_ID_COLUMN].eq("p2"), "card_value"] = 80
    constrained = replace(
        solver_input,
        candidates=candidates,
        limits=replace(
            solver_input.limits,
            point_cap_total=330,
            variant_limit=0,
        ),
    )

    solution = solve_roster_optimization(constrained, deterministic_settings())

    assert solution.is_optimal
    assert "p3" not in solution.selected_pitcher_ids
    selected = set(solution.selected_hitter_ids + solution.selected_pitcher_ids)
    total_value = int(
        candidates.loc[
            candidates[CANDIDATE_ID_COLUMN].isin(selected), "card_value"
        ].sum()
    )
    assert total_value <= 330


def test_optimizer_enforces_cumulative_tier_limit_but_not_iron():
    solver_input = build_optimizer_fixture()
    candidates = solver_input.candidates.copy()
    candidates.loc[
        candidates[CANDIDATE_ID_COLUMN].isin(["h1", "h3"]), ["tier", "tier_rank"]
    ] = [
        "gold",
        3,
    ]
    tier_limit_membership = pd.DataFrame(
        {
            CANDIDATE_ID_COLUMN: ["h1", "h3"],
            "threshold_tier": ["gold", "gold"],
        }
    )
    constrained = replace(
        solver_input,
        candidates=candidates,
        tier_limits=pd.DataFrame([{"threshold_tier": "gold", "max_selected": 1}]),
        tier_limit_membership=tier_limit_membership,
    )

    solution = solve_roster_optimization(constrained, deterministic_settings())

    assert solution.is_optimal
    assert len({"h1", "h3"}.intersection(solution.selected_hitter_ids)) <= 1
    assert len(solution.selected_hitter_ids) == 4


def test_infeasible_optimizer_result_is_returned_without_assignments():
    solver_input = build_optimizer_fixture()
    impossible = replace(
        solver_input,
        limits=replace(solver_input.limits, point_cap_total=1),
    )

    solution = solve_roster_optimization(impossible, deterministic_settings())

    assert solution.status == "infeasible"
    assert not solution.is_feasible
    assert solution.selected_hitter_ids == ()
    assert solution.hitter_assignments.empty


def test_model_exposes_sparse_decision_variable_groups():
    solver_input = build_optimizer_fixture()

    optimization_model = build_optimization_model(
        solver_input, deterministic_settings()
    )

    assert len(optimization_model.hitter_selected) == solver_input.candidate_count
    assert len(optimization_model.pitcher_selected) == solver_input.candidate_count
    assert len(optimization_model.hitter_assignment) == len(
        solver_input.matrices.hitter_assignments
    )
    assert len(optimization_model.pitcher_assignment) == len(
        solver_input.matrices.pitcher_assignments
    )
    assert len(optimization_model.bench) == solver_input.candidate_count * 2
