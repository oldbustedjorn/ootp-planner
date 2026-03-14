from __future__ import annotations

import pandas as pd

POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]


def _playable_positions_with_ratings(row: pd.Series) -> str:
    """Return a comma-separated list like SS(103),2B(118),3B(87)."""
    playable: list[str] = []

    for pos in POSITIONS:
        fld_col = f"fld_{pos}"
        if fld_col in row and pd.notna(row[fld_col]):
            try:
                rating = float(row[fld_col])
                if rating >= 1:
                    playable.append(f"{pos}({int(rating)})")
            except (TypeError, ValueError):
                pass

    return ",".join(playable)


def _best_positions_by_score(row: pd.Series, top_n: int = 3) -> str:
    """Return a compact summary like 2B:812|SS:788|3B:731."""
    scored_positions: list[tuple[str, float]] = []

    for pos in POSITIONS:
        fld_col = f"fld_{pos}"
        score_col = f"score_{pos}_overall"

        if fld_col in row and score_col in row:
            try:
                fld_rating = float(row[fld_col])
                pos_score = float(row[score_col])

                if fld_rating >= 1 and pos_score > -1_000_000:
                    scored_positions.append((pos, pos_score))
            except (TypeError, ValueError):
                pass

    scored_positions.sort(key=lambda x: x[1], reverse=True)
    top_positions = scored_positions[:top_n]

    return "|".join(f"{pos}:{int(score)}" for pos, score in top_positions)


def generate_hitter_shortlists(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    # Top players per position
    for pos in POSITIONS:
        col = f"score_{pos}_overall"

        top = (
            df.sort_values(col, ascending=False)
            .head(top_n)
            .reset_index(drop=True)
        )

        for rank, (_, r) in enumerate(top.iterrows(), start=1):
            rows.append(
                {
                    "report_type": "position",
                    "position": pos,
                    "rank": rank,
                    "name": r["name"],
                    "playable_positions": _playable_positions_with_ratings(r),
                    "best_positions_by_score": _best_positions_by_score(r),
                    "score": r[col],
                    "batting_score_overall": r.get("batting_score_overall", ""),
                    "batting_score_vs_lhp": r.get("batting_score_vs_lhp", ""),
                    "batting_score_vs_rhp": r.get("batting_score_vs_rhp", ""),
                    "score_vs_lhp": r.get(f"score_{pos}_vs_lhp", ""),
                    "score_vs_rhp": r.get(f"score_{pos}_vs_rhp", ""),
                }
            )

    # Best hitters vs LHP
    top_l = (
        df.sort_values("hitter_score_vs_lhp", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    for rank, (_, r) in enumerate(top_l.iterrows(), start=1):
        rows.append(
            {
                "report_type": "platoon",
                "position": "vs_lhp",
                "rank": rank,
                "name": r["name"],
                "playable_positions": _playable_positions_with_ratings(r),
                "best_positions_by_score": _best_positions_by_score(r),
                "score": r["hitter_score_vs_lhp"],
                "hitter_score_overall": r["hitter_score_overall"],
                "batting_score_overall": r.get("batting_score_overall", ""),
                "batting_score_vs_lhp": r.get("batting_score_vs_lhp", ""),
                "batting_score_vs_rhp": r.get("batting_score_vs_rhp", ""),
                "score_vs_lhp": r["hitter_score_vs_lhp"],
                "score_vs_rhp": r["hitter_score_vs_rhp"],
            }
        )

    # Best hitters vs RHP
    top_r = (
        df.sort_values("hitter_score_vs_rhp", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    for rank, (_, r) in enumerate(top_r.iterrows(), start=1):
        rows.append(
            {
                "report_type": "platoon",
                "position": "vs_rhp",
                "rank": rank,
                "name": r["name"],
                "playable_positions": _playable_positions_with_ratings(r),
                "best_positions_by_score": _best_positions_by_score(r),
                "score": r["hitter_score_vs_rhp"],
                "hitter_score_overall": r["hitter_score_overall"],
                "batting_score_overall": r.get("batting_score_overall", ""),
                "batting_score_vs_lhp": r.get("batting_score_vs_lhp", ""),
                "batting_score_vs_rhp": r.get("batting_score_vs_rhp", ""),
                "score_vs_lhp": r["hitter_score_vs_lhp"],
                "score_vs_rhp": r["hitter_score_vs_rhp"],
            }
        )

    return pd.DataFrame(rows)