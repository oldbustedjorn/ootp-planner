from __future__ import annotations

import pandas as pd


PT_CARD_ID_COLUMN = "pt_card_id"
CARD_VERSION_COLUMNS = (PT_CARD_ID_COLUMN, "is_variant")
INVENTORY_COPY_COLUMNS = {
    "player_id",
    "pt_on_active",
    "owned_copy_count",
}


def collapse_owned_card_copies(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse interchangeable inventory copies to one card-version row.

    CID identifies the underlying PT card and VAR distinguishes the normal and
    variant versions. Inventory-only fields may differ between physical copies;
    all card metadata and ratings must agree before copies are collapsed.
    """
    if PT_CARD_ID_COLUMN not in df.columns:
        return df

    collapsed = df.copy()
    collapsed[PT_CARD_ID_COLUMN] = pd.to_numeric(
        collapsed[PT_CARD_ID_COLUMN], errors="coerce"
    ).astype("Int64")
    if "is_variant" not in collapsed.columns:
        collapsed["is_variant"] = False

    valid_card_id = collapsed[PT_CARD_ID_COLUMN].notna() & collapsed[
        PT_CARD_ID_COLUMN
    ].gt(0)
    if not valid_card_id.any():
        return collapsed

    version_columns = list(CARD_VERSION_COLUMNS)
    version_rows = collapsed.loc[valid_card_id]
    duplicate_versions = version_rows.duplicated(version_columns, keep=False)
    if duplicate_versions.any():
        duplicated = version_rows.loc[duplicate_versions]
        stable_columns = [
            column
            for column in collapsed.columns
            if column not in INVENTORY_COPY_COLUMNS
            and column not in version_columns
        ]
        row_hashes = pd.util.hash_pandas_object(
            duplicated[stable_columns].astype(str),
            index=False,
        )
        consistency = duplicated[version_columns].copy()
        consistency["_row_hash"] = row_hashes.to_numpy()
        inconsistent = (
            consistency.groupby(version_columns, dropna=False)["_row_hash"]
            .nunique()
            .gt(1)
        )
        if inconsistent.any():
            examples = ", ".join(
                f"CID {card_id} VAR {'Y' if is_variant else 'N'}"
                for card_id, is_variant in inconsistent.loc[inconsistent]
                .index[:5]
            )
            raise ValueError(
                "Owned export contains duplicate card versions with different "
                f"metadata or ratings: {examples}"
            )

    copy_counts = version_rows.groupby(version_columns, dropna=False).size()
    collapsed["owned_copy_count"] = 1
    collapsed.loc[valid_card_id, "owned_copy_count"] = [
        int(copy_counts.loc[(card_id, is_variant)])
        for card_id, is_variant in collapsed.loc[
            valid_card_id, version_columns
        ].itertuples(index=False, name=None)
    ]

    duplicate_copy = valid_card_id & collapsed.duplicated(
        version_columns,
        keep="first",
    )
    return collapsed.loc[~duplicate_copy].copy()
