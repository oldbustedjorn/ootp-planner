from __future__ import annotations

import pandas as pd
from itertools import permutations

from ootp_opt.roster.models import PitcherRoster
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset


def select_top_n(
    df: pd.DataFrame,
    score_col: str,
    n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if score_col not in df.columns:
        raise ValueError(f"Missing required score column: {score_col}")

    selected = df.sort_values(score_col, ascending=False).head(n).copy()

    remaining = df.drop(index=selected.index).copy()
    return selected, remaining


def get_hitter_score_column(position: str) -> str:
    if position == "DH":
        return "batting_score_overall"
    return f"score_{position}_overall"


def get_player_score_for_position(player: pd.Series, position: str) -> float:
    score_col = get_hitter_score_column(position)
    if score_col not in player.index:
        raise ValueError(f"Missing required hitter score column: {score_col}")
    return float(player[score_col])


def get_defense_column(position: str) -> str:
    return f"fld_{position}"


def player_meets_position_threshold(
    player: pd.Series,
    position: str,
    ruleset: Ruleset,
) -> bool:
    defense_col = get_defense_column(position)
    threshold = ruleset.min_defense_by_position.get(position)

    if threshold is None:
        return False
    if defense_col not in player.index:
        return False

    value = player[defense_col]
    if pd.isna(value):
        return False

    return float(value) >= float(threshold)


def get_player_covered_positions(
    player: pd.Series,
    ruleset: Ruleset,
) -> set[str]:
    covered = set()

    for position in ruleset.min_defense_by_position:
        if player_meets_position_threshold(player, position, ruleset):
            covered.add(position)

    return covered


def player_qualifies_for_bench_role(
    player: pd.Series,
    role_name: str,
    ruleset: Ruleset,
) -> bool:
    role_req = ruleset.bench_role_requirements[role_name]
    covered_positions = get_player_covered_positions(player, ruleset)

    if role_req.required_positions:
        if not all(pos in covered_positions for pos in role_req.required_positions):
            return False

    if role_req.required_positions_any:
        if not any(pos in covered_positions for pos in role_req.required_positions_any):
            return False

    return True


def score_bench_candidate(
    player: pd.Series,
    role_name: str,
    ruleset: Ruleset,
    uncovered_positions: set[str] | None = None,
) -> float:
    batting_score = float(player.get("batting_score_overall", 0.0))
    covered_positions = get_player_covered_positions(player, ruleset)
    role_req = ruleset.bench_role_requirements[role_name]

    preferred_hits = sum(
        1 for pos in role_req.preferred_positions if pos in covered_positions
    )

    uncovered_hits = 0
    if uncovered_positions is not None:
        uncovered_hits = sum(
            1 for pos in uncovered_positions if pos in covered_positions
        )

    # 🔴 THIS IS THE IMPORTANT PART
    if role_name == "UTIL":
        return (uncovered_hits * 100.0) + (preferred_hits * 5.0) + batting_score

    return batting_score + (preferred_hits * 2.0) + (uncovered_hits * 5.0)


def build_pitcher_roster(df: pd.DataFrame, ruleset: Ruleset) -> PitcherRoster:
    remaining = df.copy()

    rotation, remaining = select_top_n(
        remaining,
        score_col="starter_score_overall",
        n=ruleset.rotation_size,
    )

    bullpen, remaining = select_top_n(
        remaining,
        score_col="reliever_score_overall",
        n=ruleset.primary_rp_count,
    )

    lefty_specialist, remaining = select_top_n(
        remaining,
        score_col="reliever_score_vs_lhb",
        n=ruleset.specialist_lhp_count,
    )

    long_man, remaining = select_top_n(
        remaining,
        score_col="starter_score_overall",
        n=ruleset.long_man_count,
    )

    return PitcherRoster(
        rotation=rotation,
        bullpen=bullpen,
        lefty_specialist=lefty_specialist,
        long_man=long_man,
        unused_players=remaining,
    )


def build_hitter_starters(
    df: pd.DataFrame,
    ruleset: Ruleset,
) -> tuple[dict[str, pd.Series], pd.DataFrame]:
    remaining = df.copy()
    starters_by_position: dict[str, pd.Series] = {}

    for position in ruleset.lineup_fill_order:
        score_col = get_hitter_score_column(position)

        if score_col not in remaining.columns:
            raise ValueError(f"Missing required hitter score column: {score_col}")

        selected = remaining.sort_values(score_col, ascending=False).head(1)

        if selected.empty:
            raise ValueError(f"No available hitter found for position {position}")

        selected_row = selected.iloc[0]
        starters_by_position[position] = selected_row

        remaining = remaining.drop(index=selected.index).copy()

    return starters_by_position, remaining


def optimize_hitter_starter_assignments(
    starters_by_position: dict[str, pd.Series],
    ruleset: Ruleset,
) -> dict[str, pd.Series]:
    positions = list(ruleset.lineup_fill_order)
    players = list(starters_by_position.values())

    if len(players) != len(positions):
        raise ValueError(
            f"Starter optimization requires equal counts of players and positions: "
            f"{len(players)} players vs {len(positions)} positions"
        )

    best_score = float("-inf")
    best_assignment: dict[str, pd.Series] | None = None

    for player_perm in permutations(players):
        total_score = 0.0
        assignment: dict[str, pd.Series] = {}

        for position, player in zip(positions, player_perm):
            score = get_player_score_for_position(player, position)
            total_score += score
            assignment[position] = player

        if total_score > best_score:
            best_score = total_score
            best_assignment = assignment

    if best_assignment is None:
        raise ValueError("Failed to find an optimized starter assignment.")

    return best_assignment


def build_hitter_bench(
    df_remaining: pd.DataFrame,
    ruleset: Ruleset,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    remaining = df_remaining.copy()
    selected_rows = []

    covered_by_bench: set[str] = set()

    for role_name in ruleset.bench_roles:
        eligible_mask = remaining.apply(
            lambda row: player_qualifies_for_bench_role(row, role_name, ruleset),
            axis=1,
        )
        candidates = remaining.loc[eligible_mask].copy()

        if candidates.empty:
            top_candidates = remaining.copy()
            if role_name == "C" and "fld_C" in top_candidates.columns:
                top_candidates = top_candidates.sort_values("fld_C", ascending=False)
                detail = top_candidates[
                    ["name", "fld_C", "batting_score_overall"]
                ].head(10)
            else:
                detail = top_candidates[["name", "batting_score_overall"]].head(10)

            raise ValueError(
                f"No eligible bench candidate found for role '{role_name}'.\n"
                f"Top remaining candidates:\n{detail.to_string(index=False)}"
            )

        all_positions = set(ruleset.min_defense_by_position.keys())
        uncovered_positions = all_positions - covered_by_bench

        candidates["_bench_score"] = candidates.apply(
            lambda row: score_bench_candidate(
                row,
                role_name,
                ruleset,
                uncovered_positions=uncovered_positions,
            ),
            axis=1,
        )

        selected = (
            candidates.sort_values("_bench_score", ascending=False).head(1).copy()
        )
        selected_rows.append(selected)

        selected_player = selected.iloc[0]
        selected_covered_positions = get_player_covered_positions(
            selected_player, ruleset
        )

        covered_by_bench |= selected_covered_positions
        remaining = remaining.drop(index=selected.index).copy()

        print(f"\nRole: {role_name}")
        print(f"Uncovered before pick: {sorted(uncovered_positions)}")
        print(f"Selected: {selected_player['name']}")
        print(f"Covers: {sorted(selected_covered_positions)}")
        print(f"Covered by bench so far: {sorted(covered_by_bench)}")
        print(f"Still uncovered after pick: {sorted(all_positions - covered_by_bench)}")

    bench_players = pd.concat(selected_rows, ignore_index=False).copy()
    if "_bench_score" in bench_players.columns:
        bench_players = bench_players.drop(columns=["_bench_score"])

    return bench_players, remaining


def build_hitter_roster(df: pd.DataFrame, ruleset: Ruleset) -> HitterRoster:
    greedy_starters, remaining = build_hitter_starters(df, ruleset)
    starters_by_position = optimize_hitter_starter_assignments(greedy_starters, ruleset)

    bench_players, remaining = build_hitter_bench(remaining, ruleset)

    return HitterRoster(
        starters_by_position=starters_by_position,
        bench_players=bench_players,
        unused_players=remaining,
    )
