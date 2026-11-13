"""Serialize explicitly confirmed UI observations without handwritten roster arrays.

Drafts contain expected values, not evidence. Only a caller who has compared the
capture may attest matches; overrides preserve actual discrepancies. This module
never sends input, reconciles a checkpoint, or treats a returned input as success.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from ootp_opt.automation.checkpoint import now_iso
from ootp_opt.automation.execution import _expected_membership, _load, expected_save_name
from ootp_opt.automation.rebuild import rebuild_snapshot


OBSERVATION_SCOPES = ("baseline", "membership", "pending", "pitching", "vs_rhp", "vs_lhp", "save")


def membership_keys(cards: list[dict]) -> set[tuple[str, bool]]:
    if not isinstance(cards, list):
        raise ValueError("Membership must be an array of exact CID/variant cards")
    keys = []
    for card in cards:
        if (not isinstance(card, dict) or not card.get("cid")
                or not isinstance(card.get("variant"), bool)):
            raise ValueError("Membership requires CID and explicit boolean variant")
        keys.append((str(card["cid"]), card["variant"]))
    if len(set(keys)) != len(keys):
        raise ValueError("Ambiguous duplicate CID/variant in membership")
    return set(keys)


def read_observation(path: str | Path, manifest_fingerprint: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("kind") == "ootp_observation_draft":
        raise ValueError("An observation draft is not evidence; inspect the capture and explicitly confirm")
    evidence = data.get("_evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("Observation evidence metadata must be an object")
    if evidence and evidence.get("manifest_fingerprint") != manifest_fingerprint:
        raise ValueError("Observation belongs to a different manifest")
    membership_keys(data.get("membership"))
    return data


def prepare_observation(
    checkpoint_path: str | Path, scope: str, *, base: str | Path | None = None,
    capture: str | Path | None = None, confirm_matches: bool = False,
    actual_targets: dict | None = None, actual_membership: list | None = None,
    actual_save: str | None = None,
) -> dict:
    _, execution, manifest = _load(checkpoint_path)
    if scope not in OBSERVATION_SCOPES:
        raise ValueError(f"Unknown observation scope: {scope}")
    issued = [*execution.get("unverified", [])]
    if execution["in_flight"]:
        issued.append(execution["in_flight"])
    expected_members = _expected_membership(manifest, execution, additional=issued)
    snapshot = rebuild_snapshot(manifest)
    targets = {}
    local_save = None
    confirm_membership = scope in ("baseline", "membership")
    if scope == "baseline":
        if execution["completed"] or issued:
            raise ValueError("Baseline scope is only for an untouched rebuild; use membership or pending")
    elif scope == "pending":
        actions = [a for a in execution["actions"] if a["id"] in issued]
        if not actions:
            raise ValueError("No issued actions to observe; select baseline or a named section")
        for action in actions:
            if action["operation"] == "set":
                targets[action["target"]] = deepcopy(action["value"])
            elif action["operation"] == "save":
                local_save = expected_save_name(execution, manifest)
            elif action["operation"] in ("add", "remove") or action["section"] == "sync":
                confirm_membership = True
            elif action["operation"] == "verify":
                targets.update({k: v for k, v in snapshot["targets"].items()
                                if k.startswith(action["section"] + "/")})
    elif scope == "save":
        local_save = expected_save_name(execution, manifest)
    elif scope != "membership":
        targets = {k: v for k, v in snapshot["targets"].items() if k.startswith(scope + "/")}
    data = {"membership": [{"cid": cid, "variant": variant} for cid, variant in sorted(expected_members)],
            "targets": targets}
    if local_save is not None:
        data["local_save"] = local_save
    if actual_targets:
        unknown = actual_targets.keys() - targets.keys()
        if unknown:
            raise ValueError("Actual target is outside the selected scope: " + ", ".join(sorted(unknown)))
        data["targets"].update(deepcopy(actual_targets))
    if actual_membership is not None:
        if not confirm_membership:
            raise ValueError("Assignment/save scopes reuse known membership; record membership changes separately")
        membership_keys(actual_membership)
        data["membership"] = deepcopy(actual_membership)
    if actual_save is not None:
        if local_save is None:
            raise ValueError("Actual save name is only valid in a save scope")
        data["local_save"] = actual_save
    if not confirm_matches:
        return {"kind": "ootp_observation_draft", "scope": scope,
                "manifest_fingerprint": manifest["fingerprint"], "expected": data,
                "requires_verified_membership_base": not confirm_membership,
                "instruction": "Compare every scoped field against a capture. Confirm matches explicitly; supply actual overrides for discrepancies."}
    if not capture or not Path(capture).is_file() or not Path(capture).stat().st_size:
        raise ValueError("Explicit confirmation requires an existing nonempty --capture")
    if not confirm_membership:
        if not base:
            raise ValueError("Assignment/save confirmation requires --base with already reconciled membership")
        prior = read_observation(base, manifest["fingerprint"])
        if membership_keys(prior["membership"]) != expected_members:
            raise ValueError("Base membership does not match current journal progress")
        if not any(event["event"] == "reconciled" and event.get("observation")
                   and membership_keys(event["observation"]["membership"]) == expected_members
                   for event in execution["journal"]):
            raise ValueError("Base membership has not been reconciled in this checkpoint")
        data["membership"] = deepcopy(prior["membership"])
    data["kind"] = "ootp_observation"
    data["_evidence"] = {
        "manifest_fingerprint": manifest["fingerprint"], "scope": scope,
        "capture": str(Path(capture).resolve()), "capture_sha256": sha256(Path(capture).read_bytes()).hexdigest(),
        "confirmed_at": now_iso(), "confirmation": "matches_except_explicit_actual_overrides",
        "membership_source": "live_confirmation" if confirm_membership else str(Path(base).resolve()),
        "actual_targets": sorted(actual_targets or {}),
    }
    return data
