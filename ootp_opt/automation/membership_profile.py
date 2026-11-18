"""Run-local CID filter calibration and journal-bound membership transactions.

The controller attests the screen state; this module does not recognize UI state
or navigate status checkboxes. Native timing and observed-success rules are unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from ootp_opt.automation.checkpoint import now_iso
from ootp_opt.automation.execution import _load, execution_status
from ootp_opt.automation.execution_batch import validate_execution_batch
from ootp_opt.automation.fast_executor import validate_fast_batch
from ootp_opt.automation.rebuild import card_key


def create_membership_profile(path, *, geometry, controls, screen_status, capture, note):
    checkpoint, _, _ = _load(path)
    action = execution_status(path)["next_action"]
    if not action or action["operation"] not in ("remove", "add"):
        raise ValueError("Membership profile requires a pending remove/add family")
    evidence = Path(capture)
    if not evidence.is_file() or not evidence.stat().st_size or not note.strip():
        raise ValueError("Calibration requires an inspected capture and verification note")
    profile = {
        "schema_version": 1, "checkpoint": str(Path(path).resolve()),
        "manifest_fingerprint": checkpoint["manifest_fingerprint"],
        "operation": action["operation"], "screen_status": screen_status,
        "client_geometry": list(geometry),
        "controls": {key: [list(p) for p in value] if key == "open" else list(value)
                     for key, value in controls.items()},
        "evidence": {"capture": str(evidence.resolve()),
                     "capture_sha256": sha256(evidence.read_bytes()).hexdigest(),
                     "note": note, "confirmed_at": now_iso()},
    }
    # Validate all coordinates, identity boundaries and next-action eligibility
    # before persisting a reusable calibration.
    compile_membership_batch(path, profile, screen_status=screen_status, first_only=True)
    return profile


def compile_membership_batch(path, profile, *, screen_status, first_only=False):
    checkpoint, execution, manifest = _load(path)
    if (profile.get("schema_version") != 1
            or profile.get("checkpoint") != str(Path(path).resolve())
            or profile.get("manifest_fingerprint") != checkpoint["manifest_fingerprint"]):
        raise ValueError("Membership profile belongs to another checkpoint or manifest")
    status = execution_status(path)
    if status["state"] != "ready":
        raise ValueError("Reconcile pending membership input before compiling another batch")
    operation = profile.get("operation")
    evidence = profile.get("evidence", {})
    if (operation == "add" and evidence.get("original_calibration")
            and evidence.get("capture_scope") != "controller_confirmed_exact_filter_result"):
        raise ValueError("Inherited addition profile needs a fresh confirmed filter result; recreate it")
    allowed_statuses = ("active",) if operation == "remove" else ("inactive", "all")
    if (screen_status not in allowed_statuses
            or screen_status != profile.get("screen_status")):
        raise ValueError("Collection status differs from calibration; restore or recalibrate")
    controls = profile.get("controls", {})
    if set(controls) - {"field", "activate", "apply", "confirm", "open"}:
        raise ValueError("Membership profile contains unsupported controls")
    if operation == "remove" and controls.get("confirm") is None:
        raise ValueError("Removal calibration requires the Proceed confirmation point")
    if operation == "add" and controls.get("confirm") is not None:
        raise ValueError("Addition calibration must not include a removal confirmation")
    if not controls.get("open") or controls.get("apply") is None:
        raise ValueError("Calibration requires a known CID dialog route and Apply point")
    cards = {card_key(c): c for c in manifest["roster"]["membership"]}
    baseline = execution["baseline"]["membership"]
    transactions = []
    for action in status["next_batch"]:
        if action["operation"] != operation:
            raise ValueError("Membership profile does not match the next action family")
        cid, variant = card_key(action["value"])
        unique = (sum(str(c["cid"]) == cid for c in baseline) == 1
                  if operation == "remove" else
                  cards.get((cid, variant), {}).get("owned_cid_copy_count") == 1)
        if not unique:
            break  # Never skip an ambiguous card to mutate later journal actions.
        native = {"op": "filter_batch", **deepcopy(controls), "values": [cid]}
        transactions.append({"action_id": action["id"], "actions": [native]})
        if first_only:
            break
    if not transactions:
        raise ValueError("Next membership card requires inspected CID/variant handling")
    plan = {"schema_version": 1, "manifest_id": manifest["manifest_id"],
            "section": "sync", "client_geometry": profile["client_geometry"],
            "transactions": transactions}
    validate_execution_batch(plan, manifest["manifest_id"], status["next_batch"])
    return plan


def reuse_membership_calibration(path, source, *, screen_status, note,
                                capture=None, confirm_filter_result=False):
    """Reuse removal geometry/CID controls, never its status or success evidence.

    A status transition requires a fresh, inspected exact-CID/variant result.
    Original geometry evidence alone cannot prove the filter still works.
    """
    checkpoint, _, _ = _load(path)
    if (source.get("schema_version") != 1
            or source.get("checkpoint") != str(Path(path).resolve())
            or source.get("manifest_fingerprint") != checkpoint["manifest_fingerprint"]
            or source.get("operation") != "remove"):
        raise ValueError("Reuse requires this checkpoint's verified removal profile")
    action = execution_status(path)["next_action"]
    if not action or action["operation"] != "add" or not note.strip():
        raise ValueError("Reuse requires pending additions and an unchanged-screen/status attestation")
    evidence = source.get("evidence", {})
    original = Path(evidence.get("capture", ""))
    if (not original.is_file() or not original.stat().st_size
            or sha256(original.read_bytes()).hexdigest() != evidence.get("capture_sha256")):
        raise ValueError("Original calibration capture is missing or changed; recalibrate")
    if not confirm_filter_result or not capture:
        raise ValueError("Status transition requires --capture and --confirm-filter-result after inspecting the exact CID/variant")
    inspected = Path(capture)
    if (not inspected.is_file() or not inspected.stat().st_size
            or inspected.resolve() == original.resolve()
            or sha256(inspected.read_bytes()).hexdigest() == evidence.get("capture_sha256")):
        raise ValueError("Use a fresh inspected filter result, not the inherited calibration capture")
    profile = deepcopy(source)
    profile.update(operation="add", screen_status=screen_status)
    profile["controls"].pop("confirm", None)
    profile["evidence"] = {
        "capture": str(inspected.resolve()), "capture_sha256": sha256(inspected.read_bytes()).hexdigest(),
        "capture_scope": "controller_confirmed_exact_filter_result",
        "filter_action_id": action["id"], "filter_card": deepcopy(action["value"]),
        "original_calibration": deepcopy(evidence),
        "note": note, "confirmed_at": now_iso(),
    }
    compile_membership_batch(path, profile, screen_status=screen_status, first_only=True)
    return profile


def compile_filter_preflight(path, profile, *, screen_status):
    """Open/type/apply only. Never include activation or removal confirmation.

    The plan excludes activation/Proceed steps. The caller must inspect the
    resulting rows before any roster mutation. No action is begun or verified.
    """
    checkpoint, execution, manifest = _load(path)
    if (profile.get("schema_version") != 1
            or profile.get("checkpoint") != str(Path(path).resolve())
            or profile.get("manifest_fingerprint") != checkpoint["manifest_fingerprint"]):
        raise ValueError("Filter preflight profile belongs to another checkpoint or manifest")
    index = len(execution["completed"])
    action = execution["actions"][index] if index < len(execution["actions"]) else None
    if not action or action["operation"] not in ("remove", "add"):
        raise ValueError("No pending membership card to filter")
    allowed = ("active",) if action["operation"] == "remove" else ("inactive", "all")
    if screen_status not in allowed:
        raise ValueError("Collection status is not suitable for the pending membership action")
    controls = profile["controls"]
    if not controls.get("open") or controls.get("apply") is None:
        raise ValueError("Filter preflight requires the CID dialog route and Apply point")
    plan = {"schema_version": 1, "manifest_id": manifest["manifest_id"], "section": "sync",
            "client_geometry": profile["client_geometry"], "actions": [
                {"op": "click_batch", "points": deepcopy(controls["open"]), "post_click_ms": 300},
                {"op": "type_text", "at": deepcopy(controls["field"]), "text": action["value"]["cid"]},
                {"op": "click_batch", "points": [deepcopy(controls["apply"])], "post_click_ms": 500},
            ]}
    validate_fast_batch(plan, manifest_id=manifest["manifest_id"], section="sync")
    return plan, action
