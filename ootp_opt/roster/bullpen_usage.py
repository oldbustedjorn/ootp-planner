from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


USE_MORE_OFTEN = "Use more often"
NORMAL_USAGE = "Normal Usage"
USE_LESS_OFTEN = "Use less often"
USAGE_OPTION_COLUMN = "usage_option"


@dataclass(frozen=True)
class BullpenUsageSettings:
    minimum_gap: float = 8.0
    minimum_gap_fraction: float = 0.03
    typical_gap_multiplier: float = 2.0
    max_breaks: int = 2


def assign_middle_relief_usage(
    bullpen: pd.DataFrame,
    *,
    score_column: str = "reliever_score_overall",
    settings: BullpenUsageSettings = BullpenUsageSettings(),
) -> pd.DataFrame:
    """Return middle relievers with usage options based on natural score gaps."""
    assigned = bullpen.copy()
    assigned[USAGE_OPTION_COLUMN] = NORMAL_USAGE
    if len(assigned) < 2 or score_column not in assigned.columns:
        return assigned

    scores = pd.to_numeric(assigned[score_column], errors="coerce")
    ranked = pd.DataFrame(
        {
            "position": range(len(assigned)),
            "score": scores.to_numpy(),
        }
    )
    ranked = ranked.loc[ranked["score"].map(math.isfinite)]
    ranked = ranked.sort_values("score", ascending=False, kind="stable").reset_index(
        drop=True
    )
    if len(ranked) < 2:
        return assigned

    gaps = ranked["score"] - ranked["score"].shift(-1)
    adjacent_gaps = gaps.iloc[:-1]
    typical_gap = float(adjacent_gaps.median())
    typical_score = float(ranked["score"].median())
    meaningful_gap = max(
        settings.minimum_gap,
        abs(typical_score) * settings.minimum_gap_fraction,
        typical_gap * settings.typical_gap_multiplier,
    )

    break_candidates = [
        (position, float(gap))
        for position, gap in enumerate(adjacent_gaps)
        if float(gap) >= meaningful_gap
    ]
    selected_breaks = sorted(
        position
        for position, _ in sorted(
            break_candidates,
            key=lambda item: (-item[1], item[0]),
        )[: settings.max_breaks]
    )
    if not selected_breaks:
        return assigned

    ranked_usage = [NORMAL_USAGE] * len(ranked)
    if len(selected_breaks) == 1:
        break_position = selected_breaks[0]
        high_count = break_position + 1
        low_count = len(ranked) - high_count
        if high_count <= low_count:
            ranked_usage[:high_count] = [USE_MORE_OFTEN] * high_count
        else:
            ranked_usage[high_count:] = [USE_LESS_OFTEN] * low_count
    else:
        first_break, second_break = selected_breaks
        ranked_usage[: first_break + 1] = [USE_MORE_OFTEN] * (first_break + 1)
        ranked_usage[second_break + 1 :] = [USE_LESS_OFTEN] * (
            len(ranked) - second_break - 1
        )

    usage_by_position = dict(zip(ranked["position"], ranked_usage))
    usage_column_position = assigned.columns.get_loc(USAGE_OPTION_COLUMN)
    for position, usage in usage_by_position.items():
        assigned.iloc[int(position), usage_column_position] = usage

    return assigned
