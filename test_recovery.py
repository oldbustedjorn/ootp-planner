import json
import sys

import pytest

import manage_roster_automation as cli
from ootp_opt.automation.execution import (
    begin_action, execute_action_batch, execution_status, reconcile_execution,
)
from ootp_opt.automation.recovery import resume_prompt, status_selection
from test_execution_batch import advance_until, apply, make_batch_run


@pytest.mark.parametrize("observed,desired,on,off", [
    ("active,inactive", "active", [], ["inactive"]),
    ("active,inactive", "inactive", [], ["active"]),
    ("active", "active", [], []),
    ("none", "active", ["active"], []),
    ("reserve,inactive", "all", ["active"], []),
])
def test_status_correction_changes_only_wrong_checkmarks(observed, desired, on, off):
    result = status_selection(observed, desired)
    assert result["turn_on"] == on
    assert result["turn_off"] == off
    assert not set(result["leave_on"]) & set(on + off)


@pytest.mark.parametrize("observed", ["eligible only", "active,active", "none,active", ""])
def test_status_caption_or_ambiguous_checkmarks_are_not_treated_as_selection(observed):
    with pytest.raises(ValueError):
        status_selection(observed, "active")


def test_prompt_updates_after_membership_and_never_replays_stale_card_list(tmp_path):
    path, _, observed = make_batch_run(tmp_path)
    before = path.read_bytes()
    initial = resume_prompt(path)
    assert "Continue only unfinished membership work" in initial
    assert path.read_bytes() == before
    advance_until(path, observed, "pitching/")
    before = path.read_bytes()
    current = resume_prompt(path)
    assert "Plan and membership sync are complete" in current
    assert "First unfinished action: pitching:" in current
    assert "status checkbox selections" not in current
    assert "prefer its current state" in current
    assert "Do not reuse old remaining-card lists" in current
    assert path.read_bytes() == before


def test_membership_drift_after_progress_does_not_request_old_baseline_restore(tmp_path):
    path, _, observed = make_batch_run(tmp_path)
    action = execution_status(path)["next_action"]
    begin_action(path, action["id"])
    apply(action, observed)
    reconcile_execution(path, observed)
    observed["membership"].pop()
    reconcile_execution(path, observed)
    prompt = resume_prompt(path)
    assert "Reconcile exact current CID/variant membership at journal progress" in prompt
    assert "do not restore the original baseline" in prompt


def test_pending_input_prompt_reconciles_earliest_unfinished_action(tmp_path):
    path, _, observed = make_batch_run(tmp_path)
    actions = execution_status(path)["next_batch"]
    execute_action_batch(path, [a["id"] for a in actions], lambda a: apply(a, observed))
    before = path.read_bytes()
    prompt = resume_prompt(path)
    assert f"First unfinished action: {actions[0]['id']}" in prompt
    assert "2 unverified" in prompt
    assert "reconcile the existing pending actions before any new input" in prompt
    assert path.read_bytes() == before


def test_save_only_and_completed_prompt_do_not_restart_roster_work(tmp_path):
    path, manifest, observed = make_batch_run(tmp_path)
    advance_until(path, observed, "local_save")
    prompt = resume_prompt(path)
    assert "Save verification is next" in prompt
    action = execution_status(path)["next_action"]
    begin_action(path, action["id"])
    observed["local_save"] = manifest["roster"]["name"]
    reconcile_execution(path, observed)
    before = path.read_bytes()
    assert "No resume work remains" in resume_prompt(path)
    assert "OOTP resume:" not in resume_prompt(path)
    assert path.read_bytes() == before


def test_resume_cli_file_output_cannot_overwrite_checkpoint(tmp_path, monkeypatch, capsys):
    path, _, _ = make_batch_run(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", "resume-prompt", str(path),
                                    "--output", str(path)])
    with pytest.raises(ValueError, match="overwrite"):
        cli.main()
    output = tmp_path / "resume.txt"
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", "resume-prompt", str(path),
                                    "--output", str(output)])
    cli.main()
    assert "Resume instructions:" in capsys.readouterr().out
    assert output.read_text() == resume_prompt(path)
    assert path.read_bytes() == before


def test_status_cli_only_plans_checkmark_correction(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", "status-selection",
                                    "--observed", "active,inactive", "--desired", "inactive"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["turn_off"] == ["active"]
    assert result["turn_on"] == []
