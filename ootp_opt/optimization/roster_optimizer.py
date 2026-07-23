from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PERSON_KEY_COLUMN,
)
from ootp_opt.optimization.solver_input import SolverInput


@dataclass(frozen=True)
class OptimizerSettings:
    time_limit_seconds: float = 30.0
    num_workers: int = 0
    random_seed: int = 0
    score_scale: int = 100
    bench_utility_weight: float = 0.10
    pinch_run_share: float = 0.10


@dataclass(frozen=True)
class RosterOptimizationModel:
    model: cp_model.CpModel
    hitter_selected: dict[str, cp_model.IntVar]
    pitcher_selected: dict[str, cp_model.IntVar]
    hitter_assignment: dict[tuple[str, str], cp_model.IntVar]
    pitcher_assignment: dict[tuple[str, str], cp_model.IntVar]
    bench: dict[tuple[str, str], cp_model.IntVar]


@dataclass(frozen=True)
class OptimizationSolution:
    status: str
    objective_value: float | None
    best_objective_bound: float | None
    wall_time_seconds: float
    selected_hitter_ids: tuple[str, ...]
    selected_pitcher_ids: tuple[str, ...]
    hitter_assignments: pd.DataFrame
    pitcher_assignments: pd.DataFrame
    bench_assignments: pd.DataFrame

    @property
    def is_feasible(self) -> bool:
        return self.status in {"optimal", "feasible"}

    @property
    def is_optimal(self) -> bool:
        return self.status == "optimal"


def build_optimization_model(
    solver_input: SolverInput,
    settings: OptimizerSettings | None = None,
) -> RosterOptimizationModel:
    settings = settings or OptimizerSettings()
    validate_settings(settings)

    model = cp_model.CpModel()
    candidate_ids = solver_input.candidates[CANDIDATE_ID_COLUMN].tolist()
    candidate_index = {
        candidate_id: index for index, candidate_id in enumerate(candidate_ids)
    }

    hitter_selected = {
        candidate_id: model.new_bool_var(f"h_{candidate_index[candidate_id]}")
        for candidate_id in candidate_ids
    }
    pitcher_selected = {
        candidate_id: model.new_bool_var(f"p_{candidate_index[candidate_id]}")
        for candidate_id in candidate_ids
    }

    hitter_edges = solver_input.matrices.hitter_assignments.reset_index(drop=True)
    hitter_assignment = {
        (row[CANDIDATE_ID_COLUMN], row["slot_key"]): model.new_bool_var(f"y_{index}")
        for index, row in hitter_edges.iterrows()
    }
    pitcher_edges = solver_input.matrices.pitcher_assignments.reset_index(drop=True)
    pitcher_assignment = {
        (row[CANDIDATE_ID_COLUMN], row["group_key"]): model.new_bool_var(f"z_{index}")
        for index, row in pitcher_edges.iterrows()
    }

    splits = tuple(solver_input.lineup_requirements["split"].drop_duplicates())
    bench = {
        (candidate_id, split): model.new_bool_var(
            f"b_{candidate_index[candidate_id]}_{split}"
        )
        for candidate_id in candidate_ids
        for split in splits
    }

    add_roster_size_constraints(
        model,
        solver_input,
        hitter_selected,
        pitcher_selected,
    )
    add_person_constraints(
        model,
        solver_input,
        hitter_selected,
        pitcher_selected,
    )
    add_lineup_constraints(
        model,
        solver_input,
        hitter_selected,
        hitter_assignment,
        bench,
        splits,
    )
    add_pitcher_group_constraints(
        model,
        solver_input,
        pitcher_selected,
        pitcher_assignment,
    )
    add_coverage_constraints(model, solver_input, bench)
    add_roster_limit_constraints(
        model,
        solver_input,
        hitter_selected,
        pitcher_selected,
    )
    add_objective(
        model,
        solver_input,
        settings,
        hitter_assignment,
        pitcher_assignment,
        bench,
    )

    return RosterOptimizationModel(
        model=model,
        hitter_selected=hitter_selected,
        pitcher_selected=pitcher_selected,
        hitter_assignment=hitter_assignment,
        pitcher_assignment=pitcher_assignment,
        bench=bench,
    )


def solve_roster_optimization(
    solver_input: SolverInput,
    settings: OptimizerSettings | None = None,
) -> OptimizationSolution:
    settings = settings or OptimizerSettings()
    optimization_model = build_optimization_model(solver_input, settings)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = settings.time_limit_seconds
    solver.parameters.random_seed = settings.random_seed
    if settings.num_workers > 0:
        solver.parameters.num_search_workers = settings.num_workers

    status_code = solver.solve(optimization_model.model)
    status = solver.status_name(status_code).lower()
    if status_code not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return empty_solution(status, solver.wall_time)

    return extract_solution(
        solver_input,
        optimization_model,
        solver,
        status,
        settings.score_scale,
    )


def add_roster_size_constraints(
    model: cp_model.CpModel,
    solver_input: SolverInput,
    hitter_selected: dict[str, cp_model.IntVar],
    pitcher_selected: dict[str, cp_model.IntVar],
) -> None:
    candidates = solver_input.candidates
    hitter_ids = candidates.loc[candidates["can_hit"], CANDIDATE_ID_COLUMN]
    pitcher_ids = candidates.loc[candidates["can_pitch"], CANDIDATE_ID_COLUMN]

    model.add(
        sum(hitter_selected[candidate_id] for candidate_id in hitter_ids)
        == solver_input.limits.hitter_count
    )
    model.add(
        sum(pitcher_selected[candidate_id] for candidate_id in pitcher_ids)
        == solver_input.limits.pitcher_count
    )
    for row in candidates.itertuples(index=False):
        candidate_id = getattr(row, CANDIDATE_ID_COLUMN)
        if not row.can_hit:
            model.add(hitter_selected[candidate_id] == 0)
        if not row.can_pitch:
            model.add(pitcher_selected[candidate_id] == 0)
        model.add(hitter_selected[candidate_id] + pitcher_selected[candidate_id] <= 1)


def add_person_constraints(
    model: cp_model.CpModel,
    solver_input: SolverInput,
    hitter_selected: dict[str, cp_model.IntVar],
    pitcher_selected: dict[str, cp_model.IntVar],
) -> None:
    for _, members in solver_input.person_membership.groupby(
        PERSON_KEY_COLUMN, sort=False
    ):
        model.add(
            sum(
                hitter_selected[candidate_id] + pitcher_selected[candidate_id]
                for candidate_id in members[CANDIDATE_ID_COLUMN]
            )
            <= 1
        )


def add_lineup_constraints(
    model: cp_model.CpModel,
    solver_input: SolverInput,
    hitter_selected: dict[str, cp_model.IntVar],
    hitter_assignment: dict[tuple[str, str], cp_model.IntVar],
    bench: dict[tuple[str, str], cp_model.IntVar],
    splits: tuple[str, ...],
) -> None:
    edges = solver_input.matrices.hitter_assignments
    for requirement in solver_input.lineup_requirements.itertuples(index=False):
        members = edges.loc[
            edges["slot_key"].eq(requirement.slot_key), CANDIDATE_ID_COLUMN
        ]
        model.add(
            sum(
                hitter_assignment[(candidate_id, requirement.slot_key)]
                for candidate_id in members
            )
            == int(requirement.required_count)
        )

    for candidate_id in hitter_selected:
        candidate_edges = edges.loc[edges[CANDIDATE_ID_COLUMN].eq(candidate_id)]
        for split in splits:
            split_slots = candidate_edges.loc[
                candidate_edges["split"].eq(split), "slot_key"
            ]
            model.add(
                sum(
                    hitter_assignment[(candidate_id, slot_key)]
                    for slot_key in split_slots
                )
                + bench[(candidate_id, split)]
                == hitter_selected[candidate_id]
            )


def add_pitcher_group_constraints(
    model: cp_model.CpModel,
    solver_input: SolverInput,
    pitcher_selected: dict[str, cp_model.IntVar],
    pitcher_assignment: dict[tuple[str, str], cp_model.IntVar],
) -> None:
    edges = solver_input.matrices.pitcher_assignments
    for requirement in solver_input.pitcher_group_requirements.itertuples(index=False):
        members = edges.loc[
            edges["group_key"].eq(requirement.group_key), CANDIDATE_ID_COLUMN
        ]
        model.add(
            sum(
                pitcher_assignment[(candidate_id, requirement.group_key)]
                for candidate_id in members
            )
            == int(requirement.required_count)
        )

    for candidate_id in pitcher_selected:
        groups = edges.loc[edges[CANDIDATE_ID_COLUMN].eq(candidate_id), "group_key"]
        model.add(
            sum(pitcher_assignment[(candidate_id, group_key)] for group_key in groups)
            == pitcher_selected[candidate_id]
        )


def add_coverage_constraints(
    model: cp_model.CpModel,
    solver_input: SolverInput,
    bench: dict[tuple[str, str], cp_model.IntVar],
) -> None:
    capability = solver_input.matrices.hitter_position_capability
    for requirement in solver_input.coverage_requirements.itertuples(index=False):
        members = capability.loc[
            capability["position"].eq(requirement.position), CANDIDATE_ID_COLUMN
        ]
        model.add(
            sum(bench[(candidate_id, requirement.split)] for candidate_id in members)
            >= int(requirement.minimum_bench_players)
        )


def add_roster_limit_constraints(
    model: cp_model.CpModel,
    solver_input: SolverInput,
    hitter_selected: dict[str, cp_model.IntVar],
    pitcher_selected: dict[str, cp_model.IntVar],
) -> None:
    selected = {
        candidate_id: hitter_selected[candidate_id] + pitcher_selected[candidate_id]
        for candidate_id in hitter_selected
    }
    candidates = solver_input.candidates

    if solver_input.limits.point_cap_total is not None:
        model.add(
            sum(
                int(row.card_value) * selected[getattr(row, CANDIDATE_ID_COLUMN)]
                for row in candidates.itertuples(index=False)
            )
            <= solver_input.limits.point_cap_total
        )
    if solver_input.limits.variant_limit is not None:
        variant_ids = candidates.loc[candidates["is_variant"], CANDIDATE_ID_COLUMN]
        model.add(
            sum(selected[candidate_id] for candidate_id in variant_ids)
            <= solver_input.limits.variant_limit
        )

    for limit in solver_input.tier_limits.itertuples(index=False):
        member_ids = solver_input.tier_limit_membership.loc[
            solver_input.tier_limit_membership["threshold_tier"].eq(
                limit.threshold_tier
            ),
            CANDIDATE_ID_COLUMN,
        ]
        model.add(
            sum(selected[candidate_id] for candidate_id in member_ids)
            <= int(limit.max_selected)
        )


def add_objective(
    model: cp_model.CpModel,
    solver_input: SolverInput,
    settings: OptimizerSettings,
    hitter_assignment: dict[tuple[str, str], cp_model.IntVar],
    pitcher_assignment: dict[tuple[str, str], cp_model.IntVar],
    bench: dict[tuple[str, str], cp_model.IntVar],
) -> None:
    slot_weights = solver_input.lineup_requirements.set_index("slot_key")[
        "objective_weight"
    ]
    objective_terms: list[Any] = []
    for row in solver_input.matrices.hitter_assignments.itertuples(index=False):
        coefficient = scaled_score(row.score * slot_weights[row.slot_key], settings)
        objective_terms.append(
            coefficient
            * hitter_assignment[(getattr(row, CANDIDATE_ID_COLUMN), row.slot_key)]
        )
    for row in solver_input.matrices.pitcher_assignments.itertuples(index=False):
        coefficient = scaled_score(row.score, settings)
        objective_terms.append(
            coefficient
            * pitcher_assignment[(getattr(row, CANDIDATE_ID_COLUMN), row.group_key)]
        )

    utility = solver_input.matrices.hitter_utilities.set_index(CANDIDATE_ID_COLUMN)
    split_columns = {
        "vs_rhp": "batting_score_vs_rhp",
        "vs_lhp": "batting_score_vs_lhp",
    }
    for (candidate_id, split), variable in bench.items():
        if candidate_id not in utility.index:
            continue
        row = utility.loc[candidate_id]
        bench_score = float(
            row[split_columns[split]]
        ) + settings.pinch_run_share * float(row["pinch_run_score"])
        coefficient = round(
            bench_score * settings.bench_utility_weight * settings.score_scale
        )
        objective_terms.append(coefficient * variable)

    model.maximize(sum(objective_terms))


def extract_solution(
    solver_input: SolverInput,
    optimization_model: RosterOptimizationModel,
    solver: cp_model.CpSolver,
    status: str,
    score_scale: int,
) -> OptimizationSolution:
    selected_hitter_ids = tuple(
        candidate_id
        for candidate_id, variable in optimization_model.hitter_selected.items()
        if solver.value(variable)
    )
    selected_pitcher_ids = tuple(
        candidate_id
        for candidate_id, variable in optimization_model.pitcher_selected.items()
        if solver.value(variable)
    )
    hitter_assignments = selected_edge_rows(
        solver_input.matrices.hitter_assignments,
        optimization_model.hitter_assignment,
        solver,
        [CANDIDATE_ID_COLUMN, "slot_key"],
    )
    pitcher_assignments = selected_edge_rows(
        solver_input.matrices.pitcher_assignments,
        optimization_model.pitcher_assignment,
        solver,
        [CANDIDATE_ID_COLUMN, "group_key"],
    )
    candidate_names = solver_input.candidates.set_index(CANDIDATE_ID_COLUMN)["name"]
    bench_rows = [
        {
            CANDIDATE_ID_COLUMN: candidate_id,
            "name": candidate_names[candidate_id],
            "split": split,
        }
        for (candidate_id, split), variable in optimization_model.bench.items()
        if solver.value(variable)
    ]
    return OptimizationSolution(
        status=status,
        objective_value=solver.objective_value / score_scale,
        best_objective_bound=solver.best_objective_bound / score_scale,
        wall_time_seconds=solver.wall_time,
        selected_hitter_ids=selected_hitter_ids,
        selected_pitcher_ids=selected_pitcher_ids,
        hitter_assignments=hitter_assignments,
        pitcher_assignments=pitcher_assignments,
        bench_assignments=pd.DataFrame(
            bench_rows,
            columns=[CANDIDATE_ID_COLUMN, "name", "split"],
        ),
    )


def selected_edge_rows(
    edges: pd.DataFrame,
    variables: dict[tuple[str, str], cp_model.IntVar],
    solver: cp_model.CpSolver,
    key_columns: list[str],
) -> pd.DataFrame:
    selected_indices = []
    for index, row in edges.iterrows():
        key = tuple(row[column] for column in key_columns)
        if solver.value(variables[key]):
            selected_indices.append(index)
    return edges.loc[selected_indices].reset_index(drop=True).copy()


def empty_solution(status: str, wall_time_seconds: float) -> OptimizationSolution:
    return OptimizationSolution(
        status=status,
        objective_value=None,
        best_objective_bound=None,
        wall_time_seconds=wall_time_seconds,
        selected_hitter_ids=(),
        selected_pitcher_ids=(),
        hitter_assignments=pd.DataFrame(),
        pitcher_assignments=pd.DataFrame(),
        bench_assignments=pd.DataFrame(),
    )


def scaled_score(score: float, settings: OptimizerSettings) -> int:
    return round(float(score) * settings.score_scale)


def validate_settings(settings: OptimizerSettings) -> None:
    if settings.time_limit_seconds <= 0:
        raise ValueError("Optimizer time limit must be positive.")
    if settings.num_workers < 0:
        raise ValueError("Optimizer worker count cannot be negative.")
    if settings.score_scale <= 0:
        raise ValueError("Optimizer score scale must be positive.")
    if settings.bench_utility_weight < 0 or settings.pinch_run_share < 0:
        raise ValueError("Optimizer utility weights cannot be negative.")
