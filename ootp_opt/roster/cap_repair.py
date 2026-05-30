from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from ootp_opt.roster.builder import (
    get_hitter_score_column,
    player_qualifies_for_bench_role,
    player_unique_key,
)
from ootp_opt.roster.cap_report import build_cap_summary, card_value
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset

from ootp_opt.roster.variant_report import (
    build_variant_summary,
    is_variant_card,
)

BAD_SCORE = -1_000_000_000.0


SlotKind = Literal[
    "hitter_starter",
    "hitter_bench",
    "rotation",
    "bullpen",
    "lefty_specialist",
    "long_man",
]


@dataclass(frozen=True)
class CapRepairOption:
    slot_kind: SlotKind
    slot_key: str | int
    role: str

    old_name: str
    new_name: str

    old_value: int
    new_value: int
    cap_saved: int

    old_score: float
    new_score: float
    score_loss: float
    loss_per_cap_saved: float

    candidate: pd.Series


@dataclass(frozen=True)
class CapRepairStep:
    role: str
    old_name: str
    new_name: str
    old_value: int
    new_value: int
    cap_saved: int
    old_score: float
    new_score: float
    score_loss: float
    loss_per_cap_saved: float
    roster_total_after: int
    over_cap_by_after: int


@dataclass(frozen=True)
class CapRepairResult:
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster
    steps: list[CapRepairStep]
    success: bool
    final_roster_total: int
    final_over_cap_by: int


def repair_roster_to_cap(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
    max_iterations: int = 100,
) -> CapRepairResult:
    if ruleset.point_cap_total is None:
        summary = build_cap_summary(hitter_roster, pitcher_roster, None)
        return CapRepairResult(
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            steps=[],
            success=True,
            final_roster_total=summary.roster_total,
            final_over_cap_by=0,
        )

    current_hitters = hitter_roster
    current_pitchers = pitcher_roster
    steps: list[CapRepairStep] = []

    for _ in range(max_iterations):
        summary = build_cap_summary(
            current_hitters,
            current_pitchers,
            ruleset.point_cap_total,
        )

        if not summary.is_over_cap:
            return CapRepairResult(
                hitter_roster=current_hitters,
                pitcher_roster=current_pitchers,
                steps=steps,
                success=True,
                final_roster_total=summary.roster_total,
                final_over_cap_by=summary.over_cap_by,
            )

        options = find_cap_repair_options(
            hitter_roster=current_hitters,
            pitcher_roster=current_pitchers,
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
            ruleset=ruleset,
        )

        if not options:
            return CapRepairResult(
                hitter_roster=current_hitters,
                pitcher_roster=current_pitchers,
                steps=steps,
                success=False,
                final_roster_total=summary.roster_total,
                final_over_cap_by=summary.over_cap_by,
            )

        best = options[0]

        current_hitters, current_pitchers = apply_cap_repair_option(
            hitter_roster=current_hitters,
            pitcher_roster=current_pitchers,
            option=best,
        )

        new_summary = build_cap_summary(
            current_hitters,
            current_pitchers,
            ruleset.point_cap_total,
        )

        steps.append(
            CapRepairStep(
                role=best.role,
                old_name=best.old_name,
                new_name=best.new_name,
                old_value=best.old_value,
                new_value=best.new_value,
                cap_saved=best.cap_saved,
                old_score=best.old_score,
                new_score=best.new_score,
                score_loss=best.score_loss,
                loss_per_cap_saved=best.loss_per_cap_saved,
                roster_total_after=new_summary.roster_total,
                over_cap_by_after=new_summary.over_cap_by,
            )
        )

    final_summary = build_cap_summary(
        current_hitters,
        current_pitchers,
        ruleset.point_cap_total,
    )

    return CapRepairResult(
        hitter_roster=current_hitters,
        pitcher_roster=current_pitchers,
        steps=steps,
        success=not final_summary.is_over_cap,
        final_roster_total=final_summary.roster_total,
        final_over_cap_by=final_summary.over_cap_by,
    )


def find_cap_repair_options(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
) -> list[CapRepairOption]:
    selected_keys = selected_player_keys(hitter_roster, pitcher_roster)

    variant_count = current_variant_count(hitter_roster, pitcher_roster)

    options: list[CapRepairOption] = []

    options.extend(
        find_hitter_starter_repair_options(
            hitter_roster=hitter_roster,
            eligible_hitters=eligible_hitters,
            selected_keys=selected_keys,
            ruleset=ruleset,
            variant_count=variant_count,
        )
    )

    options.extend(
        find_hitter_bench_repair_options(
            hitter_roster=hitter_roster,
            eligible_hitters=eligible_hitters,
            selected_keys=selected_keys,
            ruleset=ruleset,
            variant_count=variant_count,
        )
    )

    options.extend(
        find_pitcher_repair_options(
            pitcher_roster=pitcher_roster,
            eligible_pitchers=eligible_pitchers,
            selected_keys=selected_keys,
            ruleset=ruleset,
            variant_count=variant_count,
        )
    )

    return sorted(
        options,
        key=lambda option: (
            adjusted_loss_per_cap(option),
            option.loss_per_cap_saved,
            option.score_loss,
            -option.cap_saved,
        ),
    )


def find_hitter_starter_repair_options(
    hitter_roster: HitterRoster,
    eligible_hitters: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
    variant_count: int,
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    for position, old_row in hitter_roster.starters_by_position.items():
        role = f"Starter {position}"
        score_col = get_hitter_score_column(position)

        old_value = card_value(old_row)
        old_score = safe_score(old_row, score_col)
        current_key = player_unique_key(old_row)

        candidates = eligible_hitters.copy()
        candidates = candidates.loc[candidates["card_value"] < old_value].copy()

        candidates = filter_candidate_duplicate_names(
            candidates,
            selected_keys=selected_keys,
            current_key=current_key,
        )

        candidates = candidates.loc[
            candidates.apply(
                lambda candidate: replacement_respects_variant_limit(
                    old_row=old_row,
                    candidate=candidate,
                    current_variant_count_value=variant_count,
                    variant_limit=ruleset.variant_limit,
                ),
                axis=1,
            )
        ].copy()

        if score_col not in candidates.columns:
            continue

        candidates = candidates.loc[candidates[score_col] > BAD_SCORE / 2].copy()

        for _, candidate in candidates.iterrows():
            options.append(
                build_option(
                    slot_kind="hitter_starter",
                    slot_key=position,
                    role=role,
                    old_row=old_row,
                    candidate=candidate,
                    old_score=old_score,
                    new_score=safe_score(candidate, score_col),
                )
            )

    return valid_options(options)


def find_hitter_bench_repair_options(
    hitter_roster: HitterRoster,
    eligible_hitters: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
    variant_count: int,
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    bench_rows = list(hitter_roster.bench_players.iterrows())

    for bench_index, (_, old_row) in enumerate(bench_rows):
        role_name = bench_role_for_index(ruleset, bench_index)
        role = f"Bench {bench_index + 1} ({role_name})"

        old_value = card_value(old_row)
        old_score = safe_score(old_row, "batting_score_overall")
        current_key = player_unique_key(old_row)

        candidates = eligible_hitters.copy()
        candidates = candidates.loc[candidates["card_value"] < old_value].copy()

        candidates = filter_candidate_duplicate_names(
            candidates,
            selected_keys=selected_keys,
            current_key=current_key,
        )

        candidates = candidates.loc[
            candidates.apply(
                lambda candidate: replacement_respects_variant_limit(
                    old_row=old_row,
                    candidate=candidate,
                    current_variant_count_value=variant_count,
                    variant_limit=ruleset.variant_limit,
                ),
                axis=1,
            )
        ].copy()

        candidates = candidates.loc[
            candidates.apply(
                lambda row: player_qualifies_for_bench_role(
                    row,
                    role_name,
                    ruleset,
                ),
                axis=1,
            )
        ].copy()

        for _, candidate in candidates.iterrows():
            options.append(
                build_option(
                    slot_kind="hitter_bench",
                    slot_key=bench_index,
                    role=role,
                    old_row=old_row,
                    candidate=candidate,
                    old_score=old_score,
                    new_score=safe_score(candidate, "batting_score_overall"),
                )
            )

    return valid_options(options)


def find_pitcher_repair_options(
    pitcher_roster: PitcherRoster,
    eligible_pitchers: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
    variant_count: int,
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    options.extend(
        find_pitcher_group_repair_options(
            group=pitcher_roster.rotation,
            group_name="SP",
            slot_kind="rotation",
            score_col="starter_score_overall",
            eligible_pitchers=eligible_pitchers,
            selected_keys=selected_keys,
            ruleset=ruleset,
            variant_count=variant_count,
        )
    )

    options.extend(
        find_pitcher_group_repair_options(
            group=pitcher_roster.bullpen,
            group_name="RP",
            slot_kind="bullpen",
            score_col="reliever_score_overall",
            eligible_pitchers=eligible_pitchers,
            selected_keys=selected_keys,
            ruleset=ruleset,
            variant_count=variant_count,
        )
    )

    options.extend(
        find_pitcher_group_repair_options(
            group=pitcher_roster.lefty_specialist,
            group_name="LHP Specialist",
            slot_kind="lefty_specialist",
            score_col="reliever_score_vs_lhb",
            eligible_pitchers=eligible_pitchers,
            selected_keys=selected_keys,
            ruleset=ruleset,
            variant_count=variant_count,
        )
    )

    options.extend(
        find_pitcher_group_repair_options(
            group=pitcher_roster.long_man,
            group_name="Long Man",
            slot_kind="long_man",
            score_col="starter_score_overall",
            eligible_pitchers=eligible_pitchers,
            selected_keys=selected_keys,
            ruleset=ruleset,
            variant_count=variant_count,
        )
    )

    return valid_options(options)


def find_pitcher_group_repair_options(
    group: pd.DataFrame,
    group_name: str,
    slot_kind: SlotKind,
    score_col: str,
    eligible_pitchers: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
    variant_count: int,
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    if group.empty:
        return options

    for slot_index, (_, old_row) in enumerate(group.iterrows()):
        role = (
            f"{group_name}{slot_index + 1}"
            if group_name in {"SP", "RP"}
            else group_name
        )

        old_value = card_value(old_row)
        old_score = safe_score(old_row, score_col)
        current_key = player_unique_key(old_row)

        candidates = eligible_pitchers.copy()
        candidates = candidates.loc[candidates["card_value"] < old_value].copy()

        candidates = filter_candidate_duplicate_names(
            candidates,
            selected_keys=selected_keys,
            current_key=current_key,
        )

        candidates = candidates.loc[
            candidates.apply(
                lambda candidate: replacement_respects_variant_limit(
                    old_row=old_row,
                    candidate=candidate,
                    current_variant_count_value=variant_count,
                    variant_limit=ruleset.variant_limit,
                ),
                axis=1,
            )
        ].copy()

        if score_col not in candidates.columns:
            continue

        candidates = candidates.loc[candidates[score_col] > BAD_SCORE / 2].copy()

        for _, candidate in candidates.iterrows():
            options.append(
                build_option(
                    slot_kind=slot_kind,
                    slot_key=slot_index,
                    role=role,
                    old_row=old_row,
                    candidate=candidate,
                    old_score=old_score,
                    new_score=safe_score(candidate, score_col),
                )
            )

    return options


def build_option(
    slot_kind: SlotKind,
    slot_key: str | int,
    role: str,
    old_row: pd.Series,
    candidate: pd.Series,
    old_score: float,
    new_score: float,
) -> CapRepairOption:
    old_value = card_value(old_row)
    new_value = card_value(candidate)
    cap_saved = old_value - new_value
    score_loss = old_score - new_score

    if cap_saved <= 0:
        loss_per_cap_saved = float("inf")
    else:
        loss_per_cap_saved = score_loss / cap_saved

    return CapRepairOption(
        slot_kind=slot_kind,
        slot_key=slot_key,
        role=role,
        old_name=str(old_row.get("name", "")),
        new_name=str(candidate.get("name", "")),
        old_value=old_value,
        new_value=new_value,
        cap_saved=cap_saved,
        old_score=old_score,
        new_score=new_score,
        score_loss=score_loss,
        loss_per_cap_saved=loss_per_cap_saved,
        candidate=candidate,
    )


def valid_options(options: list[CapRepairOption]) -> list[CapRepairOption]:
    return [
        option
        for option in options
        if option.cap_saved > 0
        and option.new_score > BAD_SCORE / 2
        and option.loss_per_cap_saved != float("inf")
    ]


def cap_repair_priority_multiplier(option: CapRepairOption) -> float:
    # Lower = more willing to repair this slot.
    # Higher = protect this slot unless the repair is clearly efficient.

    if option.slot_kind == "hitter_bench":
        return 0.85

    if option.slot_kind == "long_man":
        return 0.90

    if option.slot_kind == "bullpen":
        return 0.95

    if option.slot_kind == "lefty_specialist":
        return 1.00

    if option.slot_kind == "hitter_starter" and option.slot_key == "DH":
        return 1.00

    if option.slot_kind == "hitter_starter" and option.slot_key in {"1B", "LF", "RF"}:
        return 1.05

    if option.slot_kind == "rotation":
        return 1.15

    if option.slot_kind == "hitter_starter" and option.slot_key == "3B":
        return 1.15

    if option.slot_kind == "hitter_starter" and option.slot_key == "2B":
        return 1.25

    if option.slot_kind == "hitter_starter" and option.slot_key == "CF":
        return 1.35

    if option.slot_kind == "hitter_starter" and option.slot_key == "SS":
        return 1.40

    if option.slot_kind == "hitter_starter" and option.slot_key == "C":
        return 1.45

    return 1.25


def adjusted_loss_per_cap(option: CapRepairOption) -> float:
    return option.loss_per_cap_saved * cap_repair_priority_multiplier(option)


def apply_cap_repair_option(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    option: CapRepairOption,
) -> tuple[HitterRoster, PitcherRoster]:
    if option.slot_kind == "hitter_starter":
        new_starters = dict(hitter_roster.starters_by_position)
        new_starters[str(option.slot_key)] = option.candidate

        return (
            HitterRoster(
                starters_by_position=new_starters,
                bench_players=hitter_roster.bench_players.copy(),
                unused_players=hitter_roster.unused_players.copy(),
            ),
            pitcher_roster,
        )

    if option.slot_kind == "hitter_bench":
        new_bench = replace_dataframe_row_by_position(
            hitter_roster.bench_players,
            int(option.slot_key),
            option.candidate,
        )

        return (
            HitterRoster(
                starters_by_position=dict(hitter_roster.starters_by_position),
                bench_players=new_bench,
                unused_players=hitter_roster.unused_players.copy(),
            ),
            pitcher_roster,
        )

    new_pitcher_roster = replace_pitcher_slot(pitcher_roster, option)

    return hitter_roster, new_pitcher_roster


def replace_pitcher_slot(
    pitcher_roster: PitcherRoster,
    option: CapRepairOption,
) -> PitcherRoster:
    rotation = pitcher_roster.rotation.copy()
    bullpen = pitcher_roster.bullpen.copy()
    lefty_specialist = pitcher_roster.lefty_specialist.copy()
    long_man = pitcher_roster.long_man.copy()

    if option.slot_kind == "rotation":
        rotation = replace_dataframe_row_by_position(
            rotation,
            int(option.slot_key),
            option.candidate,
        )
    elif option.slot_kind == "bullpen":
        bullpen = replace_dataframe_row_by_position(
            bullpen,
            int(option.slot_key),
            option.candidate,
        )
    elif option.slot_kind == "lefty_specialist":
        lefty_specialist = replace_dataframe_row_by_position(
            lefty_specialist,
            int(option.slot_key),
            option.candidate,
        )
    elif option.slot_kind == "long_man":
        long_man = replace_dataframe_row_by_position(
            long_man,
            int(option.slot_key),
            option.candidate,
        )

    return PitcherRoster(
        rotation=rotation,
        bullpen=bullpen,
        lefty_specialist=lefty_specialist,
        long_man=long_man,
        unused_players=pitcher_roster.unused_players.copy(),
    )


def replace_dataframe_row_by_position(
    df: pd.DataFrame,
    position: int,
    new_row: pd.Series,
) -> pd.DataFrame:
    rows: list[pd.Series] = []

    for idx, (_, row) in enumerate(df.iterrows()):
        if idx == position:
            rows.append(new_row)
        else:
            rows.append(row)

    if not rows:
        return df.copy()

    return pd.DataFrame(rows)


def selected_player_keys(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> set[str]:
    keys: set[str] = set()

    for row in hitter_roster.starters_by_position.values():
        keys.add(player_unique_key(row))

    for _, row in hitter_roster.bench_players.iterrows():
        keys.add(player_unique_key(row))

    for _, row in pitcher_roster.rotation.iterrows():
        keys.add(player_unique_key(row))

    for _, row in pitcher_roster.bullpen.iterrows():
        keys.add(player_unique_key(row))

    for _, row in pitcher_roster.lefty_specialist.iterrows():
        keys.add(player_unique_key(row))

    for _, row in pitcher_roster.long_man.iterrows():
        keys.add(player_unique_key(row))

    return keys


def filter_candidate_duplicate_names(
    candidates: pd.DataFrame,
    selected_keys: set[str],
    current_key: str,
) -> pd.DataFrame:
    blocked_keys = selected_keys - {current_key}

    return candidates.loc[
        ~candidates.apply(
            lambda row: player_unique_key(row) in blocked_keys,
            axis=1,
        )
    ].copy()


def bench_role_for_index(ruleset: Ruleset, index: int) -> str:
    if index < len(ruleset.bench_roles):
        return ruleset.bench_roles[index]

    return "UTIL"


def safe_score(row: pd.Series, score_col: str) -> float:
    value = row.get(score_col, BAD_SCORE)

    if pd.isna(value):
        return BAD_SCORE

    return float(value)


def print_cap_repair_result(result: CapRepairResult) -> None:
    print("\n=== CAP REPAIR ===")

    if not result.steps:
        if result.success:
            print("No cap repair needed.")
        else:
            print("No cap repair steps were available.")
        return

    for idx, step in enumerate(result.steps, start=1):
        print(
            f"{idx:>2}. {step.role}: "
            f"{step.old_name} ({step.old_value}) -> "
            f"{step.new_name} ({step.new_value}); "
            f"saves {step.cap_saved}, "
            f"score loss {step.score_loss:.2f}, "
            f"loss/cap {step.loss_per_cap_saved:.3f}; "
            f"total now {step.roster_total_after}, "
            f"over by {step.over_cap_by_after}"
        )

    if result.success:
        print(
            f"Cap repair successful: final total {result.final_roster_total}, "
            f"over by {result.final_over_cap_by}"
        )
    else:
        print(
            f"Cap repair incomplete: final total {result.final_roster_total}, "
            f"still over by {result.final_over_cap_by}"
        )


def current_variant_count(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> int:
    return build_variant_summary(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        variant_limit=None,
    ).variant_count


def replacement_respects_variant_limit(
    old_row: pd.Series,
    candidate: pd.Series,
    current_variant_count_value: int,
    variant_limit: int | None,
) -> bool:
    if variant_limit is None:
        return True

    old_is_variant = is_variant_card(old_row)
    new_is_variant = is_variant_card(candidate)

    new_variant_count = current_variant_count_value

    if old_is_variant:
        new_variant_count -= 1

    if new_is_variant:
        new_variant_count += 1

    return new_variant_count <= variant_limit
