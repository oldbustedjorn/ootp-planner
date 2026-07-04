from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ootp_opt.config import load_config
from ootp_opt.domain.simulation_context import (
    SimulationContext,
    apply_simulation_context_to_config,
    resolve_simulation_context,
)
from ootp_opt.ingest.pt_hitters import load_pt_cards_csv
from ootp_opt.ingest.pt_pitchers import load_pt_pitchers_csv
from ootp_opt.ingest.pt_store import load_pt_store_hitters_pitchers
from ootp_opt.roster.builder import (
    build_hitter_roster,
    build_pitcher_roster,
    validate_no_duplicate_players,
)
from ootp_opt.roster.eligibility import filter_eligible_hitters, filter_eligible_pitchers
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import (
    Ruleset,
    build_ruleset_from_base_profile,
    build_ruleset_from_tournament_preset,
)
from ootp_opt.roster.upgrade_finder import find_hitter_upgrades, find_pitcher_upgrades
from ootp_opt.roster.upgrade_html_export import export_upgrade_html
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
    ruleset: Ruleset
    simulation_context: SimulationContext
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster
    hitter_upgrades: Any
    pitcher_upgrades: Any
    eligibility_summary: dict[str, int]
    html_output: str


def find_store_upgrades(request: StoreUpgradeRequest) -> StoreUpgradeResult:
    cfg = load_config(request.config_path)
    ruleset = build_ruleset(cfg, request)

    simulation_context = resolve_simulation_context(
        simulation_year=ruleset.simulation_year,
        ballpark=ruleset.ballpark,
        ballpark_year=ruleset.ballpark_year,
        custom_park_factors=ruleset.custom_park_factors,
    )
    scoring_cfg = apply_simulation_context_to_config(cfg, simulation_context)

    hitters_df = load_pt_cards_csv(cfg["paths"]["hitters_csv"])
    pitchers_df = load_pt_pitchers_csv(cfg["paths"]["pitchers_csv"])

    scored_hitters = rate_hitters_df(hitters_df, scoring_cfg)
    scored_pitchers = rate_pitchers_df(pitchers_df, scoring_cfg)

    eligible_hitters = filter_eligible_hitters(scored_hitters, ruleset)
    eligible_pitchers = filter_eligible_pitchers(scored_pitchers, ruleset)

    if eligible_hitters.empty:
        raise ValueError("No eligible hitters after applying filters.")
    if eligible_pitchers.empty:
        raise ValueError("No eligible pitchers after applying filters.")

    hitter_roster = build_hitter_roster(eligible_hitters, ruleset)
    pitcher_roster = build_pitcher_roster(eligible_pitchers, ruleset)
    validate_no_duplicate_players(hitter_roster, pitcher_roster)

    store_hitters, store_pitchers = load_pt_store_hitters_pitchers(
        cfg["paths"]["store_csv"]
    )

    scored_store_hitters = rate_hitters_df(store_hitters, scoring_cfg)
    scored_store_pitchers = rate_pitchers_df(store_pitchers, scoring_cfg)

    eligible_store_hitters = filter_eligible_hitters(scored_store_hitters, ruleset)
    eligible_store_pitchers = filter_eligible_pitchers(scored_store_pitchers, ruleset)

    if request.include_owned:
        eligible_store_hitters = eligible_store_hitters.copy()
        eligible_store_pitchers = eligible_store_pitchers.copy()
        eligible_store_hitters["is_owned"] = False
        eligible_store_pitchers["is_owned"] = False

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
    )

    return StoreUpgradeResult(
        ruleset=ruleset,
        simulation_context=simulation_context,
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
