from __future__ import annotations

import argparse
from typing import Any

from ootp_opt.services.store_upgrade_service import (
    StoreUpgradeRequest,
    find_store_upgrades,
)


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
    parser.add_argument("--scoring-environment", default=None)
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
        "scoring_environment",
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


def main() -> None:
    args = parse_args()
    overrides = build_overrides(args)
    result = find_store_upgrades(
        StoreUpgradeRequest(
            config_path=args.config,
            base_profile=args.base_profile,
            preset=args.preset,
            overrides=overrides,
            min_gain=args.min_gain,
            include_owned=args.include_owned,
            html_output=args.html_output,
        )
    )
    ruleset = result.ruleset

    print("\n=== STORE UPGRADE RULESET ===")
    print(f"Ruleset: {ruleset.name}")
    print(f"Tier min/max: {ruleset.tier_min} / {ruleset.tier_max}")
    print(f"Card value min/max: {ruleset.card_value_min} / {ruleset.card_value_max}")
    print(f"Live mode: {ruleset.live_mode}")
    print(f"Allowed card types: {ruleset.allowed_card_types or '-'}")
    print(f"Excluded card types: {ruleset.excluded_card_types or '-'}")
    print(f"Card year min/max: {ruleset.card_year_min} / {ruleset.card_year_max}")
    print(f"Scoring environment: {result.scoring_environment.name}")
    print(f"Min gain: {args.min_gain}")
    print(f"Include owned store cards: {args.include_owned}")

    print("\n=== SIMULATION CONTEXT ===")
    for label, value in result.simulation_context.summary_rows():
        print(f"{label}: {value}")

    print("\n=== SCORING ENVIRONMENT ===")
    for label, value in result.scoring_environment.summary_rows():
        print(f"{label}: {value}")

    print("\n=== STORE ELIGIBILITY SUMMARY ===")
    print(f"Owned hitters eligible: {result.eligibility_summary['owned_hitters_eligible']}")
    print(f"Owned pitchers eligible: {result.eligibility_summary['owned_pitchers_eligible']}")
    print(f"Store hitters eligible: {result.eligibility_summary['store_hitters_eligible']}")
    print(f"Store pitchers eligible: {result.eligibility_summary['store_pitchers_eligible']}")

    print("\n=== TOP HITTER UPGRADES ===")
    print_top_rows(result.hitter_upgrades, args.top)

    print("\n=== TOP PITCHER UPGRADES ===")
    print_top_rows(result.pitcher_upgrades, args.top)

    print(f"\nHTML upgrade report written to: {result.html_output}")


def print_top_rows(df, top: int) -> None:
    if df.empty:
        print("No upgrades found.")
        return

    print(df.head(top).to_string(index=False))


if __name__ == "__main__":
    main()
