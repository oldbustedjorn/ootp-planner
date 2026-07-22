from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PERSON_KEY_COLUMN,
)
from ootp_opt.optimization.candidate_matrices import CandidateMatrices
from ootp_opt.roster.rules import Ruleset
from ootp_opt.roster.tier_slot_report import (
    FINITE_SLOT_TIERS,
    normalize_tier_name,
    normalize_tier_slots,
)


TIER_RANKS = {
    "iron": 0,
    "bronze": 1,
    "silver": 2,
    "gold": 3,
    "diamond": 4,
    "perfect": 5,
}


@dataclass(frozen=True)
class SolverLimits:
    hitter_count: int
    pitcher_count: int
    point_cap_total: int | None
    variant_limit: int | None

    @property
    def roster_count(self) -> int:
        return self.hitter_count + self.pitcher_count


@dataclass(frozen=True)
class SolverInput:
    """Solver-neutral vectors and sparse constraint relations.

    This object contains no decision variables and depends on no solver library.
    A later model can translate these tables into binary variables and linear
    constraints without returning to raw exports or configuration dictionaries.
    """

    candidates: pd.DataFrame
    person_membership: pd.DataFrame
    tier_limit_membership: pd.DataFrame
    lineup_requirements: pd.DataFrame
    pitcher_group_requirements: pd.DataFrame
    coverage_requirements: pd.DataFrame
    tier_limits: pd.DataFrame
    lineup_split_weights: dict[str, float]
    limits: SolverLimits
    matrices: CandidateMatrices

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def person_count(self) -> int:
        return self.person_membership[PERSON_KEY_COLUMN].nunique()

    @property
    def duplicate_person_group_count(self) -> int:
        counts = self.person_membership.groupby(PERSON_KEY_COLUMN).size()
        return int(counts.gt(1).sum())

    def candidate_vector(self, column: str) -> pd.Series:
        if column not in self.candidates.columns:
            raise KeyError(f"Unknown candidate vector: {column}")
        return self.candidates.set_index(CANDIDATE_ID_COLUMN)[column].copy()

    def summary_rows(self) -> list[tuple[str, str]]:
        return [
            ("Solver candidates", str(self.candidate_count)),
            ("Solver person groups", str(self.person_count)),
            (
                "Solver duplicate-person groups",
                str(self.duplicate_person_group_count),
            ),
            ("Solver lineup constraints", str(len(self.lineup_requirements))),
            (
                "Solver coverage constraints",
                str(len(self.coverage_requirements)),
            ),
            (
                "Solver pitcher-group constraints",
                str(len(self.pitcher_group_requirements)),
            ),
            ("Solver tier constraints", str(len(self.tier_limits))),
        ]


def build_solver_input(
    *,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
    scoring_config: dict[str, Any],
    matrices: CandidateMatrices,
) -> SolverInput:
    if ruleset.slot_plan is None:
        raise ValueError("Solver input requires a roster slot plan.")

    validate_active_constraint_columns(eligible_hitters, eligible_pitchers, ruleset)
    candidates = build_candidate_table(
        eligible_hitters,
        eligible_pitchers,
        matrices,
    )
    person_membership = candidates[
        [CANDIDATE_ID_COLUMN, PERSON_KEY_COLUMN]
    ].copy()
    lineup_requirements = build_lineup_requirements(ruleset, scoring_config)
    pitcher_group_requirements = build_pitcher_group_requirements(ruleset)
    coverage_requirements = build_coverage_requirements(ruleset)
    tier_limits = build_tier_limits(ruleset)
    tier_limit_membership = build_tier_limit_membership(candidates, tier_limits)
    lineup_split_weights = resolve_lineup_split_weights(scoring_config)

    solver_input = SolverInput(
        candidates=candidates,
        person_membership=person_membership,
        tier_limit_membership=tier_limit_membership,
        lineup_requirements=lineup_requirements,
        pitcher_group_requirements=pitcher_group_requirements,
        coverage_requirements=coverage_requirements,
        tier_limits=tier_limits,
        lineup_split_weights=lineup_split_weights,
        limits=SolverLimits(
            hitter_count=ruleset.hitter_count,
            pitcher_count=ruleset.pitcher_count,
            point_cap_total=ruleset.point_cap_total,
            variant_limit=ruleset.variant_limit,
        ),
        matrices=matrices,
    )
    validate_solver_input(solver_input)
    return solver_input


def build_candidate_table(
    hitters: pd.DataFrame,
    pitchers: pd.DataFrame,
    matrices: CandidateMatrices,
) -> pd.DataFrame:
    hitter_records = candidate_metadata(hitters, "hitter")
    pitcher_records = candidate_metadata(pitchers, "pitcher")
    combined = pd.concat([hitter_records, pitcher_records], ignore_index=True)
    validate_shared_candidate_metadata(combined)

    candidates = (
        combined.groupby(CANDIDATE_ID_COLUMN, sort=False, as_index=False)
        .agg(
            {
                PERSON_KEY_COLUMN: "first",
                "name": "first",
                "card_value": "first",
                "tier": "first",
                "tier_rank": "first",
                "is_variant": "first",
            }
        )
        .copy()
    )
    hitter_ids = set(matrices.hitter_assignments[CANDIDATE_ID_COLUMN])
    pitcher_ids = set(matrices.pitcher_assignments[CANDIDATE_ID_COLUMN])
    candidates["can_hit"] = candidates[CANDIDATE_ID_COLUMN].isin(hitter_ids)
    candidates["can_pitch"] = candidates[CANDIDATE_ID_COLUMN].isin(pitcher_ids)
    return candidates


def candidate_metadata(df: pd.DataFrame, candidate_side: str) -> pd.DataFrame:
    required = [CANDIDATE_ID_COLUMN, PERSON_KEY_COLUMN, "name"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            f"Missing candidate metadata columns for {candidate_side}: {missing}"
        )

    metadata = df[required].copy()
    metadata["card_value"] = numeric_column_or_default(df, "card_value", 0)
    if "pt_tier" in df.columns:
        metadata["tier"] = df["pt_tier"].map(normalize_tier_name)
    else:
        metadata["tier"] = ""
    metadata["tier_rank"] = metadata["tier"].map(TIER_RANKS).fillna(-1).astype(int)
    metadata["is_variant"] = variant_series(df)
    return metadata


def validate_shared_candidate_metadata(combined: pd.DataFrame) -> None:
    columns = [PERSON_KEY_COLUMN, "card_value", "tier", "is_variant"]
    distinct_counts = combined.groupby(CANDIDATE_ID_COLUMN, sort=False)[
        columns
    ].nunique(dropna=False)
    inconsistent = distinct_counts.gt(1)
    if not inconsistent.to_numpy().any():
        return

    candidate_id, column = inconsistent.stack().loc[lambda values: values].index[0]
    raise ValueError(
        f"Candidate '{candidate_id}' has inconsistent {column} "
        "between hitter and pitcher data."
    )


def build_lineup_requirements(
    ruleset: Ruleset,
    scoring_config: dict[str, Any],
) -> pd.DataFrame:
    weights = resolve_lineup_split_weights(scoring_config)
    return pd.DataFrame(
        [
            {
                "slot_key": slot.key,
                "split": slot.split,
                "position": slot.position,
                "required_count": 1,
                "objective_weight": weights[slot.split],
            }
            for slot in ruleset.slot_plan.lineup_slots
        ]
    )


def build_pitcher_group_requirements(ruleset: Ruleset) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "group_key": group.key,
                "group_label": group.label,
                "required_count": group.count,
            }
            for group in ruleset.slot_plan.pitcher_groups
        ]
    )


def build_coverage_requirements(ruleset: Ruleset) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "requirement_key": requirement.key,
                "split": requirement.split,
                "position": requirement.position,
                "minimum_bench_players": requirement.minimum_bench_players,
            }
            for requirement in ruleset.lineup_coverage_requirements
        ]
    )


def build_tier_limits(ruleset: Ruleset) -> pd.DataFrame:
    if not ruleset.tier_slots:
        return pd.DataFrame(columns=["threshold_tier", "max_selected"])

    normalized = normalize_tier_slots(ruleset.tier_slots)
    cumulative_slots = 0
    rows = []
    for tier in FINITE_SLOT_TIERS:
        cumulative_slots += normalized.get(tier, 0)
        rows.append(
            {
                "threshold_tier": tier,
                "max_selected": cumulative_slots,
            }
        )
    return pd.DataFrame(rows)


def build_tier_limit_membership(
    candidates: pd.DataFrame,
    tier_limits: pd.DataFrame,
) -> pd.DataFrame:
    columns = [CANDIDATE_ID_COLUMN, "threshold_tier"]
    if tier_limits.empty:
        return pd.DataFrame(columns=columns)

    frames = []
    for threshold_tier in tier_limits["threshold_tier"]:
        threshold_rank = TIER_RANKS[threshold_tier]
        members = candidates.loc[candidates["tier_rank"].ge(threshold_rank)].copy()
        members["threshold_tier"] = threshold_tier
        frames.append(members[columns])
    return pd.concat(frames, ignore_index=True)[columns]


def resolve_lineup_split_weights(scoring_config: dict[str, Any]) -> dict[str, float]:
    hitter_cfg = scoring_config.get("hitters", {})
    weights = {
        "vs_rhp": float(hitter_cfg.get("vs_rhp_weight", 0.70)),
        "vs_lhp": float(hitter_cfg.get("vs_lhp_weight", 0.30)),
    }
    if any(not np.isfinite(value) or value < 0 for value in weights.values()):
        raise ValueError(f"Lineup split weights must be finite and nonnegative: {weights}")
    if sum(weights.values()) <= 0:
        raise ValueError("At least one lineup split weight must be positive.")
    return weights


def validate_active_constraint_columns(
    hitters: pd.DataFrame,
    pitchers: pd.DataFrame,
    ruleset: Ruleset,
) -> None:
    frames = (hitters, pitchers)
    if ruleset.point_cap_total is not None:
        require_column_in_all(frames, "card_value", "point cap")
    if ruleset.tier_slots:
        require_column_in_all(frames, "pt_tier", "tier slots")
        unknown_tiers = set()
        for frame in frames:
            normalized = frame["pt_tier"].map(normalize_tier_name)
            unknown_tiers.update(normalized.loc[~normalized.isin(TIER_RANKS)].unique())
        if unknown_tiers:
            raise ValueError(
                "Tier-slot candidates contain unknown tiers: "
                f"{sorted(str(tier) for tier in unknown_tiers)}"
            )
    if ruleset.variant_limit is not None and not all(
        "is_variant" in frame.columns or "VAR" in frame.columns for frame in frames
    ):
        raise ValueError(
            "Variant limit requires is_variant or VAR in hitter and pitcher data."
        )


def validate_solver_input(solver_input: SolverInput) -> None:
    candidates = solver_input.candidates
    if candidates[CANDIDATE_ID_COLUMN].duplicated().any():
        raise ValueError("Solver candidates contain duplicate candidate IDs.")
    if candidates[PERSON_KEY_COLUMN].isna().any() or candidates[
        PERSON_KEY_COLUMN
    ].eq("").any():
        raise ValueError("Solver candidates contain blank person keys.")

    matrix_ids = set(
        pd.concat(
            [
                solver_input.matrices.hitter_assignments[CANDIDATE_ID_COLUMN],
                solver_input.matrices.pitcher_assignments[CANDIDATE_ID_COLUMN],
            ],
            ignore_index=True,
        )
    )
    unknown_matrix_ids = matrix_ids - set(candidates[CANDIDATE_ID_COLUMN])
    if unknown_matrix_ids:
        raise ValueError("Assignment matrices contain unknown candidate IDs.")

    if candidates["can_hit"].sum() < solver_input.limits.hitter_count:
        raise ValueError("Insufficient hitter candidates for requested roster size.")
    if candidates["can_pitch"].sum() < solver_input.limits.pitcher_count:
        raise ValueError("Insufficient pitcher candidates for requested roster size.")
    if solver_input.person_count < solver_input.limits.roster_count:
        raise ValueError("Insufficient unique people for requested roster size.")


def numeric_column_or_default(
    df: pd.DataFrame,
    column: str,
    default: int,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="int64")
    values = pd.to_numeric(df[column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"Candidate column contains nonnumeric values: {column}")
    return values.astype(int)


def variant_series(df: pd.DataFrame) -> pd.Series:
    if "is_variant" in df.columns:
        values = df["is_variant"]
    elif "VAR" in df.columns:
        values = df["VAR"]
    else:
        return pd.Series(False, index=df.index, dtype="bool")

    return values.map(
        lambda value: value
        if isinstance(value, bool)
        else str(value).strip().upper() in {"Y", "TRUE"}
    ).astype(bool)


def require_column_in_all(
    frames: Iterable[pd.DataFrame],
    column: str,
    context: str,
) -> None:
    if not all(column in frame.columns for frame in frames):
        raise ValueError(f"{context} requires candidate column '{column}'.")
