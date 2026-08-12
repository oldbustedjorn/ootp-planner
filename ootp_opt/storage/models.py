from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BuildMethod = Literal["greedy", "optimizer"]
RosterPlanStatus = Literal["draft", "active", "archived"]


@dataclass(frozen=True, slots=True)
class RosterPlanRecord:
    id: str
    command_name: str
    base_profile: str
    build_method: BuildMethod
    rules: dict[str, Any]
    display_title: str | None = None
    note: str | None = None
    plan_type: str = "pt_tournament"
    lifecycle_status: RosterPlanStatus = "active"
    validation_errors: dict[str, str] = field(default_factory=dict)
    source: str = "application"
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class BuildRunRecord:
    id: str
    roster_name: str
    build_type: str
    build_method: BuildMethod
    status: str
    model_version: str
    request: dict[str, Any]
    ruleset: dict[str, Any]
    source_record_id: str | None = None
    build_number: int | None = None
    preset_id: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    objective_score: float | None = None
    source_fingerprint: str | None = None
    created_at: str | None = None

    @property
    def roster_plan_id(self) -> str | None:
        return self.preset_id


# Compatibility names retained for the legacy importer and CLI surface.
PresetRecord = RosterPlanRecord
BuildRecord = BuildRunRecord
