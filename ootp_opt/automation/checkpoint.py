from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal

from ootp_opt.automation.manifest import load_manifest


PhaseName = Literal["plan", "sync", "assign"]
PhaseStatus = Literal["pending", "in_progress", "complete", "failed"]
PHASES: tuple[PhaseName, ...] = ("plan", "sync", "assign")
STATUSES = {"pending", "in_progress", "complete", "failed"}
ASSIGNMENT_SECTIONS = ("pitching", "vs_rhp", "vs_lhp")
MAX_ASSIGNMENT_REPAIR_BATCHES = 3
MAX_REPAIR_ATTEMPTS_PER_ITEM = 2


def checkpoint_path_for_manifest(manifest_path: str | Path) -> str:
    manifest = Path(manifest_path)
    return str(Path("state") / "automation" / f"{manifest.stem}.checkpoint.json")


def initialize_checkpoint(
    manifest_path: str | Path,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    destination = Path(checkpoint_path or checkpoint_path_for_manifest(manifest_path))
    if destination.exists():
        existing = load_checkpoint(destination)
        if existing["manifest_fingerprint"] != manifest["fingerprint"]:
            raise ValueError("Checkpoint already exists for another manifest")
        if manifest.get("rebuild", {}).get("baseline") and "execution" not in existing:
            from ootp_opt.automation.execution import initialize_execution
            initialize_execution(destination)
            return load_checkpoint(destination)
        return existing
    checkpoint = {
        "schema_version": 1,
        "manifest_path": str(manifest_path),
        "manifest_fingerprint": manifest["fingerprint"],
        "updated_at": now_iso(),
        "phases": {
            "plan": phase_record("complete"),
            "sync": phase_record("pending"),
            "assign": phase_record("pending"),
        },
        "assignment_repairs": {section: 0 for section in ASSIGNMENT_SECTIONS},
        "assignment_repair_items": {section: {} for section in ASSIGNMENT_SECTIONS},
        "assignment_repair_strategies": {
            section: {} for section in ASSIGNMENT_SECTIONS
        },
    }
    write_checkpoint(destination, checkpoint)
    if manifest.get("rebuild", {}).get("baseline"):
        # Import locally: execution uses the legacy checkpoint adapter too.
        from ootp_opt.automation.execution import initialize_execution
        initialize_execution(destination)
        return load_checkpoint(destination)
    return checkpoint


def load_checkpoint(
    checkpoint_path: str | Path,
    *,
    verify_manifest: bool = True,
) -> dict[str, Any]:
    checkpoint = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))
    validate_checkpoint(checkpoint)
    if verify_manifest:
        manifest = load_manifest(checkpoint["manifest_path"])
        if manifest["fingerprint"] != checkpoint["manifest_fingerprint"]:
            raise ValueError(
                "Checkpoint belongs to a different manifest revision; initialize a "
                "new checkpoint."
            )
    return checkpoint


def update_phase(
    checkpoint_path: str | Path,
    phase: PhaseName,
    status: PhaseStatus,
    *,
    completed: list[str] | None = None,
    missing: list[str] | None = None,
    ambiguous: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    checkpoint = load_checkpoint(checkpoint_path)
    if phase not in PHASES:
        raise ValueError(f"Unknown automation phase: {phase}")
    if status not in STATUSES:
        raise ValueError(f"Unknown automation phase status: {status}")
    if "execution" in checkpoint and phase in ("sync", "assign"):
        if status == "complete":
            sections = {"sync"} if phase == "sync" else {"pitching", "vs_rhp", "vs_lhp", "save"}
            execution = checkpoint["execution"]
            if any(action["id"] not in execution["completed"]
                   for action in execution["actions"] if action["section"] in sections):
                raise ValueError("Phase completion requires verified rebuild actions and local save")
    previous = checkpoint["phases"][phase]
    merged_completed = merge_unique(previous.get("completed", []), completed or [])
    merged_missing = [
        item
        for item in merge_unique(previous.get("missing", []), missing or [])
        if item not in merged_completed
    ]
    merged_ambiguous = [
        item
        for item in merge_unique(previous.get("ambiguous", []), ambiguous or [])
        if item not in merged_completed
    ]
    checkpoint["phases"][phase] = {
        "status": status,
        "completed": merged_completed,
        "missing": merged_missing,
        "ambiguous": merged_ambiguous,
        "notes": merge_unique(previous.get("notes", []), notes or []),
        "updated_at": now_iso(),
    }
    checkpoint["updated_at"] = now_iso()
    write_checkpoint(checkpoint_path, checkpoint)
    return checkpoint


def validate_checkpoint(checkpoint: dict[str, Any]) -> None:
    errors: list[str] = []
    if checkpoint.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not checkpoint.get("manifest_path"):
        errors.append("manifest_path is required")
    if not checkpoint.get("manifest_fingerprint"):
        errors.append("manifest_fingerprint is required")
    if "execution" in checkpoint and not valid_execution_record(checkpoint["execution"]):
        errors.append("invalid rebuild execution ledger")
    phases = checkpoint.get("phases", {})
    for phase in PHASES:
        record = phases.get(phase)
        if not isinstance(record, dict):
            errors.append(f"phase {phase} is missing")
            continue
        if record.get("status") not in STATUSES:
            errors.append(f"phase {phase} has an invalid status")
    repairs = checkpoint.get("assignment_repairs", {})
    if not isinstance(repairs, dict):
        errors.append("assignment_repairs must be an object")
    else:
        for section in ASSIGNMENT_SECTIONS:
            count = repairs.get(section, 0)
            if (
                not isinstance(count, int)
                or count < 0
                or count > MAX_ASSIGNMENT_REPAIR_BATCHES
            ):
                errors.append(
                    f"assignment repair count for {section} must be between 0 and "
                    f"{MAX_ASSIGNMENT_REPAIR_BATCHES}"
                )
    repair_items = checkpoint.get("assignment_repair_items", {})
    if not isinstance(repair_items, dict):
        errors.append("assignment_repair_items must be an object")
    else:
        for section in ASSIGNMENT_SECTIONS:
            items = repair_items.get(section, {})
            if not isinstance(items, dict):
                errors.append(f"assignment repair items for {section} must be an object")
                continue
            for item, attempts in items.items():
                if (
                    not isinstance(item, str)
                    or not item
                    or not isinstance(attempts, int)
                    or attempts < 1
                    or attempts > MAX_REPAIR_ATTEMPTS_PER_ITEM
                ):
                    errors.append(f"invalid assignment repair item for {section}")
    repair_strategies = checkpoint.get("assignment_repair_strategies", {})
    if not isinstance(repair_strategies, dict):
        errors.append("assignment_repair_strategies must be an object")
    else:
        for section in ASSIGNMENT_SECTIONS:
            strategies = repair_strategies.get(section, {})
            if not isinstance(strategies, dict):
                errors.append(
                    f"assignment repair strategies for {section} must be an object"
                )
                continue
            for item, values in strategies.items():
                if (
                    not isinstance(item, str)
                    or not item
                    or not isinstance(values, list)
                    or not values
                    or len(values) > MAX_REPAIR_ATTEMPTS_PER_ITEM
                    or len(values) != len(set(values))
                    or any(not isinstance(value, str) or not value for value in values)
                ):
                    errors.append(f"invalid assignment repair strategy for {section}")
    if errors:
        raise ValueError("Invalid automation checkpoint: " + "; ".join(errors))


def valid_execution_record(execution: Any) -> bool:
    try:
        ids = [action["id"] for action in execution["actions"]]
        completed = execution["completed"]
        unverified = execution.get("unverified", [])
        next_index = len(completed) + len(unverified)
        return (
            execution["schema_version"] == 1
            and isinstance(execution["baseline"]["membership"], list)
            and isinstance(execution["baseline"]["targets"], dict)
            and isinstance(execution["baseline_reconciled"], bool)
            and isinstance(execution["actions"], list) and bool(ids)
            and all(isinstance(action_id, str) and action_id for action_id in ids)
            and len(set(ids)) == len(ids)
            and isinstance(completed, list) and len(completed) <= len(ids)
            and completed == ids[:len(completed)]
            and isinstance(unverified, list) and len(unverified) <= 30 and next_index <= len(ids)
            and unverified == ids[len(completed):next_index]
            and (execution["in_flight"] is None or (
                next_index < len(ids) and execution["in_flight"] == ids[next_index]
            ))
            and isinstance(execution["journal"], list)
            and all(isinstance(event, dict) and event["sequence"] == index
                    and isinstance(event["event"], str)
                    for index, event in enumerate(execution["journal"], start=1))
        )
    except (KeyError, TypeError):
        return False


def write_checkpoint(path: str | Path, checkpoint: dict[str, Any]) -> str:
    validate_checkpoint(checkpoint)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=destination.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return str(destination)


def phase_record(status: PhaseStatus) -> dict[str, Any]:
    return {
        "status": status,
        "completed": [],
        "missing": [],
        "ambiguous": [],
        "notes": [],
        "updated_at": now_iso(),
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def merge_unique(existing: list[str], additions: list[str]) -> list[str]:
    return list(dict.fromkeys([*existing, *additions]))


def record_assignment_repair(
    checkpoint_path: str | Path,
    section: str,
    items: list[str],
    strategy: str,
) -> dict[str, Any]:
    checkpoint = load_checkpoint(checkpoint_path)
    if section not in ASSIGNMENT_SECTIONS:
        raise ValueError(f"Unknown assignment section: {section}")
    if checkpoint["phases"]["assign"]["status"] != "in_progress":
        raise ValueError("Assignment phase must be in_progress before a repair batch")
    normalized_items = merge_unique([], [item.strip() for item in items if item.strip()])
    if not normalized_items:
        raise ValueError("At least one specific repair item is required")
    normalized_strategy = strategy.strip()
    if not normalized_strategy:
        raise ValueError("A specific repair strategy is required")

    repairs = checkpoint.setdefault("assignment_repairs", {})
    attempts = int(repairs.get(section, 0))
    if attempts >= MAX_ASSIGNMENT_REPAIR_BATCHES:
        raise ValueError(
            f"Repair batch limit reached for {section}; stop and report remaining "
            "discrepancies."
        )
    repair_items = checkpoint.setdefault("assignment_repair_items", {})
    section_items = repair_items.setdefault(section, {})
    exhausted = [
        item
        for item in normalized_items
        if int(section_items.get(item, 0)) >= MAX_REPAIR_ATTEMPTS_PER_ITEM
    ]
    if exhausted:
        raise ValueError(
            "Repair attempt limit reached for: " + ", ".join(exhausted)
        )
    repair_strategies = checkpoint.setdefault("assignment_repair_strategies", {})
    section_strategies = repair_strategies.setdefault(section, {})
    repeated = [
        item
        for item in normalized_items
        if normalized_strategy in section_strategies.get(item, [])
    ]
    if repeated:
        raise ValueError(
            "Repair strategy already used for: " + ", ".join(repeated)
        )

    repairs[section] = attempts + 1
    for item in normalized_items:
        section_items[item] = int(section_items.get(item, 0)) + 1
        section_strategies.setdefault(item, []).append(normalized_strategy)
    checkpoint["updated_at"] = now_iso()
    write_checkpoint(checkpoint_path, checkpoint)
    return checkpoint


def format_checkpoint_summary(checkpoint: dict[str, Any]) -> str:
    validate_checkpoint(checkpoint)
    lines = [
        f"Manifest: {checkpoint['manifest_path']}",
        f"Fingerprint: {checkpoint['manifest_fingerprint'][:16]}",
    ]
    next_phase = None
    for phase in PHASES:
        record = checkpoint["phases"][phase]
        lines.append(
            f"{phase}: {record['status']} | "
            f"completed={len(record['completed'])} "
            f"missing={len(record['missing'])} "
            f"ambiguous={len(record['ambiguous'])}"
        )
        if next_phase is None and record["status"] != "complete":
            next_phase = phase
    lines.append(f"Next phase: {next_phase or 'none'}")
    if "execution" in checkpoint:
        execution = checkpoint["execution"]
        index = len(execution["completed"])
        actions = execution["actions"]
        next_action = actions[index]["id"] if index < len(actions) else "none"
        lines.append(f"Rebuild actions: {index}/{len(actions)} | next={next_action} | "
                     f"in_flight={execution['in_flight'] or 'none'} | "
                     f"awaiting_verification={len(execution.get('unverified', []))}")
    repairs = checkpoint.get("assignment_repairs", {})
    lines.append(
        "Assignment repairs: "
        + " ".join(
            f"{section}={repairs.get(section, 0)}"
            for section in ASSIGNMENT_SECTIONS
        )
    )
    return "\n".join(lines)
