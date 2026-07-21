from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any, Iterable
from urllib.parse import quote

import pandas as pd


CANDIDATE_ID_COLUMN = "candidate_id"
PERSON_KEY_COLUMN = "person_key"
SOURCE_RECORD_ID_COLUMN = "source_record_id"


@dataclass(frozen=True)
class CandidateIdentitySchema:
    """Describes how selectable assets and people are identified in one dataset."""

    namespace: str
    entity_kind: str
    source_id_column: str
    person_id_column: str | None = None
    name_column: str = "name"
    shared_identity_columns: tuple[str, ...] = ()
    fallback_columns: tuple[str, ...] = ()
    numeric_source_ids: bool = False


PT_CARD_IDENTITY_SCHEMA = CandidateIdentitySchema(
    namespace="ootp-pt",
    entity_kind="card",
    # OOTP calls this ID in the owned export and Card ID in the store export.
    # Both are currently normalized to the legacy column name player_id.
    source_id_column="player_id",
    name_column="name",
    # Owned-export ID and store Card ID use different number ranges. These
    # normalized card attributes are shared and unique in the current data.
    shared_identity_columns=(
        "name",
        "pt_year",
        "card_value",
        "pt_type",
        "pt_series",
    ),
    fallback_columns=(
        "name",
        "pt_title",
        "pt_year",
        "pt_type",
        "pt_subtype",
        "pt_series",
        "card_value",
    ),
    numeric_source_ids=True,
)


def build_base_game_identity_schema(save_key: str) -> CandidateIdentitySchema:
    """Create identities scoped to one OOTP base-game save.

    Base-game player IDs are expected to identify both the selectable record and
    the person. Scoping them to the save prevents unrelated leagues from
    accidentally sharing identities.
    """
    normalized_save_key = normalize_key_part(save_key)
    if not normalized_save_key:
        raise ValueError("Base-game identity schema requires a non-blank save key.")

    return CandidateIdentitySchema(
        namespace=f"ootp-base-{normalized_save_key}",
        entity_kind="player",
        source_id_column="player_id",
        person_id_column="player_id",
        name_column="name",
        fallback_columns=("name", "team", "date_of_birth"),
    )


def attach_candidate_identities(
    df: pd.DataFrame,
    schema: CandidateIdentitySchema,
) -> pd.DataFrame:
    """Return a copy with canonical candidate_id and person_key columns."""
    identified = df.copy()

    source_ids = source_identifier_series(identified, schema)
    identified[SOURCE_RECORD_ID_COLUMN] = source_ids

    if schema.shared_identity_columns and all(
        column in identified.columns for column in schema.shared_identity_columns
    ):
        candidate_ids = identified.apply(
            lambda row: build_shared_candidate_id(row, schema), axis=1
        )
    else:
        candidate_ids = source_ids.map(
            lambda value: build_scoped_key(schema, value) if value else ""
        )

    missing_candidate_ids = candidate_ids.eq("")
    if missing_candidate_ids.any():
        candidate_ids.loc[missing_candidate_ids] = identified.loc[
            missing_candidate_ids
        ].apply(lambda row: build_fallback_candidate_id(row, schema), axis=1)

    identified[CANDIDATE_ID_COLUMN] = candidate_ids
    identified[PERSON_KEY_COLUMN] = build_person_key_series(identified, schema)

    duplicate_ids = identified.loc[
        identified[CANDIDATE_ID_COLUMN].duplicated(keep=False),
        CANDIDATE_ID_COLUMN,
    ].drop_duplicates()
    if not duplicate_ids.empty:
        examples = ", ".join(duplicate_ids.head(5).astype(str))
        raise ValueError(
            "Candidate identity is not unique within the dataset. "
            f"Duplicate candidate_id values include: {examples}"
        )

    return identified


def candidate_id_for_row(row: pd.Series) -> str:
    existing = clean_text(row.get(CANDIDATE_ID_COLUMN))
    if existing:
        return existing

    if all(
        column in row.index
        for column in PT_CARD_IDENTITY_SCHEMA.shared_identity_columns
    ):
        return build_shared_candidate_id(row, PT_CARD_IDENTITY_SCHEMA)

    source_id = normalize_source_identifier(row.get("player_id"), numeric=True)
    if source_id:
        return build_scoped_key(PT_CARD_IDENTITY_SCHEMA, source_id)

    return build_fallback_candidate_id(row, PT_CARD_IDENTITY_SCHEMA)


def person_key_for_row(row: pd.Series) -> str:
    existing = clean_text(row.get(PERSON_KEY_COLUMN))
    if existing:
        return existing

    normalized_name = normalize_person_name(row.get("name"))
    if normalized_name:
        return f"person:name:{quote(normalized_name, safe='')}"

    return f"person:candidate:{quote(candidate_id_for_row(row), safe='')}"


def normalize_person_keys(values: Iterable[str]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        if text.startswith("person:"):
            keys.add(text)
            continue

        normalized_name = normalize_person_name(text)
        if normalized_name:
            keys.add(f"person:name:{quote(normalized_name, safe='')}")
    return keys


def source_identifier_series(
    df: pd.DataFrame,
    schema: CandidateIdentitySchema,
) -> pd.Series:
    if schema.source_id_column not in df.columns:
        return pd.Series("", index=df.index, dtype="object")

    return df[schema.source_id_column].map(
        lambda value: normalize_source_identifier(
            value,
            numeric=schema.numeric_source_ids,
        )
    )


def build_person_key_series(
    df: pd.DataFrame,
    schema: CandidateIdentitySchema,
) -> pd.Series:
    if schema.person_id_column and schema.person_id_column in df.columns:
        person_ids = df[schema.person_id_column].map(
            lambda value: normalize_source_identifier(
                value,
                numeric=schema.numeric_source_ids,
            )
        )
    else:
        person_ids = pd.Series("", index=df.index, dtype="object")

    names = (
        df[schema.name_column].map(normalize_person_name)
        if schema.name_column in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )

    keys = pd.Series("", index=df.index, dtype="object")
    has_person_id = person_ids.ne("")
    keys.loc[has_person_id] = person_ids.loc[has_person_id].map(
        lambda value: (
            f"person:{quote(schema.namespace, safe='')}:id:{quote(value, safe='')}"
        )
    )

    has_name = ~has_person_id & names.ne("")
    keys.loc[has_name] = names.loc[has_name].map(
        lambda value: f"person:name:{quote(value, safe='')}"
    )

    missing = keys.eq("")
    if missing.any():
        keys.loc[missing] = df.loc[missing].apply(
            lambda row: f"person:candidate:{quote(candidate_id_for_row(row), safe='')}",
            axis=1,
        )

    return keys


def build_scoped_key(schema: CandidateIdentitySchema, source_id: str) -> str:
    return ":".join(
        [
            quote(schema.namespace, safe=""),
            quote(schema.entity_kind, safe=""),
            quote(source_id, safe=""),
        ]
    )


def build_fallback_candidate_id(
    row: pd.Series,
    schema: CandidateIdentitySchema,
) -> str:
    columns = schema.fallback_columns or (schema.name_column,)
    payload = {
        column: normalize_fingerprint_value(row.get(column)) for column in columns
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return ":".join(
        [
            quote(schema.namespace, safe=""),
            quote(schema.entity_kind, safe=""),
            "derived",
            digest,
        ]
    )


def build_shared_candidate_id(
    row: pd.Series,
    schema: CandidateIdentitySchema,
) -> str:
    payload = {
        column: normalize_fingerprint_value(row.get(column))
        for column in schema.shared_identity_columns
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return ":".join(
        [
            quote(schema.namespace, safe=""),
            quote(schema.entity_kind, safe=""),
            "key",
            digest,
        ]
    )


def normalize_source_identifier(value: Any, *, numeric: bool) -> str:
    if is_missing(value):
        return ""

    text = str(value).strip()
    if not text:
        return ""

    if numeric:
        try:
            number = float(text)
        except ValueError:
            return text
        if math.isfinite(number) and number.is_integer():
            return str(int(number))

    return text


def normalize_person_name(value: Any) -> str:
    if is_missing(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def normalize_key_part(value: Any) -> str:
    text = normalize_person_name(value)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def normalize_fingerprint_value(value: Any) -> str:
    if is_missing(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def clean_text(value: Any) -> str:
    if is_missing(value):
        return ""
    return str(value).strip()


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(missing)
    except ValueError:
        return False
