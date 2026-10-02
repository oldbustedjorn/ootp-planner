"""Structured artifacts for resumable OOTP roster automation."""

from ootp_opt.automation.checkpoint import (
    initialize_checkpoint,
    load_checkpoint,
    update_phase,
)
from ootp_opt.automation.manifest import (
    automation_manifest_path,
    build_automation_manifest,
    load_manifest,
    validate_manifest,
    write_manifest,
)

__all__ = [
    "automation_manifest_path",
    "build_automation_manifest",
    "initialize_checkpoint",
    "load_checkpoint",
    "load_manifest",
    "update_phase",
    "validate_manifest",
    "write_manifest",
]
