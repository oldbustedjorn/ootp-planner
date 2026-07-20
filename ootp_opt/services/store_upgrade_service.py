from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ootp_opt.config import load_config
from ootp_opt.domain.simulation_context import SimulationContext
from ootp_opt.domain.scoring_environment import ScoringEnvironment
from ootp_opt.ingest.pt_hitters import load_pt_cards_csv
from ootp_opt.ingest.pt_pitchers import load_pt_pitchers_csv
from ootp_opt.ingest.pt_store import load_pt_store_hitters_pitchers
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
from ootp_opt.roster.upgrade_finder import find_hitter_upgrades, find_pitcher_upgrades
from ootp_opt.roster.upgrade_html_export import export_upgrade_html
from ootp_opt.services.candidate_service import (
    BuildContext,
    CandidatePool,
    build_candidate_pool,
    resolve_build_context,
)
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


def find_store_upgrades(request: StoreUpgradeRequest) -> StoreUpgradeResult:
    cfg = load_config(request.config_path)
    ruleset = build_ruleset(cfg, request)
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

    hitter_roster = build_hitter_roster(eligible_hitters, ruleset)
    pitcher_roster = build_pitcher_roster(
        eligible_pitchers,
        ruleset,
        used_player_names=selected_hitter_roster_keys(hitter_roster),
    )
    validate_no_duplicate_players(hitter_roster, pitcher_roster)

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

    hitter_upgrades = find_hitter_upgrades(
        hitter_roster,
        eligible_store_hitters,
        min_gain=request.min_gain,
    )
    pitcher_upgrades = find_pitcher_upgrades(
        pitcher_roster,
        eligible_store_pitchers,
        min_gain=request.min_gain,
    )

    html_output = request.html_output or build_output_name(ruleset)
    export_upgrade_html(
        path=html_output,
        hitter_upgrades=hitter_upgrades,
        pitcher_upgrades=pitcher_upgrades,
        title=f"OOTP Store Upgrades - {ruleset.name}",
        summary_rows=[
            ("Ruleset", ruleset.name),
            ("Scoring environment", scoring_environment.name),
            ("Scoring environment source", scoring_environment.source),
            ("Simulation year", simulation_context.simulation_year or "-"),
            ("Ballpark", simulation_context.park.park if simulation_context.park else "-"),
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
    )


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
