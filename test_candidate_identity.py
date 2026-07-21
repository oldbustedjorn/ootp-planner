import pandas as pd
import pytest

from ootp_opt.domain.candidate_identity import (
    CANDIDATE_ID_COLUMN,
    PERSON_KEY_COLUMN,
    PT_CARD_IDENTITY_SCHEMA,
    SOURCE_RECORD_ID_COLUMN,
    attach_candidate_identities,
    build_base_game_identity_schema,
)
from ootp_opt.roster.builder import (
    has_duplicate_players,
    remove_players_by_name,
)


def test_pt_cards_have_distinct_candidate_ids_and_shared_person_key():
    cards = pd.DataFrame(
        [
            {"player_id": 101, "name": "Bobby Witt Jr.", "pt_year": 2024},
            {"player_id": 202, "name": "  BOBBY   WITT JR. ", "pt_year": 2025},
        ]
    )

    identified = attach_candidate_identities(cards, PT_CARD_IDENTITY_SCHEMA)

    assert identified[CANDIDATE_ID_COLUMN].tolist() == [
        "ootp-pt:card:101",
        "ootp-pt:card:202",
    ]
    assert identified[PERSON_KEY_COLUMN].nunique() == 1
    assert has_duplicate_players([row for _, row in identified.iterrows()])


def test_pt_card_identity_matches_across_owned_and_store_numeric_formats():
    owned = pd.DataFrame([{"player_id": "12345", "name": "Same Player"}])
    store = pd.DataFrame([{"player_id": 12345.0, "name": "Same Player"}])

    owned_identified = attach_candidate_identities(owned, PT_CARD_IDENTITY_SCHEMA)
    store_identified = attach_candidate_identities(store, PT_CARD_IDENTITY_SCHEMA)

    assert (
        owned_identified.iloc[0][CANDIDATE_ID_COLUMN]
        == store_identified.iloc[0][CANDIDATE_ID_COLUMN]
        == "ootp-pt:card:12345"
    )
    assert (
        owned_identified.iloc[0][PERSON_KEY_COLUMN]
        == store_identified.iloc[0][PERSON_KEY_COLUMN]
    )


def test_pt_shared_card_attributes_override_different_export_record_ids():
    card_attributes = {
        "name": "Shared Card",
        "pt_year": 1999,
        "card_value": 88,
        "pt_type": "Snapshot",
        "pt_series": 4,
    }
    owned = pd.DataFrame([{"player_id": 123, **card_attributes}])
    store = pd.DataFrame([{"player_id": 85123, **card_attributes}])

    owned_identified = attach_candidate_identities(owned, PT_CARD_IDENTITY_SCHEMA)
    store_identified = attach_candidate_identities(store, PT_CARD_IDENTITY_SCHEMA)

    assert (
        owned_identified.iloc[0][CANDIDATE_ID_COLUMN]
        == store_identified.iloc[0][CANDIDATE_ID_COLUMN]
    )
    assert owned_identified.iloc[0][SOURCE_RECORD_ID_COLUMN] == "123"
    assert store_identified.iloc[0][SOURCE_RECORD_ID_COLUMN] == "85123"


def test_base_game_identity_is_scoped_to_save_and_uses_player_id_for_person():
    player = pd.DataFrame([{"player_id": "player_42", "name": "Future Player"}])

    save_a = attach_candidate_identities(
        player,
        build_base_game_identity_schema("My League 2035"),
    )
    save_b = attach_candidate_identities(
        player,
        build_base_game_identity_schema("Other League"),
    )

    assert save_a.iloc[0][CANDIDATE_ID_COLUMN] == (
        "ootp-base-my-league-2035:player:player_42"
    )
    assert save_a.iloc[0][PERSON_KEY_COLUMN] == (
        "person:ootp-base-my-league-2035:id:player_42"
    )
    assert (
        save_a.iloc[0][CANDIDATE_ID_COLUMN]
        != save_b.iloc[0][CANDIDATE_ID_COLUMN]
    )


def test_missing_source_id_gets_deterministic_derived_candidate_id():
    card = pd.DataFrame(
        [
            {
                "name": "Derived Card",
                "pt_title": "Snapshot",
                "pt_year": 1999,
                "card_value": 88,
            }
        ]
    )

    first = attach_candidate_identities(card, PT_CARD_IDENTITY_SCHEMA)
    second = attach_candidate_identities(card, PT_CARD_IDENTITY_SCHEMA)

    assert first.iloc[0][CANDIDATE_ID_COLUMN].startswith(
        "ootp-pt:card:derived:"
    )
    assert (
        first.iloc[0][CANDIDATE_ID_COLUMN]
        == second.iloc[0][CANDIDATE_ID_COLUMN]
    )


def test_nan_source_id_uses_derived_identity_instead_of_literal_nan():
    card = pd.DataFrame([{"player_id": float("nan"), "name": "Missing ID"}])

    identified = attach_candidate_identities(card, PT_CARD_IDENTITY_SCHEMA)

    assert ":derived:" in identified.iloc[0][CANDIDATE_ID_COLUMN]


def test_duplicate_candidate_identity_is_rejected():
    cards = pd.DataFrame(
        [
            {"player_id": 100, "name": "First Name"},
            {"player_id": 100, "name": "Second Name"},
        ]
    )

    with pytest.raises(ValueError, match="Candidate identity is not unique"):
        attach_candidate_identities(cards, PT_CARD_IDENTITY_SCHEMA)


def test_legacy_name_key_still_blocks_identified_person():
    cards = attach_candidate_identities(
        pd.DataFrame(
            [
                {"player_id": 1, "name": "Bobby Witt Jr."},
                {"player_id": 2, "name": "Other Player"},
            ]
        ),
        PT_CARD_IDENTITY_SCHEMA,
    )

    remaining = remove_players_by_name(cards, {"bobby witt jr."})

    assert remaining["name"].tolist() == ["Other Player"]
