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
    CapRepairOption,
    apply_cap_repair_option,
    bench_role_for_index,
    current_variant_count,
    filter_candidate_duplicate_names,
    replacement_respects_variant_limit,
    safe_score,
    selected_player_keys,
)
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset
from ootp_opt.roster.tier_slot_report import (
    highest_violated_tier,
    normalize_tier_name,
    tier_rank,
    tier_slots_satisfied,
)
from ootp_opt.roster.variant_repair import variant_repair_priority_multiplier


@dataclass(frozen=True)
class TierSlotRepairStep:
    role: str
    old_name: str
    new_name: str
    old_tier: str
    new_tier: str
    old_score: float
    new_score: float
    score_loss: float
    repaired_tier: str
    still_over_tier: str | None


@dataclass(frozen=True)
class TierSlotRepairResult:
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster
    steps: list[TierSlotRepairStep]
    success: bool
    final_over_tier: str | None


def repair_roster_to_tier_slots(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
    max_iterations: int = 100,
) -> TierSlotRepairResult:
    if not ruleset.tier_slots:
        return TierSlotRepairResult(
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            steps=[],
            success=True,
            final_over_tier=None,
        )

    current_hitters = hitter_roster
    current_pitchers = pitcher_roster
    steps: list[TierSlotRepairStep] = []

    for _ in range(max_iterations):
        over_tier = highest_violated_tier(
            current_hitters,
            current_pitchers,
            ruleset.tier_slots,
        )

        if over_tier is None:
            return TierSlotRepairResult(
                hitter_roster=current_hitters,
                pitcher_roster=current_pitchers,
                steps=steps,
                success=True,
                final_over_tier=None,
            )

        options = find_tier_slot_repair_options(
            hitter_roster=current_hitters,
            pitcher_roster=current_pitchers,
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
            ruleset=ruleset,
            over_tier=over_tier,
        )

        if not options:
            return TierSlotRepairResult(
                hitter_roster=current_hitters,
                pitcher_roster=current_pitchers,
                steps=steps,
                success=False,
                final_over_tier=over_tier,
            )

        best = options[0]
        old_tier = normalize_tier_name(best.old_value)
        new_tier = normalize_tier_name(best.new_value)

        current_hitters, current_pitchers = apply_cap_repair_option(
            hitter_roster=current_hitters,
            pitcher_roster=current_pitchers,
            option=best,
        )

        still_over_tier = highest_violated_tier(
            current_hitters,
            current_pitchers,
            ruleset.tier_slots,
        )

        steps.append(
            TierSlotRepairStep(
                role=best.role,
                old_name=best.old_name,
                new_name=best.new_name,
                old_tier=old_tier,
                new_tier=new_tier,
                old_score=best.old_score,
                new_score=best.new_score,
                score_loss=best.score_loss,
                repaired_tier=over_tier,
                still_over_tier=still_over_tier,
            )
        )

    final_over_tier = highest_violated_tier(
        current_hitters,
        current_pitchers,
        ruleset.tier_slots,
    )

    return TierSlotRepairResult(
        hitter_roster=current_hitters,
        pitcher_roster=current_pitchers,
        steps=steps,
        success=tier_slots_satisfied(
            current_hitters,
            current_pitchers,
            ruleset.tier_slots,
        ),
        final_over_tier=final_over_tier,
    )


def find_tier_slot_repair_options(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    ruleset: Ruleset,
    over_tier: str,
) -> list[CapRepairOption]:
    selected_keys = selected_player_keys(hitter_roster, pitcher_roster)
    variant_count = current_variant_count(hitter_roster, pitcher_roster)
    over_rank = tier_rank(over_tier)

    options: list[CapRepairOption] = []
    options.extend(
        find_hitter_starter_options(
            hitter_roster=hitter_roster,
            eligible_hitters=eligible_hitters,
            selected_keys=selected_keys,
            ruleset=ruleset,
            over_rank=over_rank,
            variant_count=variant_count,
        )
    )
    options.extend(
        find_hitter_bench_options(
            hitter_roster=hitter_roster,
            eligible_hitters=eligible_hitters,
            selected_keys=selected_keys,
            ruleset=ruleset,
            over_rank=over_rank,
            variant_count=variant_count,
        )
    )
    options.extend(
        find_pitcher_options(
            pitcher_roster=pitcher_roster,
            eligible_pitchers=eligible_pitchers,
            selected_keys=selected_keys,
            ruleset=ruleset,
            over_rank=over_rank,
            variant_count=variant_count,
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


def find_hitter_starter_options(
    hitter_roster: HitterRoster,
    eligible_hitters: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
    over_rank: int,
    variant_count: int,
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    for position, old_row in hitter_roster.starters_by_position.items():
        old_tier = normalize_tier_name(old_row.get("pt_tier", ""))
        if not tier_is_at_or_above_rank(old_tier, over_rank):
            continue

        score_col = get_hitter_score_column(position)
        old_score = safe_score(old_row, score_col)
        current_key = player_unique_key(old_row)

        candidates = eligible_hitters.copy()
        candidates = filter_candidate_duplicate_names(
            candidates,
            selected_keys=selected_keys,
            current_key=current_key,
        )
        candidates = filter_candidates_for_lower_tier(candidates, over_rank)
        candidates = filter_candidates_for_variant_limit(
            candidates, old_row, ruleset, variant_count
        )

        if score_col not in candidates.columns:
            continue

        candidates = candidates.loc[candidates[score_col] > BAD_SCORE / 2].copy()

        for _, candidate in candidates.iterrows():
            options.append(
                build_tier_option(
                    slot_kind="hitter_starter",
                    slot_key=position,
                    role=f"Starter {position}",
                    old_row=old_row,
                    candidate=candidate,
                    old_score=old_score,
                    new_score=safe_score(candidate, score_col),
                )
            )

    return valid_tier_options(options)


def find_hitter_bench_options(
    hitter_roster: HitterRoster,
    eligible_hitters: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
    over_rank: int,
    variant_count: int,
) -> list[CapRepairOption]:
    options: list[CapRepairOption] = []

    for bench_index, (_, old_row) in enumerate(hitter_roster.bench_players.iterrows()):
        old_tier = normalize_tier_name(old_row.get("pt_tier", ""))
        if not tier_is_at_or_above_rank(old_tier, over_rank):
            continue

        role_name = bench_role_for_index(ruleset, bench_index)
        old_score = safe_score(old_row, "batting_score_overall")
        current_key = player_unique_key(old_row)

        candidates = eligible_hitters.copy()
        candidates = filter_candidate_duplicate_names(
            candidates,
            selected_keys=selected_keys,
            current_key=current_key,
        )
        candidates = filter_candidates_for_lower_tier(candidates, over_rank)
        candidates = filter_candidates_for_variant_limit(
            candidates, old_row, ruleset, variant_count
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
                build_tier_option(
                    slot_kind="hitter_bench",
                    slot_key=bench_index,
                    role=f"Bench {bench_index + 1} ({role_name})",
                    old_row=old_row,
                    candidate=candidate,
                    old_score=old_score,
                    new_score=safe_score(candidate, "batting_score_overall"),
                )
            )

    return valid_tier_options(options)


def find_pitcher_options(
    pitcher_roster: PitcherRoster,
    eligible_pitchers: pd.DataFrame,
    selected_keys: set[str],
    ruleset: Ruleset,
    over_rank: int,
    variant_count: int,
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
            old_tier = normalize_tier_name(old_row.get("pt_tier", ""))
            if not tier_is_at_or_above_rank(old_tier, over_rank):
                continue

            current_key = player_unique_key(old_row)
            candidates = eligible_pitchers.copy()
            candidates = filter_candidate_duplicate_names(
                candidates,
                selected_keys=selected_keys,
                current_key=current_key,
            )
            candidates = filter_candidates_for_lower_tier(candidates, over_rank)
            candidates = filter_candidates_for_variant_limit(
                candidates, old_row, ruleset, variant_count
            )

            if score_col not in candidates.columns:
                continue

            candidates = candidates.loc[candidates[score_col] > BAD_SCORE / 2].copy()

            role = (
                f"{group_name}{slot_index + 1}"
                if group_name in {"SP", "RP"}
                else group_name
            )

            for _, candidate in candidates.iterrows():
                options.append(
                    build_tier_option(
                        slot_kind=slot_kind,
                        slot_key=slot_index,
                        role=role,
                        old_row=old_row,
                        candidate=candidate,
                        old_score=safe_score(old_row, score_col),
                        new_score=safe_score(candidate, score_col),
                    )
                )

    return valid_tier_options(options)


def filter_candidates_for_lower_tier(
    candidates: pd.DataFrame,
    over_rank: int,
) -> pd.DataFrame:
    if "pt_tier" not in candidates.columns:
        return candidates.iloc[0:0].copy()

    return candidates.loc[
        candidates["pt_tier"].apply(
            lambda tier: tier_is_below_rank(normalize_tier_name(tier), over_rank)
        )
    ].copy()


def filter_candidates_for_variant_limit(
    candidates: pd.DataFrame,
    old_row: pd.Series,
    ruleset: Ruleset,
    variant_count: int,
) -> pd.DataFrame:
    if ruleset.variant_limit is None:
        return candidates

    return candidates.loc[
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


def tier_is_at_or_above_rank(tier: str, rank: int) -> bool:
    return tier in {"perfect", "diamond", "gold", "silver", "bronze", "iron"} and (
        tier_rank(tier) <= rank
    )


def tier_is_below_rank(tier: str, rank: int) -> bool:
    return tier in {"perfect", "diamond", "gold", "silver", "bronze", "iron"} and (
        tier_rank(tier) > rank
    )


def build_tier_option(
    slot_kind,
    slot_key,
    role: str,
    old_row: pd.Series,
    candidate: pd.Series,
    old_score: float,
    new_score: float,
) -> CapRepairOption:
    score_loss = old_score - new_score

    return CapRepairOption(
        slot_kind=slot_kind,
        slot_key=slot_key,
        role=role,
        old_name=str(old_row.get("name", "")),
        new_name=str(candidate.get("name", "")),
        old_value=str(old_row.get("pt_tier", "")),
        new_value=str(candidate.get("pt_tier", "")),
        cap_saved=0,
        old_score=old_score,
        new_score=new_score,
        score_loss=score_loss,
        loss_per_cap_saved=score_loss,
        candidate=candidate,
    )


def valid_tier_options(options: list[CapRepairOption]) -> list[CapRepairOption]:
    return [option for option in options if option.new_score > BAD_SCORE / 2]


def print_tier_slot_repair_result(result: TierSlotRepairResult) -> None:
    print("\n=== TIER SLOT REPAIR ===")

    if not result.steps:
        if result.success:
            print("No tier slot repair needed.")
        else:
            print("No tier slot repair steps were available.")
        return

    for idx, step in enumerate(result.steps, start=1):
        still_over = step.still_over_tier or "none"
        print(
            f"{idx:>2}. {step.role}: "
            f"{step.old_name} ({step.old_tier}) -> "
            f"{step.new_name} ({step.new_tier}); "
            f"score loss {step.score_loss:.2f}; "
            f"repaired tier {step.repaired_tier}, "
            f"still over: {still_over}"
        )

    if result.success:
        print("Tier slot repair successful.")
    else:
        print(f"Tier slot repair incomplete: still over {result.final_over_tier}.")
