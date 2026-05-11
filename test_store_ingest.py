from ootp_opt.config import load_config
from ootp_opt.ingest.pt_store import load_pt_store_hitters_pitchers

cfg = load_config("config.toml")

STORE_PATH = cfg["paths"]["store_csv"]

hitters, pitchers = load_pt_store_hitters_pitchers(STORE_PATH)

print("\n=== STORE INGEST SUMMARY ===")
print(f"Hitters:  {len(hitters)}")
print(f"Pitchers: {len(pitchers)}")

print("\n=== PRICE FIELD CHECK ===")
for label, df in [("Hitters", hitters), ("Pitchers", pitchers)]:
    print(f"\n{label}")
    print("Has sell order:")
    print(df["has_sell_order"].value_counts(dropna=False))
    print("Has buy order:")
    print(df["has_buy_order"].value_counts(dropna=False))

print("\n=== HITTER SAMPLE ===")
print(
    hitters[
        [
            "name",
            "player_id",
            "pt_tier",
            "card_value",
            "pt_year",
            "pt_type",
            "store_position",
            "bats",
            "sell_order_low",
            "has_sell_order",
            "last_10_price",
        ]
    ]
    .head(10)
    .to_string(index=False)
)

print("\n=== PITCHER SAMPLE ===")
print(
    pitchers[
        [
            "name",
            "player_id",
            "pt_tier",
            "card_value",
            "pt_year",
            "pt_type",
            "store_position",
            "throws",
            "sell_order_low",
            "has_sell_order",
            "last_10_price",
        ]
    ]
    .head(10)
    .to_string(index=False)
)
