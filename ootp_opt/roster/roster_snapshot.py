from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from ootp_opt.roster.models import HitterRoster, PitcherRoster


POOLED_ROLE_PREFIXES = {
    "bench": ("Bench ",),
    "middle_relief": ("Middle Relief ", "RP"),
    "lefty_specialist": ("LHP Specialist ",),
    "long_relief": ("Long Relief ", "Long Man "),
}


def build_roster_snapshot(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> dict[str, str]:
    snapshot: dict[str, str] = {}

    for position, row in hitter_roster.starters_by_position.items():
        snapshot[f"Starter {position}"] = card_identity(row)

    for idx, (_, row) in enumerate(hitter_roster.bench_players.iterrows(), start=1):
        snapshot[f"Bench {idx}"] = card_identity(row)

    for idx, (_, row) in enumerate(pitcher_roster.rotation.iterrows(), start=1):
        snapshot[f"SP{idx}"] = card_identity(row)

    for idx, (_, row) in enumerate(pitcher_roster.bullpen.iterrows(), start=1):
        snapshot[f"Middle Relief {idx}"] = card_identity(row)

    for idx, (_, row) in enumerate(pitcher_roster.lefty_specialist.iterrows(), start=1):
        snapshot[f"LHP Specialist {idx}"] = card_identity(row)

    for idx, (_, row) in enumerate(pitcher_roster.long_man.iterrows(), start=1):
        snapshot[f"Long Relief {idx}"] = card_identity(row)

    return snapshot


def card_identity(row: pd.Series) -> str:
    return "|".join(
        [
            str(row.get("name", "")),
            str(row.get("card_value", "")),
            str(row.get("pt_tier", "")),
            str(row.get("pt_year", "")),
            str(row.get("pt_type", "")),
        ]
    )


def snapshot_path_for_html(html_path: str | Path) -> Path:
    path = Path(html_path)
    return path.with_suffix(".snapshot.json")


def load_snapshot(path: str | Path) -> dict[str, str] | None:
    path = Path(path)

    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(raw, dict):
        return None

    return {str(key): str(value) for key, value in raw.items()}


def write_snapshot(path: str | Path, snapshot: dict[str, str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def compare_snapshots(
    old_snapshot: dict[str, str] | None,
    new_snapshot: dict[str, str],
) -> dict[str, str]:
    if old_snapshot is None:
        return {role: "new" for role in new_snapshot}

    statuses: dict[str, str] = {}

    for role, new_identity in new_snapshot.items():
        pool_key = pooled_role_key(role)
        if pool_key is not None:
            old_pool_identities = identities_for_pool(old_snapshot, pool_key)
            if not old_pool_identities:
                statuses[role] = "new"
            elif new_identity in old_pool_identities:
                statuses[role] = "unchanged"
            else:
                statuses[role] = "changed"
            continue

        old_identity = old_snapshot.get(role)

        if old_identity is None:
            statuses[role] = "new"
        elif old_identity == new_identity:
            statuses[role] = "unchanged"
        else:
            statuses[role] = "changed"

    return statuses


def pooled_role_key(role: str) -> str | None:
    for pool_key, prefixes in POOLED_ROLE_PREFIXES.items():
        if any(role.startswith(prefix) for prefix in prefixes):
            return pool_key
    return None


def identities_for_pool(snapshot: dict[str, str], pool_key: str) -> set[str]:
    prefixes = POOLED_ROLE_PREFIXES[pool_key]
    return {
        identity
        for role, identity in snapshot.items()
        if any(role.startswith(prefix) for prefix in prefixes)
    }
