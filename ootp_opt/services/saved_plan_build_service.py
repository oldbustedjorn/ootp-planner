from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ootp_opt.services.application_state_service import (
    append_application_build_record,
    load_application_build_records,
    load_runtime_config,
    record_application_roster_plan_error,
    update_application_preset_build_method,
)
from ootp_opt.services.preset_service import (
    infer_build_type_from_base_profile,
    preset_roster_output_path,
    resolve_preset_build_metadata,
)
from ootp_opt.services.roster_build_service import (
    RosterBuildRequest,
    RosterBuildResult,
    build_roster,
)


@dataclass(frozen=True, slots=True)
class SavedPlanBuildResult:
    preset_name: str
    roster_name: str
    build_number: int
    build_record_id: str
    result: RosterBuildResult


def build_saved_plan(
    plan_identifier: str,
    *,
    config_path: str | Path = "config.toml",
) -> SavedPlanBuildResult:
    """Run a saved plan without the GUI while preserving application history."""
    config_path = str(config_path)
    cfg = load_runtime_config(config_path)
    preset_name = resolve_saved_plan_name(cfg, plan_identifier)
    preset_cfg = dict(cfg.get("tournament_presets", {}).get(preset_name) or {})

    metadata = resolve_preset_build_metadata(
        preset_name,
        preset_cfg,
        load_application_build_records(config_path),
    )
    roster_name = str(metadata.get("roster_name") or "").strip()
    build_number = metadata.get("build_number")
    if not roster_name or not isinstance(build_number, int):
        raise ValueError(
            f"Roster plan '{preset_name}' is missing its saved roster name or build "
            "number; open it in the planner and save that metadata before CLI use."
        )

    base_profile = str(preset_cfg.get("base_profile") or "playoff_pt")
    build_type = str(
        metadata.get("build_type")
        or infer_build_type_from_base_profile(base_profile)
    )
    html_output = str(
        metadata.get("html_output") or preset_roster_output_path(preset_name)
    )
    update_application_preset_build_method(
        config_path=config_path,
        preset_name=preset_name,
        build_method="optimizer",
    )

    try:
        result = build_roster(
            RosterBuildRequest(
                config_path=config_path,
                preset=preset_name,
                html_output=html_output,
                build_method="optimizer",
                roster_name=roster_name,
            )
        )
        record = append_application_build_record(
            config_path=config_path,
            build_number=build_number,
            roster_name=roster_name,
            build_type=build_type,
            preset_name=preset_name,
            base_profile=base_profile,
            overrides={},
            html_output=result.html_output,
            snapshot_path=result.snapshot_path,
            automation_manifest_path=result.automation_manifest_path,
            status="success",
            build_method=result.build_method,
            objective_score=(
                result.optimization_solution.objective_value
                if result.optimization_solution is not None
                else None
            ),
            diagnostics={"total_seconds": result.build_timing.total_seconds},
        )
    except Exception as exc:
        try:
            record_application_roster_plan_error(
                config_path=config_path,
                plan_name=preset_name,
                error=exc,
            )
        except Exception:
            pass
        raise

    return SavedPlanBuildResult(
        preset_name=preset_name,
        roster_name=roster_name,
        build_number=build_number,
        build_record_id=str(record["id"]),
        result=result,
    )


def resolve_saved_plan_name(cfg: dict, plan_identifier: str) -> str:
    presets = cfg.get("tournament_presets", {})
    if plan_identifier in presets:
        return plan_identifier

    wanted = plan_identifier.strip().casefold()
    matches = [
        name
        for name, preset in presets.items()
        if wanted
        in {
            str(name).strip().casefold(),
            str(preset.get("_gui_title") or "").strip().casefold(),
            str(preset.get("_gui_roster_name") or "").strip().casefold(),
        }
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"Roster plan identifier '{plan_identifier}' is ambiguous: "
            + ", ".join(sorted(matches))
        )
    raise ValueError(
        f"Roster plan '{plan_identifier}' does not exist or is not active."
    )
