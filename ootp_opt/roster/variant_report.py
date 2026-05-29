from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ootp_opt.roster.cap_report import iter_roster_rows
from ootp_opt.roster.models import HitterRoster, PitcherRoster

MAX_VARIANT_REPAIR_SCORE_LOSS = 75.0


@dataclass(frozen=True)
class VariantSummary:
    variant_limit: int | None
    variant_count: int
    over_limit_by: int
    is_over_limit: bool


def is_variant_card(row: pd.Series) -> bool:
    """
    Variant detection for OOTP variant caps.

    OOTP export column:
      VAR = Y -> variant
      VAR = N -> non-variant

    Normalized ingest column:
      is_variant = True / False
    """
    if "is_variant" in row.index:
        value = row.get("is_variant", False)

        if isinstance(value, bool):
            return value

        text = str(value).strip().upper()
        return text == "Y" or text == "TRUE"

    if "VAR" in row.index:
        text = str(row.get("VAR", "")).strip().upper()
        return text == "Y"

    return False


def build_variant_summary(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    variant_limit: int | None,
) -> VariantSummary:
    variant_count = sum(
        1
        for _, row in iter_roster_rows(hitter_roster, pitcher_roster)
        if is_variant_card(row)
    )

    if variant_limit is None:
        return VariantSummary(
            variant_limit=None,
            variant_count=variant_count,
            over_limit_by=0,
            is_over_limit=False,
        )

    over_limit_by = max(0, variant_count - variant_limit)

    return VariantSummary(
        variant_limit=variant_limit,
        variant_count=variant_count,
        over_limit_by=over_limit_by,
        is_over_limit=over_limit_by > 0,
    )


def build_variant_table(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for role, row in iter_roster_rows(hitter_roster, pitcher_roster):
        if not is_variant_card(row):
            continue

        records.append(
            {
                "role": role,
                "name": row.get("name", ""),
                "card_value": row.get("card_value", ""),
                "tier": row.get("pt_tier", ""),
                "year": row.get("pt_year", ""),
                "type": row.get("pt_type", ""),
                "is_variant": row.get("is_variant", row.get("VAR", "")),
                "subtype": row.get("pt_subtype", row.get("pt_subtype_raw", "")),
            }
        )

    return pd.DataFrame(records)


def print_variant_report(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    variant_limit: int | None,
) -> None:
    summary = build_variant_summary(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        variant_limit=variant_limit,
    )

    print("\n=== VARIANT SUMMARY ===")

    if summary.variant_limit is None:
        print(f"Variant cards selected: {summary.variant_count}")
    else:
        print(
            f"Variant cards selected: "
            f"{summary.variant_count} / {summary.variant_limit}"
        )

        if summary.is_over_limit:
            print(f"OVER VARIANT LIMIT by: {summary.over_limit_by}")
        else:
            print("Variant limit satisfied.")

    table = build_variant_table(hitter_roster, pitcher_roster)

    if table.empty:
        print("No selected variants detected.")
        return

    print("\n=== SELECTED VARIANT CARDS ===")
    print(table.to_string(index=False))
