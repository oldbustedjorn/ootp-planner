from ootp_opt.config import load_config
from ootp_opt.ingest.pt_store import load_pt_store_hitters_pitchers
from ootp_opt.services.rating_service import rate_hitters_df, rate_pitchers_df

cfg = load_config("config.toml")
store_path = cfg["paths"]["store_csv"]

store_hitters, store_pitchers = load_pt_store_hitters_pitchers(store_path)

scored_hitters = rate_hitters_df(store_hitters, cfg)
scored_pitchers = rate_pitchers_df(store_pitchers, cfg)

print("\n=== STORE SCORING SUMMARY ===")
print(f"Hitters:  {len(store_hitters)} -> {len(scored_hitters)}")
print(f"Pitchers: {len(store_pitchers)} -> {len(scored_pitchers)}")

print("\n=== HITTER SCORE COLUMNS CHECK ===")
hitter_cols = [
    "name",
    "pt_tier",
    "card_value",
    "batting_score_overall",
    "batting_score_vs_lhp",
    "batting_score_vs_rhp",
    "score_C_overall",
    "score_SS_overall",
    "score_CF_overall",
    "offensive_baserunning_bonus",
    "power",
    "eye",
    "avoid_k",
    "babip",
    "gap_power",
    "speed",
    "baserunning",
]
print(scored_hitters[hitter_cols].head(10).to_string(index=False))

print("\n=== PITCHER SCORE COLUMNS CHECK ===")
pitcher_cols = [
    "name",
    "pt_tier",
    "card_value",
    "starter_score_overall",
    "reliever_score_overall",
    "reliever_score_vs_lhb",
]
print(scored_pitchers[pitcher_cols].head(10).to_string(index=False))
