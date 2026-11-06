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
    select_assignment_moves,
)
from ootp_opt.automation.manifest import load_manifest
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
from ootp_opt.automation.windows_drag import find_unique_window
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
    assignment_drag.add_argument("section", choices=ASSIGNMENT_DRAG_SECTIONS)
    assignment_drag.add_argument("family", choices=ASSIGNMENT_DRAG_FAMILIES)
    assignment_drag.add_argument(
        "--client-geometry",
        type=parse_client_geometry,
        required=True,
        metavar="LEFT,TOP,WIDTH,HEIGHT",
    )
    assignment_drag.add_argument(
        "--source",
        action="append",
        type=parse_named_point,
        required=True,
        metavar="CID=X,Y",
    )
    assignment_drag.add_argument(
        "--target",
        action="append",
        type=parse_named_point,
        required=True,
        metavar="KEY=X,Y",
    )
    selection = assignment_drag.add_mutually_exclusive_group()
    selection.add_argument("--first-only", action="store_true")
    selection.add_argument("--skip-first", type=int, default=0)
    assignment_drag.add_argument("--execute", action="store_true")
    assignment_drag.add_argument("--capture-after", default=None)
    assignment_drag.add_argument("--title", default="Out of the Park Baseball 27")

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
        if not args.execute:
            print(
                json.dumps(
                    {
                        "manifest_id": manifest["manifest_id"],
                        "section": args.section,
                        "family": args.family,
                        "moves": selected,
                    },
                    separators=(",", ":"),
                )
            )
            return
        if not args.capture_after:
            raise ValueError("--execute requires --capture-after for verification.")
        hwnd, _title = find_unique_window(args.title)
        result = execute_fast_batch(
            hwnd,
            batch,
            capture_after=args.capture_after,
        )
        print(json.dumps(result, separators=(",", ":")))
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
    main()
