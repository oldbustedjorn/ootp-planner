from __future__ import annotations

import pandas as pd

from ootp_opt.roster.builder import (
    get_defense_column,
    get_player_covered_positions,
    player_meets_position_threshold,
)
from ootp_opt.roster.models import HitterRoster
from ootp_opt.roster.rules import Ruleset


def get_split_score_col(split: str) -> str:
    if split == "vs_rhp":
        return "batting_score_vs_rhp"
    if split == "vs_lhp":
        return "batting_score_vs_lhp"
    if split == "overall":
        return "batting_score_overall"

    raise ValueError(
        f"Unknown lineup split '{split}'. Expected 'overall', 'vs_rhp', or 'vs_lhp'."
    )


def normalize_bats(value: object) -> str:
    bats = str(value).strip().upper()
    if bats in {"L", "R", "S"}:
        return bats
    return ""


def same_side_for_run(bats: object) -> str:
    """Switch hitters break handedness runs."""
    bats_norm = normalize_bats(bats)
    if bats_norm == "S":
        return "S"
    return bats_norm


def has_three_same_handed_in_row(lineup: list[tuple[str, pd.Series]]) -> bool:
    for i in range(len(lineup) - 2):
        hands = [
            same_side_for_run(lineup[i + offset][1].get("bats", ""))
            for offset in range(3)
        ]
        if hands[0] in {"L", "R"} and hands[0] == hands[1] == hands[2]:
            return True
    return False


def smooth_lineup_handedness(
    lineup: list[tuple[str, pd.Series]],
    score_col: str,
    max_same_hand_in_row: int = 2,
    max_swap_distance: int = 4,
    max_score_loss: float = 35.0,
) -> list[tuple[str, pd.Series]]:
    """Try to avoid 3+ L/R batters in a row using local swaps.

    This is intentionally heuristic. Switch hitters are treated as run breakers.
    """
    if max_same_hand_in_row != 2:
        raise ValueError("v1 only supports max_same_hand_in_row=2")

    smoothed = lineup.copy()

    changed = True
    while changed:
        changed = False

        for i in range(len(smoothed) - 2):
            h1 = same_side_for_run(smoothed[i][1].get("bats", ""))
            h2 = same_side_for_run(smoothed[i + 1][1].get("bats", ""))
            h3 = same_side_for_run(smoothed[i + 2][1].get("bats", ""))

            if h1 not in {"L", "R"} or not (h1 == h2 == h3):
                continue

            original_player = smoothed[i + 2][1]
            original_score = float(original_player.get(score_col, 0.0))

            best_swap_idx: int | None = None
            best_swap_loss = float("inf")

            search_end = min(len(smoothed), i + 3 + max_swap_distance)
            for candidate_idx in range(i + 3, search_end):
                candidate_player = smoothed[candidate_idx][1]
                candidate_hand = same_side_for_run(candidate_player.get("bats", ""))

                if candidate_hand == h1:
                    continue

                candidate_score = float(candidate_player.get(score_col, 0.0))
                score_loss = original_score - candidate_score

                if score_loss <= max_score_loss and score_loss < best_swap_loss:
                    best_swap_idx = candidate_idx
                    best_swap_loss = score_loss

            if best_swap_idx is not None:
                smoothed[i + 2], smoothed[best_swap_idx] = (
                    smoothed[best_swap_idx],
                    smoothed[i + 2],
                )
                changed = True
                break

    return smoothed


def build_lineup_order(
    starters_by_position: dict[str, pd.Series],
    split: str,
    smooth_handedness: bool = True,
) -> list[tuple[int, str, pd.Series]]:
    score_col = get_split_score_col(split)

    players = [(position, player) for position, player in starters_by_position.items()]

    if len(players) != 9:
        raise ValueError(f"Expected 9 starters for lineup order, got {len(players)}.")

    ranked = sorted(
        players,
        key=lambda item: float(item[1].get(score_col, 0.0)),
        reverse=True,
    )

    # Simple modern-ish lineup heuristic:
    # best bats concentrated near 2/3/4, weakest at 8/9.
    lineup = [
        ranked[2],  # leadoff: strong bat, preserves top 2 for run production
        ranked[0],  # best bat
        ranked[1],  # second-best bat
        ranked[3],  # cleanup-ish
        ranked[4],
        ranked[5],
        ranked[6],
        ranked[8],  # weakest
        ranked[7],  # second weakest / "second leadoff"
    ]

    if smooth_handedness:
        lineup = smooth_lineup_handedness(lineup, score_col=score_col)

    return [
        (idx, position, player)
        for idx, (position, player) in enumerate(lineup, start=1)
    ]


def assign_position_backups(
    position: str,
    bench_players: pd.DataFrame,
    ruleset: Ruleset,
    limit: int = 2,
) -> list[pd.Series]:
    if bench_players.empty:
        return []

    if position == "DH":
        candidates = bench_players.copy()

        # Prefer not to use backup catcher as DH depth.
        non_catchers = []
        for _, row in candidates.iterrows():
            if "C" not in get_player_covered_positions(row, ruleset):
                non_catchers.append(row)

        if non_catchers:
            candidates = pd.DataFrame(non_catchers)

        score_col = "batting_score_overall"
        if score_col not in candidates.columns:
            return []

        selected = candidates.sort_values(score_col, ascending=False).head(limit)

        return [row for _, row in selected.iterrows()]

    candidates = []

    for _, row in bench_players.iterrows():
        if not player_meets_position_threshold(row, position, ruleset):
            continue

        defense_col = get_defense_column(position)
        defense_score = float(row.get(defense_col, 0.0))
        bat_score = float(row.get("batting_score_overall", 0.0))

        candidates.append((defense_score, bat_score, row))

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)

    return [row for _, _, row in candidates[:limit]]


def build_lineup_depth_rows(
    hitter_roster: HitterRoster,
    ruleset: Ruleset,
    split: str,
) -> list[dict[str, object]]:
    lineup = build_lineup_order(
        hitter_roster.starters_by_position,
        split=split,
        smooth_handedness=True,
    )

    rows: list[dict[str, object]] = []

    for spot, position, player in lineup:
        backups = assign_position_backups(
            position=position,
            bench_players=hitter_roster.bench_players,
            ruleset=ruleset,
            limit=2,
        )

        utility_1 = backups[0] if len(backups) >= 1 else None
        utility_2 = backups[1] if len(backups) >= 2 else None

        score_col = get_split_score_col(split)

        rows.append(
            {
                "spot": spot,
                "bats": player.get("bats", ""),
                "name": player.get("name", ""),
                "position": position,
                "score": float(player.get(score_col, 0.0)),
                "utility_1": "" if utility_1 is None else utility_1.get("name", ""),
                "utility_1_starts": "" if utility_1 is None else "If Starter tired",
                "utility_2": "" if utility_2 is None else utility_2.get("name", ""),
                "utility_2_starts": "" if utility_2 is None else "If Starter tired",
            }
        )

    return rows


def build_pinch_hitters(
    bench_players: pd.DataFrame,
    split: str = "overall",
    limit: int = 4,
) -> pd.DataFrame:
    if bench_players.empty:
        return bench_players.copy()

    score_col = get_split_score_col(split)
    if score_col not in bench_players.columns:
        score_col = "batting_score_overall"

    return bench_players.sort_values(score_col, ascending=False).head(limit).copy()


def build_pinch_runners(
    bench_players: pd.DataFrame,
    limit: int = 4,
) -> pd.DataFrame:
    if bench_players.empty:
        return bench_players.copy()

    score_col = "pinch_run_score"
    if score_col not in bench_players.columns:
        return bench_players.head(0).copy()

    return bench_players.sort_values(score_col, ascending=False).head(limit).copy()


def format_lineup_depth_rows(rows: list[dict[str, object]]) -> str:
    header = (
        f"{'#':>2}  {'B':<1}  {'Player':<25} {'POS':<3}  "
        f"{'Utility 1':<25} {'Starts':<18} "
        f"{'Utility 2':<25} {'Starts':<18}"
    )

    lines = [header, "-" * len(header)]

    for row in rows:
        lines.append(
            f"{row['spot']:>2}  "
            f"{str(row['bats']):<1}  "
            f"{str(row['name']):<25} "
            f"{str(row['position']):<3}  "
            f"{str(row['utility_1']):<25} "
            f"{str(row['utility_1_starts']):<18} "
            f"{str(row['utility_2']):<25} "
            f"{str(row['utility_2_starts']):<18}"
        )

    return "\n".join(lines)
