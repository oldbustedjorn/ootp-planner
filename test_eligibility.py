from ootp_opt.config import load_config
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.roster.eligibility import filter_eligible_hitters, filter_eligible_pitchers
from ootp_opt.services.rating_service import rate_cards_service

cfg = load_config("config.toml")

ruleset = build_ruleset_from_base_profile(
    cfg,
    "playoff_pt",
    overrides={
        "tier_max": "diamond",
        "live_mode": "non_live",
        "card_value_max": 89,
        "card_year_max": 1930,
    },
)

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

print("\n=== RULESET FILTERS ===")
print(f"tier_min: {ruleset.tier_min}")
print(f"tier_max: {ruleset.tier_max}")
print(f"live_mode: {ruleset.live_mode}")
print(f"card_value_min: {ruleset.card_value_min}")
print(f"card_value_max: {ruleset.card_value_max}")
print(f"card_year_min: {ruleset.card_year_min}")
print(f"card_year_max: {ruleset.card_year_max}")

print("\n=== COUNTS ===")
print(f"Hitters:  {len(hitters_df)} -> {len(eligible_hitters)}")
print(f"Pitchers: {len(pitchers_df)} -> {len(eligible_pitchers)}")

print("\n=== ELIGIBLE HITTER SAMPLE ===")
print(
    eligible_hitters[
        ["name", "pt_tier", "card_value", "pt_type", "pt_year"]
    ].head(20)
)

print("\n=== ELIGIBLE PITCHER SAMPLE ===")
print(
    eligible_pitchers[
        ["name", "pt_tier", "card_value", "pt_type", "pt_year"]
    ].head(20)
)