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
                    "score": r[col],
                    "hitter_score_overall": r["hitter_score_overall"],
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
                "score": r["hitter_score_vs_lhp"],
                "hitter_score_overall": r["hitter_score_overall"],
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
                "score": r["hitter_score_vs_rhp"],
                "hitter_score_overall": r["hitter_score_overall"],
                "score_vs_lhp": r["hitter_score_vs_lhp"],
                "score_vs_rhp": r["hitter_score_vs_rhp"],
            }
        )

    return pd.DataFrame(rows)