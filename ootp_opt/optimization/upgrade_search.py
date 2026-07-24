from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from ootp_opt.domain.candidate_identity import CANDIDATE_ID_COLUMN
from ootp_opt.optimization.candidate_matrices import (
    build_hitter_assignments,
    build_pitcher_assignments,
)
from ootp_opt.optimization.roster_optimizer import (
    OptimizationSolution,
    OptimizerSettings,
    build_optimization_model,
    solve_optimization_model,
)
from ootp_opt.optimization.solver_input import SolverInput
from ootp_opt.roster.rules import Ruleset


DIRECT_UPGRADE_COLUMNS = [
    CANDIDATE_ID_COLUMN,
    "type",
    "role_key",
    "role",
    "current_candidate_id",
    "current_player",
    "current_score",
    "candidate_score",
    "direct_score_gain",
    "estimated_objective_gain",
]


@dataclass(frozen=True)
class CandidateUpgradeSolution:
    candidate_id: str
    objective_gain: float
    solution: OptimizationSolution


def build_direct_upgrade_opportunities(
    *,
    store_hitters: pd.DataFrame,
    store_pitchers: pd.DataFrame,
    ruleset: Ruleset,
    baseline_solution: OptimizationSolution,
    baseline_input: SolverInput,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not store_hitters.empty:
        store_assignments = build_hitter_assignments(store_hitters, ruleset)
        current = baseline_solution.hitter_assignments[
            [CANDIDATE_ID_COLUMN, "slot_key", "name", "score"]
        ].rename(
            columns={
                CANDIDATE_ID_COLUMN: "current_candidate_id",
                "name": "current_player",
                "score": "current_score",
            }
        )
        hitter_opportunities = store_assignments.merge(
            current,
            on="slot_key",
            how="inner",
        )
        slot_weights = baseline_input.lineup_requirements.set_index("slot_key")[
            "objective_weight"
        ]
        hitter_opportunities["type"] = "hitter"
        hitter_opportunities["role_key"] = hitter_opportunities["slot_key"]
        hitter_opportunities["role"] = hitter_opportunities.apply(
            lambda row: f"{split_label(row['split'])} {row['position']}",
            axis=1,
        )
        hitter_opportunities["candidate_score"] = hitter_opportunities["score"]
        hitter_opportunities["direct_score_gain"] = (
            hitter_opportunities["candidate_score"]
            - hitter_opportunities["current_score"]
        )
        hitter_opportunities["estimated_objective_gain"] = (
            hitter_opportunities["direct_score_gain"]
            * hitter_opportunities["slot_key"].map(slot_weights)
        )
        frames.append(hitter_opportunities[DIRECT_UPGRADE_COLUMNS])

    if not store_pitchers.empty:
        store_assignments = build_pitcher_assignments(store_pitchers, ruleset)
        current = (
            baseline_solution.pitcher_assignments.sort_values("score")
            .groupby("group_key", sort=False)
            .head(1)[
                [CANDIDATE_ID_COLUMN, "group_key", "name", "score"]
            ]
            .rename(
                columns={
                    CANDIDATE_ID_COLUMN: "current_candidate_id",
                    "name": "current_player",
                    "score": "current_score",
                }
            )
        )
        pitcher_opportunities = store_assignments.merge(
            current,
            on="group_key",
            how="inner",
        )
        pitcher_opportunities["type"] = "pitcher"
        pitcher_opportunities["role_key"] = pitcher_opportunities["group_key"]
        pitcher_opportunities["role"] = pitcher_opportunities["group_label"]
        pitcher_opportunities["candidate_score"] = pitcher_opportunities["score"]
        pitcher_opportunities["direct_score_gain"] = (
            pitcher_opportunities["candidate_score"]
            - pitcher_opportunities["current_score"]
        )
        pitcher_opportunities["estimated_objective_gain"] = pitcher_opportunities[
            "direct_score_gain"
        ]
        frames.append(pitcher_opportunities[DIRECT_UPGRADE_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=DIRECT_UPGRADE_COLUMNS)
    return (
        pd.concat(frames, ignore_index=True)
        .loc[lambda frame: frame["direct_score_gain"].gt(0)]
        .sort_values("estimated_objective_gain", ascending=False)
        .reset_index(drop=True)
    )


def enumerate_single_purchase_upgrades(
    *,
    solver_input: SolverInput,
    store_candidate_ids: Iterable[str],
    baseline_solution: OptimizationSolution,
    min_gain: float,
    max_results: int,
    settings: OptimizerSettings | None = None,
) -> list[CandidateUpgradeSolution]:
    if not baseline_solution.is_feasible or baseline_solution.objective_value is None:
        raise ValueError("Upgrade search requires a feasible optimizer baseline.")
    if max_results <= 0:
        raise ValueError("Upgrade result count must be positive.")

    settings = settings or OptimizerSettings()
    known_ids = set(solver_input.candidates[CANDIDATE_ID_COLUMN])
    store_ids = tuple(dict.fromkeys(store_candidate_ids))
    unknown = set(store_ids) - known_ids
    if unknown:
        raise ValueError(f"Unknown store candidate IDs: {sorted(unknown)}")
    if not store_ids:
        return []

    optimization_model = build_optimization_model(solver_input, settings)
    selected = {
        candidate_id: (
            optimization_model.hitter_selected[candidate_id]
            + optimization_model.pitcher_selected[candidate_id]
        )
        for candidate_id in store_ids
    }
    optimization_model.model.add(sum(selected.values()) <= 1)

    results: list[CandidateUpgradeSolution] = []
    for _ in range(max_results):
        solution = solve_optimization_model(
            solver_input,
            optimization_model,
            settings,
        )
        if not solution.is_feasible or solution.objective_value is None:
            break

        purchased = selected_store_candidate(solution, set(store_ids))
        if purchased is None:
            break

        gain = solution.objective_value - baseline_solution.objective_value
        optimization_model.model.add(selected[purchased] == 0)
        if gain + 1e-9 < min_gain:
            break

        results.append(
            CandidateUpgradeSolution(
                candidate_id=purchased,
                objective_gain=gain,
                solution=solution,
            )
        )

    return results


def selected_store_candidate(
    solution: OptimizationSolution,
    store_candidate_ids: set[str],
) -> str | None:
    selected = store_candidate_ids.intersection(
        solution.selected_hitter_ids + solution.selected_pitcher_ids
    )
    if len(selected) > 1:
        raise ValueError("Upgrade solution selected more than one store candidate.")
    return next(iter(selected), None)


def split_label(split: str) -> str:
    return "vs RHP" if split == "vs_rhp" else "vs LHP"
