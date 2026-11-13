"""Compact CLI receipts and local serialization; no execution policy lives here."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ootp_opt.automation.checkpoint import load_checkpoint
from ootp_opt.automation.execution import _expected_membership, _load
from ootp_opt.automation.rebuild import card_key


def write_json_output(path: str | Path, value: Any, *, protected: list[str | Path] = ()) -> str:
    destination = Path(path)
    require_output_path(destination, protected)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(destination)


def require_output_path(path: str | Path | None, protected: list[str | Path]) -> None:
    if path and Path(path).resolve() in {Path(p).resolve() for p in protected if p}:
        raise ValueError("Output must not overwrite a checkpoint, manifest, input file, or capture")


def compact_execution_receipt(result: dict, *, checkpoint_path: str | Path | None = None) -> str:
    if "state" in result:
        lines = [f"{result['state']} | completed={result['completed']}/{result['total']} "
                 f"unverified={len(result.get('unverified', []))} "
                 f"in_flight={result.get('in_flight') or 'none'}"]
        action = result.get("next_action")
        if result.get("local_save_name"):
            lines.append(f"Local save name: {json.dumps(result['local_save_name'])}")
        if action:
            count = len(result.get("next_batch", []))
            lines.append(f"Next: {action['id']} {action['operation']} {action['target']} | family_actions={count}")
        event = result.get("last_event") or {}
        for key in ("missing", "unexpected", "targets", "error"):
            if event.get(key):
                lines.append(f"{key}: {json.dumps(event[key], separators=(',', ':'))}")
        if checkpoint_path and event.get("event") in ("blocked", "batch_verification_failed"):
            checkpoint = load_checkpoint(checkpoint_path)
            execution = checkpoint["execution"]
            observation = execution["journal"][-1].get("observation", {})
            for target in event.get("targets", []):
                action = next(a for a in execution["actions"] if a["target"] == target)
                lines.append(_mismatch(target, action["value"], observation.get("targets", {}).get(target)))
            if event.get("action"):
                action = next(a for a in execution["actions"] if a["id"] == event["action"])
                if action["operation"] in ("set", "save"):
                    actual = observation.get("local_save") if action["operation"] == "save" else observation.get("targets", {}).get(action["target"])
                    expected = (result.get("local_save_name") or action["value"]) if action["operation"] == "save" else action["value"]
                    lines.append(_mismatch(action["target"], expected, actual))
                elif action["operation"] in ("add", "remove"):
                    _, current, manifest = _load(checkpoint_path)
                    pending = current.get("unverified", [])
                    observed = {card_key(card) for card in observation.get("membership", [])}
                    for label, after in (("before", None), ("after", action)):
                        expected = _expected_membership(manifest, current, additional=pending, after=after)
                        lines.append(f"Membership {label} action: missing={json.dumps(sorted(expected - observed), separators=(',', ':'))} unexpected={json.dumps(sorted(observed - expected), separators=(',', ':'))}")
    elif "id" in result and "operation" in result:
        lines = [f"Intent: {result['id']} {result['operation']} {result['target']} "
                 f"expected={json.dumps(result['value'], separators=(',', ':'))}"]
    elif "transactions" in result and isinstance(result["transactions"], list):
        lines = [f"Plan: {result['section']} | transactions={len(result['transactions'])} "
                 f"manifest={result['manifest_id']} | not executed"]
    elif "valid" in result:
        lines = [f"Valid batch | transactions={result['transactions']}"]
    elif "moves" in result:
        lines = [f"Plan: {result['section']}/{result['family']} | moves={len(result['moves'])} "
                 f"manifest={result['manifest_id']} | not executed"]
    elif "actions_completed" in result:
        lines = [f"Input returned | native_actions={result['actions_completed']} | verification required"]
    elif result.get("kind") in ("ootp_observation", "ootp_observation_draft"):
        draft = result["kind"].endswith("_draft")
        data = result["expected"] if draft else result
        lines = [f"{'Draft (not evidence)' if draft else 'Confirmed observation file'}: "
                 f"membership={len(data['membership'])} targets={len(data.get('targets', {}))} | checkpoint unchanged"]
    else:
        lines = [json.dumps(result, separators=(",", ":"))]
    if result.get("capture"):
        lines.append(f"Capture: {result['capture']}")
    return "\n".join(lines)


def _mismatch(target: str, expected: Any, observed: Any) -> str:
    return f"Mismatch {target}: expected={json.dumps(expected, separators=(',', ':'))} observed={json.dumps(observed, separators=(',', ':'))}"


def assignment_coordinates(args, manifest: dict) -> tuple:
    if args.coordinate_map:
        if args.client_geometry or args.source or args.target:
            raise ValueError("Use --coordinate-map or inline coordinate flags, not both")
        data = json.loads(Path(args.coordinate_map).read_text(encoding="utf-8-sig"))
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or data.get("manifest_fingerprint") != manifest["fingerprint"]
                or data.get("section") != args.section or data.get("family") != args.family):
            raise ValueError("Coordinate map does not match this manifest, section, and family")
        geometry, sources, targets = data["client_geometry"], data["sources"], data["targets"]
    else:
        geometry, sources, targets = args.client_geometry, dict(args.source), dict(args.target)
    if not geometry or not sources or not targets:
        raise ValueError("Supply --coordinate-map or --client-geometry, --source, and --target")
    if (not isinstance(geometry, (tuple, list)) or len(geometry) != 4 or any(type(v) is not int for v in geometry)
            or geometry[2] <= 0 or geometry[3] <= 0):
        raise ValueError("Invalid coordinate-map client geometry")
    for mapping in (sources, targets):
        if not isinstance(mapping, dict):
            raise ValueError("Coordinate-map sources and targets must be objects")
        for key, point in mapping.items():
            if (not isinstance(key, str) or not key or not isinstance(point, (list, tuple))
                    or len(point) != 2 or any(type(v) is not int for v in point)
                    or not 0 <= point[0] < geometry[2] or not 0 <= point[1] < geometry[3]):
                raise ValueError(f"Invalid client coordinate for {key}")
    return tuple(geometry), sources, targets


def save_assignment_coordinates(args, manifest: dict, geometry: tuple, sources: dict, targets: dict) -> None:
    if args.save_coordinate_map:
        destination = Path(args.save_coordinate_map)
        if destination.exists():
            raise FileExistsError("Coordinate map already exists; reuse it with --coordinate-map")
        write_json_output(destination, {
            "schema_version": 1, "manifest_fingerprint": manifest["fingerprint"],
            "section": args.section, "family": args.family, "client_geometry": list(geometry),
            "sources": sources, "targets": targets,
        })
