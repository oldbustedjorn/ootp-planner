from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PERSON_KEY_COLUMN,
)
from ootp_opt.roster.rules import Ruleset


NAME_COLUMN = "name"
HITTER_UTILITY_COLUMNS = (
    "batting_score_vs_rhp",
    "batting_score_vs_lhp",
    "pinch_run_score",
)


@dataclass(frozen=True)
class CandidateMatrices:
    """Sparse optimizer inputs derived from one eligible candidate pool.

    Bench status is intentionally absent. The optimizer will derive it for each
    split from selected hitters who are not assigned to that split lineup.
    """

    hitter_position_capability: pd.DataFrame
    hitter_assignments: pd.DataFrame
    hitter_utilities: pd.DataFrame
    pitcher_assignments: pd.DataFrame

    @property
    def position_capability_count(self) -> int:
        return len(self.hitter_position_capability)

    @property
    def hitter_assignment_count(self) -> int:
        return len(self.hitter_assignments)

    @property
    def pitcher_assignment_count(self) -> int:
        return len(self.pitcher_assignments)

    def capable_hitters(self, position: str) -> pd.DataFrame:
        return self.hitter_position_capability.loc[
            self.hitter_position_capability["position"].eq(position)
        ].copy()

    def hitters_for_slot(self, slot_key: str) -> pd.DataFrame:
        return self.hitter_assignments.loc[
            self.hitter_assignments["slot_key"].eq(slot_key)
        ].copy()

    def pitchers_for_group(self, group_key: str) -> pd.DataFrame:
        return self.pitcher_assignments.loc[
            self.pitcher_assignments["group_key"].eq(group_key)
        ].copy()

    def summary_rows(self) -> list[tuple[str, str]]:
        return [
            ("Position capability edges", str(self.position_capability_count)),
            ("Hitter assignment edges", str(self.hitter_assignment_count)),
            ("Pitcher role edges", str(self.pitcher_assignment_count)),
        ]


def build_candidate_matrices(
    *,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
) -> CandidateMatrices:
    if ruleset.slot_plan is None:
        raise ValueError("Candidate matrices require a roster slot plan.")

    validate_candidate_frame(eligible_hitters, "hitter")
    validate_candidate_frame(eligible_pitchers, "pitcher")

    hitter_position_capability = build_hitter_position_capability(
        eligible_hitters,
        ruleset,
    )
    hitter_assignments = build_hitter_assignments(
        eligible_hitters,
        ruleset,
    )
    hitter_utilities = build_hitter_utilities(eligible_hitters)
    pitcher_assignments = build_pitcher_assignments(
        eligible_pitchers,
        ruleset,
    )

    matrices = CandidateMatrices(
        hitter_position_capability=hitter_position_capability,
        hitter_assignments=hitter_assignments,
        hitter_utilities=hitter_utilities,
        pitcher_assignments=pitcher_assignments,
    )
    validate_matrix_edges(matrices, ruleset)
    return matrices


def build_hitter_position_capability(
    hitters: pd.DataFrame,
    ruleset: Ruleset,
) -> pd.DataFrame:
    columns = [
        CANDIDATE_ID_COLUMN,
        PERSON_KEY_COLUMN,
        NAME_COLUMN,
        "position",
        "defense_rating",
        "minimum_rating",
    ]
    frames: list[pd.DataFrame] = []
    defensive_positions = distinct_in_order(
        slot.position
        for slot in ruleset.slot_plan.lineup_slots
        if slot.position != "DH" and slot.rating_column is not None
    )

    for position in defensive_positions:
        slot = next(
            slot
            for slot in ruleset.slot_plan.lineup_slots
            if slot.position == position and slot.rating_column is not None
        )
        require_columns(hitters, [slot.rating_column], "hitter capability")
        ratings = pd.to_numeric(hitters[slot.rating_column], errors="coerce")
        capable = hitters.loc[ratings.ge(float(slot.minimum_rating))].copy()
        if capable.empty:
            continue
        capable["position"] = position
        capable["defense_rating"] = ratings.loc[capable.index].astype(float)
        capable["minimum_rating"] = float(slot.minimum_rating)
        frames.append(capable[columns])

    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns]


def build_hitter_assignments(
    hitters: pd.DataFrame,
    ruleset: Ruleset,
) -> pd.DataFrame:
    columns = [
        CANDIDATE_ID_COLUMN,
        PERSON_KEY_COLUMN,
        NAME_COLUMN,
        "slot_key",
        "split",
        "position",
        "score",
    ]
    frames: list[pd.DataFrame] = []

    for slot in ruleset.slot_plan.lineup_slots:
        required = [slot.score_column]
        if slot.rating_column is not None:
            required.append(slot.rating_column)
        require_columns(hitters, required, f"lineup slot {slot.key}")

        scores = pd.to_numeric(hitters[slot.score_column], errors="coerce")
        eligible_mask = pd.Series(np.isfinite(scores), index=hitters.index)
        if slot.rating_column is not None:
            ratings = pd.to_numeric(hitters[slot.rating_column], errors="coerce")
            eligible_mask &= ratings.ge(float(slot.minimum_rating))

        eligible = hitters.loc[eligible_mask].copy()
        if eligible.empty:
            continue
        eligible["slot_key"] = slot.key
        eligible["split"] = slot.split
        eligible["position"] = slot.position
        eligible["score"] = scores.loc[eligible.index].astype(float)
        frames.append(eligible[columns])

    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns]


def build_hitter_utilities(hitters: pd.DataFrame) -> pd.DataFrame:
    require_columns(hitters, HITTER_UTILITY_COLUMNS, "hitter utilities")
    columns = [
        CANDIDATE_ID_COLUMN,
        PERSON_KEY_COLUMN,
        NAME_COLUMN,
        *HITTER_UTILITY_COLUMNS,
    ]
    utilities = hitters[columns].copy()
    for column in HITTER_UTILITY_COLUMNS:
        utilities[column] = pd.to_numeric(utilities[column], errors="coerce")
        if not np.isfinite(utilities[column]).all():
            raise ValueError(f"Hitter utility column contains non-finite values: {column}")
    return utilities


def build_pitcher_assignments(
    pitchers: pd.DataFrame,
    ruleset: Ruleset,
) -> pd.DataFrame:
    columns = [
        CANDIDATE_ID_COLUMN,
        PERSON_KEY_COLUMN,
        NAME_COLUMN,
        "group_key",
        "group_label",
        "score",
    ]
    frames: list[pd.DataFrame] = []

    for group in ruleset.slot_plan.pitcher_groups:
        require_columns(pitchers, [group.score_column], f"pitcher group {group.key}")
        scores = pd.to_numeric(pitchers[group.score_column], errors="coerce")
        eligible = pitchers.loc[np.isfinite(scores)].copy()
        if eligible.empty:
            continue
        eligible["group_key"] = group.key
        eligible["group_label"] = group.label
        eligible["score"] = scores.loc[eligible.index].astype(float)
        frames.append(eligible[columns])

    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns]


def validate_candidate_frame(df: pd.DataFrame, candidate_kind: str) -> None:
    require_columns(
        df,
        [CANDIDATE_ID_COLUMN, PERSON_KEY_COLUMN, NAME_COLUMN],
        f"eligible {candidate_kind} candidates",
    )
    if df.empty:
        raise ValueError(f"No eligible {candidate_kind} candidates for matrices.")
    if df[CANDIDATE_ID_COLUMN].isna().any() or df[CANDIDATE_ID_COLUMN].eq("").any():
        raise ValueError(f"Eligible {candidate_kind} candidates contain blank IDs.")
    if df[CANDIDATE_ID_COLUMN].duplicated().any():
        raise ValueError(
            f"Eligible {candidate_kind} candidates contain duplicate candidate IDs."
        )
    if df[PERSON_KEY_COLUMN].isna().any() or df[PERSON_KEY_COLUMN].eq("").any():
        raise ValueError(f"Eligible {candidate_kind} candidates contain blank person keys.")


def validate_matrix_edges(
    matrices: CandidateMatrices,
    ruleset: Ruleset,
) -> None:
    assert_unique_edges(
        matrices.hitter_position_capability,
        [CANDIDATE_ID_COLUMN, "position"],
        "hitter position capability",
    )
    assert_unique_edges(
        matrices.hitter_assignments,
        [CANDIDATE_ID_COLUMN, "slot_key"],
        "hitter assignment",
    )
    assert_unique_edges(
        matrices.pitcher_assignments,
        [CANDIDATE_ID_COLUMN, "group_key"],
        "pitcher role",
    )

    missing_slots = [
        slot.key
        for slot in ruleset.slot_plan.lineup_slots
        if matrices.hitters_for_slot(slot.key).empty
    ]
    if missing_slots:
        raise ValueError(
            "No eligible hitter assignment candidates for: "
            + ", ".join(missing_slots)
        )

    missing_groups = [
        group.key
        for group in ruleset.slot_plan.pitcher_groups
        if len(matrices.pitchers_for_group(group.key)) < group.count
    ]
    if missing_groups:
        raise ValueError(
            "Insufficient eligible pitcher candidates for groups: "
            + ", ".join(missing_groups)
        )


def assert_unique_edges(
    df: pd.DataFrame,
    columns: list[str],
    label: str,
) -> None:
    if df.duplicated(columns).any():
        raise ValueError(f"Duplicate {label} edges detected.")


def require_columns(
    df: pd.DataFrame,
    required: Iterable[str],
    context: str,
) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing columns for {context}: {missing}")


def distinct_in_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
