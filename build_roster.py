from __future__ import annotations

import argparse
from typing import Any

from ootp_opt.config import load_config
from ootp_opt.roster.builder import (
    build_hitter_roster,
    build_pitcher_roster,
    get_player_covered_positions,
)
from ootp_opt.roster.eligibility import (
    filter_eligible_hitters,
    filter_eligible_pitchers,
)
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.services.rating_service import rate_cards_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an OOTP roster from a ruleset.")

    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--base-profile", default=None)

    parser.add_argument("--tier-min", default=None)
    parser.add_argument("--tier-max", default=None)

    parser.add_argument("--card-value-min", type=int, default=None)
    parser.add_argument("--card-value-max", type=int, default=None)

    parser.add_argument(
        "--live-mode",
        choices=["all", "live", "non_live"],
        default=None,
    )

    parser.add_argument("--card-year-min", type=int, default=None)
    parser.add_argument("--card-year-max", type=int, default=None)

    return parser.parse_args()


def build_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}

    for field in [
        "tier_min",
        "tier_max",
        "card_value_min",
        "card_value_max",
        "live_mode",
        "card_year_min",
        "card_year_max",
    ]:
        value = getattr(args, field)
        if value is not None:
            overrides[field] = value

    return overrides


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    overrides = build_overrides(args)

    ruleset = build_ruleset_from_base_profile(
        cfg,
        base_profile_name=args.base_profile,
        overrides=overrides,
    )

    print("\n=== BUILD RULESET ===")
    print(f"Base profile: {ruleset.name}")
    print(f"Hitters/Pitchers: {ruleset.hitter_count}/{ruleset.pitcher_count}")
    print(f"DH enabled: {ruleset.dh_enabled}")
    print(f"Tier min/max: {ruleset.tier_min} / {ruleset.tier_max}")
    print(f"Card value min/max: {ruleset.card_value_min} / {ruleset.card_value_max}")
    print(f"Live mode: {ruleset.live_mode}")
    print(f"Card year min/max: {ruleset.card_year_min} / {ruleset.card_year_max}")

    hitters_df = rate_cards_service(
        input_path=cfg["paths"]["hitters_csv"],
        profile="hitters",
        config=cfg,
    )

    pitchers_df = rate_cards_service(
        input_path=cfg["paths"]["pitchers_csv"],
        profile="pitchers",
        config=cfg,
    )

    eligible_hitters = filter_eligible_hitters(hitters_df, ruleset)
    eligible_pitchers = filter_eligible_pitchers(pitchers_df, ruleset)

    print("\n=== ELIGIBILITY SUMMARY ===")
    print(f"Hitters:  {len(hitters_df)} -> {len(eligible_hitters)}")
    print(f"Pitchers: {len(pitchers_df)} -> {len(eligible_pitchers)}")

    if eligible_hitters.empty:
        raise ValueError("No eligible hitters after applying filters.")

    if eligible_pitchers.empty:
        raise ValueError("No eligible pitchers after applying filters.")

    hitter_roster = build_hitter_roster(eligible_hitters, ruleset)
    pitcher_roster = build_pitcher_roster(eligible_pitchers, ruleset)

    print("\n=== STARTERS ===")
    for position, row in hitter_roster.starters_by_position.items():
        score_col = (
            "batting_score_overall" if position == "DH" else f"score_{position}_overall"
        )
        print(f"{position:>2}  {row['name']:<25}  {row[score_col]:.2f}")

    print("\n=== BENCH ===")
    for _, row in hitter_roster.bench_players.iterrows():
        covered = sorted(get_player_covered_positions(row, ruleset))
        print(
            f"{row['name']:<25}  bat={row['batting_score_overall']:.2f}  covers={covered}"
        )

    print("\n=== ROTATION ===")
    print(
        pitcher_roster.rotation[["name", "starter_score_overall"]].to_string(
            index=False
        )
    )

    print("\n=== BULLPEN ===")
    print(
        pitcher_roster.bullpen[["name", "reliever_score_overall"]].to_string(
            index=False
        )
    )

    print("\n=== LEFTY SPECIALIST ===")
    print(
        pitcher_roster.lefty_specialist[["name", "reliever_score_vs_lhb"]].to_string(
            index=False
        )
    )

    print("\n=== LONG MAN ===")
    print(
        pitcher_roster.long_man[["name", "starter_score_overall"]].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()
