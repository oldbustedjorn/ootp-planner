from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from ootp_opt.automation.checkpoint import (
    ASSIGNMENT_SECTIONS,
    checkpoint_path_for_manifest,
    format_checkpoint_summary,
    initialize_checkpoint,
    load_checkpoint,
    record_assignment_repair,
    update_phase,
)
from ootp_opt.automation.fast_executor import (
    FAST_BATCH_SCHEMA_VERSION,
    execute_fast_batch,
    load_fast_batch,
    validate_fast_batch,
)
from ootp_opt.automation.fast_compile import (
    ASSIGNMENT_DRAG_FAMILIES,
    ASSIGNMENT_DRAG_SECTIONS,
    compile_assignment_moves,
    compile_journal_assignment_moves,
    select_assignment_moves,
)
from ootp_opt.automation.manifest import load_manifest
from ootp_opt.automation.execution import (
    begin_action,
    bind_local_save_name,
    execute_action,
    execution_status,
    initialize_execution,
    reconcile_execution,
)
from ootp_opt.automation.execution_batch import run_execution_batch, validate_execution_batch
from ootp_opt.automation.execution_io import (
    assignment_coordinates, compact_execution_receipt, require_output_path,
    save_assignment_coordinates, write_json_output,
)
from ootp_opt.automation.observation_io import OBSERVATION_SCOPES, prepare_observation, read_observation
from ootp_opt.automation.recovery import resume_prompt, status_selection
from ootp_opt.automation.membership_profile import (
    create_membership_profile, compile_membership_batch, reuse_membership_calibration,
    compile_filter_preflight,
)
from ootp_opt.automation.run_metrics import (
    METRIC_EVENTS,
    METRIC_STAGES,
    analyze_session,
    format_metrics_summary,
    latest_metric_session,
    metric_marker,
    write_metrics_html,
    write_metrics_json,
)
from ootp_opt.automation.ui_plan import (
    UI_PLAN_SECTIONS,
    automation_status,
    compact_ui_plan,
    require_cid_copy_counts,
)
from ootp_opt.automation.windows_drag import find_unique_window, require_host_input, run_cli, parse_point
from ootp_opt.services.saved_plan_build_service import build_saved_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage OOTP automation artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a manifest.")
    validate.add_argument("manifest")

    build_plan = subparsers.add_parser(
        "build-plan",
        help="Run an existing saved roster plan with the Full Optimizer.",
    )
    build_plan.add_argument("preset")
    build_plan.add_argument("--config", default="config.toml")

    service_check = subparsers.add_parser(
        "service-check", help="Verify the running planner automation contract."
    )
    service_check.add_argument(
        "--url", default="http://127.0.0.1:8765/automation-status"
    )

    initialize = subparsers.add_parser("init", help="Create a fresh checkpoint.")
    initialize.add_argument("manifest")
    initialize.add_argument("--checkpoint", default=None)
    initialize.add_argument("--json", action="store_true")

    status = subparsers.add_parser("status", help="Show checkpoint status.")
    status.add_argument("checkpoint")
    status.add_argument("--json", action="store_true")

    resume = subparsers.add_parser("resume-prompt", help="Generate read-only resume instructions from current checkpoint state")
    resume.add_argument("checkpoint")
    resume.add_argument("--output", help="Optional local text file; default prints the prompt")
    selection = subparsers.add_parser("status-selection", help="Plan corrections from inspected status checkmarks; sends no UI input")
    selection.add_argument("--observed", required=True,
                           help="All checked categories: active,reserve,inactive; use none for no checkmarks")
    selection.add_argument("--desired", choices=("active", "inactive", "all"), required=True)

    execution = subparsers.add_parser(
        "rebuild-execution", help="Manage the resumable rebuild action journal."
    )
    execution.add_argument("operation", choices=[
        "init", "status", "reconcile", "begin", "run", "validate-batch", "run-batch", "bind-save-name",
    ])
    execution.add_argument("checkpoint")
    execution.add_argument("--baseline-manifest", help="Verified prior manifest for legacy rebuilds")
    execution.add_argument("--observation", help="JSON with exact active membership and observed targets")
    execution.add_argument("--retry-unapplied", action="store_true")
    execution.add_argument("--action-id")
    execution.add_argument("--batch", help="Native plan for one action or a journaled action family")
    execution.add_argument("--capture-after")
    execution.add_argument("--name", help="Verified existing OOTP roster name for bind-save-name")
    execution.add_argument("--capture", help="Inspected capture establishing the existing roster identity")
    execution.add_argument("--note", help="How the existing roster identity was verified")
    execution.add_argument("--title", default="Out of the Park Baseball 27")
    execution.add_argument("--json", action="store_true", help="Print the full machine-readable result")
    execution.add_argument("--json-output", help="Write full result JSON locally; keep console output compact")

    observation = subparsers.add_parser(
        "observation", help="Prepare a draft or explicitly confirmed observation without roster-array scripts"
    )
    observation.add_argument("checkpoint")
    observation.add_argument("--scope", choices=OBSERVATION_SCOPES, required=True)
    observation.add_argument("--output", required=True)
    observation.add_argument("--base", help="Prior observation with reconciled membership to reuse")
    observation.add_argument("--capture", help="Capture the caller has inspected for every scoped field")
    observation.add_argument("--confirm-matches", action="store_true",
                             help="Attest scoped UI fields match, except explicit actual overrides")
    observation.add_argument("--actual-target", action="append", default=[], type=parse_actual_target,
                             metavar="TARGET=JSON")
    observation.add_argument("--actual-membership", help="JSON file containing the actual membership array")
    observation.add_argument("--actual-save", help="Actual name shown in OOTP's save confirmation")
    observation.add_argument("--json", action="store_true")

    repair = subparsers.add_parser(
        "repair-attempt",
        help="Claim a targeted repair batch for an assignment section.",
    )
    repair.add_argument("checkpoint")
    repair.add_argument("section", choices=ASSIGNMENT_SECTIONS)
    repair.add_argument(
        "--item",
        action="append",
        required=True,
        help="Exact missing or mismatched target repaired by this batch.",
    )
    repair.add_argument(
        "--strategy",
        required=True,
        help="Distinct source or target strategy used by this repair batch.",
    )

    actions = subparsers.add_parser(
        "actions", help="Show compact manifest actions for one UI section."
    )
    actions.add_argument("manifest")
    actions.add_argument(
        "section", choices=["sync", "pitching", "vs_rhp", "vs_lhp"]
    )

    ui_plan = subparsers.add_parser(
        "ui-plan", help="Emit a compact deterministic UI execution plan."
    )
    ui_plan.add_argument("manifest")
    ui_plan.add_argument("section", choices=UI_PLAN_SECTIONS)
    ui_plan.add_argument(
        "--require-cid-copy-counts",
        action="store_true",
        help="Reject a new sync manifest that cannot use duplicate-safe batching.",
    )

    fast_batch = subparsers.add_parser(
        "fast-batch",
        help="Validate or execute a manifest-bound native UI action batch.",
    )
    fast_batch.add_argument("manifest")
    fast_batch.add_argument("section", choices=UI_PLAN_SECTIONS)
    fast_batch.add_argument("batch")
    fast_batch.add_argument("--execute", action="store_true")
    fast_batch.add_argument(
        "--capture-after",
        default=None,
        help=(
            "Verification image path. Defaults to "
            "<batch-stem>.verification.bmp when executing."
        ),
    )
    fast_batch.add_argument("--title", default="Out of the Park Baseball 27")

    assignment_drag = subparsers.add_parser(
        "assignment-drag",
        help="Compile and optionally execute one assignment drag family.",
    )
    assignment_drag.add_argument("manifest")
    assignment_drag.add_argument("--checkpoint", help="Journal and verify one family as a batch")
    assignment_drag.add_argument("--coordinate-map", help="Reuse this manifest/section/family's saved coordinates")
    assignment_drag.add_argument("--save-coordinate-map", help="Save supplied calibration locally for the remainder")
    assignment_drag.add_argument("--json", action="store_true", help="Print full result or dry-run plan")
    assignment_drag.add_argument("--json-output", help="Write full result or dry-run plan JSON locally")
    assignment_drag.add_argument("section", choices=ASSIGNMENT_DRAG_SECTIONS)
    assignment_drag.add_argument("family", choices=ASSIGNMENT_DRAG_FAMILIES)
    assignment_drag.add_argument(
        "--client-geometry",
        type=parse_client_geometry,
        default=None,
        metavar="LEFT,TOP,WIDTH,HEIGHT",
    )
    assignment_drag.add_argument(
        "--source",
        action="append",
        type=parse_named_point,
        default=[],
        metavar="CID=X,Y",
    )
    assignment_drag.add_argument(
        "--target",
        action="append",
        type=parse_named_point,
        default=[],
        metavar="KEY=X,Y",
    )
    selection = assignment_drag.add_mutually_exclusive_group()
    selection.add_argument("--first-only", action="store_true")
    selection.add_argument("--skip-first", type=int, default=0)
    assignment_drag.add_argument("--execute", action="store_true")
    assignment_drag.add_argument("--capture-after", default=None)
    assignment_drag.add_argument("--title", default="Out of the Park Baseball 27")

    membership = subparsers.add_parser(
        "membership-filter", help="Reuse verified run-local CID/status calibration for journaled sync."
    )
    membership.add_argument("checkpoint")
    profiles = membership.add_mutually_exclusive_group(required=True)
    profiles.add_argument("--profile", help="Reuse this rebuild's calibrated profile")
    profiles.add_argument("--save-profile", help="Save a new explicitly verified calibration")
    membership.add_argument("--reuse-calibration", help="Derive an addition profile from this run's removal controls")
    membership.add_argument("--screen-status", choices=("active", "inactive", "all"), required=True,
                            help="Attest current collection-status selection; not auto-detected")
    membership.add_argument("--client-geometry", type=parse_client_geometry)
    for control in ("field", "activate", "apply", "confirm"):
        membership.add_argument(f"--{control}", type=parse_point)
    membership.add_argument("--open", type=parse_point, action="append", default=[])
    membership.add_argument("--capture", help="Inspected calibration capture")
    membership.add_argument("--note", help="Verified view, status categories and CID dialog state")
    membership.add_argument("--confirm-calibration", action="store_true")
    membership.add_argument("--confirm-filter-result", action="store_true",
                            help="Attest the fresh capture shows the intended exact CID/variant after a status change")
    membership.add_argument("--prepare-only", action="store_true",
                            help="Open/type/apply the pending CID and capture results without activating a card")
    membership.add_argument("--first-only", action="store_true")
    membership.add_argument("--execute", action="store_true")
    membership.add_argument("--capture-after")
    membership.add_argument("--title", default="Out of the Park Baseball 27")
    membership.add_argument("--json", action="store_true")
    membership.add_argument("--json-output")

    phase = subparsers.add_parser("phase", help="Update one checkpoint phase.")
    phase.add_argument("checkpoint")
    phase.add_argument("phase", choices=["plan", "sync", "assign"])
    phase.add_argument(
        "status", choices=["pending", "in_progress", "complete", "failed"]
    )
    phase.add_argument("--completed", action="append", default=[])
    phase.add_argument("--missing", action="append", default=[])
    phase.add_argument("--ambiguous", action="append", default=[])
    phase.add_argument("--note", action="append", default=[])
    phase.add_argument(
        "--complete-all",
        action="store_true",
        help="Record every manifest card as completed for this phase.",
    )
    phase.add_argument("--json", action="store_true")

    marker = subparsers.add_parser(
        "metric-marker", help="Emit a timestamped roster automation metric marker."
    )
    marker.add_argument("run_id")
    marker.add_argument("stage", choices=METRIC_STAGES)
    marker.add_argument("event", choices=METRIC_EVENTS)

    report = subparsers.add_parser(
        "metric-report", help="Report time and Codex tokens by automation stage."
    )
    report.add_argument("--session", default=None)
    report.add_argument("--session-root", default=None)
    report.add_argument("--run-id", default=None)
    report.add_argument("--html", default=None)
    report.add_argument("--json-output", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "resume-prompt":
        checkpoint = load_checkpoint(args.checkpoint)
        require_output_path(args.output, [args.checkpoint, checkpoint["manifest_path"]])
        prompt = resume_prompt(args.checkpoint)
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(prompt, encoding="utf-8")
            print(f"Resume instructions: {destination}")
        else:
            print(prompt, end="")
        return
    if args.command == "status-selection":
        print(json.dumps(status_selection(args.observed, args.desired), separators=(",", ":")))
        return
    if args.command in ("fast-batch", "assignment-drag", "membership-filter") and (
        args.execute or getattr(args, "prepare_only", False)
    ):
        require_host_input()
    if args.command == "membership-filter":
        manage_membership_filter(args)
        return
    if args.command == "rebuild-execution":
        manage_execution(args)
        return
    if args.command == "observation":
        manage_observation(args)
        return
    if args.command == "build-plan":
        built = build_saved_plan(args.preset, config_path=args.config)
        result = built.result
        print(
            f"Built saved plan {built.preset_name} as roster "
            f"{built.roster_name!r} in {result.build_timing.total_seconds:.2f}s"
        )
        print(f"Build record: {built.build_record_id}")
        print(f"HTML: {result.html_output}")
        print(f"Manifest: {result.automation_manifest_path}")
        return

    if args.command == "service-check":
        try:
            check_service(args.url)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from None
        return

    if args.command == "validate":
        manifest = load_manifest(args.manifest)
        print(
            f"Valid manifest {manifest['manifest_id']}: "
            f"{manifest['roster']['expected_total']} cards"
        )
        return

    if args.command == "metric-marker":
        print(metric_marker(args.run_id, args.stage, args.event))
        return

    if args.command == "metric-report":
        session_path = Path(args.session) if args.session else latest_metric_session(
            args.session_root,
            args.run_id,
        )
        metrics = analyze_session(session_path, args.run_id)
        print(format_metrics_summary(metrics))
        if args.html:
            print(f"HTML: {write_metrics_html(args.html, metrics, session_path=session_path)}")
        if args.json_output:
            print(f"JSON: {write_metrics_json(args.json_output, metrics)}")
        return

    if args.command == "init":
        checkpoint = initialize_checkpoint(args.manifest, args.checkpoint)
        if not args.json:
            checkpoint_path = args.checkpoint or checkpoint_path_for_manifest(args.manifest)
            print(f"Checkpoint: {checkpoint_path}")
        print_output(checkpoint, args.json)
        return

    if args.command == "status":
        print_output(load_checkpoint(args.checkpoint), args.json)
        return

    if args.command == "repair-attempt":
        checkpoint = record_assignment_repair(
            args.checkpoint, args.section, args.item, args.strategy
        )
        print(
            f"Repair batch claimed for {args.section}: "
            f"{checkpoint['assignment_repairs'][args.section]}/3; "
            f"items={','.join(args.item)}; strategy={args.strategy}"
        )
        return

    if args.command == "actions":
        print(format_actions(load_manifest(args.manifest), args.section))
        return

    if args.command == "ui-plan":
        manifest = load_manifest(args.manifest)
        if args.require_cid_copy_counts:
            if args.section != "sync":
                raise ValueError(
                    "--require-cid-copy-counts is valid only for the sync section"
                )
            require_cid_copy_counts(manifest)
        print(compact_ui_plan(manifest, args.section))
        return

    if args.command == "fast-batch":
        manifest = load_manifest(args.manifest)
        batch = load_fast_batch(args.batch)
        validate_fast_batch(
            batch,
            manifest_id=manifest["manifest_id"],
            section=args.section,
        )
        if not args.execute:
            print(
                f"Valid fast batch {batch['section']}: "
                f"{len(batch['actions'])} actions"
            )
            return
        capture_after = args.capture_after or str(
            Path(args.batch).with_suffix(".verification.bmp")
        )
        hwnd, _title = find_unique_window(args.title)
        result = execute_fast_batch(
            hwnd,
            batch,
            capture_after=capture_after,
        )
        print(json.dumps(result, separators=(",", ":")))
        return

    if args.command == "assignment-drag":
        manifest = load_manifest(args.manifest)
        protected = [args.manifest, args.checkpoint, args.coordinate_map, args.capture_after]
        if args.checkpoint:
            protected.append(load_checkpoint(args.checkpoint)["manifest_path"])
        require_output_path(args.json_output, protected)
        require_output_path(args.save_coordinate_map, [*protected, args.json_output])
        geometry, sources, targets = assignment_coordinates(args, manifest)
        args.client_geometry, args.source, args.target = geometry, list(sources.items()), list(targets.items())
        if args.checkpoint:
            journal_assignment_drag(args, manifest)
            return
        moves = compile_assignment_moves(
            manifest,
            args.section,
            args.family,
            sources=dict(args.source),
            targets=dict(args.target),
        )
        selected = select_assignment_moves(
            moves,
            first_only=args.first_only,
            skip_first=args.skip_first,
        )
        batch = {
            "schema_version": FAST_BATCH_SCHEMA_VERSION,
            "manifest_id": manifest["manifest_id"],
            "section": args.section,
            "client_geometry": list(args.client_geometry),
            "actions": [
                {
                    "op": "drag_batch",
                    "moves": [[move["from"], move["to"]] for move in selected],
                }
            ],
        }
        validate_fast_batch(batch)
        save_assignment_coordinates(args, manifest, geometry, sources, targets)
        if not args.execute:
            print_execution_result({
                "manifest_id": manifest["manifest_id"], "section": args.section,
                "family": args.family, "moves": selected,
            }, args)
            return
        if not args.capture_after:
            raise ValueError("--execute requires --capture-after for verification.")
        hwnd, _title = find_unique_window(args.title)
        result = execute_fast_batch(
            hwnd,
            batch,
            capture_after=args.capture_after,
        )
        print_execution_result(result, args)
        return

    completed = list(args.completed)
    if args.complete_all:
        checkpoint = load_checkpoint(args.checkpoint)
        manifest = load_manifest(checkpoint["manifest_path"])
        completed.extend(
            card["candidate_id"] for card in manifest["roster"]["membership"]
        )
    checkpoint = update_phase(
        args.checkpoint,
        args.phase,
        args.status,
        completed=completed,
        missing=args.missing,
        ambiguous=args.ambiguous,
        notes=args.note,
    )
    print_output(checkpoint, args.json)


def check_service(url: str) -> None:
    expected = automation_status()
    try:
        with urlopen(url, timeout=3) as response:
            observed = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Planner automation service check failed. Restart this repository's "
            "launch_gui.py before building a roster."
        ) from exc

    if observed != expected:
        raise RuntimeError(
            "Planner automation service is stale or incompatible. Restart this "
            "repository's launch_gui.py before building a roster."
        )
    print(
        "Planner automation service ready: "
        f"contract={expected['automation_contract_version']} "
        f"ui_plan={expected['ui_plan_schema_version']}"
    )


def manage_membership_filter(args: argparse.Namespace) -> None:
    checkpoint = load_checkpoint(args.checkpoint)
    protected = [args.checkpoint, checkpoint["manifest_path"], args.profile, args.reuse_calibration,
                 args.capture, args.capture_after]
    require_output_path(args.json_output, [*protected, args.save_profile])
    require_output_path(args.save_profile, protected)
    require_output_path(args.capture_after, [args.checkpoint, checkpoint["manifest_path"],
                                           args.profile, args.save_profile, args.capture, args.json_output])
    if args.prepare_only:
        if (not args.profile or args.execute or args.reuse_calibration or args.confirm_filter_result
                or args.client_geometry or args.open or args.capture or args.note or args.confirm_calibration
                or any(getattr(args, key) for key in ("field", "activate", "apply", "confirm"))):
            raise ValueError("--prepare-only requires --profile without mutation or new calibration flags")
        if not args.capture_after:
            raise ValueError("--prepare-only requires --capture-after for inspection before activation")
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        for destination in (args.capture_after, args.json_output):
            require_output_path(destination, [profile.get("evidence", {}).get("capture")])
        plan, action = compile_filter_preflight(args.checkpoint, profile, screen_status=args.screen_status)
        hwnd, _ = find_unique_window(args.title)
        result = execute_fast_batch(hwnd, plan, capture_after=args.capture_after)
        result.update(kind="membership_filter_preflight", action_id=action["id"], card=action["value"])
        print_execution_result(result, args)
        return
    if args.profile:
        if (args.confirm_filter_result or args.reuse_calibration or args.client_geometry or args.open or args.capture or args.note or args.confirm_calibration
                or any(getattr(args, key) for key in ("field", "activate", "apply", "confirm"))):
            raise ValueError("Use --profile or new calibration flags, not both")
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    elif args.reuse_calibration:
        if not args.confirm_calibration or not args.note:
            raise ValueError("Reuse requires --confirm-calibration and --note for unchanged screen and known status")
        if (args.client_geometry or args.open
                or any(getattr(args, key) for key in ("field", "activate", "apply", "confirm"))):
            raise ValueError("Reuse inherits controls; omit new calibration coordinates")
        source = json.loads(Path(args.reuse_calibration).read_text(encoding="utf-8"))
        profile = reuse_membership_calibration(
            args.checkpoint, source, screen_status=args.screen_status, note=args.note,
            capture=args.capture, confirm_filter_result=args.confirm_filter_result,
        )
    else:
        if not (args.confirm_calibration and args.capture and args.note and args.client_geometry):
            raise ValueError("New profile requires geometry, --capture, --note and --confirm-calibration")
        controls = {key: getattr(args, key) for key in ("field", "activate", "apply", "confirm", "open")
                    if getattr(args, key) is not None}
        profile = create_membership_profile(
            args.checkpoint, geometry=args.client_geometry, controls=controls,
            screen_status=args.screen_status, capture=args.capture, note=args.note,
        )
    evidence_capture = profile.get("evidence", {}).get("capture")
    original_capture = profile.get("evidence", {}).get("original_calibration", {}).get("capture")
    for destination in (args.save_profile, args.json_output, args.capture_after):
        require_output_path(destination, [evidence_capture, original_capture])
    plan = compile_membership_batch(args.checkpoint, profile, screen_status=args.screen_status,
                                    first_only=args.first_only)
    if args.execute and not args.capture_after:
        raise ValueError("--execute requires --capture-after for aggregate verification")
    if args.save_profile:
        write_json_output(args.save_profile, profile, protected=protected)
    result = run_execution_batch(
        args.checkpoint, plan["manifest_id"], plan, title=args.title, capture_after=args.capture_after,
    ) if args.execute else plan
    print_execution_result(result, args)


def manage_execution(args: argparse.Namespace) -> None:
    checkpoint = load_checkpoint(args.checkpoint)
    require_output_path(args.json_output, [args.checkpoint, checkpoint["manifest_path"],
                                         args.observation, args.batch, args.capture_after, args.capture])
    if args.operation == "init":
        result = initialize_execution(args.checkpoint, args.baseline_manifest)
    elif args.operation == "status":
        result = execution_status(args.checkpoint)
    elif args.operation == "bind-save-name":
        if not args.name or not args.capture or not args.note:
            raise ValueError("bind-save-name requires --name, --capture and --note")
        result = bind_local_save_name(args.checkpoint, args.name, capture=args.capture, note=args.note)
    elif args.operation == "reconcile":
        if not args.observation:
            raise ValueError("reconcile requires --observation")
        observation = read_observation(args.observation, checkpoint["manifest_fingerprint"])
        result = reconcile_execution(
            args.checkpoint, observation, retry_unapplied=args.retry_unapplied,
        )
    elif args.operation == "begin":
        result = begin_action(args.checkpoint, args.action_id)
    elif args.operation in ("validate-batch", "run-batch"):
        if not args.batch:
            raise ValueError("Execution batch requires --batch")
        checkpoint = load_checkpoint(args.checkpoint)
        manifest = load_manifest(checkpoint["manifest_path"])
        batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        if args.operation == "validate-batch":
            native = validate_execution_batch(
                batch, manifest["manifest_id"], execution_status(args.checkpoint)["next_batch"],
            )
            result = {"valid": True, "transactions": len(native)}
        else:
            if not args.capture_after:
                raise ValueError("run-batch requires --capture-after")
            result = run_execution_batch(
                args.checkpoint, manifest["manifest_id"], batch,
                title=args.title, capture_after=args.capture_after,
            )
    else:
        if not args.batch or not args.capture_after:
            raise ValueError("run requires --batch and --capture-after")
        # Fail before any journal intent, retry count, window activation, or input.
        require_host_input()
        checkpoint = load_checkpoint(args.checkpoint)
        manifest = load_manifest(checkpoint["manifest_path"])
        action = execution_status(args.checkpoint)["next_action"]
        if action is None or action["id"] != args.action_id:
            raise ValueError("Only the next action may execute")
        if action["operation"] == "verify":
            raise ValueError("Verification uses begin and reconcile without native input")
        batch = load_fast_batch(args.batch)
        validate_fast_batch(batch, manifest_id=manifest["manifest_id"], section=action["section"])
        hwnd, _ = find_unique_window(args.title)
        result = execute_action(
            args.checkpoint, args.action_id,
            lambda _: execute_fast_batch(hwnd, batch, capture_after=args.capture_after),
        )
    print_execution_result(result, args)


def journal_assignment_drag(args: argparse.Namespace, manifest: dict) -> None:
    checkpoint = load_checkpoint(args.checkpoint)
    if checkpoint["manifest_fingerprint"] != manifest["fingerprint"]:
        raise ValueError("Assignment manifest does not match the checkpoint")
    if args.skip_first:
        raise ValueError("Journaled drags skip completed actions automatically; omit --skip-first")
    status = execution_status(args.checkpoint)
    if status["state"] != "ready":
        raise ValueError("Reconcile the checkpoint before compiling the next drag family")
    actions = status["next_batch"][:1] if args.first_only else status["next_batch"]
    moves = compile_journal_assignment_moves(
        actions, args.section, args.family, sources=dict(args.source), targets=dict(args.target),
    )
    plan = {
        "schema_version": 1, "manifest_id": manifest["manifest_id"], "section": args.section,
        "client_geometry": list(args.client_geometry),
        "transactions": [{"action_id": move["action_id"], "actions": [{
            "op": "drag_batch", "moves": [[move["from"], move["to"]]],
        }]} for move in moves],
    }
    validate_execution_batch(plan, manifest["manifest_id"], actions)
    save_assignment_coordinates(args, manifest, args.client_geometry, dict(args.source), dict(args.target))
    if not args.execute:
        print_execution_result(plan, args)
        return
    if not args.capture_after:
        raise ValueError("--execute requires --capture-after for aggregate verification")
    result = run_execution_batch(
        args.checkpoint, manifest["manifest_id"], plan,
        title=args.title, capture_after=args.capture_after,
    )
    print_execution_result(result, args)


def print_execution_result(result: dict, args: argparse.Namespace) -> None:
    output = write_json_output(args.json_output, result) if args.json_output else None
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(compact_execution_receipt(result, checkpoint_path=args.checkpoint))
        if output:
            print(f"JSON: {output}")
        if getattr(args, "save_coordinate_map", None):
            print(f"Coordinate map: {args.save_coordinate_map}")


def manage_observation(args: argparse.Namespace) -> None:
    checkpoint = load_checkpoint(args.checkpoint)
    require_output_path(args.output, [args.checkpoint, checkpoint["manifest_path"], args.base,
                                     args.capture, args.actual_membership])
    actual = None
    if args.actual_membership:
        actual = json.loads(Path(args.actual_membership).read_text(encoding="utf-8-sig"))
        if isinstance(actual, dict):
            actual = actual.get("membership")
        if not isinstance(actual, list):
            raise ValueError("--actual-membership must contain an actual membership array")
    overrides = dict(args.actual_target)
    if len(overrides) != len(args.actual_target):
        raise ValueError("Each actual target must be supplied once")
    observation = prepare_observation(
        args.checkpoint, args.scope, base=args.base, capture=args.capture,
        confirm_matches=args.confirm_matches, actual_targets=overrides,
        actual_membership=actual, actual_save=args.actual_save,
    )
    write_json_output(args.output, observation)
    print(json.dumps(observation, indent=2, sort_keys=True) if args.json else compact_execution_receipt(observation))
    if not args.json:
        print(f"Observation: {args.output}")


def parse_actual_target(value: str) -> tuple[str, object]:
    key, separator, raw = value.partition("=")
    if not separator or not key:
        raise argparse.ArgumentTypeError("expected TARGET=JSON")
    try:
        return key, json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("expected TARGET=JSON") from exc


def parse_named_point(value: str) -> tuple[str, tuple[int, int]]:
    key, separator, point = value.partition("=")
    if not separator or not key:
        raise argparse.ArgumentTypeError("expected KEY=X,Y")
    try:
        x_text, y_text = point.split(",", 1)
        return key, (int(x_text), int(y_text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected KEY=X,Y") from exc


def parse_client_geometry(value: str) -> tuple[int, int, int, int]:
    try:
        parts = tuple(int(part) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected LEFT,TOP,WIDTH,HEIGHT"
        ) from exc
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("expected LEFT,TOP,WIDTH,HEIGHT")
    return parts


def print_output(checkpoint: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(checkpoint, indent=2, sort_keys=True))
    else:
        print(format_checkpoint_summary(checkpoint))


def format_actions(manifest: dict, section: str) -> str:
    if section == "sync":
        lines = ["candidate_id\tcid\tvariant\ttype\tname"]
        for card in manifest["roster"]["membership"]:
            lines.append(
                "\t".join(
                    [
                        card["candidate_id"],
                        card["cid"],
                        "Y" if card["variant"] else "N",
                        card["player_type"],
                        card["name"],
                    ]
                )
            )
        return "\n".join(lines)

    if section == "pitching":
        lines = ["ROTATION"]
        for entry in manifest["pitching"]["rotation"]:
            card = entry["card"]
            lines.append(
                f"{entry['order']}\t{card['cid']}\t"
                f"{'Y' if card['variant'] else 'N'}\t{card['name']}"
            )
        lines.append("BULLPEN")
        for entry in manifest["pitching"]["bullpen"]:
            card = entry["card"]
            lines.append(
                "\t".join(
                    [
                        card["cid"],
                        "Y" if card["variant"] else "N",
                        card["name"],
                        entry["primary_role"],
                        entry["usage"],
                        entry["secondary_role"] or "-",
                    ]
                )
            )
        return "\n".join(lines)

    lineup = manifest["lineups"][section]["starters"]
    bench = manifest["bench_actions"][section]
    lines = [f"LINEUP {section}"]
    for entry in lineup:
        card = entry["card"]
        lines.append(
            f"{entry['batting_order']}\t{entry['position']}\t"
            f"{card['cid']}\t{card['name']}"
        )
        for depth in entry["depth"]:
            backup = depth["card"]
            lines.append(
                f"  depth {depth['order']}\t{entry['position']}\t"
                f"{backup['cid']}\t{backup['name']}\t{depth['condition']}"
            )
    for label, key in (
        ("PINCH HITTERS", "pinch_hitters"),
        ("PINCH RUNNERS", "pinch_runners"),
    ):
        lines.append(label)
        for entry in bench[key]:
            card = entry["card"]
            lines.append(f"{entry['order']}\t{card['cid']}\t{card['name']}")
    return "\n".join(lines)


if __name__ == "__main__":
    run_cli(main)
