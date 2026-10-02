from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal

from ootp_opt.automation.manifest import load_manifest


PhaseName = Literal["plan", "sync", "assign"]
PhaseStatus = Literal["pending", "in_progress", "complete", "failed"]
PHASES: tuple[PhaseName, ...] = ("plan", "sync", "assign")
STATUSES = {"pending", "in_progress", "complete", "failed"}


def checkpoint_path_for_manifest(manifest_path: str | Path) -> str:
    manifest = Path(manifest_path)
    return str(Path("state") / "automation" / f"{manifest.stem}.checkpoint.json")


def initialize_checkpoint(
    manifest_path: str | Path,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    destination = Path(checkpoint_path or checkpoint_path_for_manifest(manifest_path))
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
    }
    write_checkpoint(destination, checkpoint)
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
    phases = checkpoint.get("phases", {})
    for phase in PHASES:
        record = phases.get(phase)
        if not isinstance(record, dict):
            errors.append(f"phase {phase} is missing")
            continue
        if record.get("status") not in STATUSES:
            errors.append(f"phase {phase} has an invalid status")
    if errors:
        raise ValueError("Invalid automation checkpoint: " + "; ".join(errors))


def write_checkpoint(path: str | Path, checkpoint: dict[str, Any]) -> str:
    validate_checkpoint(checkpoint)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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
    return "\n".join(lines)
