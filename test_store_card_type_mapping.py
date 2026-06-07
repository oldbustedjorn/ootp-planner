import pandas as pd

from ootp_opt.ingest.pt_store import normalize_pt_type_from_code


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
