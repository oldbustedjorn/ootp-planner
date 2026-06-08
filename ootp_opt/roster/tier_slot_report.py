from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ootp_opt.roster.cap_report import iter_roster_rows
from ootp_opt.roster.models import HitterRoster, PitcherRoster

TIER_ORDER = ["perfect", "diamond", "gold", "silver", "bronze", "iron"]


@dataclass(frozen=True)
class TierSlotRow:
    tier: str
    selected_count: int
    direct_slots: int
    cumulative_selected: int
    cumulative_slots: int
    remaining: int
    is_over_limit: bool


def build_tier_slot_rows(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    tier_slots: dict[str, int],
) -> list[TierSlotRow]:
    selected_counts = count_roster_tiers(hitter_roster, pitcher_roster)
    normalized_slots = normalize_tier_slots(tier_slots)
    tiers = ordered_tiers(selected_counts, normalized_slots)

    rows = []
    cumulative_selected = 0
    cumulative_slots = 0

    for tier in tiers:
        selected_count = selected_counts.get(tier, 0)
        direct_slots = normalized_slots.get(tier, 0)
        cumulative_selected += selected_count
        cumulative_slots += direct_slots
        remaining = cumulative_slots - cumulative_selected

        rows.append(
            TierSlotRow(
                tier=tier,
                selected_count=selected_count,
                direct_slots=direct_slots,
                cumulative_selected=cumulative_selected,
                cumulative_slots=cumulative_slots,
                remaining=remaining,
                is_over_limit=remaining < 0,
            )
        )

    return rows


def count_roster_tiers(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for _, row in iter_roster_rows(hitter_roster, pitcher_roster):
        tier = normalize_tier_name(row.get("pt_tier", ""))
        if not tier:
            continue

        counts[tier] = counts.get(tier, 0) + 1

    return counts


def normalize_tier_slots(tier_slots: dict[str, int]) -> dict[str, int]:
    return {
        normalize_tier_name(tier): int(count)
        for tier, count in tier_slots.items()
        if normalize_tier_name(tier)
    }


def ordered_tiers(
    selected_counts: dict[str, int],
    tier_slots: dict[str, int],
) -> list[str]:
    known = [tier for tier in TIER_ORDER if tier in selected_counts or tier in tier_slots]
    unknown = sorted((set(selected_counts) | set(tier_slots)) - set(TIER_ORDER))
    return known + unknown


def normalize_tier_name(value: object) -> str:
    text = str(value).strip().lower()

    aliases = {
        "p": "perfect",
        "perf": "perfect",
        "perfect": "perfect",
        "d": "diamond",
        "dia": "diamond",
        "diamond": "diamond",
        "g": "gold",
        "gold": "gold",
        "s": "silver",
        "silv": "silver",
        "silver": "silver",
        "b": "bronze",
        "bronze": "bronze",
        "i": "iron",
        "iron": "iron",
    }

    return aliases.get(text, text)


def print_tier_slot_report(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    tier_slots: dict[str, int],
) -> None:
    rows = build_tier_slot_rows(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        tier_slots=tier_slots,
    )

    print("\n=== TIER SLOT SUMMARY ===")

    if not rows:
        print("No selected card tiers found.")
        return

    if not tier_slots:
        print("No tier slot targets set.")
        table = pd.DataFrame(
            [
                {
                    "tier": row.tier,
                    "selected": row.selected_count,
                    "slots": "-",
                    "selected_or_better": "-",
                    "slots_or_better": "-",
                    "remaining": "-",
                    "status": "-",
                }
                for row in rows
            ]
        )

        print(table.to_string(index=False))
        return

    table = pd.DataFrame(
        [
            {
                "tier": row.tier,
                "selected": row.selected_count,
                "slots": row.direct_slots,
                "selected_or_better": row.cumulative_selected,
                "slots_or_better": row.cumulative_slots,
                "remaining": signed_delta(row.remaining),
                "status": "OVER" if row.is_over_limit else "OK",
            }
            for row in rows
        ]
    )

    print(table.to_string(index=False))


def signed_delta(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)
