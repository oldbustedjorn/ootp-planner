from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ootp_opt.roster.portfolio_upgrade_html_export import (
    export_portfolio_upgrade_html,
)
from ootp_opt.services.application_state_service import (
    list_application_roster_plans,
)
from ootp_opt.services.store_upgrade_service import (
    StoreUpgradeRequest,
    find_store_upgrades,
)


DEFAULT_EXCLUDED_TITLE_TERMS = (
    "PTWC",
    "PTCS",
    "PTMS",
    "Limited Edition",
)

PORTFOLIO_REPORT_COLUMNS = [
    "rank",
    "candidate",
    "pt_card_id",
    "is_variant",
    "candidate_tier",
    "candidate_value",
    "card_title",
    "is_clubhouse_card",
    "clubhouse_star_cost",
    "pp_per_clubhouse_star",
    "portfolio_score",
    "rosters_helped",
    "total_estimated_gain",
    "best_estimated_gain",
    "best_roster",
    "purchase_price",
    "sell_order_low",
    "helped_rosters",
]


@dataclass(frozen=True)
class PortfolioUpgradeRequest:
    config_path: str = "config.toml"
    output_path: str = "outputs/all_rosters_upgrade_portfolio.html"
    details_directory: str = "outputs/upgrade_portfolio_details"
    min_gain: float = 0.01
    top_per_type: int = 20
    excluded_title_terms: tuple[str, ...] = DEFAULT_EXCLUDED_TITLE_TERMS
    plan_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioUpgradeResult:
    hitter_upgrades: pd.DataFrame
    pitcher_upgrades: pd.DataFrame
    completed_rosters: tuple[str, ...]
    failed_rosters: dict[str, str] = field(default_factory=dict)
    output_path: str = ""


def find_portfolio_upgrades(
    request: PortfolioUpgradeRequest,
    *,
    progress: Callable[[str], None] | None = None,
) -> PortfolioUpgradeResult:
    plans = list_application_roster_plans(request.config_path)
    details_directory = Path(request.details_directory)
    details_directory.mkdir(parents=True, exist_ok=True)

    collected: list[pd.DataFrame] = []
    completed: list[str] = []
    failed: dict[str, str] = {}
    total = len(plans)

    for index, plan in enumerate(plans, start=1):
        label = plan.display_title or plan.command_name
        if progress is not None:
            progress(f"[{index}/{total}] Finding upgrades for {label}...")
        try:
            result = find_store_upgrades(
                StoreUpgradeRequest(
                    config_path=request.config_path,
                    preset=plan.command_name,
                    overrides=request.plan_overrides.get(plan.command_name, {}),
                    min_gain=request.min_gain,
                    include_owned=False,
                    html_output=str(details_directory / f"{plan.command_name}.html"),
                    build_method="optimizer",
                    exact_results=0,
                    max_price=None,
                    require_sell_order=False,
                )
            )
        except Exception as exc:
            failed[label] = f"{type(exc).__name__}: {exc}"
            if progress is not None:
                progress(f"[{index}/{total}] Failed: {failed[label]}")
            continue

        collected.extend(
            _tag_upgrade_rows(result.hitter_upgrades, "hitter", plan.command_name, label)
        )
        collected.extend(
            _tag_upgrade_rows(result.pitcher_upgrades, "pitcher", plan.command_name, label)
        )
        completed.append(label)
        if progress is not None:
            progress(
                f"[{index}/{total}] Complete: "
                f"{len(result.hitter_upgrades)} hitters, "
                f"{len(result.pitcher_upgrades)} pitchers"
            )

    all_rows = (
        pd.concat(collected, ignore_index=True, sort=False)
        if collected
        else pd.DataFrame()
    )
    filtered = exclude_card_titles(all_rows, request.excluded_title_terms)
    hitters = aggregate_portfolio_upgrades(
        filtered.loc[filtered.get("type", pd.Series(dtype=str)).eq("hitter")],
        top=request.top_per_type,
    )
    pitchers = aggregate_portfolio_upgrades(
        filtered.loc[filtered.get("type", pd.Series(dtype=str)).eq("pitcher")],
        top=request.top_per_type,
    )

    export_portfolio_upgrade_html(
        request.output_path,
        hitter_upgrades=hitters,
        pitcher_upgrades=pitchers,
        completed_rosters=completed,
        failed_rosters=failed,
        excluded_title_terms=request.excluded_title_terms,
        applied_overrides=request.plan_overrides,
    )
    return PortfolioUpgradeResult(
        hitter_upgrades=hitters,
        pitcher_upgrades=pitchers,
        completed_rosters=tuple(completed),
        failed_rosters=failed,
        output_path=request.output_path,
    )


def _tag_upgrade_rows(
    rows: pd.DataFrame,
    upgrade_type: str,
    roster_id: str,
    roster_name: str,
) -> list[pd.DataFrame]:
    if rows.empty:
        return []
    tagged = rows.copy()
    tagged["type"] = upgrade_type
    tagged["roster_id"] = roster_id
    tagged["roster_name"] = roster_name
    return [tagged]


def exclude_card_titles(
    rows: pd.DataFrame,
    excluded_terms: tuple[str, ...],
) -> pd.DataFrame:
    if rows.empty or not excluded_terms:
        return rows.copy()
    searchable = (
        rows.get("card_title", pd.Series("", index=rows.index))
        .fillna("")
        .astype(str)
    )
    excluded = pd.Series(False, index=rows.index)
    for term in excluded_terms:
        excluded |= searchable.str.contains(term, case=False, regex=False)
    return rows.loc[~excluded].copy()


def aggregate_portfolio_upgrades(rows: pd.DataFrame, *, top: int) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=PORTFOLIO_REPORT_COLUMNS)

    working = rows.copy()
    working["estimated_objective_gain"] = pd.to_numeric(
        working["estimated_objective_gain"], errors="coerce"
    ).fillna(0.0)
    working = working.loc[working["estimated_objective_gain"] > 0].copy()
    if working.empty:
        return pd.DataFrame(columns=PORTFOLIO_REPORT_COLUMNS)

    # Keep one opportunity per card and roster before calculating breadth.
    identity = ["type", "pt_card_id", "is_variant"]
    working = working.sort_values("estimated_objective_gain", ascending=False)
    working = working.drop_duplicates(identity + ["roster_id"], keep="first")
    roster_max = working.groupby("roster_id")["estimated_objective_gain"].transform(
        "max"
    )
    working["relative_benefit"] = working["estimated_objective_gain"] / roster_max
    working["portfolio_points"] = 100.0 * working["relative_benefit"] + 5.0

    output_rows: list[dict[str, object]] = []
    for _, group in working.groupby(identity, sort=False, dropna=False):
        ranked = group.sort_values("estimated_objective_gain", ascending=False)
        best = ranked.iloc[0]
        roster_details = ranked.sort_values(
            "relative_benefit", ascending=False
        ).apply(
            lambda row: (
                f"{row['roster_name']} (+{row['estimated_objective_gain']:.2f}; "
                f"{row['relative_benefit']:.0%} of roster leader)"
            ),
            axis=1,
        )
        output_rows.append(
            {
                "candidate": best.get("candidate", ""),
                "pt_card_id": best.get("pt_card_id", ""),
                "is_variant": bool(best.get("is_variant", False)),
                "candidate_tier": best.get("candidate_tier", ""),
                "candidate_value": best.get("candidate_value", ""),
                "card_title": best.get("card_title", ""),
                "is_clubhouse_card": bool(
                    best.get("is_clubhouse_card", False)
                ),
                "clubhouse_star_cost": best.get("clubhouse_star_cost"),
                "pp_per_clubhouse_star": best.get("pp_per_clubhouse_star"),
                "portfolio_score": round(float(group["portfolio_points"].sum()), 2),
                "rosters_helped": int(group["roster_id"].nunique()),
                "total_estimated_gain": round(
                    float(group["estimated_objective_gain"].sum()), 2
                ),
                "best_estimated_gain": round(
                    float(best["estimated_objective_gain"]), 2
                ),
                "best_roster": best["roster_name"],
                "purchase_price": _optional_int(best.get("purchase_price")),
                "sell_order_low": _optional_int(best.get("sell_order_low")),
                "helped_rosters": "; ".join(roster_details.tolist()),
            }
        )

    result = pd.DataFrame(output_rows).sort_values(
        ["portfolio_score", "rosters_helped", "total_estimated_gain"],
        ascending=False,
    )
    result = result.head(top).reset_index(drop=True)
    result.insert(0, "rank", result.index + 1)
    return result[PORTFOLIO_REPORT_COLUMNS]


def _optional_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)
