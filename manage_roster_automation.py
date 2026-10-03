from __future__ import annotations

import argparse
import json

from ootp_opt.automation.checkpoint import (
    format_checkpoint_summary,
    initialize_checkpoint,
    load_checkpoint,
    update_phase,
)
from ootp_opt.automation.manifest import load_manifest
from ootp_opt.automation.ui_plan import UI_PLAN_SECTIONS, compact_ui_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage OOTP automation artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a manifest.")
    validate.add_argument("manifest")

    initialize = subparsers.add_parser("init", help="Create a fresh checkpoint.")
    initialize.add_argument("manifest")
    initialize.add_argument("--checkpoint", default=None)
    initialize.add_argument("--json", action="store_true")

    status = subparsers.add_parser("status", help="Show checkpoint status.")
    status.add_argument("checkpoint")
    status.add_argument("--json", action="store_true")

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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "validate":
        manifest = load_manifest(args.manifest)
        print(
            f"Valid manifest {manifest['manifest_id']}: "
            f"{manifest['roster']['expected_total']} cards"
        )
        return

    if args.command == "init":
        checkpoint = initialize_checkpoint(args.manifest, args.checkpoint)
        print_output(checkpoint, args.json)
        return

    if args.command == "status":
        print_output(load_checkpoint(args.checkpoint), args.json)
        return

    if args.command == "actions":
        print(format_actions(load_manifest(args.manifest), args.section))
        return

    if args.command == "ui-plan":
        print(compact_ui_plan(load_manifest(args.manifest), args.section))
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
