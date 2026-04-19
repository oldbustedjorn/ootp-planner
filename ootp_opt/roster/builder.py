from __future__ import annotations

import pandas as pd
from itertools import permutations

from ootp_opt.roster.models import PitcherRoster
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset


def get_hitter_score_column(position: str) -> str:
    if position == "DH":
        return "batting_score_overall"
    return f"score_{position}_overall"


def get_player_score_for_position(player: pd.Series, position: str) -> float:
    score_col = get_hitter_score_column(position)
    if score_col not in player.index:
        raise ValueError(f"Missing required hitter score column: {score_col}")
    return float(player[score_col])


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


def build_hitter_roster(df: pd.DataFrame, ruleset: Ruleset) -> HitterRoster:
    starters_by_position, remaining = build_hitter_starters(df, ruleset)
    starters_by_position = optimize_hitter_starter_assignments(
        starters_by_position, ruleset
    )

    return HitterRoster(
        starters_by_position=starters_by_position,
        bench_players=remaining.head(0).copy(),
        unused_players=remaining,
    )
