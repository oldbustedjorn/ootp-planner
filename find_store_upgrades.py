from __future__ import annotations

import argparse
from typing import Any

from ootp_opt.config import load_config
from ootp_opt.domain.simulation_context import (
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
from ootp_opt.roster.rules import (
    Ruleset,
    build_ruleset_from_base_profile,
    build_ruleset_from_tournament_preset,
)
from ootp_opt.roster.upgrade_finder import find_hitter_upgrades, find_pitcher_upgrades
from ootp_opt.roster.upgrade_html_export import export_upgrade_html
from ootp_opt.services.rating_service import rate_hitters_df, rate_pitchers_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find store upgrades for a roster ruleset."
    )

    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--base-profile", default=None)
    parser.add_argument("--preset", default=None)

    parser.add_argument("--tier-min", default=None)
    parser.add_argument("--tier-max", default=None)
    parser.add_argument("--card-value-min", type=int, default=None)
    parser.add_argument("--card-value-max", type=int, default=None)

    parser.add_argument(
        "--live-mode",
        choices=["all", "live", "non_live"],
        default=None,
    )
    parser.add_argument("--card-types", default=None)
    parser.add_argument("--exclude-card-types", default=None)
    parser.add_argument("--card-year-min", type=int, default=None)
    parser.add_argument("--card-year-max", type=int, default=None)

    parser.add_argument("--simulation-year", type=int, default=None)
    parser.add_argument("--ballpark", default=None)
    parser.add_argument("--ballpark-year", type=int, default=None)
    parser.add_argument("--park-ba-lh", type=float, default=None)
    parser.add_argument("--park-ba-rh", type=float, default=None)
    parser.add_argument("--park-hr-lh", type=float, default=None)
    parser.add_argument("--park-hr-rh", type=float, default=None)
    parser.add_argument("--park-2b", type=float, default=None)
    parser.add_argument("--park-3b", type=float, default=None)

    parser.add_argument(
        "--min-gain",
        type=float,
        default=5.0,
        help="Minimum score gain required for an upgrade row.",
    )
    parser.add_argument(
        "--include-owned",
        action="store_true",
        help="Include already-owned store cards in upgrade candidates.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Number of top rows to print for hitters and pitchers.",
    )
    parser.add_argument("--html-output", default=None)

    return parser.parse_args()


def build_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}

    for field in [
        "tier_min",
        "tier_max",
        "card_value_min",
        "card_value_max",
        "live_mode",
        "card_types",
        "exclude_card_types",
        "card_year_min",
        "card_year_max",
        "simulation_year",
        "ballpark",
        "ballpark_year",
    ]:
        value = getattr(args, field)
        if value is not None:
            if field == "card_types":
                overrides["allowed_card_types"] = split_csv_arg(value)
            elif field == "exclude_card_types":
                overrides["excluded_card_types"] = split_csv_arg(value)
            else:
                overrides[field] = value

    custom_park_factors = build_custom_park_factor_overrides(args)
    if custom_park_factors:
        overrides["custom_park_factors"] = custom_park_factors

    return overrides


def split_csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_custom_park_factor_overrides(args: argparse.Namespace) -> dict[str, float]:
    fields = {
        "ba_lh": args.park_ba_lh,
        "ba_rh": args.park_ba_rh,
        "hr_lh": args.park_hr_lh,
        "hr_rh": args.park_hr_rh,
        "doubles_overall": args.park_2b,
        "triples_overall": args.park_3b,
    }

    return {key: value for key, value in fields.items() if value is not None}


def build_ruleset(
    cfg: dict[str, Any],
    args: argparse.Namespace,
    overrides: dict[str, Any],
) -> Ruleset:
    if args.preset:
        return build_ruleset_from_tournament_preset(
            cfg,
            preset_name=args.preset,
            overrides=overrides,
        )

    return build_ruleset_from_base_profile(
        cfg,
        base_profile_name=args.base_profile,
        overrides=overrides,
    )


def build_output_name(ruleset: Ruleset) -> str:
    safe_name = ruleset.name.replace(" ", "_").replace("/", "_")
    return f"outputs/store_upgrades_{safe_name}.html"


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    overrides = build_overrides(args)
    ruleset = build_ruleset(cfg, args, overrides)

    simulation_context = resolve_simulation_context(
        simulation_year=ruleset.simulation_year,
        ballpark=ruleset.ballpark,
        ballpark_year=ruleset.ballpark_year,
        custom_park_factors=ruleset.custom_park_factors,
    )
    scoring_cfg = apply_simulation_context_to_config(cfg, simulation_context)

    print("\n=== STORE UPGRADE RULESET ===")
    print(f"Ruleset: {ruleset.name}")
    print(f"Tier min/max: {ruleset.tier_min} / {ruleset.tier_max}")
    print(f"Card value min/max: {ruleset.card_value_min} / {ruleset.card_value_max}")
    print(f"Live mode: {ruleset.live_mode}")
    print(f"Allowed card types: {ruleset.allowed_card_types or '-'}")
    print(f"Excluded card types: {ruleset.excluded_card_types or '-'}")
    print(f"Card year min/max: {ruleset.card_year_min} / {ruleset.card_year_max}")
    print(f"Min gain: {args.min_gain}")
    print(f"Include owned store cards: {args.include_owned}")

    print("\n=== SIMULATION CONTEXT ===")
    for label, value in simulation_context.summary_rows():
        print(f"{label}: {value}")

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

    if args.include_owned:
        eligible_store_hitters = eligible_store_hitters.copy()
        eligible_store_pitchers = eligible_store_pitchers.copy()
        eligible_store_hitters["is_owned"] = False
        eligible_store_pitchers["is_owned"] = False

    hitter_upgrades = find_hitter_upgrades(
        hitter_roster,
        eligible_store_hitters,
        min_gain=args.min_gain,
    )
    pitcher_upgrades = find_pitcher_upgrades(
        pitcher_roster,
        eligible_store_pitchers,
        min_gain=args.min_gain,
    )

    print("\n=== STORE ELIGIBILITY SUMMARY ===")
    print(f"Owned hitters eligible: {len(eligible_hitters)}")
    print(f"Owned pitchers eligible: {len(eligible_pitchers)}")
    print(f"Store hitters eligible: {len(eligible_store_hitters)}")
    print(f"Store pitchers eligible: {len(eligible_store_pitchers)}")

    print("\n=== TOP HITTER UPGRADES ===")
    print_top_rows(hitter_upgrades, args.top)

    print("\n=== TOP PITCHER UPGRADES ===")
    print_top_rows(pitcher_upgrades, args.top)

    html_output = args.html_output or build_output_name(ruleset)
    export_upgrade_html(
        path=html_output,
        hitter_upgrades=hitter_upgrades,
        pitcher_upgrades=pitcher_upgrades,
        title=f"OOTP Store Upgrades - {ruleset.name}",
    )

    print(f"\nHTML upgrade report written to: {html_output}")


def print_top_rows(df, top: int) -> None:
    if df.empty:
        print("No upgrades found.")
        return

    print(df.head(top).to_string(index=False))


if __name__ == "__main__":
    main()
