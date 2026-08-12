import pandas as pd

from ootp_opt.ingest.pt_store import load_pt_store_csv, normalize_pt_type_from_code


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
