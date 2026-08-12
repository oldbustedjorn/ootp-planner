from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from ootp_opt.domain.candidate_identity import CANDIDATE_ID_COLUMN
from ootp_opt.domain.simulation_context import SimulationContext
from ootp_opt.domain.scoring_environment import ScoringEnvironment
from ootp_opt.ingest.pt_hitters import load_pt_cards_csv
from ootp_opt.ingest.pt_pitchers import load_pt_pitchers_csv
from ootp_opt.ingest.pt_store import load_pt_store_hitters_pitchers
from ootp_opt.optimization.roster_optimizer import (
    OptimizationSolution,
    OptimizerSettings,
    solve_roster_optimization,
)
from ootp_opt.optimization.solution_adapter import convert_optimization_solution
from ootp_opt.optimization.solver_input import SolverInput
from ootp_opt.optimization.upgrade_search import (
    CandidateUpgradeSolution,
    build_direct_upgrade_opportunities,
    enumerate_single_purchase_upgrades,
)
from ootp_opt.roster.builder import (
    build_hitter_roster,
    build_pitcher_roster,
    selected_hitter_roster_keys,
    validate_no_duplicate_players,
)
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import (
    Ruleset,
    build_ruleset_from_base_profile,
    build_ruleset_from_tournament_preset,
)
from ootp_opt.roster.upgrade_finder import (
    estimate_purchase_price,
    find_hitter_upgrades,
    find_pitcher_upgrades,
    safe_cost_per_gain,
)
from ootp_opt.roster.upgrade_html_export import export_upgrade_html
from ootp_opt.services.candidate_service import (
    BuildContext,
    CandidatePool,
    build_candidate_pool,
    resolve_build_context,
)
from ootp_opt.services.application_state_service import load_runtime_config
from ootp_opt.services.rating_service import rate_hitters_df, rate_pitchers_df


@dataclass(frozen=True)
class StoreUpgradeRequest:
    config_path: str = "config.toml"
    base_profile: str | None = None
    preset: str | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    min_gain: float = 5.0
    include_owned: bool = False
    html_output: str | None = None
    build_method: Literal["greedy", "optimizer"] | None = None
    exact_results: int = 0
    max_price: int | None = None
    require_sell_order: bool = True


@dataclass(frozen=True)
class StoreUpgradeResult:
    context: BuildContext
    owned_candidates: CandidatePool
    store_candidates: CandidatePool
    ruleset: Ruleset
    simulation_context: SimulationContext
    scoring_environment: ScoringEnvironment
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster
    hitter_upgrades: Any
    pitcher_upgrades: Any
    eligibility_summary: dict[str, int]
    html_output: str
    build_method: Literal["greedy", "optimizer"]
    optimization_summary: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class UpgradeComputation:
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster
    hitter_upgrades: pd.DataFrame
    pitcher_upgrades: pd.DataFrame
    summary: dict[str, str] = field(default_factory=dict)


def find_store_upgrades(request: StoreUpgradeRequest) -> StoreUpgradeResult:
    cfg = load_runtime_config(request.config_path)
    ruleset = build_ruleset(cfg, request)
    build_method = resolve_upgrade_build_method(cfg, request)
    context = resolve_build_context(cfg, ruleset)
    scoring_environment = context.scoring_environment
    simulation_context = context.simulation_context

    hitters_df = load_pt_cards_csv(cfg["paths"]["hitters_csv"])
    pitchers_df = load_pt_pitchers_csv(cfg["paths"]["pitchers_csv"])

    scored_hitters = rate_hitters_df(hitters_df, context.scoring_config)
    scored_pitchers = rate_pitchers_df(pitchers_df, context.scoring_config)
    owned_candidates = build_candidate_pool(
        source="owned",
        context=context,
        scored_hitters=scored_hitters,
        scored_pitchers=scored_pitchers,
    )
    owned_candidates.require_eligible_cards()
    eligible_hitters = owned_candidates.eligible_hitters
    eligible_pitchers = owned_candidates.eligible_pitchers

    store_hitters, store_pitchers = load_pt_store_hitters_pitchers(
        cfg["paths"]["store_csv"]
    )

    scored_store_hitters = rate_hitters_df(store_hitters, context.scoring_config)
    scored_store_pitchers = rate_pitchers_df(store_pitchers, context.scoring_config)
    store_candidates = build_candidate_pool(
        source="store",
        context=context,
        scored_hitters=scored_store_hitters,
        scored_pitchers=scored_store_pitchers,
    )
    eligible_store_hitters = store_candidates.eligible_hitters
    eligible_store_pitchers = store_candidates.eligible_pitchers

    if request.include_owned:
        eligible_store_hitters = eligible_store_hitters.copy()
        eligible_store_pitchers = eligible_store_pitchers.copy()
        eligible_store_hitters["is_owned"] = False
        eligible_store_pitchers["is_owned"] = False
        store_candidates = replace(
            store_candidates,
            eligible_hitters=eligible_store_hitters,
            eligible_pitchers=eligible_store_pitchers,
        )

    if build_method == "optimizer":
        computation = find_optimizer_upgrades(
            owned_candidates=owned_candidates,
            store_hitters=eligible_store_hitters,
            store_pitchers=eligible_store_pitchers,
            request=request,
        )
    else:
        computation = find_greedy_upgrades(
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
            store_hitters=eligible_store_hitters,
            store_pitchers=eligible_store_pitchers,
            ruleset=ruleset,
            min_gain=request.min_gain,
        )

    hitter_roster = computation.hitter_roster
    pitcher_roster = computation.pitcher_roster
    hitter_upgrades = computation.hitter_upgrades
    pitcher_upgrades = computation.pitcher_upgrades

    html_output = request.html_output or build_output_name(ruleset)
    export_upgrade_html(
        path=html_output,
        hitter_upgrades=hitter_upgrades,
        pitcher_upgrades=pitcher_upgrades,
        title=f"OOTP Store Upgrades - {ruleset.name}",
        summary_rows=[
            ("Ruleset", ruleset.name),
            ("Build method", build_method),
            ("Scoring environment", scoring_environment.name),
            ("Scoring environment source", scoring_environment.source),
            ("Simulation year", simulation_context.simulation_year or "-"),
            ("Ballpark", simulation_context.park.park if simulation_context.park else "-"),
            *computation.summary.items(),
        ],
    )

    return StoreUpgradeResult(
        context=context,
        owned_candidates=owned_candidates,
        store_candidates=store_candidates,
        ruleset=ruleset,
        simulation_context=simulation_context,
        scoring_environment=scoring_environment,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        hitter_upgrades=hitter_upgrades,
        pitcher_upgrades=pitcher_upgrades,
        eligibility_summary={
            "owned_hitters_eligible": len(eligible_hitters),
            "owned_pitchers_eligible": len(eligible_pitchers),
            "store_hitters_eligible": len(eligible_store_hitters),
            "store_pitchers_eligible": len(eligible_store_pitchers),
        },
        html_output=html_output,
        build_method=build_method,
        optimization_summary=computation.summary,
    )


def find_greedy_upgrades(
    *,
    eligible_hitters: pd.DataFrame,
    eligible_pitchers: pd.DataFrame,
    store_hitters: pd.DataFrame,
    store_pitchers: pd.DataFrame,
    ruleset: Ruleset,
    min_gain: float,
) -> UpgradeComputation:
    hitter_roster = build_hitter_roster(eligible_hitters, ruleset)
    pitcher_roster = build_pitcher_roster(
        eligible_pitchers,
        ruleset,
        used_player_names=selected_hitter_roster_keys(hitter_roster),
    )
    validate_no_duplicate_players(hitter_roster, pitcher_roster)
    return UpgradeComputation(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        hitter_upgrades=find_hitter_upgrades(
            hitter_roster,
            store_hitters,
            min_gain=min_gain,
        ),
        pitcher_upgrades=find_pitcher_upgrades(
            pitcher_roster,
            store_pitchers,
            min_gain=min_gain,
        ),
    )


def find_optimizer_upgrades(
    *,
    owned_candidates: CandidatePool,
    store_hitters: pd.DataFrame,
    store_pitchers: pd.DataFrame,
    request: StoreUpgradeRequest,
) -> UpgradeComputation:
    if request.exact_results < 0:
        raise ValueError("Exact upgrade result count cannot be negative.")
    if request.max_price is not None and request.max_price < 0:
        raise ValueError("Maximum upgrade price cannot be negative.")

    settings = OptimizerSettings()
    owned_matrices = owned_candidates.build_matrices()
    owned_input = owned_candidates.build_solver_input(owned_matrices)
    baseline = solve_roster_optimization(owned_input, settings)
    require_feasible_upgrade_solution(baseline, "baseline")

    converted = convert_optimization_solution(
        solution=baseline,
        solver_input=owned_input,
        eligible_hitters=owned_candidates.eligible_hitters,
        eligible_pitchers=owned_candidates.eligible_pitchers,
    )

    owned_ids = set(owned_input.candidates["candidate_id"])
    purchase_hitters = available_store_cards(
        store_hitters,
        include_owned=request.include_owned,
        excluded_ids=owned_ids,
    )
    purchase_pitchers = available_store_cards(
        store_pitchers,
        include_owned=request.include_owned,
        excluded_ids=owned_ids,
    )
    opportunities = build_direct_upgrade_opportunities(
        store_hitters=purchase_hitters,
        store_pitchers=purchase_pitchers,
        ruleset=owned_candidates.context.ruleset,
        baseline_solution=baseline,
        baseline_input=owned_input,
    )
    rows = build_direct_upgrade_rows(
        opportunities=opportunities,
        store_hitters=purchase_hitters,
        store_pitchers=purchase_pitchers,
        min_gain=request.min_gain,
        max_price=request.max_price,
        require_sell_order=request.require_sell_order,
    )

    summary = {
        "Baseline objective": f"{baseline.objective_value:.2f}",
        "Baseline solve time": f"{baseline.wall_time_seconds:.3f} s",
        "Store cards screened": str(len(purchase_hitters) + len(purchase_pitchers)),
        "Direct upgrades found": str(len(rows)),
        "Active sell order required": (
            "yes" if request.require_sell_order else "no"
        ),
        "Maximum price": (
            "-" if request.max_price is None else f"{request.max_price:,}"
        ),
    }
    if rows.empty or request.exact_results <= 0:
        return UpgradeComputation(
            hitter_roster=converted.hitter_roster,
            pitcher_roster=converted.pitcher_roster,
            hitter_upgrades=upgrade_rows_for_type(rows, "hitter"),
            pitcher_upgrades=upgrade_rows_for_type(rows, "pitcher"),
            summary=summary,
        )

    exact_candidate_ids = tuple(
        rows.head(request.exact_results)[CANDIDATE_ID_COLUMN]
    )
    exact_hitters = purchase_hitters.loc[
        purchase_hitters[CANDIDATE_ID_COLUMN].isin(exact_candidate_ids)
    ].copy()
    exact_pitchers = purchase_pitchers.loc[
        purchase_pitchers[CANDIDATE_ID_COLUMN].isin(exact_candidate_ids)
    ].copy()
    augmented_hitters = append_candidates(
        owned_candidates.eligible_hitters,
        exact_hitters,
    )
    augmented_pitchers = append_candidates(
        owned_candidates.eligible_pitchers,
        exact_pitchers,
    )
    augmented_pool = replace(
        owned_candidates,
        eligible_hitters=augmented_hitters,
        eligible_pitchers=augmented_pitchers,
    )
    augmented_matrices = augmented_pool.build_matrices()
    augmented_input = augmented_pool.build_solver_input(augmented_matrices)
    upgrades = enumerate_single_purchase_upgrades(
        solver_input=augmented_input,
        store_candidate_ids=exact_candidate_ids,
        baseline_solution=baseline,
        min_gain=0.01,
        max_results=len(exact_candidate_ids),
        settings=settings,
    )
    exact_rows = build_optimizer_upgrade_rows(
        upgrades=upgrades,
        baseline=baseline,
        solver_input=augmented_input,
        store_hitters=exact_hitters,
        store_pitchers=exact_pitchers,
    )
    rows = attach_exact_results(rows, exact_rows)
    summary["Exact candidates checked"] = str(len(exact_candidate_ids))
    summary["Exact improvements found"] = str(len(exact_rows))
    summary["Exact solve time"] = (
        f"{sum(upgrade.solution.wall_time_seconds for upgrade in upgrades):.3f} s"
    )
    return UpgradeComputation(
        hitter_roster=converted.hitter_roster,
        pitcher_roster=converted.pitcher_roster,
        hitter_upgrades=upgrade_rows_for_type(rows, "hitter"),
        pitcher_upgrades=upgrade_rows_for_type(rows, "pitcher"),
        summary=summary,
    )


DIRECT_UPGRADE_REPORT_COLUMNS = [
    CANDIDATE_ID_COLUMN,
    "type",
    "candidate",
    "candidate_tier",
    "candidate_value",
    "card_title",
    "is_clubhouse_card",
    "best_role",
    "current_player",
    "current_score",
    "candidate_score",
    "direct_score_gain",
    "estimated_objective_gain",
    "positive_opportunities",
    "purchase_price",
    "cost_per_gain",
    "sell_order_low",
    "buy_order_high",
    "last_10_price",
    "exact_objective_gain",
    "exact_removed_from_roster",
    "exact_other_owned_added",
    "exact_usage",
    "exact_assignment_changes",
    "exact_solver_status",
    "exact_solve_seconds",
]


EXACT_UPGRADE_COLUMNS = [
    CANDIDATE_ID_COLUMN,
    "type",
    "candidate",
    "candidate_tier",
    "candidate_value",
    "card_title",
    "is_clubhouse_card",
    "exact_objective_gain",
    "exact_removed_from_roster",
    "exact_other_owned_added",
    "exact_usage",
    "exact_assignment_changes",
    "estimated_price",
    "cost_per_gain",
    "sell_order_low",
    "buy_order_high",
    "last_10_price",
    "exact_solver_status",
    "exact_solve_seconds",
]


def build_direct_upgrade_rows(
    *,
    opportunities: pd.DataFrame,
    store_hitters: pd.DataFrame,
    store_pitchers: pd.DataFrame,
    min_gain: float,
    max_price: int | None,
    require_sell_order: bool,
) -> pd.DataFrame:
    if opportunities.empty:
        return pd.DataFrame(columns=DIRECT_UPGRADE_REPORT_COLUMNS)

    metadata = pd.concat(
        [store_hitters, store_pitchers],
        ignore_index=True,
        sort=False,
    ).set_index(CANDIDATE_ID_COLUMN)
    rows = []
    for candidate_id, candidate_opportunities in opportunities.groupby(
        CANDIDATE_ID_COLUMN,
        sort=False,
    ):
        ranked = candidate_opportunities.sort_values(
            "estimated_objective_gain",
            ascending=False,
        )
        best = ranked.iloc[0]
        if float(best["estimated_objective_gain"]) < min_gain:
            continue

        card = metadata.loc[candidate_id]
        sell_order = int(card.get("sell_order_low", 0) or 0)
        if require_sell_order and sell_order <= 0:
            continue
        estimated_price = estimate_purchase_price(card)
        purchase_price = sell_order if sell_order > 0 else estimated_price
        if max_price is not None and (
            purchase_price is None or purchase_price > max_price
        ):
            continue
        estimated_gain = float(best["estimated_objective_gain"])
        cost_per_gain = safe_cost_per_gain(purchase_price, estimated_gain)
        opportunity_text = "; ".join(
            (
                f"{row.role}: {row.current_player} "
                f"+{float(row.direct_score_gain):.2f}"
            )
            for row in ranked.itertuples(index=False)
            if float(row.estimated_objective_gain) >= min_gain
        )
        rows.append(
            {
                CANDIDATE_ID_COLUMN: candidate_id,
                "type": best["type"],
                "candidate": card.get("name", ""),
                "candidate_tier": card.get("pt_tier", ""),
                "candidate_value": int(card.get("card_value", 0) or 0),
                "card_title": card.get("card_title", ""),
                "is_clubhouse_card": bool(
                    card.get("is_clubhouse_card", False)
                ),
                "best_role": best["role"],
                "current_player": best["current_player"],
                "current_score": round(float(best["current_score"]), 2),
                "candidate_score": round(float(best["candidate_score"]), 2),
                "direct_score_gain": round(float(best["direct_score_gain"]), 2),
                "estimated_objective_gain": round(estimated_gain, 2),
                "positive_opportunities": opportunity_text,
                "purchase_price": purchase_price,
                "cost_per_gain": (
                    None if cost_per_gain is None else round(cost_per_gain, 2)
                ),
                "sell_order_low": sell_order,
                "buy_order_high": int(card.get("buy_order_high", 0) or 0),
                "last_10_price": int(card.get("last_10_price", 0) or 0),
            }
        )

    if not rows:
        return pd.DataFrame(columns=DIRECT_UPGRADE_REPORT_COLUMNS)
    result = pd.DataFrame(rows)
    for column in DIRECT_UPGRADE_REPORT_COLUMNS:
        if column not in result:
            result[column] = None
    return result[DIRECT_UPGRADE_REPORT_COLUMNS].sort_values(
        ["cost_per_gain", "purchase_price", "estimated_objective_gain"],
        ascending=[True, True, False],
        na_position="last",
    ).reset_index(drop=True)


def attach_exact_results(
    direct_rows: pd.DataFrame,
    exact_rows: pd.DataFrame,
) -> pd.DataFrame:
    if exact_rows.empty:
        return direct_rows
    exact_columns = [
        CANDIDATE_ID_COLUMN,
        "exact_objective_gain",
        "exact_removed_from_roster",
        "exact_other_owned_added",
        "exact_usage",
        "exact_assignment_changes",
        "exact_solver_status",
        "exact_solve_seconds",
    ]
    base = direct_rows.drop(columns=exact_columns[1:], errors="ignore")
    merged = base.merge(exact_rows[exact_columns], on=CANDIDATE_ID_COLUMN, how="left")
    return merged[DIRECT_UPGRADE_REPORT_COLUMNS]


def upgrade_rows_for_type(rows: pd.DataFrame, upgrade_type: str) -> pd.DataFrame:
    report_columns = [
        column
        for column in DIRECT_UPGRADE_REPORT_COLUMNS
        if column != CANDIDATE_ID_COLUMN
    ]
    report = (
        rows.loc[rows["type"].eq(upgrade_type), report_columns]
        .reset_index(drop=True)
        .copy()
    )
    return report.dropna(axis=1, how="all")


def append_candidates(
    owned: pd.DataFrame,
    store: pd.DataFrame,
) -> pd.DataFrame:
    if store.empty:
        return owned.copy()
    return pd.concat([owned, store], ignore_index=True, sort=False)


def available_store_cards(
    cards: pd.DataFrame,
    *,
    include_owned: bool,
    excluded_ids: set[str],
) -> pd.DataFrame:
    available = cards.copy()
    if not include_owned and "is_owned" in available.columns:
        available = available.loc[~available["is_owned"]].copy()
    return available.loc[
        ~available[CANDIDATE_ID_COLUMN].isin(excluded_ids)
    ].copy()


def require_feasible_upgrade_solution(
    solution: OptimizationSolution,
    label: str,
) -> None:
    if not solution.is_feasible or solution.objective_value is None:
        raise ValueError(
            f"Optimizer upgrade {label} did not find a feasible solution: "
            f"{solution.status}."
        )


def build_optimizer_upgrade_rows(
    *,
    upgrades: list[CandidateUpgradeSolution],
    baseline: OptimizationSolution,
    solver_input: SolverInput,
    store_hitters: pd.DataFrame,
    store_pitchers: pd.DataFrame,
) -> pd.DataFrame:
    if not upgrades:
        return pd.DataFrame(columns=EXACT_UPGRADE_COLUMNS)

    hitter_metadata = store_hitters.copy()
    hitter_metadata["upgrade_type"] = "hitter"
    pitcher_metadata = store_pitchers.copy()
    pitcher_metadata["upgrade_type"] = "pitcher"
    metadata = pd.concat(
        [hitter_metadata, pitcher_metadata],
        ignore_index=True,
        sort=False,
    ).set_index(CANDIDATE_ID_COLUMN)
    names = solver_input.candidates.set_index(CANDIDATE_ID_COLUMN)["name"]
    baseline_selected = set(
        baseline.selected_hitter_ids + baseline.selected_pitcher_ids
    )

    rows = []
    for upgrade in upgrades:
        row = metadata.loc[upgrade.candidate_id]
        solution = upgrade.solution
        selected = set(solution.selected_hitter_ids + solution.selected_pitcher_ids)
        removed_ids = sorted(baseline_selected - selected)
        other_added_ids = sorted(
            selected - baseline_selected - {upgrade.candidate_id}
        )
        removed_names = ", ".join(str(names[candidate_id]) for candidate_id in removed_ids)
        other_added_names = ", ".join(
            str(names[candidate_id]) for candidate_id in other_added_ids
        )
        estimated_price = estimate_purchase_price(row)
        cost_per_gain = safe_cost_per_gain(estimated_price, upgrade.objective_gain)
        rows.append(
            {
                CANDIDATE_ID_COLUMN: upgrade.candidate_id,
                "type": row["upgrade_type"],
                "candidate": row.get("name", names[upgrade.candidate_id]),
                "candidate_tier": row.get("pt_tier", ""),
                "candidate_value": int(row.get("card_value", 0) or 0),
                "card_title": row.get("card_title", ""),
                "is_clubhouse_card": bool(
                    row.get("is_clubhouse_card", False)
                ),
                "exact_objective_gain": round(upgrade.objective_gain, 2),
                "exact_removed_from_roster": removed_names,
                "exact_other_owned_added": other_added_names,
                "exact_usage": candidate_usage(
                    solution,
                    upgrade.candidate_id,
                    solver_input,
                ),
                "exact_assignment_changes": describe_assignment_changes(
                    baseline,
                    solution,
                    solver_input,
                ),
                "estimated_price": estimated_price,
                "cost_per_gain": (
                    None if cost_per_gain is None else round(cost_per_gain, 2)
                ),
                "sell_order_low": int(row.get("sell_order_low", 0) or 0),
                "buy_order_high": int(row.get("buy_order_high", 0) or 0),
                "last_10_price": int(row.get("last_10_price", 0) or 0),
                "exact_solver_status": solution.status,
                "exact_solve_seconds": round(solution.wall_time_seconds, 3),
            }
        )

    return pd.DataFrame(rows, columns=EXACT_UPGRADE_COLUMNS)


def candidate_usage(
    solution: OptimizationSolution,
    candidate_id: str,
    solver_input: SolverInput,
) -> str:
    usage = []
    hitter_rows = solution.hitter_assignments.loc[
        solution.hitter_assignments[CANDIDATE_ID_COLUMN].eq(candidate_id)
    ]
    for row in hitter_rows.itertuples(index=False):
        usage.append(f"{split_label(row.split)} {row.position}")

    bench_rows = solution.bench_assignments.loc[
        solution.bench_assignments[CANDIDATE_ID_COLUMN].eq(candidate_id)
    ]
    for row in bench_rows.itertuples(index=False):
        usage.append(f"{split_label(row.split)} bench")

    pitcher_rows = solution.pitcher_assignments.loc[
        solution.pitcher_assignments[CANDIDATE_ID_COLUMN].eq(candidate_id)
    ]
    group_labels = solver_input.pitcher_group_requirements.set_index("group_key")[
        "group_label"
    ]
    for row in pitcher_rows.itertuples(index=False):
        usage.append(str(group_labels[row.group_key]))

    return "; ".join(usage)


def describe_assignment_changes(
    baseline: OptimizationSolution,
    upgraded: OptimizationSolution,
    solver_input: SolverInput,
) -> str:
    names = solver_input.candidates.set_index(CANDIDATE_ID_COLUMN)["name"]
    old_lineup = assignment_name_map(baseline.hitter_assignments, "slot_key", names)
    new_lineup = assignment_name_map(upgraded.hitter_assignments, "slot_key", names)
    slot_details = solver_input.lineup_requirements.set_index("slot_key")
    changes = []
    for slot_key in slot_details.index:
        old_name = old_lineup.get(slot_key, "-")
        new_name = new_lineup.get(slot_key, "-")
        if old_name == new_name:
            continue
        detail = slot_details.loc[slot_key]
        changes.append(
            f"{split_label(detail['split'])} {detail['position']}: "
            f"{old_name} -> {new_name}"
        )

    old_bench = bench_name_sets(baseline.bench_assignments, names)
    new_bench = bench_name_sets(upgraded.bench_assignments, names)
    for split in solver_input.lineup_split_weights:
        removed = sorted(old_bench.get(split, set()) - new_bench.get(split, set()))
        added = sorted(new_bench.get(split, set()) - old_bench.get(split, set()))
        if removed or added:
            changes.append(
                f"{split_label(split)} bench: "
                f"{', '.join(removed) or '-'} -> {', '.join(added) or '-'}"
            )

    old_pitchers = assignment_group_sets(baseline.pitcher_assignments, names)
    new_pitchers = assignment_group_sets(upgraded.pitcher_assignments, names)
    group_labels = solver_input.pitcher_group_requirements.set_index("group_key")[
        "group_label"
    ]
    for group_key in group_labels.index:
        removed = sorted(old_pitchers.get(group_key, set()) - new_pitchers.get(group_key, set()))
        added = sorted(new_pitchers.get(group_key, set()) - old_pitchers.get(group_key, set()))
        if removed or added:
            changes.append(
                f"{group_labels[group_key]}: "
                f"{', '.join(removed) or '-'} -> {', '.join(added) or '-'}"
            )

    return "; ".join(changes)


def assignment_name_map(
    assignments: pd.DataFrame,
    key_column: str,
    names: pd.Series,
) -> dict[str, str]:
    return {
        str(row[key_column]): str(names[row[CANDIDATE_ID_COLUMN]])
        for _, row in assignments.iterrows()
    }


def assignment_group_sets(
    assignments: pd.DataFrame,
    names: pd.Series,
) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for row in assignments.itertuples(index=False):
        groups.setdefault(row.group_key, set()).add(
            str(names[getattr(row, CANDIDATE_ID_COLUMN)])
        )
    return groups


def bench_name_sets(
    assignments: pd.DataFrame,
    names: pd.Series,
) -> dict[str, set[str]]:
    benches: dict[str, set[str]] = {}
    for row in assignments.itertuples(index=False):
        benches.setdefault(row.split, set()).add(
            str(names[getattr(row, CANDIDATE_ID_COLUMN)])
        )
    return benches


def split_label(split: str) -> str:
    return "vs RHP" if split == "vs_rhp" else "vs LHP"


def resolve_upgrade_build_method(
    cfg: dict[str, Any],
    request: StoreUpgradeRequest,
) -> Literal["greedy", "optimizer"]:
    value = request.build_method
    if value is None and request.preset:
        value = (
            cfg.get("tournament_presets", {})
            .get(request.preset, {})
            .get("build_method")
        )
    value = value or "greedy"
    if value not in {"greedy", "optimizer"}:
        raise ValueError(
            f"Unknown upgrade build method '{value}'. Expected greedy or optimizer."
        )
    return value


def build_ruleset(cfg: dict[str, Any], request: StoreUpgradeRequest) -> Ruleset:
    if request.preset:
        return build_ruleset_from_tournament_preset(
            cfg,
            preset_name=request.preset,
            overrides=request.overrides,
        )

    return build_ruleset_from_base_profile(
        cfg,
        base_profile_name=request.base_profile,
        overrides=request.overrides,
    )


def build_output_name(ruleset: Ruleset) -> str:
    safe_name = ruleset.name.replace(" ", "_").replace("/", "_")
    return str(Path("outputs") / f"store_upgrades_{safe_name}.html")
