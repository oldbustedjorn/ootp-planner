from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LineupSplit = Literal["vs_rhp", "vs_lhp"]


@dataclass(frozen=True)
class LineupAssignmentSlot:
    """One position assignment in one opposing-pitcher split lineup."""

    key: str
    label: str
    split: LineupSplit
    position: str
    score_column: str
    rating_column: str | None = None
    minimum_rating: float | None = None

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.label.strip():
            raise ValueError("Lineup assignment keys and labels cannot be blank.")
        if self.split not in {"vs_rhp", "vs_lhp"}:
            raise ValueError(
                f"Lineup assignment '{self.key}' has invalid split '{self.split}'."
            )
        if not self.position.strip() or not self.score_column.strip():
            raise ValueError(
                f"Lineup assignment '{self.key}' requires a position and score column."
            )
        if (self.rating_column is None) != (self.minimum_rating is None):
            raise ValueError(
                f"Lineup assignment '{self.key}' must specify both defensive "
                "rating column and minimum, or neither."
            )


@dataclass(frozen=True)
class PitcherRoleGroup:
    """A configurable group of selected pitchers with a common intended use."""

    key: str
    label: str
    count: int
    score_column: str
    member_order_matters: bool = False

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.label.strip():
            raise ValueError("Pitcher role group keys and labels cannot be blank.")
        if self.count <= 0:
            raise ValueError(
                f"Pitcher role group '{self.key}' must have a positive count."
            )
        if not self.score_column.strip():
            raise ValueError(
                f"Pitcher role group '{self.key}' has a blank score column."
            )


@dataclass(frozen=True)
class LineupCoverageRequirement:
    """Bench coverage required for one position in one split lineup.

    The future optimizer will count selected hitters who are not assigned to
    that split lineup and who meet this defensive threshold. A versatile bench
    player may satisfy several position requirements.
    """

    key: str
    label: str
    split: LineupSplit
    position: str
    rating_column: str
    minimum_rating: float
    minimum_bench_players: int

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.label.strip():
            raise ValueError("Lineup coverage keys and labels cannot be blank.")
        if self.split not in {"vs_rhp", "vs_lhp"}:
            raise ValueError(
                f"Lineup coverage '{self.key}' has invalid split '{self.split}'."
            )
        if not self.position.strip() or not self.rating_column.strip():
            raise ValueError(
                f"Lineup coverage '{self.key}' requires a position and rating column."
            )
        if self.minimum_bench_players <= 0:
            raise ValueError(
                f"Lineup coverage '{self.key}' must require at least one bench player."
            )


@dataclass(frozen=True)
class RosterSlotPlan:
    """Split lineup assignments plus selected-pitcher allocation groups.

    Hitters are selected as one roster pool. Their starter and bench status is
    derived independently for each split lineup, so bench is intentionally not
    represented as a permanent slot or scored role.
    """

    lineup_slots: tuple[LineupAssignmentSlot, ...]
    pitcher_groups: tuple[PitcherRoleGroup, ...]
    hitter_count: int
    pitcher_count: int

    def __post_init__(self) -> None:
        if self.hitter_count < 0 or self.pitcher_count < 0:
            raise ValueError("Roster slot plan counts cannot be negative.")

        lineup_keys = [slot.key for slot in self.lineup_slots]
        if len(lineup_keys) != len(set(lineup_keys)):
            raise ValueError("Lineup assignment keys must be unique.")

        pitcher_keys = [group.key for group in self.pitcher_groups]
        if len(pitcher_keys) != len(set(pitcher_keys)):
            raise ValueError("Pitcher role group keys must be unique.")

        for split in ("vs_rhp", "vs_lhp"):
            positions = [slot.position for slot in self.lineup_for_split(split)]
            if len(positions) != len(set(positions)):
                raise ValueError(f"Lineup positions must be unique for {split}.")
            if len(positions) > self.hitter_count:
                raise ValueError(
                    f"{split} has {len(positions)} starters but only "
                    f"{self.hitter_count} selected hitters."
                )

        allocated_pitchers = sum(group.count for group in self.pitcher_groups)
        if allocated_pitchers != self.pitcher_count:
            raise ValueError(
                "Pitcher role groups do not match roster size: "
                f"{allocated_pitchers} slots vs {self.pitcher_count} pitchers."
            )

    def pitcher_group(self, key: str) -> PitcherRoleGroup:
        for group in self.pitcher_groups:
            if group.key == key:
                return group
        raise KeyError(f"Unknown pitcher role group: {key}")

    def lineup_for_split(
        self,
        split: LineupSplit,
    ) -> tuple[LineupAssignmentSlot, ...]:
        return tuple(slot for slot in self.lineup_slots if slot.split == split)

    def lineup_slot(
        self,
        split: LineupSplit,
        position: str,
    ) -> LineupAssignmentSlot:
        for slot in self.lineup_slots:
            if slot.split == split and slot.position == position:
                return slot
        raise KeyError(f"Unknown lineup assignment: {split} {position}")

    def lineup_summary(self) -> str:
        summaries = []
        for split, label in (("vs_rhp", "vs RHP"), ("vs_lhp", "vs LHP")):
            positions = ", ".join(
                slot.position for slot in self.lineup_for_split(split)
            )
            summaries.append(f"{label}: {positions}")
        return "; ".join(summaries)

    def pitcher_group_summary(self) -> str:
        return ", ".join(
            f"{group.label} x{group.count}" for group in self.pitcher_groups
        )


def build_current_roster_slot_plan(
    *,
    hitter_count: int,
    pitcher_count: int,
    lineup_positions: list[str],
    rotation_size: int,
    middle_relief_count: int,
    lefty_specialist_count: int,
    long_relief_count: int,
    min_defense_by_position: dict[str, float],
) -> RosterSlotPlan:
    lineup_slots = tuple(
        build_lineup_slot(position, split, min_defense_by_position)
        for split in ("vs_rhp", "vs_lhp")
        for position in lineup_positions
    )

    pitcher_groups: list[PitcherRoleGroup] = []
    add_pitcher_group(
        pitcher_groups,
        key="rotation",
        label="Rotation",
        count=rotation_size,
        score_column="starter_score_overall",
        member_order_matters=True,
    )
    add_pitcher_group(
        pitcher_groups,
        key="middle_relief",
        label="Middle Relief",
        count=middle_relief_count,
        score_column="reliever_score_overall",
    )
    add_pitcher_group(
        pitcher_groups,
        key="lefty_specialist",
        label="Lefty Specialist",
        count=lefty_specialist_count,
        score_column="reliever_score_vs_lhb",
    )
    add_pitcher_group(
        pitcher_groups,
        key="long_relief",
        label="Long Relief",
        count=long_relief_count,
        score_column="starter_score_overall",
    )

    return RosterSlotPlan(
        lineup_slots=lineup_slots,
        pitcher_groups=tuple(pitcher_groups),
        hitter_count=hitter_count,
        pitcher_count=pitcher_count,
    )


def build_lineup_coverage_requirements(
    *,
    lineup_positions: list[str],
    min_defense_by_position: dict[str, float],
    minimum_lineup_backup_coverage: dict[str, int],
) -> tuple[LineupCoverageRequirement, ...]:
    return tuple(
        LineupCoverageRequirement(
            key=f"{split}_{position.lower()}_bench_coverage",
            label=f"{position} bench coverage {split.replace('_', ' ')}",
            split=split,
            position=position,
            rating_column=f"fld_{position}",
            minimum_rating=float(min_defense_by_position[position]),
            minimum_bench_players=int(minimum_lineup_backup_coverage[position]),
        )
        for split in ("vs_rhp", "vs_lhp")
        for position in lineup_positions
        if position != "DH" and minimum_lineup_backup_coverage.get(position, 0) > 0
    )


def coverage_summary(
    requirements: tuple[LineupCoverageRequirement, ...],
) -> str:
    if not requirements:
        return "-"

    by_position: dict[str, LineupCoverageRequirement] = {}
    for requirement in requirements:
        by_position.setdefault(requirement.position, requirement)
    return ", ".join(
        f"{requirement.position} x{requirement.minimum_bench_players} per lineup "
        f"(rating >= {requirement.minimum_rating:g})"
        for requirement in by_position.values()
    )


def build_lineup_slot(
    position: str,
    split: LineupSplit,
    min_defense_by_position: dict[str, float],
) -> LineupAssignmentSlot:
    split_label = split.replace("_", " ")
    if position == "DH":
        return LineupAssignmentSlot(
            key=f"{split}_dh",
            label=f"DH {split_label}",
            split=split,
            position=position,
            score_column=f"batting_score_{split}",
        )

    minimum_rating = min_defense_by_position.get(position)
    return LineupAssignmentSlot(
        key=f"{split}_{position.lower()}",
        label=f"{position} {split_label}",
        split=split,
        position=position,
        score_column=f"score_{position}_{split}",
        rating_column=f"fld_{position}" if minimum_rating is not None else None,
        minimum_rating=(
            float(minimum_rating) if minimum_rating is not None else None
        ),
    )


def add_pitcher_group(
    groups: list[PitcherRoleGroup],
    *,
    key: str,
    label: str,
    count: int,
    score_column: str,
    member_order_matters: bool = False,
) -> None:
    if count <= 0:
        return
    groups.append(
        PitcherRoleGroup(
            key=key,
            label=label,
            count=count,
            score_column=score_column,
            member_order_matters=member_order_matters,
        )
    )
