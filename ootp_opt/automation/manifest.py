from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ootp_opt.domain.candidate_identity import (
    candidate_id_for_row,
    pt_card_id_for_row,
)
from ootp_opt.roster.bullpen_usage import assign_middle_relief_usage
from ootp_opt.roster.lineup import (
    assign_position_backups,
    build_lineup_order,
    build_pinch_hitters,
    build_pinch_runners,
)
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset


SCHEMA_VERSION = 1
SPLITS = ("vs_rhp", "vs_lhp")


def automation_manifest_path(html_output: str | Path) -> str:
    path = Path(html_output)
    return str(path.with_suffix(".automation.json"))


def build_automation_manifest(
    *,
    ruleset: Ruleset,
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    html_output: str | Path,
    roster_name: str | None,
    preset_name: str | None,
    base_profile: str | None,
    config_path: str | Path,
) -> dict[str, Any]:
    hitters = selected_hitter_rows(hitter_roster)
    pitchers = selected_pitcher_rows(pitcher_roster)
    membership = [
        *[card_reference(row, player_type="hitter") for row in hitters],
        *[card_reference(row, player_type="pitcher") for row in pitchers],
    ]

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "config_path": str(config_path),
            "preset_name": preset_name,
            "base_profile": base_profile,
            "build_method": "optimizer",
            "html_report": str(html_output),
        },
        "roster": {
            "name": roster_name or ruleset.name,
            "expected_hitters": ruleset.hitter_count,
            "expected_pitchers": ruleset.pitcher_count,
            "expected_total": ruleset.hitter_count + ruleset.pitcher_count,
            "membership": membership,
        },
        "tournament": tournament_constraints(ruleset),
        "pitching": pitching_assignments(pitcher_roster),
        "lineups": {
            split: lineup_assignments(hitter_roster, ruleset, split)
            for split in SPLITS
        },
        "bench_actions": {
            split: bench_assignments(hitter_roster, split) for split in SPLITS
        },
    }
    manifest["fingerprint"] = manifest_fingerprint(manifest)
    manifest["manifest_id"] = manifest["fingerprint"][:16]
    validate_manifest(manifest)
    return manifest


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> str:
    validate_manifest(manifest)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(destination)


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION}, got "
            f"{manifest.get('schema_version')!r}"
        )
    if manifest.get("source", {}).get("build_method") != "optimizer":
        errors.append("automation manifests require the Full Optimizer")

    roster = manifest.get("roster", {})
    membership = roster.get("membership", [])
    expected_total = roster.get("expected_total")
    if expected_total != len(membership):
        errors.append(
            f"membership has {len(membership)} cards; expected {expected_total}"
        )

    candidate_ids = [str(card.get("candidate_id") or "") for card in membership]
    if any(not candidate_id for candidate_id in candidate_ids):
        errors.append("every selected card must have a candidate_id")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("selected candidate_id values must be unique")

    missing_cids = [
        str(card.get("name") or card.get("candidate_id") or "unknown")
        for card in membership
        if not str(card.get("cid") or "").strip()
    ]
    if missing_cids:
        errors.append("selected cards missing CID: " + ", ".join(missing_cids))

    membership_ids = set(candidate_ids)
    for split in SPLITS:
        lineup = manifest.get("lineups", {}).get(split, {})
        starters = lineup.get("starters", [])
        expected_starters = 9 if manifest.get("tournament", {}).get("dh_enabled") else 8
        if len(starters) != expected_starters:
            errors.append(
                f"{split} has {len(starters)} starters; expected {expected_starters}"
            )
        starter_ids = [entry.get("card", {}).get("candidate_id") for entry in starters]
        if len(starter_ids) != len(set(starter_ids)):
            errors.append(f"{split} assigns one card more than once")
        unknown = sorted(set(starter_ids) - membership_ids)
        if unknown:
            errors.append(f"{split} references unknown cards: {', '.join(unknown)}")

    actual_fingerprint = manifest_fingerprint(manifest)
    if manifest.get("fingerprint") != actual_fingerprint:
        errors.append("manifest fingerprint does not match its contents")

    if errors:
        raise ValueError("Invalid automation manifest: " + "; ".join(errors))


def manifest_fingerprint(manifest: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"fingerprint", "manifest_id", "generated_at"}
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def tournament_constraints(ruleset: Ruleset) -> dict[str, Any]:
    return {
        "ruleset_name": ruleset.name,
        "mode": ruleset.mode,
        "dh_enabled": ruleset.dh_enabled,
        "platoons_allowed": ruleset.platoons_allowed,
        "tier_min": ruleset.tier_min,
        "tier_max": ruleset.tier_max,
        "card_value_min": ruleset.card_value_min,
        "card_value_max": ruleset.card_value_max,
        "point_cap_total": ruleset.point_cap_total,
        "tier_slots": ruleset.tier_slots,
        "variant_limit": ruleset.variant_limit,
        "live_mode": ruleset.live_mode,
        "allowed_card_types": ruleset.allowed_card_types,
        "excluded_card_types": ruleset.excluded_card_types,
        "card_year_min": ruleset.card_year_min,
        "card_year_max": ruleset.card_year_max,
        "simulation_year": ruleset.simulation_year,
        "ballpark": ruleset.ballpark,
        "ballpark_year": ruleset.ballpark_year,
        "custom_park_factors": ruleset.custom_park_factors,
    }


def pitching_assignments(pitcher_roster: PitcherRoster) -> dict[str, Any]:
    rotation = [
        {
            "order": index,
            "card": card_reference(row, player_type="pitcher"),
        }
        for index, (_, row) in enumerate(pitcher_roster.rotation.iterrows(), start=1)
    ]

    bullpen: list[dict[str, Any]] = []
    middle_relief = assign_middle_relief_usage(pitcher_roster.bullpen)
    for _, row in middle_relief.iterrows():
        bullpen.append(
            pitcher_role_assignment(
                row,
                role="Middle Relief",
                usage=str(row["usage_option"]),
            )
        )
    for _, row in pitcher_roster.lefty_specialist.iterrows():
        bullpen.append(
            pitcher_role_assignment(
                row,
                role="Specialist",
                usage="vs Left-Handed",
            )
        )
    for _, row in pitcher_roster.long_man.iterrows():
        bullpen.append(
            pitcher_role_assignment(row, role="Long Relief", usage="Normal Usage")
        )

    return {"rotation": rotation, "bullpen": bullpen}


def pitcher_role_assignment(
    row: pd.Series,
    *,
    role: str,
    usage: str,
) -> dict[str, Any]:
    return {
        "card": card_reference(row, player_type="pitcher"),
        "primary_role": role,
        "usage": usage,
        "secondary_role": (
            "Long Relief"
            if role != "Long Relief" and bool(row.get("is_long_secondary", False))
            else None
        ),
    }


def lineup_assignments(
    hitter_roster: HitterRoster,
    ruleset: Ruleset,
    split: str,
) -> dict[str, Any]:
    starters = hitter_roster.starters_for_split(split)
    bench = hitter_roster.bench_for_split(split)
    lineup = build_lineup_order(starters, split=split, smooth_handedness=True)
    entries: list[dict[str, Any]] = []

    for batting_order, position, row in lineup:
        backups = assign_position_backups(position, bench, ruleset, limit=2)
        entries.append(
            {
                "batting_order": batting_order,
                "position": position,
                "card": card_reference(row, player_type="hitter"),
                "depth": [
                    {
                        "order": index,
                        "condition": "If Starter tired",
                        "card": card_reference(backup, player_type="hitter"),
                    }
                    for index, backup in enumerate(backups, start=1)
                ],
            }
        )

    return {"starters": entries}


def bench_assignments(hitter_roster: HitterRoster, split: str) -> dict[str, Any]:
    bench = hitter_roster.bench_for_split(split)
    return {
        "pinch_hitters": ranked_cards(
            build_pinch_hitters(bench, split=split, limit=4), "hitter"
        ),
        "pinch_runners": ranked_cards(build_pinch_runners(bench, limit=4), "hitter"),
    }


def ranked_cards(rows: pd.DataFrame, player_type: str) -> list[dict[str, Any]]:
    return [
        {"order": index, "card": card_reference(row, player_type=player_type)}
        for index, (_, row) in enumerate(rows.iterrows(), start=1)
    ]


def card_reference(row: pd.Series, *, player_type: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id_for_row(row),
        "cid": pt_card_id_for_row(row),
        "source_record_id": scalar_text(row.get("source_record_id")),
        "name": scalar_text(row.get("name")),
        "player_type": player_type,
        "variant": bool(row.get("is_variant", False)),
        "owned_copy_count": scalar_int(row.get("owned_copy_count")),
        "card_value": scalar_int(row.get("card_value")),
        "year": scalar_int(row.get("pt_year")),
        "card_type": scalar_text(row.get("pt_type")),
        "bats": scalar_text(row.get("bats")),
        "throws": scalar_text(row.get("throws")),
    }


def selected_hitter_rows(hitter_roster: HitterRoster) -> list[pd.Series]:
    rows = [*hitter_roster.starters_by_position.values()]
    rows.extend(row for _, row in hitter_roster.bench_players.iterrows())
    return unique_rows(rows)


def selected_pitcher_rows(pitcher_roster: PitcherRoster) -> list[pd.Series]:
    rows: list[pd.Series] = []
    for frame in (
        pitcher_roster.rotation,
        pitcher_roster.bullpen,
        pitcher_roster.lefty_specialist,
        pitcher_roster.long_man,
    ):
        rows.extend(row for _, row in frame.iterrows())
    return unique_rows(rows)


def unique_rows(rows: Iterable[pd.Series]) -> list[pd.Series]:
    result: list[pd.Series] = []
    seen: set[str] = set()
    for row in rows:
        candidate_id = candidate_id_for_row(row)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        result.append(row)
    return result


def scalar_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def scalar_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
