"""Deterministic rebuild protocol. Native input is separate from observed success.

An intent is durably stored before input. Interrupted intents are never replayed
until an observation proves whether their postcondition was reached.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from functools import wraps
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Callable

from ootp_opt.automation.checkpoint import load_checkpoint, now_iso, write_checkpoint
from ootp_opt.automation.manifest import load_manifest
from ootp_opt.automation.rebuild import card_key, rebuild_snapshot


MAX_EXECUTION_BATCH = 30


def batch_family(action: dict) -> tuple:
    if action["operation"] in ("add", "remove"):
        return action["section"], action["operation"]
    if action["operation"] == "set":
        return tuple(action["target"].split("/")[:2])
    return (action["id"],)  # Verification and save are explicit boundaries.


def next_batch_actions(actions: list[dict], start: int) -> list[dict]:
    if start >= len(actions):
        return []
    family = batch_family(actions[start])
    batch = []
    for action in actions[start:start + MAX_EXECUTION_BATCH]:
        if batch_family(action) != family:
            break
        batch.append(action)
    return batch


@contextmanager
def _writer_lock(path: str | Path):
    """OS-owned nonblocking lock; a crashed process leaves no stale ownership."""
    with Path(str(path) + ".execution.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another rebuild checkpoint writer is active") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _serialized(function):
    @wraps(function)
    def wrapped(path, *args, **kwargs):
        with _writer_lock(path):
            return function(path, *args, **kwargs)
    return wrapped


def compile_rebuild_actions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rebuild = manifest.get("rebuild")
    if not rebuild or "baseline" not in rebuild:
        raise ValueError("Rebuild execution requires a reconciliable baseline snapshot")
    baseline = rebuild["baseline"]
    desired = rebuild_snapshot(manifest)
    members = _membership(baseline["membership"])
    for card in rebuild["membership"]["remove"]:
        key = card_key(card)
        if key not in members:
            raise ValueError("Rebuild removal is absent from baseline")
        members.remove(key)
    for card in rebuild["membership"]["add"]:
        key = card_key(card)
        if key in members:
            raise ValueError("Rebuild addition already exists in baseline")
        members.add(key)
    if members != _membership(desired["membership"]):
        raise ValueError("Rebuild delta does not reconcile baseline to desired membership")
    actions: list[dict[str, Any]] = []

    def add(section: str, operation: str, target: str, value: Any) -> None:
        payload = dict(section=section, operation=operation, target=target, value=value)
        digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        actions.append({"id": f"{section}:{digest}", **payload})

    # Membership comes from the manifest delta, never reconstructed from a screen.
    for operation in ("remove", "add"):
        for card in rebuild["membership"][operation]:
            cid, variant = card_key(card)
            add("sync", operation, f"membership/{cid}/{str(variant).lower()}",
                {"cid": cid, "variant": variant})
    add("sync", "verify", "sync", None)

    old_targets = baseline["targets"]
    targets = desired["targets"]
    for section in ("pitching", "vs_rhp", "vs_lhp"):
        if section == "pitching":
            families = ("rotation_size", "rotation", "bullpen")
        else:
            families = ("starters", "depth", "batting_order", "pinch_hitters", "pinch_runners")
        for family in families:
            prefix = f"{section}/{family}"
            # Dict insertion follows manifest order, including numeric rank/order.
            for target, value in targets.items():
                if (target == prefix or target.startswith(prefix + "/")) and (
                    target not in old_targets or old_targets[target] != value
                ):
                    add(section, "set", target, value)
        add(section, "verify", section, None)
    add("save", "save", "local_save", manifest["roster"]["name"])
    return actions


@_serialized
def initialize_execution(
    checkpoint_path: str | Path, baseline_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    checkpoint = load_checkpoint(checkpoint_path)
    if "execution" in checkpoint:
        return execution_status(checkpoint_path)
    manifest = load_manifest(checkpoint["manifest_path"])
    baseline = manifest.get("rebuild", {}).get("baseline")
    if baseline is None:
        baseline_path = baseline_manifest_path or manifest.get("rebuild", {}).get(
            "previous_artifacts", {}
        ).get("manifest")
        if not baseline_path:
            raise ValueError("Rebuild execution requires a baseline snapshot or --baseline-manifest")
        previous = load_manifest(baseline_path)
        if previous["manifest_id"] != manifest.get("rebuild", {}).get("previous_manifest_id"):
            raise ValueError("Baseline manifest does not match the rebuild source")
        baseline = rebuild_snapshot(previous)
        manifest["rebuild"]["baseline"] = baseline
    actions = compile_rebuild_actions(manifest)
    # Legacy phase completion is evidence for skipping work, but never for save.
    completed = [
        action["id"] for action in actions
        if action["section"] != "save" and checkpoint["phases"][
            "sync" if action["section"] == "sync" else "assign"
        ]["status"] == "complete"
    ]
    if completed != [action["id"] for action in actions[:len(completed)]]:
        raise ValueError("Cannot migrate phases completed out of order")
    checkpoint["execution"] = {
        "schema_version": 1,
        "baseline": baseline,
        "actions": actions,
        "completed": completed,
        "in_flight": None,
        "unverified": [],
        "baseline_reconciled": False,
        "journal": [],
    }
    _persist(checkpoint_path, checkpoint, "initialized")
    return execution_status(checkpoint_path)


def _load(path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    checkpoint = load_checkpoint(path)
    execution = checkpoint.get("execution")
    if not execution or execution.get("schema_version") != 1:
        raise ValueError("Initialize rebuild execution first")
    manifest = load_manifest(checkpoint["manifest_path"])
    if "baseline" not in manifest.get("rebuild", {}):
        manifest["rebuild"]["baseline"] = execution["baseline"]
    if execution["actions"] != compile_rebuild_actions(manifest):
        raise ValueError("Execution action plan does not match the manifest")
    ids = [action["id"] for action in execution["actions"]]
    completed = execution["completed"]
    if completed != ids[:len(completed)] or len(completed) > len(ids):
        raise ValueError("Execution completion must be an ordered action prefix")
    unverified = execution.get("unverified", [])
    next_index = len(completed) + len(unverified)
    if unverified and any(batch_family(a) != batch_family(execution["actions"][len(completed)])
                          for a in execution["actions"][len(completed):next_index]):
        raise ValueError("Unverified actions cross an execution batch boundary")
    if (unverified and execution["in_flight"] and next_index < len(ids)
            and batch_family(execution["actions"][next_index])
            != batch_family(execution["actions"][len(completed)])):
        raise ValueError("In-flight action crosses an unverified batch boundary")
    if execution["in_flight"] is not None and (
        next_index == len(ids) or execution["in_flight"] != ids[next_index]
    ):
        raise ValueError("Invalid in-flight execution action")
    return checkpoint, execution, manifest


def execution_status(path: str | Path) -> dict[str, Any]:
    checkpoint, execution, _ = _load(path)
    actions = execution["actions"]
    index = len(execution["completed"])
    unverified = execution.get("unverified", [])
    next_index = index + len(unverified)
    unresolved = checkpoint["phases"]["plan"]["status"] != "complete" or any(
        record["missing"] or record["ambiguous"] for record in checkpoint["phases"].values()
    )
    return {
        "state": ("blocked" if unresolved else
                  "needs_reconciliation" if execution["in_flight"] else
                  "needs_verification" if unverified else
                  "needs_baseline" if not execution["baseline_reconciled"] else
                  "complete" if index == len(actions) else "ready"),
        "completed": index,
        "total": len(actions),
        "next_action": actions[next_index] if next_index < len(actions) else None,
        "next_batch": next_batch_actions(actions, next_index) if not unverified
                      and not execution["in_flight"] else [],
        "unverified": unverified,
        "in_flight": execution["in_flight"],
        "local_save_name": execution.get("local_save_binding", {}).get("name"),
        "last_event": {key: value for key, value in execution["journal"][-1].items()
                       if key != "observation"} if execution["journal"] else None,
    }


@_serialized
def bind_local_save_name(path: str | Path, name: str, *, capture: str | Path,
                         note: str) -> dict[str, Any]:
    """Record the controller-verified existing roster identity, without changing the plan.

    The controller must inspect the capture and verify this is the intended roster;
    a matching numeric suffix alone is not evidence of identity. Binding does not
    verify a save or advance any action.
    """
    checkpoint, execution, manifest = _load(path)
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError("Local save name must be nonempty without surrounding whitespace")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("Explain how the existing roster identity was verified")
    evidence = Path(capture)
    if not evidence.is_file() or not evidence.stat().st_size:
        raise ValueError("Binding requires an inspected nonempty capture")
    previous = execution.get("local_save_binding")
    if previous:
        if previous["name"] != name:
            raise ValueError("Local save name is already bound; do not silently rebind another roster")
        return execution_status(path)
    if execution["actions"][-1]["id"] in execution["completed"]:
        raise ValueError("Cannot bind a name after save completion")
    binding = {
        "name": name, "manifest_name": manifest["roster"]["name"],
        "capture": str(evidence.resolve()),
        "capture_sha256": sha256(evidence.read_bytes()).hexdigest(),
        "note": note, "confirmed_at": now_iso(),
    }
    execution["local_save_binding"] = binding
    _persist(path, checkpoint, "local_save_name_bound", **binding)
    return execution_status(path)


def expected_save_name(execution: dict, manifest: dict) -> str:
    return execution.get("local_save_binding", {}).get("name", manifest["roster"]["name"])


def _membership(cards: list[dict[str, Any]]) -> set[tuple[str, bool]]:
    keys = []
    for card in cards:
        if not card.get("cid") or not isinstance(card.get("variant"), bool):
            raise ValueError("Observed cards require CID and explicit boolean variant")
        keys.append(card_key(card))
    if len(set(keys)) != len(keys):
        raise ValueError("Ambiguous duplicate CID/variant in observed active roster")
    return set(keys)


def _expected_membership(
    manifest: dict, execution: dict, *, after: dict | None = None,
    additional: list[str] | None = None,
) -> set:
    members = _membership(manifest["rebuild"]["baseline"]["membership"])
    for action in execution["actions"]:
        if (action["id"] not in execution["completed"]
                and action["id"] not in (additional or []) and action != after):
            continue
        if action["operation"] == "remove":
            members.remove(card_key(action["value"]))
        elif action["operation"] == "add":
            members.add(card_key(action["value"]))
    return members


@_serialized
def reconcile_execution(
    path: str | Path, observation: dict[str, Any], *, retry_unapplied: bool = False,
) -> dict[str, Any]:
    """Reconcile exact membership; resolve uncertain input only from live facts.

    Observations are explicit controller evidence, not inferred from native calls.
    A mismatch is journaled and blocks all subsequent input without rewriting the
    baseline, substituting variants, or removing unexpected cards.
    """
    checkpoint, execution, manifest = _load(path)
    observed = _membership(observation["membership"])
    unverified = execution.get("unverified", [])
    expected = _expected_membership(manifest, execution, additional=unverified)
    action = execution_status(path)["next_action"]
    pending_actions = [a for a in execution["actions"] if a["id"] in unverified]
    # Returned input is not success. Verify the whole batch from one observation.
    failed_targets = [a["target"] for a in pending_actions
                      if not _postcondition(manifest, a, observation, execution)]
    if failed_targets:
        execution["baseline_reconciled"] = False
        _persist(path, checkpoint, "batch_verification_failed", targets=failed_targets,
                 observation=observation)
        return execution_status(path)
    resolution = None
    if execution["in_flight"]:
        after = _expected_membership(manifest, execution, after=action, additional=unverified)
        operation = action["operation"]
        if observed == after and _postcondition(manifest, action, observation, execution):
            execution["completed"].extend([*unverified, action["id"]])
            execution["unverified"] = []
            execution["in_flight"] = None
            resolution = "applied"
        elif observed == expected and operation in ("remove", "add"):
            execution["completed"].extend(unverified)
            execution["unverified"] = []
            execution["in_flight"] = None
            resolution = "not_applied"
        elif observed == expected and operation == "verify":
            execution["in_flight"] = None
            resolution = "verification_failed"
        elif observed == expected and operation == "set" and retry_unapplied and (
            action["target"] in manifest["rebuild"]["baseline"]["targets"]
            and observation.get("targets", {}).get(action["target"])
            == manifest["rebuild"]["baseline"]["targets"][action["target"]]
        ):
            execution["completed"].extend(unverified)
            execution["unverified"] = []
            execution["in_flight"] = None
            resolution = "not_applied"
        # Assignment and save failures may be partial; never infer safe replay.
        else:
            execution["baseline_reconciled"] = False
            _persist(path, checkpoint, "blocked", action=action["id"], observation=observation)
            return execution_status(path)
    elif observed != expected:
        execution["baseline_reconciled"] = False
        _persist(path, checkpoint, "baseline_mismatch", observation=observation,
                 missing=sorted(expected - observed), unexpected=sorted(observed - expected))
        return execution_status(path)
    elif unverified:
        execution["completed"].extend(unverified)
        execution["unverified"] = []
        resolution = "batch_applied"
    if resolution == "not_applied" and _attempts(execution, action["id"]) >= 2:
        # Keep the intent open so a targeted manual repair can still be verified.
        execution["in_flight"] = action["id"]
        execution["baseline_reconciled"] = False
        _persist(path, checkpoint, "attempt_limit", action=action["id"], observation=observation)
        return execution_status(path)
    execution["baseline_reconciled"] = True
    _persist(path, checkpoint, "reconciled", resolution=resolution, observation=observation)
    return execution_status(path)


def _postcondition(manifest: dict, action: dict, observation: dict, execution: dict) -> bool:
    operation = action["operation"]
    if operation in ("add", "remove"):
        return True  # Full active membership was compared by the caller.
    if operation == "save":
        return observation.get("local_save") == expected_save_name(execution, manifest)
    targets = observation.get("targets", {})
    if operation == "set":
        return action["target"] in targets and targets[action["target"]] == action["value"]
    if action["section"] == "sync":
        return True
    expected = rebuild_snapshot(manifest)["targets"]
    return all(key in targets and targets[key] == value for key, value in expected.items()
               if key.startswith(action["section"] + "/"))


@_serialized
def begin_action(path: str | Path, action_id: str) -> dict[str, Any]:
    return _begin_action(path, action_id)


def _attempts(execution: dict, action_id: str) -> int:
    return sum(event["event"] == "intent" and event.get("action") == action_id
               for event in execution["journal"])


def _begin_action(path: str | Path, action_id: str) -> dict[str, Any]:
    checkpoint, execution, _ = _load(path)
    status = execution_status(path)
    if status["state"] != "ready" or status["next_action"]["id"] != action_id:
        raise ValueError("Action is not ready; reconcile and execute only the next action")
    action = status["next_action"]
    attempts = _attempts(execution, action_id)
    if attempts >= 2 and action["operation"] != "verify":
        raise ValueError("Action attempt limit reached; use targeted repair and reconcile")
    phase = "sync" if action["section"] == "sync" else "assign"
    checkpoint["phases"][phase]["status"] = "in_progress"
    checkpoint["phases"][phase]["updated_at"] = now_iso()
    execution["in_flight"] = action_id
    _persist(path, checkpoint, "intent", action=action_id)
    return deepcopy(action)


@_serialized
def execute_action(
    path: str | Path,
    action_id: str,
    execute: Callable[[dict[str, Any]], Any],
) -> Any:
    """Input success leaves an intent in flight until reconcile verifies it."""
    action = _begin_action(path, action_id)
    try:
        result = execute(action)
    except BaseException as exc:
        _record_input(path, "input_interrupted", action=action_id,
                      error=f"{type(exc).__name__}: {exc}")
        raise
    _record_input(path, "input_returned", action=action_id)
    return result


@_serialized
def execute_action_batch(
    path: str | Path,
    action_ids: list[str],
    execute: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    """Run a calibrated family with durable per-action receipts and one observation.

    Never mark input as verified, cross a family/phase boundary, or retry an
    interrupted transaction. The caller supplies a final aggregate observation.
    """
    checkpoint, execution, _ = _load(path)
    status = execution_status(path)
    if status["state"] != "ready":
        raise ValueError("Batch is not ready; reconcile before executing more input")
    allowed = status["next_batch"]
    if (not action_ids or action_ids != [a["id"] for a in allowed[:len(action_ids)]]
            or len(action_ids) > len(allowed)):
        raise ValueError("Batch must be an ordered prefix of the next action family")
    actions = allowed[:len(action_ids)]
    if any(a["operation"] in ("verify", "save") for a in actions):
        raise ValueError("Verification and local save use the single-action path")
    if any(_attempts(execution, a["id"]) >= 2 for a in actions):
        raise ValueError("Action attempt limit reached; use targeted repair and reconcile")
    phase = "sync" if actions[0]["section"] == "sync" else "assign"
    checkpoint["phases"][phase]["status"] = "in_progress"
    checkpoint["phases"][phase]["updated_at"] = now_iso()
    for action in actions:
        execution["in_flight"] = action["id"]
        _persist(path, checkpoint, "intent", action=action["id"])
        try:
            execute(deepcopy(action))
        except BaseException as exc:
            _persist(path, checkpoint, "input_interrupted", action=action["id"],
                     error=f"{type(exc).__name__}: {exc}")
            raise
        execution.setdefault("unverified", []).append(action["id"])
        execution["in_flight"] = None
        _persist(path, checkpoint, "input_returned", action=action["id"])
    return execution_status(path)


def _record_input(path: str | Path, event: str, **details: Any) -> None:
    checkpoint, _, _ = _load(path)
    _persist(path, checkpoint, event, **details)


def _persist(path: str | Path, checkpoint: dict, event: str, **details: Any) -> None:
    execution = checkpoint["execution"]
    execution["journal"].append({
        "sequence": len(execution["journal"]) + 1, "at": now_iso(),
        "event": event, **details,
    })
    # Derive legacy phase views from verified actions; local save gates assign.
    for phase, sections in (("sync", {"sync"}), ("assign", {"pitching", "vs_rhp", "vs_lhp", "save"})):
        actions = [a for a in execution["actions"] if a["section"] in sections]
        if all(a["id"] in execution["completed"] for a in actions):
            record = checkpoint["phases"][phase]
            if not record["missing"] and not record["ambiguous"]:
                if record["status"] != "complete":
                    record["updated_at"] = now_iso()
                record["status"] = "complete"
                manifest = load_manifest(checkpoint["manifest_path"])
                record["completed"] = [card["candidate_id"]
                                       for card in manifest["roster"]["membership"]]
        elif checkpoint["phases"][phase]["status"] == "complete":
            checkpoint["phases"][phase]["status"] = "in_progress"
            checkpoint["phases"][phase]["updated_at"] = now_iso()
    checkpoint["updated_at"] = now_iso()
    write_checkpoint(path, checkpoint)
