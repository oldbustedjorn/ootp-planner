from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from ootp_opt.roster.builder import (
    get_hitter_score_column,
    player_qualifies_for_bench_role,
    player_unique_key,
)
from ootp_opt.roster.cap_repair import (
    BAD_SCORE,
    apply_cap_repair_option,
    bench_role_for_index,
    filter_candidate_duplicate_names,
    selected_player_keys,
    safe_score,
)
from ootp_opt.roster.cap_repair import CapRepairOption
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset
from ootp_opt.roster.variant_report import (
    build_variant_summary,
    is_variant_card,
)


@dataclass(frozen=True)
class VariantRepairStep:
    role: str
    old_name: str
    new_name: str
    old_value: int
    new_value: int
    old_score: float
    new_score: float
    score_loss: float
    variant_count_after: int
    over_limit_by_after: int


@dataclass(frozen=True)
class VariantRepairResult:
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster
    steps: list[VariantRepairStep]
    success: bool
    final_variant_count: int
    final_over_limit_by: int


def repair_roster_to_variant_limit(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
    max_iterations: int = 100,
) -> VariantRepairResult:
    if ruleset.variant_limit is None:
        summary = build_variant_summary(hitter_roster, pitcher_roster, None)
        return VariantRepairResult(
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            steps=[],
            success=True,
            final_variant_count=summary.variant_count,
            final_over_limit_by=0,
        )

    current_hitters = hitter_roster
    current_pitchers = pitcher_roster
    steps: list[VariantRepairStep] = []

    for _ in range(max_iterations):
        summary = build_variant_summary(
            current_hitters,
            current_pitchers,
            ruleset.variant_limit,
        )

        if not summary.is_over_limit:
            return VariantRepairResult(
                hitter_roster=current_hitters,
                pitcher_roster=current_pitchers,
                steps=steps,
                success=True,
                final_variant_count=summary.variant_count,
                final_over_limit_by=summary.over_limit_by,
            )

        options = find_variant_repair_options(
            hitter_roster=current_hitters,
            pitcher_roster=current_pitchers,
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
            ruleset=ruleset,
        )

        if not options:
            return VariantRepairResult(
                hitter_roster=current_hitters,
                pitcher_roster=current_pitchers,
                steps=steps,
                success=False,
                final_variant_count=summary.variant_count,
                final_over_limit_by=summary.over_limit_by,
            )

        best = options[0]

        current_hitters, current_pitchers = apply_cap_repair_option(
            hitter_roster=current_hitters,
            pitcher_roster=current_pitchers,
            option=best,
        )

        new_summary = build_variant_summary(
            current_hitters,
            current_pitchers,
            ruleset.variant_limit,
        )

        steps.append(
            VariantRepairStep(
                role=best.role,
                old_name=best.old_name,
                new_name=best.new_name,
                old_value=best.old_value,
                new_value=best.new_value,
                old_score=best.old_score,
                new_score=best.new_score,
                score_loss=best.score_loss,
                variant_count_after=new_summary.variant_count,
                over_limit_by_after=new_summary.over_limit_by,
            )
        )

    final_summary = build_variant_summary(
        current_hitters,
        current_pitchers,
        ruleset.variant_limit,
    )

    return VariantRepairResult(
        hitter_roster=current_hitters,
        pitcher_roster=current_pitchers,
        steps=steps,
        success=not final_summary.is_over_limit,
        final_variant_count=final_summary.variant_count,
        final_over_limit_by=final_summary.over_limit_by,
    )


def find_variant_repair_options(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
) -> list[CapRepairOption]:
    selected_keys = selected_player_keys(hitter_roster, pitcher_roster)
    options: list[CapRepairOption] = []

    options.extend(
        find_variant_hitter_starter_options(
            hitter_roster=hitter_roster,
            eligible_hitters=eligible_hitters,
            selected_keys=selected_keys,
        )
    )

    options.extend(
        find_variant_hitter_bench_options(
            hitter_roster=hitter_roster,
            eligible_hitters=eligible_hitters,
            selected_keys=selected_keys,
            ruleset=ruleset,
        )
    )

    options.extend(
        find_variant_pitcher_options(
            pitcher_roster=pitcher_roster,
            eligible_pitchers=eligible_pitchers,
            selected_keys=selected_keys,
        )
    )

    return sorted(
        options,
        key=lambda option: (
            variant_repair_priority_multiplier(option),
            option.score_loss,
            option.loss_per_cap_saved,
        ),
    )


def find_variant_hitter_starter_options(
    hitter_roster: HitterRoster,
    eligible_hitters: pd.DataFrame,
    selected_keys: set[str],
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    for position, old_row in hitter_roster.starters_by_position.items():
        if not is_variant_card(old_row):
            continue

        role = f"Starter {position}"
        score_col = get_hitter_score_column(position)
        old_score = safe_score(old_row, score_col)
        current_key = player_unique_key(old_row)

        candidates = eligible_hitters.copy()
        candidates = candidates.loc[~candidates.apply(is_variant_card, axis=1)].copy()

        candidates = filter_candidate_duplicate_names(
            candidates,
            selected_keys=selected_keys,
            current_key=current_key,
        )

        if score_col not in candidates.columns:
            continue

        candidates = candidates.loc[candidates[score_col] > BAD_SCORE / 2].copy()

        for _, candidate in candidates.iterrows():
            options.append(
                build_variant_option(
                    slot_kind="hitter_starter",
                    slot_key=position,
                    role=role,
                    old_row=old_row,
                    candidate=candidate,
                    old_score=old_score,
                    new_score=safe_score(candidate, score_col),
                )
            )

    return valid_variant_options(options)


def find_variant_hitter_bench_options(
    hitter_roster: HitterRoster,
    eligible_hitters: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    for bench_index, (_, old_row) in enumerate(hitter_roster.bench_players.iterrows()):
        if not is_variant_card(old_row):
            continue

        role_name = bench_role_for_index(ruleset, bench_index)
        role = f"Bench {bench_index + 1} ({role_name})"
        old_score = safe_score(old_row, "batting_score_overall")
        current_key = player_unique_key(old_row)

        candidates = eligible_hitters.copy()
        candidates = candidates.loc[~candidates.apply(is_variant_card, axis=1)].copy()

        candidates = filter_candidate_duplicate_names(
            candidates,
            selected_keys=selected_keys,
            current_key=current_key,
        )

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
                build_variant_option(
                    slot_kind="hitter_bench",
                    slot_key=bench_index,
                    role=role,
                    old_row=old_row,
                    candidate=candidate,
                    old_score=old_score,
                    new_score=safe_score(candidate, "batting_score_overall"),
                )
            )

    return valid_variant_options(options)


def find_variant_pitcher_options(
    pitcher_roster: PitcherRoster,
    eligible_pitchers: pd.DataFrame,
    selected_keys: set[str],
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    pitcher_groups = [
        ("rotation", pitcher_roster.rotation, "SP", "starter_score_overall"),
        ("bullpen", pitcher_roster.bullpen, "RP", "reliever_score_overall"),
        (
            "lefty_specialist",
            pitcher_roster.lefty_specialist,
            "LHP Specialist",
            "reliever_score_vs_lhb",
        ),
        ("long_man", pitcher_roster.long_man, "Long Man", "starter_score_overall"),
    ]

    for slot_kind, group, group_name, score_col in pitcher_groups:
        if group.empty:
            continue

        for slot_index, (_, old_row) in enumerate(group.iterrows()):
            if not is_variant_card(old_row):
                continue

            role = (
                f"{group_name}{slot_index + 1}"
                if group_name in {"SP", "RP"}
                else group_name
            )

            old_score = safe_score(old_row, score_col)
            current_key = player_unique_key(old_row)

            candidates = eligible_pitchers.copy()
            candidates = candidates.loc[
                ~candidates.apply(is_variant_card, axis=1)
            ].copy()

            candidates = filter_candidate_duplicate_names(
                candidates,
                selected_keys=selected_keys,
                current_key=current_key,
            )

            if score_col not in candidates.columns:
                continue

            candidates = candidates.loc[candidates[score_col] > BAD_SCORE / 2].copy()

            for _, candidate in candidates.iterrows():
                options.append(
                    build_variant_option(
                        slot_kind=slot_kind,
                        slot_key=slot_index,
                        role=role,
                        old_row=old_row,
                        candidate=candidate,
                        old_score=old_score,
                        new_score=safe_score(candidate, score_col),
                    )
                )

    return valid_variant_options(options)


def build_variant_option(
    slot_kind,
    slot_key,
    role: str,
    old_row: pd.Series,
    candidate: pd.Series,
    old_score: float,
    new_score: float,
) -> CapRepairOption:
    old_value = int(old_row.get("card_value", 0) or 0)
    new_value = int(candidate.get("card_value", 0) or 0)
    cap_saved = old_value - new_value
    score_loss = old_score - new_score

    loss_per_cap_saved = score_loss / cap_saved if cap_saved > 0 else score_loss

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


def valid_variant_options(options: list[CapRepairOption]) -> list[CapRepairOption]:
    return [option for option in options if option.new_score > BAD_SCORE / 2]


def variant_repair_priority_multiplier(option: CapRepairOption) -> float:
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


def print_variant_repair_result(result: VariantRepairResult) -> None:
    print("\n=== VARIANT REPAIR ===")

    if not result.steps:
        if result.success:
            print("No variant repair needed.")
        else:
            print("No variant repair steps were available.")
        return

    for idx, step in enumerate(result.steps, start=1):
        print(
            f"{idx:>2}. {step.role}: "
            f"{step.old_name} ({step.old_value}) -> "
            f"{step.new_name} ({step.new_value}); "
            f"score loss {step.score_loss:.2f}; "
            f"variants now {step.variant_count_after}, "
            f"over by {step.over_limit_by_after}"
        )

    if result.success:
        print(
            f"Variant repair successful: final variants "
            f"{result.final_variant_count}, over by {result.final_over_limit_by}"
        )
    else:
        print(
            f"Variant repair incomplete: final variants "
            f"{result.final_variant_count}, still over by "
            f"{result.final_over_limit_by}"
        )
