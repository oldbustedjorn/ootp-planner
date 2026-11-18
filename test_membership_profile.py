from copy import deepcopy
import json
import sys

import pytest

import manage_roster_automation as cli
from ootp_opt.automation import execution_batch
from ootp_opt.automation.execution import execute_action_batch, execution_status, reconcile_execution
from ootp_opt.automation.membership_profile import (
    create_membership_profile, compile_membership_batch, reuse_membership_calibration,
    compile_filter_preflight,
)
from test_execution_batch import make_batch_run, apply


@pytest.fixture
def calibrated(tmp_path):
    path, manifest, observed = make_batch_run(tmp_path)
    capture = tmp_path / "calibration.bmp"
    capture.write_bytes(b"inspected view/status/CID dialog")
    controls = dict(field=[50, 70], activate=[700, 90], apply=[400, 300],
                    open=[[200, 50], [200, 90]], confirm=[500, 400])
    profile = create_membership_profile(
        path, geometry=[0, 0, 1000, 800], controls=controls, screen_status="active",
        capture=capture, note="Verified RosterLoad, active selected, CID filter and Proceed",
    )
    return path, manifest, observed, profile, capture


def test_profile_reuses_coordinates_and_compiles_only_remaining_journal_actions(calibrated):
    path, _, observed, profile, _ = calibrated
    before = path.read_bytes()
    plan = compile_membership_batch(path, profile, screen_status="active", first_only=True)
    assert path.read_bytes() == before
    assert len(plan["transactions"]) == 1
    action = execution_status(path)["next_action"]
    assert plan["transactions"][0]["actions"][0]["values"] == [action["value"]["cid"]]
    execute_action_batch(path, [action["id"]], lambda a: apply(a, observed))
    with pytest.raises(ValueError, match="Reconcile pending"):
        compile_membership_batch(path, profile, screen_status="active")
    reconcile_execution(path, observed)
    rest = compile_membership_batch(path, profile, screen_status="active")
    assert len(rest["transactions"]) == 1
    assert rest["transactions"][0]["action_id"] != action["id"]
    assert rest["transactions"][0]["actions"][0]["confirm"] == [500, 400]


@pytest.mark.parametrize("change", ["checkpoint", "manifest", "status", "bounds", "confirm"])
def test_invalid_profile_rejected_before_input_or_checkpoint_change(calibrated, change):
    path, _, _, profile, _ = calibrated
    bad = deepcopy(profile)
    if change == "checkpoint":
        bad["checkpoint"] += ".other"
    elif change == "manifest":
        bad["manifest_fingerprint"] = "other"
    elif change == "status":
        bad["screen_status"] = "inactive"
    elif change == "bounds":
        bad["controls"]["field"] = [1001, 30]
    else:
        del bad["controls"]["confirm"]
    before = path.read_bytes()
    with pytest.raises(ValueError):
        compile_membership_batch(path, bad, screen_status="active")
    assert path.read_bytes() == before


def test_addition_prefix_stops_at_ambiguous_card(calibrated, monkeypatch):
    from ootp_opt.automation import membership_profile as module
    path, _, observed, profile, capture = calibrated
    actions = execution_status(path)["next_batch"]
    execute_action_batch(path, [a["id"] for a in actions], lambda a: apply(a, observed))
    reconcile_execution(path, observed)
    controls = deepcopy(profile["controls"])
    del controls["confirm"]
    addition = create_membership_profile(path, geometry=profile["client_geometry"], controls=controls,
                                         screen_status="all", capture=capture, note="All statuses selected")
    # Exercise the metadata boundary without altering a real checkpoint/manifest.
    original_load = module._load
    def load(p):
        c, e, m = original_load(p)
        pending = execution_status(p)["next_batch"]
        card = next(c for c in m["roster"]["membership"] if c["cid"] == pending[1]["value"]["cid"])
        card["owned_cid_copy_count"] = 2
        return c, e, m
    monkeypatch.setattr(module, "_load", load)
    plan = compile_membership_batch(path, addition, screen_status="all")
    assert len(plan["transactions"]) == 1
    assert "confirm" not in plan["transactions"][0]["actions"][0]
    first = execution_status(path)["next_action"]
    execute_action_batch(path, [first["id"]], lambda a: apply(a, observed))
    reconcile_execution(path, observed)
    # The now-first ambiguous card must use the inspected path, never skip ahead.
    monkeypatch.setattr(module, "_load", original_load)
    c, e, m = original_load(path)
    cid = execution_status(path)["next_action"]["value"]["cid"]
    next(c for c in m["roster"]["membership"] if c["cid"] == cid)["owned_cid_copy_count"] = 2
    monkeypatch.setattr(module, "_load", lambda p: (c, e, m))
    with pytest.raises(ValueError, match="inspected CID/variant"):
        compile_membership_batch(path, addition, screen_status="all")


def test_cli_serializes_profile_and_returns_compact_dry_run(calibrated, monkeypatch, capsys):
    path, _, _, _, capture = calibrated
    saved = path.parent / "remove.profile.json"
    result = path.parent / "plan.json"
    args = ["membership-filter", path, "--save-profile", saved, "--client-geometry", "0,0,1000,800",
            "--screen-status", "active", "--field", "50,70", "--activate", "700,90",
            "--apply", "400,300", "--confirm", "500,400", "--open", "200,50", "--open", "200,90",
            "--capture", capture, "--note", "Verified status and CID dialog", "--confirm-calibration",
            "--json-output", result]
    before = path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", *map(str, args)])
    cli.main()
    assert "Plan: sync | transactions=2" in capsys.readouterr().out
    assert json.loads(saved.read_text())["controls"]["field"] == [50, 70]
    expected = json.loads(result.read_text())
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", "membership-filter", str(path),
                                    "--profile", str(saved), "--screen-status", "active", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out) == expected
    assert path.read_bytes() == before


def test_live_geometry_change_rejects_profile_batch_before_input(calibrated, monkeypatch):
    path, _, _, profile, _ = calibrated
    plan = compile_membership_batch(path, profile, screen_status="active")
    monkeypatch.setattr(execution_batch.windows_drag, "require_host_input", lambda: None)
    monkeypatch.setattr(execution_batch.windows_drag, "find_unique_window", lambda title: (1, title))
    monkeypatch.setattr(execution_batch.windows_drag, "client_geometry", lambda hwnd: (0, 0, 1200, 800))
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="geometry changed"):
        execution_batch.run_execution_batch(path, plan["manifest_id"], plan,
                                            title="OOTP", capture_after=path.parent / "after.bmp")
    assert path.read_bytes() == before


def advance_to_additions(path, observed):
    actions = execution_status(path)["next_batch"]
    execute_action_batch(path, [a["id"] for a in actions], lambda a: apply(a, observed))
    reconcile_execution(path, observed)


def test_reused_controls_keep_provenance_without_marking_additions_applied(calibrated):
    path, _, observed, source, _ = calibrated
    advance_to_additions(path, observed)
    original = deepcopy(source)
    before = path.read_bytes()
    inspected = path.parent / "exact-addition.bmp"
    inspected.write_bytes(b"inspected exact CID/variant after status transition")
    profile = reuse_membership_calibration(path, source, screen_status="all",
                                          note="Same controller/view/geometry; all statuses selected",
                                          capture=inspected, confirm_filter_result=True)
    assert source == original
    assert profile["operation"] == "add" and profile["screen_status"] == "all"
    assert "confirm" not in profile["controls"]
    assert profile["controls"]["open"] == source["controls"]["open"]
    assert profile["evidence"]["original_calibration"] == source["evidence"]
    assert profile["evidence"]["capture_scope"] == "controller_confirmed_exact_filter_result"
    assert profile["evidence"]["filter_card"] == execution_status(path)["next_action"]["value"]
    assert path.read_bytes() == before
    assert len(compile_membership_batch(path, profile, screen_status="all")["transactions"]) == 2


@pytest.mark.parametrize("fault", ["changed_capture", "wrong_checkpoint", "unknown_status", "no_attestation"])
def test_reuse_rejects_invalid_evidence_or_state(calibrated, fault):
    path, _, observed, source, capture = calibrated
    advance_to_additions(path, observed)
    if fault == "changed_capture":
        capture.write_bytes(b"replaced capture")
    if fault == "wrong_checkpoint":
        source["checkpoint"] += ".other"
    before = path.read_bytes()
    with pytest.raises(ValueError):
        reuse_membership_calibration(path, source,
                                    screen_status="active" if fault == "unknown_status" else "all",
                                    note="" if fault == "no_attestation" else "Unchanged controls and known status")
    assert path.read_bytes() == before


def test_cli_reuses_calibration_with_inspected_filter_result(calibrated, monkeypatch, capsys):
    path, _, observed, source, capture = calibrated
    advance_to_additions(path, observed)
    saved = path.parent / "remove.profile.json"
    saved.write_text(json.dumps(source))
    target = path.parent / "add.profile.json"
    inspected = path.parent / "exact-addition.bmp"
    inspected.write_bytes(b"inspected exact result")
    args = ["manage_roster_automation.py", "membership-filter", str(path),
            "--save-profile", str(target), "--reuse-calibration", str(saved),
            "--screen-status", "all", "--note", "Same view/geometry; known all-status transition",
            "--confirm-calibration", "--first-only", "--capture", str(inspected), "--confirm-filter-result"]
    before = path.read_bytes()
    original_capture = capture.read_bytes()
    monkeypatch.setattr(sys, "argv", args)
    cli.main()
    assert "Plan: sync | transactions=1" in capsys.readouterr().out
    assert json.loads(target.read_text())["evidence"]["capture"] == str(inspected.resolve())
    assert capture.read_bytes() == original_capture
    assert path.read_bytes() == before
    # Original calibration evidence must also be protected from output writes.
    monkeypatch.setattr(sys, "argv", [*args, "--json-output", str(capture)])
    with pytest.raises(ValueError, match="overwrite"):
        cli.main()
    assert capture.read_bytes() == original_capture


@pytest.mark.parametrize("confirmation", [False, True])
def test_status_transition_rejects_inherited_capture_as_filter_proof(calibrated, confirmation):
    path, _, observed, source, capture = calibrated
    advance_to_additions(path, observed)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="fresh inspected|confirm-filter-result"):
        reuse_membership_calibration(path, source, screen_status="all", note="Unchanged geometry",
                                    capture=capture, confirm_filter_result=confirmation)
    assert path.read_bytes() == before


def test_filter_only_preflight_does_not_activate_or_advance_pending_actions(calibrated):
    path, _, observed, source, _ = calibrated
    advance_to_additions(path, observed)
    before = path.read_bytes()
    plan, _ = compile_filter_preflight(path, source, screen_status="all")
    assert [a["op"] for a in plan["actions"]] == ["click_batch", "type_text", "click_batch"]
    assert plan["actions"][1]["text"] == execution_status(path)["next_action"]["value"]["cid"]
    points = [p for a in plan["actions"] for p in a.get("points", [])]
    assert source["controls"]["activate"] not in points
    assert source["controls"]["confirm"] not in points
    assert path.read_bytes() == before


def test_status_transition_rejects_a_copy_of_old_calibration_image(calibrated):
    path, _, observed, source, capture = calibrated
    advance_to_additions(path, observed)
    copied = path.parent / "old-image-renamed.bmp"
    copied.write_bytes(capture.read_bytes())
    with pytest.raises(ValueError, match="fresh inspected"):
        reuse_membership_calibration(path, source, screen_status="all", note="Known status",
                                    capture=copied, confirm_filter_result=True)


def test_legacy_inherited_profile_cannot_bypass_filter_result_confirmation(calibrated):
    path, _, observed, source, _ = calibrated
    advance_to_additions(path, observed)
    old = deepcopy(source)
    old.update(operation="add", screen_status="all")
    old["controls"].pop("confirm")
    old["evidence"]["original_calibration"] = deepcopy(source["evidence"])
    old["evidence"]["capture_scope"] = "inherited_geometry_and_cid_controls_only"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="fresh confirmed filter result"):
        compile_membership_batch(path, old, screen_status="all")
    assert path.read_bytes() == before


def test_cli_prepare_only_captures_without_journaling_or_activation(calibrated, monkeypatch, capsys):
    path, _, observed, source, _ = calibrated
    advance_to_additions(path, observed)
    saved = path.parent / "remove.profile.json"
    saved.write_text(json.dumps(source))
    after = path.parent / "filter-result.bmp"
    calls = []
    monkeypatch.setattr(cli, "require_host_input", lambda: None)
    monkeypatch.setattr(cli, "find_unique_window", lambda title: (1, title))
    def execute(hwnd, plan, capture_after):
        calls.append(plan)
        after.write_bytes(b"result screenshot")
        return {"capture": str(after), "actions_completed": len(plan["actions"])}
    monkeypatch.setattr(cli, "execute_fast_batch", execute)
    monkeypatch.setattr(sys, "argv", ["manage_roster_automation.py", "membership-filter", str(path),
                                    "--profile", str(saved), "--screen-status", "all",
                                    "--prepare-only", "--capture-after", str(after)])
    before = path.read_bytes()
    cli.main()
    assert "no activation" in capsys.readouterr().out
    assert len(calls) == 1
    assert path.read_bytes() == before
