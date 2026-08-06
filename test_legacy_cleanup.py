import json
import zipfile

import pytest

from ootp_opt.storage.legacy_cleanup import (
    CleanupError,
    apply_legacy_cleanup,
    plan_legacy_cleanup,
    render_cleanup_plan,
)


def test_cleanup_preview_and_apply_back_up_before_removing_orphans(tmp_path):
    config_path, history_path = _write_cleanup_fixture(tmp_path)
    outputs = tmp_path / "outputs"
    old_html = outputs / "old_a.html"
    old_snapshot = outputs / "old_a.snapshot.json"
    shared_html = outputs / "current_a.html"
    current_b = outputs / "current_b.html"
    for path in (old_html, old_snapshot, shared_html, current_b):
        path.write_text(path.name, encoding="utf-8")

    plan = plan_legacy_cleanup(config_path, history_path)

    assert plan.can_apply
    assert len(plan.retained_records) == 2
    assert plan.removed_record_count == 2
    assert set(plan.delete_paths) == {old_html.resolve(), old_snapshot.resolve()}
    assert shared_html.resolve() in plan.shared_paths
    assert "No files were changed" in render_cleanup_plan(plan)
    assert old_html.exists()

    result = apply_legacy_cleanup(plan, tmp_path / "state" / "backups")

    assert result.retained_record_count == 2
    assert result.removed_record_count == 2
    assert set(result.deleted_paths) == {old_html.resolve(), old_snapshot.resolve()}
    assert result.failed_paths == ()
    assert not old_html.exists()
    assert not old_snapshot.exists()
    assert shared_html.exists()
    assert current_b.exists()
    retained = json.loads(history_path.read_text(encoding="utf-8"))
    assert [record["created_at"] for record in retained] == [
        "2026-08-05T12:00:00",
        "2026-08-05T11:00:00",
    ]

    with zipfile.ZipFile(result.backup_path) as archive:
        names = set(archive.namelist())
        assert "source/config.toml" in names
        assert "source/roster_build_registry.json" in names
        assert "cleanup_manifest.json" in names
        assert "artifacts/old_a.html" in names
        original_history = json.loads(
            archive.read("source/roster_build_registry.json")
        )
        assert len(original_history) == 4


def test_cleanup_rejects_plan_after_history_changes(tmp_path):
    config_path, history_path = _write_cleanup_fixture(tmp_path)
    plan = plan_legacy_cleanup(config_path, history_path)
    history_path.write_text("[]", encoding="utf-8")

    with pytest.raises(CleanupError, match="History changed"):
        apply_legacy_cleanup(plan, tmp_path / "backups")

    assert not (tmp_path / "backups").exists()


def test_cleanup_plan_blocks_active_preset_without_history(tmp_path):
    config_path = tmp_path / "config.toml"
    history_path = tmp_path / "outputs" / "roster_build_registry.json"
    history_path.parent.mkdir()
    config_path.write_text(
        """
[tournament_presets.missing]
base_profile = "playoff_pt"
""".strip(),
        encoding="utf-8",
    )
    history_path.write_text("[]", encoding="utf-8")

    plan = plan_legacy_cleanup(config_path, history_path)

    assert not plan.can_apply
    assert plan.error_count == 1
    with pytest.raises(CleanupError, match="contains errors"):
        apply_legacy_cleanup(plan, tmp_path / "backups")


def test_cleanup_ignores_artifacts_outside_output_directory(tmp_path):
    config_path, history_path = _write_cleanup_fixture(tmp_path)
    external = tmp_path / "external.html"
    external.write_text("do not delete", encoding="utf-8")
    history = json.loads(history_path.read_text(encoding="utf-8"))
    history[-1]["html_output"] = str(external)
    history_path.write_text(json.dumps(history), encoding="utf-8")

    plan = plan_legacy_cleanup(config_path, history_path)

    assert external.resolve() not in plan.delete_paths
    assert any("outside the output directory" in issue.message for issue in plan.issues)
    assert external.exists()


def _write_cleanup_fixture(tmp_path):
    config_path = tmp_path / "config.toml"
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    history_path = outputs / "roster_build_registry.json"
    config_path.write_text(
        """
[tournament_presets.preset_a]
base_profile = "playoff_pt"
_gui_roster_name = "Roster A"
_gui_build_number = 1
_gui_html_output = "outputs/current_a.html"

[tournament_presets.preset_b]
base_profile = "playoff_pt"
_gui_roster_name = "Roster B"
_gui_build_number = 2
_gui_html_output = "outputs/current_b.html"
""".strip(),
        encoding="utf-8",
    )
    history = [
        {
            "id": "001-a",
            "build_number": 1,
            "created_at": "2026-08-05T12:00:00",
            "roster_name": "Roster A",
            "preset_name": "preset_a",
            "status": "success",
            "html_output": "outputs/current_a.html",
            "snapshot_path": "outputs/current_a.snapshot.json",
        },
        {
            "id": "002-b",
            "build_number": 2,
            "created_at": "2026-08-05T11:00:00",
            "roster_name": "Roster B",
            "preset_name": "preset_b",
            "status": "success",
            "html_output": "outputs/current_b.html",
            "snapshot_path": "outputs/current_b.snapshot.json",
        },
        {
            "id": "001-a",
            "build_number": 1,
            "created_at": "2026-08-04T12:00:00",
            "roster_name": "Roster A",
            "preset_name": "preset_a",
            "status": "success",
            "html_output": "outputs/current_a.html",
            "snapshot_path": "outputs/current_a.snapshot.json",
        },
        {
            "id": "001-a-old",
            "build_number": 1,
            "created_at": "2026-08-03T12:00:00",
            "roster_name": "Roster A",
            "status": "success",
            "html_output": "outputs/old_a.html",
            "snapshot_path": "outputs/old_a.snapshot.json",
        },
    ]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return config_path, history_path
