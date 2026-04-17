from ootp_opt.config import load_config
from ootp_opt.roster.rules import load_roster_profile
from ootp_opt.roster.eligibility import filter_eligible_pitchers
from ootp_opt.roster.builder import build_pitcher_roster
from ootp_opt.services.rating_service import rate_cards_service


cfg = load_config("config.toml")
ruleset = load_roster_profile(cfg, "standard_pt")

pitchers_df = rate_cards_service(
    input_path=cfg["paths"]["pitchers_csv"],
    profile="pitchers",
    config=cfg,
)

eligible_pitchers = filter_eligible_pitchers(pitchers_df, ruleset)
pitcher_roster = build_pitcher_roster(eligible_pitchers, ruleset)

print("\n=== ROTATION ===")
print(pitcher_roster.rotation[["name", "starter_score_overall"]])

print("\n=== BULLPEN ===")
print(pitcher_roster.bullpen[["name", "reliever_score_overall"]])

print("\n=== LEFTY SPECIALIST ===")
print(pitcher_roster.lefty_specialist[["name", "reliever_score_vs_lhb"]])

print("\n=== LONG MAN ===")
print(pitcher_roster.long_man[["name", "starter_score_overall"]])
