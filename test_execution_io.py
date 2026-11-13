from copy import deepcopy
import json
import sys

import pytest

import manage_roster_automation as cli
from ootp_opt.automation.checkpoint import load_checkpoint
from ootp_opt.automation.execution import begin_action, execute_action_batch, execution_status, reconcile_execution
from ootp_opt.automation.execution_io import compact_execution_receipt
from ootp_opt.automation.observation_io import prepare_observation, read_observation
from test_execution_batch import advance_until, apply, make_batch_run


@pytest.fixture
def batch_run(tmp_path):
    return make_batch_run(tmp_path)


def invoke(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", *map(str, arguments)])
    cli.main()


def save(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_compact_receipt_and_full_json_are_equivalent_readonly_views(batch_run, monkeypatch, capsys):
    path, _, _ = batch_run
    before = path.read_bytes()
    result_path = path.parent / "status.json"
    status = execution_status(path)
    invoke(monkeypatch, ["rebuild-execution", "status", path, "--json-output", result_path])
    compact = capsys.readouterr().out
    assert "ready | completed=0/" in compact and "family_actions=2" in compact
    assert status["next_action"]["id"] in compact
    assert '"next_batch"' not in compact
    assert json.loads(result_path.read_text()) == status
    assert len(compact) < len(json.dumps(status, indent=2)) * 0.4
    invoke(monkeypatch, ["rebuild-execution", "status", path, "--json"])
    assert json.loads(capsys.readouterr().out) == status
    assert path.read_bytes() == before


def test_cli_binds_verified_name_without_advancing_or_overwriting_evidence(batch_run, monkeypatch, capsys):
    path, _, _ = batch_run
    capture = path.parent / "roster.bmp"
    capture.write_bytes(b"inspected roster capture")
    before = load_checkpoint(path)["execution"]
    args = ["rebuild-execution", "bind-save-name", path, "--name", "Wed Ice 1490029",
            "--capture", capture, "--note", "Verified existing roster name and rules"]
    with pytest.raises(ValueError, match="overwrite"):
        invoke(monkeypatch, [*args, "--json-output", capture])
    invoke(monkeypatch, args)
    assert 'Local save name: "Wed Ice 1490029"' in capsys.readouterr().out
    after = load_checkpoint(path)["execution"]
    assert after["completed"] == before["completed"]
    assert after["actions"] == before["actions"]
    assert after["local_save_binding"]["name"] == "Wed Ice 1490029"
    assert capture.read_bytes() == b"inspected roster capture"


def test_compact_failure_preserves_exact_save_discrepancy(batch_run):
    path, manifest, observed = batch_run
    advance_until(path, observed, "local_save")
    begin_action(path, execution_status(path)["next_action"]["id"])
    observed["local_save"] = "Different actual roster name"
    status = reconcile_execution(path, observed)
    before = path.read_bytes()
    text = compact_execution_receipt(status, checkpoint_path=path)
    assert "Mismatch local_save" in text
    assert manifest["roster"]["name"] in text
    assert 'observed="Different actual roster name"' in text
    assert path.read_bytes() == before


def test_output_cannot_overwrite_checkpoint_before_input(batch_run, monkeypatch):
    path, _, _ = batch_run
    before = path.read_bytes()
    invoke_args = ["rebuild-execution", "run", path, "--batch", "unused.json",
                   "--capture-after", "unused.bmp", "--json-output", path]
    with pytest.raises(ValueError, match="must not overwrite"):
        invoke(monkeypatch, invoke_args)
    assert path.read_bytes() == before


def test_coordinate_file_produces_identical_native_plan_without_repeating_arrays(batch_run, monkeypatch, capsys):
    path, manifest, observed = batch_run
    advance_until(path, observed, "vs_rhp/starters/")
    actions = execution_status(path)["next_batch"]
    coordinate_map = path.parent / "starters.coords.json"
    plan1, plan2 = path.parent / "plan1.json", path.parent / "plan2.json"
    prefix = ["assignment-drag", load_checkpoint(path)["manifest_path"], "vs_rhp", "starters",
              "--checkpoint", path]
    inline = [*prefix, "--client-geometry", "0,31,1850,1062", "--save-coordinate-map", coordinate_map,
              "--json-output", plan1]
    for action in actions:
        inline += ["--source", f"{action['value']['cid']}=100,200",
                   "--target", f"{action['target'].split('/')[-1]}=600,300"]
    before = path.read_bytes()
    invoke(monkeypatch, inline)
    assert "Plan: vs_rhp | transactions=2" in capsys.readouterr().out
    invoke(monkeypatch, [*prefix, "--coordinate-map", coordinate_map, "--json-output", plan2])
    assert "not executed" in capsys.readouterr().out
    assert json.loads(plan1.read_text()) == json.loads(plan2.read_text())
    assert json.loads(coordinate_map.read_text())["manifest_fingerprint"] == manifest["fingerprint"]
    assert path.read_bytes() == before
    for key, value in (("manifest_fingerprint", "other"), ("section", "vs_lhp"), ("family", "depth")):
        data = json.loads(coordinate_map.read_text())
        data[key] = value
        bad_map = save(path.parent / f"bad-{key}.json", data)
        with pytest.raises(ValueError, match="does not match"):
            invoke(monkeypatch, [*prefix, "--coordinate-map", bad_map])


def test_draft_is_not_evidence_and_never_changes_checkpoint(batch_run, monkeypatch, capsys):
    path, manifest, _ = batch_run
    before = path.read_bytes()
    draft_path = path.parent / "draft.json"
    invoke(monkeypatch, ["observation", path, "--scope", "baseline", "--output", draft_path])
    output = capsys.readouterr().out
    assert "Draft (not evidence)" in output and '"membership"' not in output
    assert json.loads(draft_path.read_text())["kind"] == "ootp_observation_draft"
    with pytest.raises(ValueError, match="draft is not evidence"):
        read_observation(draft_path, manifest["fingerprint"])
    with pytest.raises(ValueError, match="draft is not evidence"):
        invoke(monkeypatch, ["rebuild-execution", "reconcile", path, "--observation", draft_path])
    assert path.read_bytes() == before


def test_explicit_baseline_confirmation_has_capture_provenance_not_automatic_success(batch_run):
    path, manifest, observed = batch_run
    before = path.read_bytes()
    with pytest.raises(ValueError, match="requires an existing nonempty --capture"):
        prepare_observation(path, "baseline", confirm_matches=True)
    capture = path.parent / "viewed.bmp"
    capture.write_bytes(b"test capture reference")
    result = prepare_observation(path, "baseline", capture=capture, confirm_matches=True)
    assert set((c["cid"], c["variant"]) for c in result["membership"]) == set((c["cid"], c["variant"]) for c in observed["membership"])
    assert result["_evidence"]["manifest_fingerprint"] == manifest["fingerprint"]
    assert result["_evidence"]["capture_sha256"]
    assert path.read_bytes() == before


def test_pending_assignment_serializes_exact_values_and_reuses_only_reconciled_membership(batch_run):
    path, _, observed = batch_run
    advance_until(path, observed, "pitching/bullpen/")
    base = save(path.parent / "known-membership.json", observed)
    actions = execution_status(path)["next_batch"]
    execute_action_batch(path, [a["id"] for a in actions], lambda a: apply(a, observed))
    before = path.read_bytes()
    capture = path.parent / "viewed.bmp"
    capture.write_bytes(b"test capture reference")
    with pytest.raises(ValueError, match="requires --base"):
        prepare_observation(path, "pending", capture=capture, confirm_matches=True)
    actual = {actions[0]["target"]: {**actions[0]["value"], "usage": "Actual different usage"}}
    result = prepare_observation(path, "pending", base=base, capture=capture,
                                 confirm_matches=True, actual_targets=actual)
    assert result["targets"][actions[0]["target"]]["usage"] == "Actual different usage"
    assert result["targets"][actions[1]["target"]] == actions[1]["value"]
    assert result["membership"] == json.loads(base.read_text())["membership"]
    assert path.read_bytes() == before
    result_path = save(path.parent / "observed.json", result)
    status = reconcile_execution(path, read_observation(result_path, result["_evidence"]["manifest_fingerprint"]))
    assert status["state"] == "needs_verification"  # Actual mismatch is preserved and blocks.
    bad = deepcopy(observed)
    bad["membership"][0]["variant"] = not bad["membership"][0]["variant"]
    bad_base = save(path.parent / "bad-membership.json", bad)
    with pytest.raises(ValueError, match="does not match current journal progress"):
        prepare_observation(path, "pending", base=bad_base, capture=capture, confirm_matches=True)


def test_observation_manifest_binding_and_actual_save_name_are_not_silently_adopted(batch_run):
    path, manifest, observed = batch_run
    advance_until(path, observed, "local_save")
    base = save(path.parent / "known-membership.json", observed)
    begin_action(path, execution_status(path)["next_action"]["id"])
    capture = path.parent / "save.bmp"
    capture.write_bytes(b"test capture reference")
    result = prepare_observation(path, "save", base=base, capture=capture,
                                 confirm_matches=True, actual_save="Actual existing name")
    assert result["local_save"] == "Actual existing name"
    observation_path = save(path.parent / "save.json", result)
    with pytest.raises(ValueError, match="different manifest"):
        read_observation(observation_path, "different fingerprint")
    status = reconcile_execution(path, read_observation(observation_path, manifest["fingerprint"]))
    assert status["state"] == "needs_reconciliation"
    assert status["completed"] < status["total"]


def test_actual_membership_and_target_scope_are_preserved(batch_run):
    path, _, observed = batch_run
    capture = path.parent / "viewed.bmp"
    capture.write_bytes(b"test capture reference")
    actual = deepcopy(observed["membership"])
    actual[0]["cid"] = "unexpected-card"
    result = prepare_observation(path, "membership", capture=capture,
                                 confirm_matches=True, actual_membership=actual)
    assert result["membership"] == actual
    assert reconcile_execution(path, result)["state"] == "needs_baseline"
    with pytest.raises(ValueError, match="outside the selected scope"):
        prepare_observation(path, "baseline", actual_targets={"vs_rhp/starters/SS": None})


def test_confirmed_cli_observation_is_a_file_not_an_implicit_reconcile(batch_run, monkeypatch, capsys):
    path, manifest, _ = batch_run
    capture = path.parent / "baseline.bmp"
    capture.write_bytes(b"test capture reference")
    output = path.parent / "baseline.json"
    before = path.read_bytes()
    invoke(monkeypatch, ["observation", path, "--scope", "baseline", "--output", output,
                        "--capture", capture, "--confirm-matches"])
    assert "Confirmed observation file" in capsys.readouterr().out
    assert read_observation(output, manifest["fingerprint"])["kind"] == "ootp_observation"
    assert path.read_bytes() == before


def test_coordinate_json_output_cannot_overwrite_saved_calibration(batch_run, monkeypatch):
    path, _, observed = batch_run
    advance_until(path, observed, "vs_rhp/starters/")
    coordinate_map = path.parent / "existing.json"
    coordinate_map.write_text('{"original":true}', encoding="utf-8")
    before = coordinate_map.read_bytes()
    with pytest.raises(ValueError, match="must not overwrite"):
        invoke(monkeypatch, ["assignment-drag", load_checkpoint(path)["manifest_path"],
                            "vs_rhp", "starters", "--checkpoint", path,
                            "--coordinate-map", coordinate_map, "--json-output", coordinate_map])
    assert coordinate_map.read_bytes() == before


def test_malformed_actual_membership_is_not_replaced_with_expected_values(batch_run, monkeypatch):
    path, _, _ = batch_run
    invalid = save(path.parent / "invalid.json", {"expected": {"membership": []}})
    with pytest.raises(ValueError, match="actual membership array"):
        invoke(monkeypatch, ["observation", path, "--scope", "membership",
                            "--output", path.parent / "observation.json", "--actual-membership", invalid])
    assert not (path.parent / "observation.json").exists()


def test_compact_interrupted_membership_receipt_names_unexpected_cards(batch_run):
    path, _, observed = batch_run
    action = execution_status(path)["next_action"]
    begin_action(path, action["id"])
    observed["membership"].append({"cid": "unexpected-card", "variant": False})
    status = reconcile_execution(path, observed)
    text = compact_execution_receipt(status, checkpoint_path=path)
    assert "Membership before action:" in text and "Membership after action:" in text
    assert "unexpected-card" in text
    assert execution_status(path)["in_flight"] == action["id"]
