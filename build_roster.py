from __future__ import annotations

import argparse
from typing import Any

from ootp_opt.services.roster_build_service import (
    RosterBuildRequest,
    build_roster,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an OOTP roster from a ruleset.")

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

    parser.add_argument(
        "--card-types",
        default=None,
        help="Comma-separated pt_type allow-list, matched case-insensitively.",
    )

    parser.add_argument(
        "--exclude-card-types",
        default=None,
        help="Comma-separated pt_type block-list, matched case-insensitively.",
    )

    parser.add_argument(
        "--dh-enabled",
        choices=["true", "false"],
        default=None,
        help="Override DH setting for the roster build.",
    )

    parser.add_argument("--card-year-min", type=int, default=None)
    parser.add_argument("--card-year-max", type=int, default=None)

    parser.add_argument(
        "--simulation-year",
        type=int,
        default=None,
        help="Simulation era year used for environment-adjusted scoring.",
    )

    parser.add_argument(
        "--ballpark",
        default=None,
        help="Ballpark name used for environment-adjusted scoring.",
    )

    parser.add_argument(
        "--ballpark-year",
        type=int,
        default=None,
        help="Park-factor year. Defaults to simulation year when omitted.",
    )

    parser.add_argument("--park-ba-lh", type=float, default=None)
    parser.add_argument("--park-ba-rh", type=float, default=None)
    parser.add_argument("--park-hr-lh", type=float, default=None)
    parser.add_argument("--park-hr-rh", type=float, default=None)
    parser.add_argument("--park-2b", type=float, default=None)
    parser.add_argument("--park-3b", type=float, default=None)

    parser.add_argument(
        "--point-cap-total",
        type=int,
        default=None,
        help="Override total roster card-value cap.",
    )

    parser.add_argument(
        "--repair-cap",
        action="store_true",
        help="Ignored; cap repair runs whenever a point cap is configured.",
    )

    parser.add_argument(
        "--variant-limit",
        type=int,
        default=None,
        help="Maximum allowed variant cards on the final roster.",
    )

    parser.add_argument("--html-output", default=None)

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print extra diagnostic output.",
    )

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
        "point_cap_total",
        "variant_limit",
    ]:
        value = getattr(args, field)
        if value is not None:
            if field == "card_types":
                overrides["allowed_card_types"] = split_csv_arg(value)
            elif field == "exclude_card_types":
                overrides["excluded_card_types"] = split_csv_arg(value)
            else:
                overrides[field] = value

    if args.dh_enabled is not None:
        overrides["dh_enabled"] = args.dh_enabled.lower() == "true"

    custom_park_factors = build_custom_park_factor_overrides(args)
    if custom_park_factors:
        overrides["custom_park_factors"] = custom_park_factors

    return overrides


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


def split_csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def print_report_sections(report_sections: list[tuple[str, str]]) -> None:
    for title, text in report_sections:
        print(f"\n=== {title} ===")
        if text:
            print(text)


def main() -> None:
    args = parse_args()
    result = build_roster(
        RosterBuildRequest(
            config_path=args.config,
            base_profile=args.base_profile,
            preset=args.preset,
            overrides=build_overrides(args),
            html_output=args.html_output,
            debug=args.debug,
        )
    )
    print_report_sections(result.report_sections)


if __name__ == "__main__":
    main()
