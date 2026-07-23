from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PERSON_KEY_COLUMN,
)
from ootp_opt.optimization.roster_optimizer import OptimizationSolution
from ootp_opt.optimization.solver_input import SolverInput
from ootp_opt.roster.builder import validate_no_duplicate_players
from ootp_opt.roster.models import HitterRoster, PitcherRoster


@dataclass(frozen=True)
class ConvertedOptimizationRoster:
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster


def convert_optimization_solution(
    *,
    solution: OptimizationSolution,
    solver_input: SolverInput,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
) -> ConvertedOptimizationRoster:
    """Convert a feasible solver result into the existing roster contracts."""
    validate_solution_against_input(solution, solver_input)
    validate_source_candidates(eligible_hitters, "hitter")
    validate_source_candidates(eligible_pitchers, "pitcher")

    require_source_ids(
        eligible_hitters,
        solution.selected_hitter_ids,
        "selected hitters",
    )
    require_source_ids(
        eligible_pitchers,
        solution.selected_pitcher_ids,
        "selected pitchers",
    )

    starters_by_split = build_split_starters(solution, eligible_hitters)
    bench_by_split = build_split_benches(solution, eligible_hitters)
    primary_split = preferred_primary_split(starters_by_split)
    groups_by_key = build_pitcher_groups(solution, eligible_pitchers)

    selected_person_keys = selected_roster_person_keys(solution, solver_input)
    hitter_roster = HitterRoster(
        starters_by_position=starters_by_split[primary_split],
        bench_players=bench_by_split[primary_split],
        unused_players=unused_candidates(eligible_hitters, selected_person_keys),
        starters_by_split=starters_by_split,
        bench_by_split=bench_by_split,
    )
    pitcher_roster = PitcherRoster(
        rotation=group_or_empty(groups_by_key, "rotation", eligible_pitchers),
        bullpen=group_or_empty(groups_by_key, "middle_relief", eligible_pitchers),
        lefty_specialist=group_or_empty(
            groups_by_key,
            "lefty_specialist",
            eligible_pitchers,
        ),
        long_man=group_or_empty(groups_by_key, "long_relief", eligible_pitchers),
        unused_players=unused_candidates(eligible_pitchers, selected_person_keys),
        groups_by_key=groups_by_key,
    )
    converted = ConvertedOptimizationRoster(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
    )
    validate_converted_roster(converted, solution, solver_input)
    return converted


def validate_solution_against_input(
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> None:
    if not solution.is_feasible:
        raise ValueError(
            f"Cannot convert optimizer solution with status '{solution.status}'."
        )

    hitter_ids = tuple(solution.selected_hitter_ids)
    pitcher_ids = tuple(solution.selected_pitcher_ids)
    require_unique_ids(hitter_ids, "selected hitters")
    require_unique_ids(pitcher_ids, "selected pitchers")
    if set(hitter_ids).intersection(pitcher_ids):
        raise ValueError("A candidate cannot be selected as both hitter and pitcher.")
    if len(hitter_ids) != solver_input.limits.hitter_count:
        raise ValueError(
            "Optimizer hitter count does not match solver input: "
            f"{len(hitter_ids)} != {solver_input.limits.hitter_count}."
        )
    if len(pitcher_ids) != solver_input.limits.pitcher_count:
        raise ValueError(
            "Optimizer pitcher count does not match solver input: "
            f"{len(pitcher_ids)} != {solver_input.limits.pitcher_count}."
        )

    candidates = solver_input.candidates.set_index(CANDIDATE_ID_COLUMN, drop=False)
    require_known_ids(candidates, hitter_ids + pitcher_ids, "selected roster")
    if not candidates.loc[list(hitter_ids), "can_hit"].all():
        raise ValueError("Optimizer selected a candidate without hitter eligibility.")
    if not candidates.loc[list(pitcher_ids), "can_pitch"].all():
        raise ValueError("Optimizer selected a candidate without pitcher eligibility.")

    validate_person_uniqueness(candidates.loc[list(hitter_ids + pitcher_ids)])
    validate_lineup_assignments(solution, solver_input)
    validate_pitcher_assignments(solution, solver_input)
    validate_roster_limits(solution, solver_input)


def validate_lineup_assignments(
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> None:
    assignments = solution.hitter_assignments
    required_columns = {CANDIDATE_ID_COLUMN, "slot_key", "split", "position"}
    require_columns(assignments, required_columns, "hitter assignments")
    if assignments.duplicated([CANDIDATE_ID_COLUMN, "split"]).any():
        raise ValueError("A hitter is assigned to multiple positions in one lineup.")

    selected_ids = set(solution.selected_hitter_ids)
    if not set(assignments[CANDIDATE_ID_COLUMN]).issubset(selected_ids):
        raise ValueError("Hitter assignments contain an unselected candidate.")

    requirements = solver_input.lineup_requirements.set_index("slot_key")
    assignment_slots = set(assignments["slot_key"])
    unknown_slots = assignment_slots - set(requirements.index)
    if unknown_slots:
        raise ValueError(f"Hitter assignments contain unknown slots: {unknown_slots}")

    for slot_key, requirement in requirements.iterrows():
        rows = assignments.loc[assignments["slot_key"].eq(slot_key)]
        if len(rows) != int(requirement["required_count"]):
            raise ValueError(
                f"Lineup slot '{slot_key}' has {len(rows)} assignments; "
                f"expected {int(requirement['required_count'])}."
            )
        if (
            not rows["split"].eq(requirement["split"]).all()
            or not rows["position"].eq(requirement["position"]).all()
        ):
            raise ValueError(f"Lineup slot '{slot_key}' has mismatched metadata.")

    validate_bench_membership(solution, solver_input)
    validate_coverage(solution, solver_input)


def validate_bench_membership(
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> None:
    bench = solution.bench_assignments
    require_columns(bench, {CANDIDATE_ID_COLUMN, "split"}, "bench assignments")
    if bench.duplicated([CANDIDATE_ID_COLUMN, "split"]).any():
        raise ValueError("Optimizer bench assignments contain duplicate rows.")

    selected_ids = set(solution.selected_hitter_ids)
    splits = solver_input.lineup_requirements["split"].drop_duplicates()
    for split in splits:
        starter_ids = set(
            solution.hitter_assignments.loc[
                solution.hitter_assignments["split"].eq(split), CANDIDATE_ID_COLUMN
            ]
        )
        bench_ids = set(bench.loc[bench["split"].eq(split), CANDIDATE_ID_COLUMN])
        if starter_ids.intersection(bench_ids):
            raise ValueError(f"A {split} starter is also marked as bench.")
        if starter_ids.union(bench_ids) != selected_ids:
            raise ValueError(
                f"The {split} starter and bench assignments do not partition "
                "the selected hitter roster."
            )


def validate_coverage(
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> None:
    capability = solver_input.matrices.hitter_position_capability
    for requirement in solver_input.coverage_requirements.itertuples(index=False):
        bench_ids = set(
            solution.bench_assignments.loc[
                solution.bench_assignments["split"].eq(requirement.split),
                CANDIDATE_ID_COLUMN,
            ]
        )
        capable_ids = set(
            capability.loc[
                capability["position"].eq(requirement.position),
                CANDIDATE_ID_COLUMN,
            ]
        )
        covered_count = len(bench_ids.intersection(capable_ids))
        if covered_count < int(requirement.minimum_bench_players):
            raise ValueError(
                f"Coverage requirement '{requirement.requirement_key}' has "
                f"{covered_count} qualified bench players; expected at least "
                f"{int(requirement.minimum_bench_players)}."
            )


def validate_pitcher_assignments(
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> None:
    assignments = solution.pitcher_assignments
    required_columns = {CANDIDATE_ID_COLUMN, "group_key"}
    require_columns(assignments, required_columns, "pitcher assignments")
    if assignments[CANDIDATE_ID_COLUMN].duplicated().any():
        raise ValueError("A pitcher is assigned to multiple role groups.")

    selected_ids = set(solution.selected_pitcher_ids)
    if set(assignments[CANDIDATE_ID_COLUMN]) != selected_ids:
        raise ValueError(
            "Pitcher role assignments do not match the selected pitcher roster."
        )

    requirements = solver_input.pitcher_group_requirements.set_index("group_key")
    unknown_groups = set(assignments["group_key"]) - set(requirements.index)
    if unknown_groups:
        raise ValueError(
            f"Pitcher assignments contain unknown groups: {unknown_groups}"
        )
    for group_key, requirement in requirements.iterrows():
        count = int(assignments["group_key"].eq(group_key).sum())
        if count != int(requirement["required_count"]):
            raise ValueError(
                f"Pitcher group '{group_key}' has {count} assignments; "
                f"expected {int(requirement['required_count'])}."
            )


def validate_roster_limits(
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> None:
    selected_ids = set(solution.selected_hitter_ids + solution.selected_pitcher_ids)
    selected = solver_input.candidates.loc[
        solver_input.candidates[CANDIDATE_ID_COLUMN].isin(selected_ids)
    ]

    if solver_input.limits.point_cap_total is not None:
        total_value = int(selected["card_value"].sum())
        if total_value > solver_input.limits.point_cap_total:
            raise ValueError(
                f"Optimized roster value {total_value} exceeds point cap "
                f"{solver_input.limits.point_cap_total}."
            )
    if solver_input.limits.variant_limit is not None:
        variant_count = int(selected["is_variant"].sum())
        if variant_count > solver_input.limits.variant_limit:
            raise ValueError(
                f"Optimized roster has {variant_count} variants; limit is "
                f"{solver_input.limits.variant_limit}."
            )

    for limit in solver_input.tier_limits.itertuples(index=False):
        member_ids = set(
            solver_input.tier_limit_membership.loc[
                solver_input.tier_limit_membership["threshold_tier"].eq(
                    limit.threshold_tier
                ),
                CANDIDATE_ID_COLUMN,
            ]
        )
        selected_count = len(selected_ids.intersection(member_ids))
        if selected_count > int(limit.max_selected):
            raise ValueError(
                f"Optimized roster uses {selected_count} cards at or above "
                f"{limit.threshold_tier}; limit is {int(limit.max_selected)}."
            )


def build_split_starters(
    solution: OptimizationSolution,
    eligible_hitters: pd.DataFrame,
) -> dict[str, dict[str, pd.Series]]:
    lineups: dict[str, dict[str, pd.Series]] = {}
    for split, rows in solution.hitter_assignments.groupby("split", sort=False):
        lineups[str(split)] = {
            str(row.position): source_row(
                eligible_hitters,
                getattr(row, CANDIDATE_ID_COLUMN),
            )
            for row in rows.itertuples(index=False)
        }
    return lineups


def build_split_benches(
    solution: OptimizationSolution,
    eligible_hitters: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    benches: dict[str, pd.DataFrame] = {}
    selected_order = list(solution.selected_hitter_ids)
    for split in solution.hitter_assignments["split"].drop_duplicates():
        bench_ids = set(
            solution.bench_assignments.loc[
                solution.bench_assignments["split"].eq(split), CANDIDATE_ID_COLUMN
            ]
        )
        ordered_ids = [
            candidate_id for candidate_id in selected_order if candidate_id in bench_ids
        ]
        benches[str(split)] = source_rows(eligible_hitters, ordered_ids)
    return benches


def build_pitcher_groups(
    solution: OptimizationSolution,
    eligible_pitchers: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    groups: dict[str, pd.DataFrame] = {}
    for group_key, rows in solution.pitcher_assignments.groupby(
        "group_key", sort=False
    ):
        ordered = rows.sort_values("score", ascending=False)
        groups[str(group_key)] = source_rows(
            eligible_pitchers,
            ordered[CANDIDATE_ID_COLUMN].tolist(),
        )
    return groups


def validate_converted_roster(
    converted: ConvertedOptimizationRoster,
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> None:
    hitter_roster = converted.hitter_roster
    pitcher_roster = converted.pitcher_roster
    expected_splits = set(solver_input.lineup_requirements["split"])
    if set(hitter_roster.starters_by_split) != expected_splits:
        raise ValueError("Converted roster is missing one or more split lineups.")
    if set(hitter_roster.bench_by_split) != expected_splits:
        raise ValueError("Converted roster is missing one or more split benches.")

    for split in expected_splits:
        starter_ids = {
            str(row[CANDIDATE_ID_COLUMN])
            for row in hitter_roster.starters_by_split[split].values()
        }
        bench_ids = set(hitter_roster.bench_by_split[split][CANDIDATE_ID_COLUMN])
        if starter_ids.union(bench_ids) != set(solution.selected_hitter_ids):
            raise ValueError(
                f"Converted {split} hitter roster does not match solution."
            )

    converted_pitcher_ids = set()
    for group in pitcher_roster.groups_by_key.values():
        converted_pitcher_ids.update(group[CANDIDATE_ID_COLUMN])
    if converted_pitcher_ids != set(solution.selected_pitcher_ids):
        raise ValueError("Converted pitcher roster does not match solution.")

    validate_no_duplicate_players(hitter_roster, pitcher_roster)


def preferred_primary_split(
    starters_by_split: dict[str, dict[str, pd.Series]],
) -> str:
    if "vs_rhp" in starters_by_split:
        return "vs_rhp"
    if not starters_by_split:
        raise ValueError("Optimizer solution contains no hitter lineups.")
    return next(iter(starters_by_split))


def selected_roster_person_keys(
    solution: OptimizationSolution,
    solver_input: SolverInput,
) -> set[str]:
    selected_ids = set(solution.selected_hitter_ids + solution.selected_pitcher_ids)
    return set(
        solver_input.candidates.loc[
            solver_input.candidates[CANDIDATE_ID_COLUMN].isin(selected_ids),
            PERSON_KEY_COLUMN,
        ]
    )


def unused_candidates(
    candidates: pd.DataFrame,
    selected_person_keys: set[str],
) -> pd.DataFrame:
    return candidates.loc[
        ~candidates[PERSON_KEY_COLUMN].isin(selected_person_keys)
    ].copy()


def group_or_empty(
    groups: dict[str, pd.DataFrame],
    group_key: str,
    source: pd.DataFrame,
) -> pd.DataFrame:
    return groups.get(group_key, source.head(0).copy())


def source_row(source: pd.DataFrame, candidate_id: str) -> pd.Series:
    rows = source.loc[source[CANDIDATE_ID_COLUMN].eq(candidate_id)]
    if len(rows) != 1:
        raise ValueError(
            f"Expected one source row for candidate '{candidate_id}', found {len(rows)}."
        )
    return rows.iloc[0].copy()


def source_rows(source: pd.DataFrame, candidate_ids: list[str]) -> pd.DataFrame:
    if not candidate_ids:
        return source.head(0).copy()
    indexed = source.set_index(CANDIDATE_ID_COLUMN, drop=False)
    return indexed.loc[candidate_ids].copy()


def validate_source_candidates(source: pd.DataFrame, label: str) -> None:
    require_columns(
        source,
        {CANDIDATE_ID_COLUMN, PERSON_KEY_COLUMN},
        f"eligible {label} source",
    )
    if source[CANDIDATE_ID_COLUMN].duplicated().any():
        raise ValueError(f"Eligible {label} source contains duplicate candidate IDs.")


def require_source_ids(
    source: pd.DataFrame,
    candidate_ids: tuple[str, ...],
    label: str,
) -> None:
    missing = set(candidate_ids) - set(source[CANDIDATE_ID_COLUMN])
    if missing:
        raise ValueError(f"Source data is missing {label}: {sorted(missing)}")


def require_known_ids(
    indexed_candidates: pd.DataFrame,
    candidate_ids: tuple[str, ...],
    label: str,
) -> None:
    missing = set(candidate_ids) - set(indexed_candidates.index)
    if missing:
        raise ValueError(f"Solver input is missing {label} IDs: {sorted(missing)}")


def require_unique_ids(candidate_ids: tuple[str, ...], label: str) -> None:
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(f"Optimizer {label} contain duplicate candidate IDs.")


def validate_person_uniqueness(selected: pd.DataFrame) -> None:
    duplicate_people = selected[PERSON_KEY_COLUMN].duplicated(keep=False)
    if duplicate_people.any():
        names = selected.loc[duplicate_people, "name"].tolist()
        raise ValueError(f"Optimizer selected alternate cards for one person: {names}")


def require_columns(
    frame: pd.DataFrame,
    columns: set[str],
    label: str,
) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for {label}: {sorted(missing)}")
