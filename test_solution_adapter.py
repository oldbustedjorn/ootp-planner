from dataclasses import replace

import pytest

from ootp_opt.domain.candidate_identity import CANDIDATE_ID_COLUMN
from ootp_opt.optimization.roster_optimizer import solve_roster_optimization
from ootp_opt.optimization.solution_adapter import (
    convert_optimization_solution,
    validate_solution_against_input,
)
from test_roster_optimizer import build_optimizer_fixture, deterministic_settings


def solved_fixture():
    solver_input = build_optimizer_fixture()
    solution = solve_roster_optimization(solver_input, deterministic_settings())
    hitters = solver_input.candidates.loc[solver_input.candidates["can_hit"]].copy()
    pitchers = solver_input.candidates.loc[solver_input.candidates["can_pitch"]].copy()
    return solver_input, solution, hitters, pitchers


def test_solution_adapter_preserves_both_split_lineups_and_benches():
    solver_input, solution, hitters, pitchers = solved_fixture()

    converted = convert_optimization_solution(
        solution=solution,
        solver_input=solver_input,
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
    )

    roster = converted.hitter_roster
    assert set(roster.starters_by_split) == {"vs_rhp", "vs_lhp"}
    assert roster.starters_by_split["vs_rhp"]["C"][CANDIDATE_ID_COLUMN] == "h1"
    assert roster.starters_by_split["vs_lhp"]["C"][CANDIDATE_ID_COLUMN] == "h3"
    assert roster.starters_by_position is roster.starters_by_split["vs_rhp"]
    assert set(roster.bench_by_split["vs_rhp"][CANDIDATE_ID_COLUMN]) == {
        "h3",
        "h4",
    }
    assert set(roster.bench_by_split["vs_lhp"][CANDIDATE_ID_COLUMN]) == {
        "h1",
        "h4",
    }
    assert roster.bench_players is roster.bench_by_split["vs_rhp"]


def test_solution_adapter_maps_pitcher_groups_and_unused_candidates():
    solver_input, solution, hitters, pitchers = solved_fixture()

    converted = convert_optimization_solution(
        solution=solution,
        solver_input=solver_input,
        eligible_hitters=hitters,
        eligible_pitchers=pitchers,
    )

    roster = converted.pitcher_roster
    assert set(roster.groups_by_key) == {"rotation", "middle_relief"}
    assert set(roster.rotation[CANDIDATE_ID_COLUMN]).union(
        roster.bullpen[CANDIDATE_ID_COLUMN]
    ) == set(solution.selected_pitcher_ids)
    assert roster.lefty_specialist.empty
    assert roster.long_man.empty
    assert "p1" not in set(roster.unused_players[CANDIDATE_ID_COLUMN])
    assert set(converted.hitter_roster.unused_players[CANDIDATE_ID_COLUMN]) == {"h5"}


def test_solution_validation_rejects_incomplete_lineup_assignments():
    solver_input, solution, _, _ = solved_fixture()
    broken = replace(
        solution,
        hitter_assignments=solution.hitter_assignments.iloc[1:].copy(),
    )

    with pytest.raises(ValueError, match="Lineup slot .* has 0 assignments"):
        validate_solution_against_input(broken, solver_input)


def test_solution_validation_rejects_broken_bench_partition():
    solver_input, solution, _, _ = solved_fixture()
    broken = replace(
        solution,
        bench_assignments=solution.bench_assignments.iloc[1:].copy(),
    )

    with pytest.raises(ValueError, match="do not partition"):
        validate_solution_against_input(broken, solver_input)


def test_solution_validation_rechecks_point_cap_after_solve():
    solver_input, solution, _, _ = solved_fixture()
    selected = set(solution.selected_hitter_ids + solution.selected_pitcher_ids)
    selected_value = int(
        solver_input.candidates.loc[
            solver_input.candidates[CANDIDATE_ID_COLUMN].isin(selected), "card_value"
        ].sum()
    )
    constrained = replace(
        solver_input,
        limits=replace(solver_input.limits, point_cap_total=selected_value - 1),
    )

    with pytest.raises(ValueError, match="exceeds point cap"):
        validate_solution_against_input(solution, constrained)


def test_solution_adapter_requires_every_selected_source_card():
    solver_input, solution, hitters, pitchers = solved_fixture()
    missing_id = solution.selected_hitter_ids[0]
    hitters = hitters.loc[~hitters[CANDIDATE_ID_COLUMN].eq(missing_id)].copy()

    with pytest.raises(ValueError, match="Source data is missing selected hitters"):
        convert_optimization_solution(
            solution=solution,
            solver_input=solver_input,
            eligible_hitters=hitters,
            eligible_pitchers=pitchers,
        )


def test_solution_adapter_rejects_nonfeasible_solution():
    solver_input, solution, hitters, pitchers = solved_fixture()
    infeasible = replace(solution, status="infeasible")

    with pytest.raises(ValueError, match="status 'infeasible'"):
        convert_optimization_solution(
            solution=infeasible,
            solver_input=solver_input,
            eligible_hitters=hitters,
            eligible_pitchers=pitchers,
        )
