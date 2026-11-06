from types import SimpleNamespace

import pytest

from ootp_opt.services import saved_plan_build_service as service


def test_build_saved_plan_runs_optimizer_and_records_history(monkeypatch):
    preset = "roster_055_daily_low_gold_cap_1910135"
    monkeypatch.setattr(
        service,
        "load_runtime_config",
        lambda _: {
            "tournament_presets": {
                preset: {"base_profile": "playoff_pt", "build_method": "optimizer"}
            }
        },
    )
    monkeypatch.setattr(service, "load_application_build_records", lambda _: [])
    monkeypatch.setattr(
        service,
        "resolve_preset_build_metadata",
        lambda *_: {
            "roster_name": "Daily Low Gold Cap 1910135",
            "build_number": 55,
            "build_type": "pt_tournament",
            "html_output": "outputs/roster.html",
        },
    )
    method_updates = []
    monkeypatch.setattr(
        service,
        "update_application_preset_build_method",
        lambda **kwargs: method_updates.append(kwargs),
    )
    optimizer_solution = SimpleNamespace(objective_value=123.5)
    build_result = SimpleNamespace(
        html_output="outputs/roster.html",
        snapshot_path="outputs/roster.snapshot.json",
        automation_manifest_path="outputs/roster.automation.json",
        build_method="optimizer",
        optimization_solution=optimizer_solution,
        build_timing=SimpleNamespace(total_seconds=4.25),
    )
    requests = []
    monkeypatch.setattr(
        service,
        "build_roster",
        lambda request: requests.append(request) or build_result,
    )
    records = []
    monkeypatch.setattr(
        service,
        "append_application_build_record",
        lambda **kwargs: records.append(kwargs) or {"id": "build-id"},
    )

    built = service.build_saved_plan(preset)

    assert built.build_record_id == "build-id"
    assert built.roster_name == "Daily Low Gold Cap 1910135"
    assert requests[0].preset == preset
    assert requests[0].build_method == "optimizer"
    assert requests[0].roster_name == "Daily Low Gold Cap 1910135"
    assert records[0]["automation_manifest_path"] == "outputs/roster.automation.json"
    assert records[0]["objective_score"] == 123.5
    assert method_updates[0]["build_method"] == "optimizer"


def test_build_saved_plan_requires_stable_roster_metadata(monkeypatch):
    preset = "missing_metadata"
    monkeypatch.setattr(
        service,
        "load_runtime_config",
        lambda _: {"tournament_presets": {preset: {"base_profile": "playoff_pt"}}},
    )
    monkeypatch.setattr(service, "load_application_build_records", lambda _: [])
    monkeypatch.setattr(service, "resolve_preset_build_metadata", lambda *_: {})

    with pytest.raises(ValueError, match="missing its saved roster name"):
        service.build_saved_plan(preset)


def test_build_saved_plan_resolves_display_title(monkeypatch):
    preset = "roster_055_daily_low_gold_cap_1910135"
    monkeypatch.setattr(
        service,
        "load_runtime_config",
        lambda _: {
            "tournament_presets": {
                preset: {
                    "_gui_title": "Daily Low Gold Cap 1910135",
                    "_gui_roster_name": "Daily Low Gold Cap 1910135",
                    "base_profile": "playoff_pt",
                }
            }
        },
    )
    monkeypatch.setattr(service, "load_application_build_records", lambda _: [])
    monkeypatch.setattr(
        service,
        "resolve_preset_build_metadata",
        lambda *_: {
            "roster_name": "Daily Low Gold Cap 1910135",
            "build_number": 55,
            "build_type": "pt_tournament",
        },
    )
    monkeypatch.setattr(service, "update_application_preset_build_method", lambda **_: None)
    build_result = SimpleNamespace(
        html_output="outputs/roster.html",
        snapshot_path="outputs/roster.snapshot.json",
        automation_manifest_path="outputs/roster.automation.json",
        build_method="optimizer",
        optimization_solution=None,
        build_timing=SimpleNamespace(total_seconds=4.25),
    )
    monkeypatch.setattr(service, "build_roster", lambda _: build_result)
    monkeypatch.setattr(
        service,
        "append_application_build_record",
        lambda **_: {"id": "build-id"},
    )

    built = service.build_saved_plan("Daily Low Gold Cap 1910135")

    assert built.preset_name == preset
