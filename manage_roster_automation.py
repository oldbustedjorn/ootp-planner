from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from ootp_opt.automation.checkpoint import (
    ASSIGNMENT_SECTIONS,
    format_checkpoint_summary,
    initialize_checkpoint,
    load_checkpoint,
    record_assignment_repair,
    update_phase,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage OOTP automation artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a manifest.")
    validate.add_argument("manifest")

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
