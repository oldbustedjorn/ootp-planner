from copy import deepcopy
import json
import sys

import pytest

from ootp_opt.automation.checkpoint import initialize_checkpoint, load_checkpoint
from ootp_opt.automation.execution import (
    begin_action, execute_action_batch, execution_status, reconcile_execution,
)
from ootp_opt.automation import execution_batch
from ootp_opt.automation.manifest import manifest_fingerprint, write_manifest
from ootp_opt.automation.rebuild import build_rebuild_delta, rebuild_snapshot
from test_automation_manifest import build_manifest


def make_batch_run(tmp_path):
    previous = build_manifest()
    current = deepcopy(previous)
    replacements = {
        current["roster"]["membership"][index]["cid"]: str(99000 + index)
        for index in (11, 12)
    }
    def replace(value):
        if isinstance(value, dict):
            if value.get("cid") in replacements:
                value["cid"] = replacements[value["cid"]]
                value["candidate_id"] = "replacement-" + value["cid"]
            for child in value.values():
                replace(child)
        elif isinstance(value, list):
            for child in value:
                replace(child)
    replace(current)
    for entry in current["pitching"]["bullpen"][:2]:
        entry["usage"] = "Use more often"
    for split in ("vs_rhp", "vs_lhp"):
        starters = current["lineups"][split]["starters"]
        starters[0]["card"], starters[1]["card"] = starters[1]["card"], starters[0]["card"]
    current["rebuild"] = build_rebuild_delta(previous, current)
    current["fingerprint"] = manifest_fingerprint(current)
    current["manifest_id"] = current["fingerprint"][:16]
    manifest_path = tmp_path / "manifest.json"
    path = tmp_path / "checkpoint.json"
    write_manifest(manifest_path, current)
    initialize_checkpoint(manifest_path, path)
    observed = rebuild_snapshot(previous)
    reconcile_execution(path, observed)
    return path, current, observed


@pytest.fixture
def batch_run(tmp_path):
    return make_batch_run(tmp_path)


def apply(action, observed):
    if action["operation"] == "remove":
        observed["membership"].remove(action["value"])
    elif action["operation"] == "add":
        observed["membership"].append(action["value"])
    elif action["operation"] == "set":
        observed["targets"][action["target"]] = action["value"]


def advance_until(path, observed, target):
    while True:
        action = execution_status(path)["next_action"]
        if action["target"].startswith(target):
            return
        begin_action(path, action["id"])
        apply(action, observed)
        reconcile_execution(path, observed)


def native_plan(manifest, actions):
    return {
        "schema_version": 1, "manifest_id": manifest["manifest_id"], "section": actions[0]["section"],
        "client_geometry": [0, 31, 1850, 1062],
        "transactions": [{"action_id": a["id"], "actions": [{"op": "wait", "ms": 0}]}
                         for a in actions],
    }


def test_batch_journals_each_action_then_verifies_once(batch_run):
    path, _, observed = batch_run
    actions = execution_status(path)["next_batch"]
    assert len(actions) == 2
    def execute(action):
        journal = load_checkpoint(path)["execution"]["journal"]
        assert journal[-1]["event"] == "intent"
        assert journal[-1]["action"] == action["id"]
        apply(action, observed)
    result = execute_action_batch(path, [a["id"] for a in actions], execute)
    assert result["state"] == "needs_verification"
    assert result["completed"] == 0
    assert len(result["unverified"]) == 2
    with pytest.raises(ValueError, match="not ready"):
        begin_action(path, result["next_action"]["id"])
    assert reconcile_execution(path, observed)["completed"] == 2
    assert execution_status(path)["next_action"]["operation"] == "add"


@pytest.mark.parametrize("second_applied", [True, False])
def test_batch_interruption_resolves_exact_prefix_without_replaying_returned_input(batch_run, second_applied):
    path, _, observed = batch_run
    actions = execution_status(path)["next_batch"]
    calls = []
    def execute(action):
        calls.append(action["id"])
        if len(calls) == 1 or second_applied:
            apply(action, observed)
        if len(calls) == 2:
            raise RuntimeError("native interrupted")
    with pytest.raises(RuntimeError, match="interrupted"):
        execute_action_batch(path, [a["id"] for a in actions], execute)
    assert execution_status(path)["state"] == "needs_reconciliation"
    assert len(execution_status(path)["unverified"]) == 1
    result = reconcile_execution(path, observed)
    assert result["completed"] == (2 if second_applied else 1)
    assert result["unverified"] == []
    assert result["in_flight"] is None
    assert calls == [a["id"] for a in actions]


def test_batch_refuses_cross_family_or_out_of_order_before_input(batch_run):
    path, _, _ = batch_run
    actions = load_checkpoint(path)["execution"]["actions"]
    before = path.read_bytes()
    for ids in ([actions[1]["id"], actions[0]["id"]], [a["id"] for a in actions[:3]]):
        with pytest.raises(ValueError, match="ordered prefix"):
            execute_action_batch(path, ids, lambda _: pytest.fail("Unexpected native input"))
    assert path.read_bytes() == before


def test_incorrect_returned_assignment_blocks_without_replaying_correct_targets(batch_run):
    path, _, observed = batch_run
    advance_until(path, observed, "pitching/bullpen/")
    actions = execution_status(path)["next_batch"]
    assert len(actions) == 2
    execute_action_batch(path, [a["id"] for a in actions], lambda a: apply(a, observed)
                         if a == actions[1] else None)
    result = reconcile_execution(path, observed)
    assert result["state"] == "needs_verification"
    assert result["last_event"]["targets"] == [actions[0]["target"]]
    with pytest.raises(ValueError, match="not ready"):
        execute_action_batch(path, [actions[0]["id"]], lambda _: None)
    apply(actions[0], observed)  # Only the confirmed discrepancy is repaired.
    result = reconcile_execution(path, observed)
    assert result["unverified"] == []
    assert result["next_action"]["operation"] == "verify"


def test_native_batch_takes_only_final_capture_and_validates_all_transactions(batch_run, monkeypatch):
    path, manifest, _ = batch_run
    actions = execution_status(path)["next_batch"]
    plan = native_plan(manifest, actions)
    calls = []
    monkeypatch.setattr(execution_batch.windows_drag, "require_host_input", lambda: None)
    monkeypatch.setattr(execution_batch.windows_drag, "find_unique_window", lambda _: (123, "OOTP"))
    monkeypatch.setattr(execution_batch.windows_drag, "client_geometry", lambda _: tuple(plan["client_geometry"]))
    monkeypatch.setattr(execution_batch, "execute_fast_batch", lambda *a, **kw: calls.append(kw["capture_after"]))
    bad = deepcopy(plan)
    bad["transactions"][-1]["actions"] = [{"op": "click_batch", "points": [9999, 9999]}]
    with pytest.raises(ValueError, match="outside"):
        execution_batch.run_execution_batch(path, manifest["manifest_id"], bad,
                                           title="OOTP", capture_after="final.bmp")
    assert calls == []
    result = execution_batch.run_execution_batch(path, manifest["manifest_id"], plan,
                                                title="OOTP", capture_after="final.bmp")
    assert result["state"] == "needs_verification"
    assert calls == [None, "final.bmp"]


def test_journal_drag_cli_compiles_only_remaining_actions_without_intermediate_files(batch_run, monkeypatch, capsys):
    import manage_roster_automation as cli
    path, manifest, observed = batch_run
    advance_until(path, observed, "vs_rhp/starters/")
    actions = execution_status(path)["next_batch"]
    assert len(actions) == 2
    execute_action_batch(path, [actions[0]["id"]], lambda a: apply(a, observed))
    reconcile_execution(path, observed)
    actions = execution_status(path)["next_batch"]
    assert len(actions) == 1  # Completed preflight is excluded without --skip-first.
    arguments = ["manage_roster_automation.py", "assignment-drag", load_checkpoint(path)["manifest_path"],
                 "vs_rhp", "starters", "--checkpoint", str(path),
                 "--client-geometry", "0,31,1850,1062", "--json"]
    for action in actions:
        arguments += ["--source", f"{action['value']['cid']}=100,200",
                      "--target", f"{action['target'].split('/')[-1]}=600,300"]
    monkeypatch.setattr(sys, "argv", arguments)
    cli.main()
    plan = json.loads(capsys.readouterr().out)
    assert [t["action_id"] for t in plan["transactions"]] == [a["id"] for a in actions]
    assert plan["manifest_id"] == manifest["manifest_id"]


def test_batch_host_rejection_leaves_journal_unchanged(batch_run, monkeypatch):
    from ootp_opt.automation.windows_drag import NativeInputContextError
    path, manifest, _ = batch_run
    plan = native_plan(manifest, execution_status(path)["next_batch"])
    before = path.read_bytes()
    def reject():
        raise NativeInputContextError()
    monkeypatch.setattr(execution_batch.windows_drag, "require_host_input", reject)
    with pytest.raises(NativeInputContextError):
        execution_batch.run_execution_batch(path, manifest["manifest_id"], plan,
                                           title="OOTP", capture_after="unused.bmp")
    assert path.read_bytes() == before


def test_verification_boundary_cannot_be_executed_in_native_batch(batch_run):
    path, _, observed = batch_run
    advance_until(path, observed, "sync")
    action = execution_status(path)["next_action"]
    assert action["operation"] == "verify"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="single-action"):
        execute_action_batch(path, [action["id"]], lambda _: pytest.fail("Unexpected input"))
    assert path.read_bytes() == before


def test_full_batched_replay_reduces_observations_without_skipping_actions(batch_run):
    path, manifest, observed = batch_run
    native_calls = []
    observations = 0
    while execution_status(path)["state"] != "complete":
        status = execution_status(path)
        actions = status["next_batch"]
        action = actions[0]
        if action["operation"] in ("verify", "save"):
            begin_action(path, action["id"])
            if action["operation"] == "save":
                observed["local_save"] = manifest["roster"]["name"]
        else:
            def execute(item):
                native_calls.append(item["id"])
                apply(item, observed)
            execute_action_batch(path, [a["id"] for a in actions], execute)
        reconcile_execution(path, observed)
        observations += 1
    execution = load_checkpoint(path)["execution"]
    expected = [a["id"] for a in execution["actions"] if a["operation"] in ("set", "add", "remove")]
    assert native_calls == expected
    assert observations < len(execution["actions"])
    assert execution["completed"] == [a["id"] for a in execution["actions"]]
    assert load_checkpoint(path)["phases"]["assign"]["status"] == "complete"
