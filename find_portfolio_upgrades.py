from __future__ import annotations

import argparse

from ootp_opt.services.portfolio_upgrade_service import (
    PortfolioUpgradeRequest,
    find_portfolio_upgrades,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find and aggregate upgrades across all active roster plans."
    )
    parser.add_argument("--config", default="config.toml")
    parser.add_argument(
        "--output", default="outputs/all_rosters_upgrade_portfolio.html"
    )
    parser.add_argument(
        "--details-directory", default="outputs/upgrade_portfolio_details"
    )
    parser.add_argument("--min-gain", type=float, default=0.01)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--plan-park-year",
        action="append",
        default=[],
        metavar="PLAN=YEAR",
        help="Apply a run-only park-year override to one roster plan.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan_overrides = {}
    for value in args.plan_park_year:
        plan, separator, year = value.partition("=")
        if not separator:
            raise ValueError("--plan-park-year must use PLAN=YEAR.")
        plan_overrides[plan] = {"ballpark_year": int(year)}
    result = find_portfolio_upgrades(
        PortfolioUpgradeRequest(
            config_path=args.config,
            output_path=args.output,
            details_directory=args.details_directory,
            min_gain=args.min_gain,
            top_per_type=args.top,
            plan_overrides=plan_overrides,
        ),
        progress=lambda message: print(message, flush=True),
    )
    print()
    print(f"Completed rosters: {len(result.completed_rosters)}")
    print(f"Failed rosters: {len(result.failed_rosters)}")
    print(f"Report: {result.output_path}")


if __name__ == "__main__":
    main()
