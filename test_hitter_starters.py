from ootp_opt.config import load_config
from ootp_opt.roster.rules import load_roster_profile
from ootp_opt.roster.eligibility import filter_eligible_hitters
from ootp_opt.services.rating_service import rate_cards_service
from ootp_opt.roster.builder import build_hitter_roster, get_player_covered_positions


cfg = load_config("config.toml")
ruleset = load_roster_profile(cfg, "standard_pt")

hitters_df = rate_cards_service(
    input_path=cfg["paths"]["hitters_csv"],
    profile="hitters",
    config=cfg,
)

eligible_hitters = filter_eligible_hitters(hitters_df, ruleset)
hitter_roster = build_hitter_roster(eligible_hitters, ruleset)

print("\n=== STARTERS ===")
for position, row in hitter_roster.starters_by_position.items():
    score_col = (
        "batting_score_overall" if position == "DH" else f"score_{position}_overall"
    )
    print(f"{position:>2}  {row['name']:<25}  {row[score_col]:.2f}")

print("\n=== BENCH ===")
for _, row in hitter_roster.bench_players.iterrows():
    print(f"{row['name']:<25}  bat={row['batting_score_overall']:.2f}")

print("\n=== BENCH COVERAGE ===")
for _, row in hitter_roster.bench_players.iterrows():
    covered = sorted(get_player_covered_positions(row, ruleset))
    print(f"{row['name']:<25}  {covered}")
