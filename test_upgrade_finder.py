from ootp_opt.config import load_config

from ootp_opt.ingest.pt_hitters import load_pt_cards_csv
from ootp_opt.ingest.pt_pitchers import load_pt_pitchers_csv
from ootp_opt.ingest.pt_store import load_pt_store_hitters_pitchers

from ootp_opt.services.rating_service import (
    rate_hitters_df,
    rate_pitchers_df,
)

from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.roster.builder import (
    build_hitter_roster,
    build_pitcher_roster,
)

from ootp_opt.roster.eligibility import filter_eligible_players

from ootp_opt.roster.upgrade_finder import (
    find_hitter_upgrades,
    find_pitcher_upgrades,
)

cfg = load_config("config.toml")

ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

# Current owned inventory
hitters_df = load_pt_cards_csv(cfg["paths"]["hitters_csv"])
pitchers_df = load_pt_pitchers_csv(cfg["paths"]["pitchers_csv"])

scored_hitters = rate_hitters_df(hitters_df, cfg)
scored_pitchers = rate_pitchers_df(pitchers_df, cfg)

eligible_hitters = filter_eligible_players(
    scored_hitters,
    ruleset,
)

eligible_pitchers = filter_eligible_players(
    scored_pitchers,
    ruleset,
)

hitter_roster = build_hitter_roster(
    eligible_hitters,
    ruleset,
)

pitcher_roster = build_pitcher_roster(
    eligible_pitchers,
    ruleset,
)

# Store cards
store_hitters, store_pitchers = load_pt_store_hitters_pitchers(
    cfg["paths"]["store_csv"]
)

scored_store_hitters = rate_hitters_df(store_hitters, cfg)
scored_store_pitchers = rate_pitchers_df(store_pitchers, cfg)

hitter_upgrades = find_hitter_upgrades(
    hitter_roster,
    scored_store_hitters,
    min_gain=5.0,
)

pitcher_upgrades = find_pitcher_upgrades(
    pitcher_roster,
    scored_store_pitchers,
    min_gain=5.0,
)

print("\n=== TOP HITTER UPGRADES ===")
print(hitter_upgrades.head(25).to_string(index=False))

print("\n=== TOP PITCHER UPGRADES ===")
print(pitcher_upgrades.head(25).to_string(index=False))
