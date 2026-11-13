from copy import deepcopy
import json

import pytest

from ootp_opt.automation import checkpoint as checkpoint_module
from ootp_opt.automation.checkpoint import initialize_checkpoint, load_checkpoint, update_phase
from ootp_opt.automation.execution import (
    _writer_lock,
    begin_action, compile_rebuild_actions, execute_action, execution_status,
    initialize_execution, reconcile_execution,
    bind_local_save_name,
)
from ootp_opt.automation.manifest import manifest_fingerprint, write_manifest
from ootp_opt.automation.rebuild import build_rebuild_delta, rebuild_snapshot
from test_automation_manifest import build_manifest


@pytest.fixture
def run(tmp_path):
    previous = build_manifest()
    current = deepcopy(previous)
    # Replacing an unused bench card isolates membership recovery tests.
    old = current["roster"]["membership"][12]
    old["cid"] = "9999"
    old["candidate_id"] = "new-card"
    # Update every reference so final aggregate verification remains meaningful.
    def replace(value):
        if isinstance(value, dict):
            if value.get("cid") == previous["roster"]["membership"][12]["cid"]:
                value.update(deepcopy(old))
            else:
                for item in value.values():
                    replace(item)
        elif isinstance(value, list):
            for item in value:
                replace(item)
    replace(current)
    current["lineups"]["vs_rhp"]["starters"].reverse()
    current["lineups"]["vs_rhp"]["starters"][0]["depth"][0]["condition"] = "Always"
    current["rebuild"] = build_rebuild_delta(previous, current)
    current["fingerprint"] = manifest_fingerprint(current)
    current["manifest_id"] = current["fingerprint"][:16]
    manifest_path = tmp_path / "manifest.json"
    path = tmp_path / "checkpoint.json"
    write_manifest(manifest_path, current)
    initialize_checkpoint(manifest_path, path)
    initialize_execution(path)
    return path, previous, current


def test_deterministic_plan_and_depth_before_order(run):
    _, _, manifest = run
    actions = compile_rebuild_actions(manifest)
    assert actions == compile_rebuild_actions(deepcopy(manifest))
    assert len({action["id"] for action in actions}) == len(actions)
    assert [action["operation"] for action in actions[:3]] == ["remove", "add", "verify"]
    assert actions[-1]["operation"] == "save"
    changed = deepcopy(manifest)
    changed["lineups"]["vs_rhp"]["starters"][-1]["batting_order"] = 99
    actions = compile_rebuild_actions(changed)
    targets = [action["target"] for action in actions]
    depth_index = next(i for i, target in enumerate(targets) if "/depth/" in target)
    assert depth_index < targets.index("vs_rhp/batting_order")


def test_variant_mismatch_blocks_without_mutation_and_reconciles(run):
    path, previous, _ = run
    observed = rebuild_snapshot(previous)
    observed["membership"][0]["variant"] = not observed["membership"][0]["variant"]
    assert reconcile_execution(path, observed)["state"] == "needs_baseline"
    action_id = execution_status(path)["next_action"]["id"]
    called = []
    with pytest.raises(ValueError, match="not ready"):
        execute_action(path, action_id, called.append)
    assert called == []
    assert reconcile_execution(path, rebuild_snapshot(previous))["state"] == "ready"


def test_input_failure_after_effect_is_recovered_without_replay(run):
    path, previous, _ = run
    observed = rebuild_snapshot(previous)
    reconcile_execution(path, observed)
    action = execution_status(path)["next_action"]

    def interrupted(action):
        assert load_checkpoint(path)["execution"]["journal"][-1]["event"] == "intent"
        observed["membership"].remove(action["value"])
        raise RuntimeError("lost response")

    with pytest.raises(RuntimeError, match="lost response"):
        execute_action(path, action["id"], interrupted)
    assert execution_status(path)["state"] == "needs_reconciliation"
    with pytest.raises(ValueError):
        begin_action(path, action["id"])
    result = reconcile_execution(path, observed)
    assert result["completed"] == 1
    assert result["next_action"]["operation"] == "add"
    assert load_checkpoint(path)["execution"]["journal"][-1]["resolution"] == "applied"


def test_unapplied_membership_input_can_retry_with_bounded_attempts(run):
    path, previous, _ = run
    observed = rebuild_snapshot(previous)
    reconcile_execution(path, observed)
    action_id = execution_status(path)["next_action"]["id"]
    for _ in range(2):
        begin_action(path, action_id)
        assert reconcile_execution(path, observed)["completed"] == 0
    with pytest.raises(ValueError, match="not ready"):
        begin_action(path, action_id)
    assert execution_status(path)["last_event"]["event"] == "attempt_limit"
    # After the controller's exact targeted repair, the open intent can resolve.
    action = execution_status(path)["next_action"]
    observed["membership"].remove(action["value"])
    assert reconcile_execution(path, observed)["completed"] == 1


def test_full_execution_requires_aggregate_verification_and_save(run):
    path, previous, current = run
    observed = rebuild_snapshot(previous)
    reconcile_execution(path, observed)
    while True:
        action = execution_status(path)["next_action"]
        if action["operation"] == "save":
            break
        begin_action(path, action["id"])
        if action["operation"] == "remove":
            observed["membership"].remove(action["value"])
        elif action["operation"] == "add":
            observed["membership"].append(action["value"])
        elif action["operation"] == "set":
            observed["targets"][action["target"]] = action["value"]
        assert reconcile_execution(path, observed)["in_flight"] is None
    with pytest.raises(ValueError, match="verified rebuild actions"):
        update_phase(path, "assign", "complete")
    begin_action(path, action["id"])
    assert reconcile_execution(path, observed)["state"] == "needs_reconciliation"
    observed["local_save"] = current["roster"]["name"]
    assert reconcile_execution(path, observed)["state"] == "complete"
    checkpoint = load_checkpoint(path)
    assert checkpoint["phases"]["assign"]["status"] == "complete"
    assert checkpoint["phases"]["sync"]["status"] == "complete"
    assert [event["sequence"] for event in checkpoint["execution"]["journal"]] == list(
        range(1, len(checkpoint["execution"]["journal"]) + 1)
    )


@pytest.mark.parametrize("bind_before", [True, False])
def test_existing_local_name_preserves_plan_and_recovers_save_without_replay(run, bind_before):
    from ootp_opt.automation.observation_io import prepare_observation
    from ootp_opt.automation.execution_io import compact_execution_receipt

    path, previous, current = run
    name = "Wed Ice to See You 1490029"
    capture = path.parent / "viewed.bmp"
    capture.write_bytes(b"controller inspected capture")
    before = load_checkpoint(path)
    manifest_path = path.parent / "manifest.json"
    original_manifest = manifest_path.read_bytes()

    def bind():
        prior = load_checkpoint(path)["execution"]
        bind_local_save_name(path, name, capture=capture, note="Verified existing roster and rules")
        execution = load_checkpoint(path)["execution"]
        for key in ("actions", "completed", "unverified", "in_flight", "baseline_reconciled"):
            assert execution[key] == prior[key]
        assert execution["local_save_binding"]["manifest_name"] == current["roster"]["name"]
        assert execution["journal"][-1]["event"] == "local_save_name_bound"
        saved = path.read_bytes()
        bind_local_save_name(path, name, capture=capture, note="Same roster")
        assert path.read_bytes() == saved
        with pytest.raises(ValueError, match="already bound"):
            bind_local_save_name(path, "Another roster", capture=capture, note="Different")

    if bind_before:
        bind()
    observed = rebuild_snapshot(previous)
    reconcile_execution(path, observed)
    while (action := execution_status(path)["next_action"])["operation"] != "save":
        begin_action(path, action["id"])
        if action["operation"] == "remove":
            observed["membership"].remove(action["value"])
        elif action["operation"] == "add":
            observed["membership"].append(action["value"])
        elif action["operation"] == "set":
            observed["targets"][action["target"]] = action["value"]
        reconcile_execution(path, observed)
    begin_action(path, action["id"])
    observed["local_save"] = name
    if not bind_before:
        assert reconcile_execution(path, observed)["state"] == "needs_reconciliation"
        bind()
    draft = prepare_observation(path, "save")
    pending = prepare_observation(path, "pending")
    assert draft["expected"]["local_save"] == pending["expected"]["local_save"] == name
    observed["local_save"] = "Wrong name 1490029"
    blocked = reconcile_execution(path, observed)
    assert blocked["in_flight"] == action["id"]
    receipt = compact_execution_receipt(blocked, checkpoint_path=path)
    assert f'expected="{name}"' in receipt
    observed["local_save"] = name
    wrong_members = deepcopy(observed)
    wrong_members["membership"].pop()
    assert reconcile_execution(path, wrong_members)["state"] == "needs_reconciliation"
    assert reconcile_execution(path, observed)["state"] == "complete"
    after = load_checkpoint(path)
    assert after["execution"]["actions"] == before["execution"]["actions"]
    assert manifest_path.read_bytes() == original_manifest
    assert after["phases"]["assign"]["status"] == "complete"
    assert sum(e["event"] == "intent" and e.get("action") == action["id"]
               for e in after["execution"]["journal"]) == 1


@pytest.mark.parametrize("name,note,capture_exists", [
    ("", "verified", True), (" padded ", "verified", True),
    ("Local name", "", True), ("Local name", "verified", False),
])
def test_local_save_binding_requires_identity_evidence(run, name, note, capture_exists):
    path, _, _ = run
    capture = path.parent / "capture.bmp"
    if capture_exists:
        capture.write_bytes(b"viewed")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        bind_local_save_name(path, name, capture=capture, note=note)
    assert path.read_bytes() == before


def test_init_preserves_journal_and_atomic_write_survives_failure(run, monkeypatch):
    path, previous, _ = run
    reconcile_execution(path, rebuild_snapshot(previous))
    before = path.read_bytes()
    initialize_checkpoint(load_checkpoint(path)["manifest_path"], path)
    initialize_execution(path)
    assert path.read_bytes() == before
    def fail(*args):
        raise OSError("disk error")
    monkeypatch.setattr(checkpoint_module.os, "replace", fail)
    with pytest.raises(OSError, match="disk error"):
        begin_action(path, execution_status(path)["next_action"]["id"])
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))


def test_execution_rejects_tampered_actions(run):
    path, _, _ = run
    checkpoint = load_checkpoint(path)
    checkpoint["execution"]["actions"].reverse()
    path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        execution_status(path)


def test_duplicate_observation_is_ambiguous(run):
    path, previous, _ = run
    observed = rebuild_snapshot(previous)
    observed["membership"].append(observed["membership"][0])
    with pytest.raises(ValueError, match="Ambiguous duplicate"):
        reconcile_execution(path, observed)


def test_legacy_checkpoint_is_readable_without_execution(run, tmp_path):
    _, _, current = run
    del current["rebuild"]["baseline"]
    current["fingerprint"] = manifest_fingerprint(current)
    current["manifest_id"] = current["fingerprint"][:16]
    manifest_path = tmp_path / "legacy.json"
    path = tmp_path / "legacy.checkpoint.json"
    write_manifest(manifest_path, current)
    initialize_checkpoint(manifest_path, path)
    assert load_checkpoint(path)["phases"]["plan"]["status"] == "complete"
    with pytest.raises(ValueError, match="baseline snapshot"):
        initialize_execution(path)


def test_legacy_execution_uses_verified_archived_baseline(run, tmp_path):
    _, previous, current = run
    baseline_path = tmp_path / "previous.json"
    write_manifest(baseline_path, previous)
    del current["rebuild"]["baseline"]
    current["rebuild"]["previous_artifacts"] = {"manifest": str(baseline_path)}
    current["fingerprint"] = manifest_fingerprint(current)
    current["manifest_id"] = current["fingerprint"][:16]
    manifest_path = tmp_path / "archived.json"
    path = tmp_path / "archived.checkpoint.json"
    write_manifest(manifest_path, current)
    initialize_checkpoint(manifest_path, path)
    before = manifest_path.read_bytes()
    assert initialize_execution(path)["state"] == "needs_baseline"
    assert reconcile_execution(path, rebuild_snapshot(previous))["state"] == "ready"
    assert manifest_path.read_bytes() == before


def test_legacy_completed_phases_skip_actions_but_require_local_save(run, tmp_path):
    _, _, current = run
    manifest_path = tmp_path / "completed.json"
    write_manifest(manifest_path, current)
    path = tmp_path / "completed.checkpoint.json"
    checkpoint = initialize_checkpoint(manifest_path, path)
    del checkpoint["execution"]  # A legacy run recorded only phase-level progress.
    checkpoint["phases"]["sync"]["status"] = "complete"
    checkpoint["phases"]["assign"]["status"] = "complete"
    checkpoint_module.write_checkpoint(path, checkpoint)
    result = initialize_execution(path)
    assert result["next_action"]["operation"] == "save"
    assert load_checkpoint(path)["phases"]["assign"]["status"] == "in_progress"
    observed = rebuild_snapshot(current)
    assert reconcile_execution(path, observed)["state"] == "ready"


def test_second_checkpoint_writer_is_rejected(run):
    path, previous, _ = run
    with _writer_lock(path):
        with pytest.raises(RuntimeError, match="writer is active"):
            reconcile_execution(path, rebuild_snapshot(previous))
    assert reconcile_execution(path, rebuild_snapshot(previous))["state"] == "ready"


def test_assignment_input_success_requires_evidence_and_explicit_retry(run):
    path, previous, _ = run
    observed = rebuild_snapshot(previous)
    reconcile_execution(path, observed)
    while execution_status(path)["next_action"]["operation"] != "set":
        action = execution_status(path)["next_action"]
        begin_action(path, action["id"])
        if action["operation"] == "remove":
            observed["membership"].remove(action["value"])
        elif action["operation"] == "add":
            observed["membership"].append(action["value"])
        reconcile_execution(path, observed)
    action = execution_status(path)["next_action"]
    execute_action(path, action["id"], lambda _: None)
    assert execution_status(path)["state"] == "needs_reconciliation"
    assert reconcile_execution(path, observed)["state"] == "needs_reconciliation"
    assert reconcile_execution(path, observed, retry_unapplied=True)["state"] == "ready"
    begin_action(path, action["id"])
    observed["targets"][action["target"]] = action["value"]
    assert reconcile_execution(path, observed)["state"] == "ready"


def test_cli_journals_native_input_without_claiming_verification(run, monkeypatch, capsys):
    import sys
    import manage_roster_automation as cli
    path, previous, current = run
    reconcile_execution(path, rebuild_snapshot(previous))
    action = execution_status(path)["next_action"]
    batch_path = path.parent / "batch.json"
    batch_path.write_text(json.dumps({
        "schema_version": 1, "manifest_id": current["manifest_id"], "section": "sync",
        "client_geometry": [0, 0, 1000, 1000],
        "actions": [{"op": "click_batch", "points": [100, 100]}],
    }), encoding="utf-8")
    monkeypatch.setattr(cli, "find_unique_window", lambda _: (42, "OOTP"))
    monkeypatch.setattr(cli, "require_host_input", lambda: None)
    monkeypatch.setattr(cli, "execute_fast_batch", lambda *a, **k: {"actions_completed": 1})
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", "rebuild-execution",
        "run", str(path), "--action-id", action["id"], "--batch", str(batch_path),
        "--capture-after", str(path.parent / "capture.bmp"), "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out) == {"actions_completed": 1}
    assert execution_status(path)["state"] == "needs_reconciliation"


@pytest.mark.parametrize("field,value", [
    ("completed", ["unknown"]), ("journal", [{"sequence": 3, "event": "intent"}]),
    ("in_flight", "unknown"), ("baseline_reconciled", "yes"), ("actions", None),
])
def test_checkpoint_rejects_malformed_execution_before_resume(run, field, value):
    path, _, _ = run
    checkpoint = load_checkpoint(path)
    checkpoint["execution"][field] = value
    path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid rebuild execution ledger"):
        load_checkpoint(path)


def test_init_recovers_interruption_before_execution_initialization(run):
    path, _, _ = run
    checkpoint = load_checkpoint(path)
    del checkpoint["execution"]
    checkpoint_module.write_checkpoint(path, checkpoint)
    resumed = initialize_checkpoint(checkpoint["manifest_path"], path)
    assert resumed["execution"]["completed"] == []
    assert execution_status(path)["state"] == "needs_baseline"


def test_journaled_run_rejects_sandbox_before_intent_and_preserves_resume(run, monkeypatch):
    import sys
    import manage_roster_automation as cli
    from ootp_opt.automation.windows_drag import NativeInputContextError
    path, previous, _ = run
    observed = rebuild_snapshot(previous)
    reconcile_execution(path, observed)
    first = execution_status(path)["next_action"]
    begin_action(path, first["id"])
    observed["membership"].remove(first["value"])
    reconcile_execution(path, observed)
    before = path.read_bytes()
    action = execution_status(path)["next_action"]
    def reject():
        raise NativeInputContextError()
    monkeypatch.setattr(cli, "require_host_input", reject)
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", "rebuild-execution",
        "run", str(path), "--action-id", action["id"], "--batch", "unused.json",
        "--capture-after", "unused.bmp"])
    with pytest.raises(NativeInputContextError):
        cli.main()
    assert path.read_bytes() == before
    assert execution_status(path)["state"] == "ready"
    assert execution_status(path)["in_flight"] is None
    assert execution_status(path)["completed"] == 1


@pytest.mark.parametrize("arguments", [
    ["fast-batch", "unused.json", "sync", "unused-batch.json", "--execute"],
    ["assignment-drag", "unused.json", "pitching", "rotation", "--client-geometry", "0,0,100,100",
     "--source", "123=1,1", "--target", "1=2,2", "--execute"],
])
def test_other_native_cli_commands_reject_context_before_any_work(monkeypatch, arguments):
    import sys
    import manage_roster_automation as cli
    from ootp_opt.automation.windows_drag import NativeInputContextError
    def reject():
        raise NativeInputContextError()
    monkeypatch.setattr(cli, "require_host_input", reject)
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", *arguments])
    with pytest.raises(NativeInputContextError):
        cli.main()
