import pandas as pd

from ootp_opt.ingest.pt_store import (
    attach_clubhouse_shop_data,
    load_pt_store_csv,
    normalize_pt_type_from_code,
)


def test_store_card_type_codes_match_collection_pt_type_codes():
    df = pd.DataFrame(
        {
            "pt_type_raw": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        }
    )

    normalize_pt_type_from_code(df)

    assert df["pt_type"].tolist() == [
        "2026Live",
        "NeL",
        "RS",
        "Leg",
        "AS",
        "FL",
        "Snap",
        "UnH",
        "HaH",
        "VET",
    ]


def test_store_ingest_normalizes_missions_and_clubhouse_title(tmp_path):
    path = tmp_path / "store.csv"
    pd.DataFrame(
        [
            {
                "//Card Title": "Clubhouse Collection Reward - Test Player",
                "Card ID": 101,
                "Position": 3,
            },
            {
                "//Card Title": "Historical All-Star - Other Player",
                "Card ID": 102,
                "Position": 1,
            },
        ]
    ).to_csv(path, index=False)

    cards = load_pt_store_csv(path)

    assert cards["is_clubhouse_card"].tolist() == [True, False]
    assert cards["pt_card_id"].tolist() == [101, 102]
    assert cards["player_id"].tolist() == [101, 102]


def test_clubhouse_shop_data_joins_by_player_id(tmp_path):
    shop_path = tmp_path / "clubhouse_shop.csv"
    pd.DataFrame(
        [
            {
                "player_id": 102,
                "clubhouse_star_cost": 75,
                "as_of_date": "2026-09-16",
                "card_title": "Human-readable maintenance reference",
            }
        ]
    ).to_csv(shop_path, index=False)
    cards = pd.DataFrame(
        [
            {"player_id": 101, "card_title": "First"},
            {"player_id": 102, "card_title": "Second"},
        ]
    )

    enriched = attach_clubhouse_shop_data(cards, shop_path)

    assert pd.isna(enriched.loc[0, "clubhouse_star_cost"])
    assert enriched.loc[1, "clubhouse_star_cost"] == 75
    assert enriched.loc[1, "clubhouse_shop_as_of"] == "2026-09-16"
