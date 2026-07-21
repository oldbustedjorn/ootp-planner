from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ootp_opt.roster.models import HitterRoster, PitcherRoster


@dataclass(frozen=True)
class RosterCapSummary:
    cap_total: int | None
    roster_total: int
    cap_remaining: int | None
    over_cap_by: int
    is_over_cap: bool


def card_value(row: pd.Series) -> int:
    value = row.get("card_value", 0)

    if pd.isna(value):
        return 0

    return int(value)


def role_score(row: pd.Series, role: str) -> float:
    if role.startswith("Starter "):
        pos = role.removeprefix("Starter ")
        if pos == "DH":
            return float(row.get("batting_score_overall", 0.0))
        return float(row.get(f"score_{pos}_overall", 0.0))

    if role.startswith("SP") or role.startswith(("Long Man", "Long Relief")):
        return float(row.get("starter_score_overall", 0.0))

    if role.startswith(("RP", "Bullpen", "Middle Relief")):
        return float(row.get("reliever_score_overall", 0.0))

    if role.startswith("LHP Specialist"):
        return float(row.get("reliever_score_vs_lhb", 0.0))

    return float(row.get("batting_score_overall", 0.0))


def iter_roster_rows(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> list[tuple[str, pd.Series]]:
    rows: list[tuple[str, pd.Series]] = []

    for position, row in hitter_roster.starters_by_position.items():
        rows.append((f"Starter {position}", row))

    for idx, (_, row) in enumerate(hitter_roster.bench_players.iterrows(), start=1):
        rows.append((f"Bench {idx}", row))

    for idx, (_, row) in enumerate(pitcher_roster.rotation.iterrows(), start=1):
        rows.append((f"SP{idx}", row))

    for idx, (_, row) in enumerate(pitcher_roster.bullpen.iterrows(), start=1):
        rows.append((f"Middle Relief {idx}", row))

    for idx, (_, row) in enumerate(pitcher_roster.lefty_specialist.iterrows(), start=1):
        rows.append((f"LHP Specialist {idx}", row))

    for idx, (_, row) in enumerate(pitcher_roster.long_man.iterrows(), start=1):
        rows.append((f"Long Relief {idx}", row))

    return rows


def build_cap_summary(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    point_cap_total: int | None,
) -> RosterCapSummary:
    roster_total = sum(
        card_value(row) for _, row in iter_roster_rows(hitter_roster, pitcher_roster)
    )

    if point_cap_total is None:
        return RosterCapSummary(
            cap_total=None,
            roster_total=roster_total,
            cap_remaining=None,
            over_cap_by=0,
            is_over_cap=False,
        )

    cap_remaining = point_cap_total - roster_total
    over_cap_by = max(0, roster_total - point_cap_total)

    return RosterCapSummary(
        cap_total=point_cap_total,
        roster_total=roster_total,
        cap_remaining=cap_remaining,
        over_cap_by=over_cap_by,
        is_over_cap=over_cap_by > 0,
    )


def build_cap_table(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for role, row in iter_roster_rows(hitter_roster, pitcher_roster):
        value = card_value(row)
        score = role_score(row, role)

        records.append(
            {
                "role": role,
                "name": row.get("name", ""),
                "card_value": value,
                "score": round(score, 2),
                "score_per_value": None if value <= 0 else round(score / value, 3),
                "tier": row.get("pt_tier", ""),
                "year": row.get("pt_year", ""),
                "type": row.get("pt_type", ""),
            }
        )

    return pd.DataFrame(records)


def print_cap_report(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    point_cap_total: int | None,
) -> None:
    summary = build_cap_summary(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        point_cap_total=point_cap_total,
    )

    print("\n=== CAP SUMMARY ===")
    if summary.cap_total is None:
        print(f"Roster card-value total: {summary.roster_total}")
        print("No point cap set.")
        return

    print(f"Roster card-value total: {summary.roster_total} / {summary.cap_total}")

    if summary.is_over_cap:
        print(f"OVER CAP by: {summary.over_cap_by}")
    else:
        print(f"Under cap by: {summary.cap_remaining}")

    table = build_cap_table(hitter_roster, pitcher_roster)

    print("\n=== MOST EXPENSIVE SELECTED CARDS ===")
    print(
        table.sort_values("card_value", ascending=False).head(10).to_string(index=False)
    )

    print("\n=== LOWEST SCORE PER CARD VALUE ===")
    print(
        table.sort_values("score_per_value", ascending=True, na_position="last")
        .head(10)
        .to_string(index=False)
    )
