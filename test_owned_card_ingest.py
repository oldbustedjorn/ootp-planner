import pandas as pd
import pytest

from ootp_opt.ingest.owned_cards import collapse_owned_card_copies


def test_duplicate_physical_copies_collapse_to_one_card_version():
    cards = pd.DataFrame(
        [
            {
                "player_id": 101,
                "pt_card_id": 86730,
                "is_variant": False,
                "name": "Duplicate Card",
                "power": 100,
            },
            {
                "player_id": 202,
                "pt_card_id": 86730,
                "is_variant": False,
                "name": "Duplicate Card",
                "power": 100,
            },
        ]
    )

    collapsed = collapse_owned_card_copies(cards)

    assert len(collapsed) == 1
    assert collapsed.iloc[0]["player_id"] == 101
    assert collapsed.iloc[0]["owned_copy_count"] == 2
    assert collapsed.iloc[0]["owned_cid_copy_count"] == 2


def test_normal_and_variant_versions_are_not_collapsed_together():
    cards = pd.DataFrame(
        [
            {
                "player_id": 101,
                "pt_card_id": 86730,
                "is_variant": False,
                "name": "Versioned Card",
            },
            {
                "player_id": 202,
                "pt_card_id": 86730,
                "is_variant": True,
                "name": "Versioned Card",
            },
        ]
    )

    collapsed = collapse_owned_card_copies(cards)

    assert len(collapsed) == 2
    assert collapsed["is_variant"].tolist() == [False, True]
    assert collapsed["owned_copy_count"].tolist() == [1, 1]
    assert collapsed["owned_cid_copy_count"].tolist() == [2, 2]


def test_duplicate_version_with_inconsistent_ratings_is_rejected():
    cards = pd.DataFrame(
        [
            {
                "player_id": 101,
                "pt_card_id": 86730,
                "is_variant": False,
                "name": "Inconsistent Card",
                "power": 100,
            },
            {
                "player_id": 202,
                "pt_card_id": 86730,
                "is_variant": False,
                "name": "Inconsistent Card",
                "power": 101,
            },
        ]
    )

    with pytest.raises(ValueError, match="different metadata or ratings"):
        collapse_owned_card_copies(cards)
