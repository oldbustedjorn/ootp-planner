from __future__ import annotations

import argparse
import json

from ootp_opt.automation.checkpoint import (
    initialize_checkpoint,
    load_checkpoint,
    update_phase,
)
from ootp_opt.automation.manifest import load_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage OOTP automation artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a manifest.")
    validate.add_argument("manifest")

    initialize = subparsers.add_parser("init", help="Create a fresh checkpoint.")
    initialize.add_argument("manifest")
    initialize.add_argument("--checkpoint", default=None)

    status = subparsers.add_parser("status", help="Show checkpoint status.")
    status.add_argument("checkpoint")

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
        print(json.dumps(checkpoint, indent=2, sort_keys=True))
        return

    if args.command == "status":
        print(json.dumps(load_checkpoint(args.checkpoint), indent=2, sort_keys=True))
        return

    checkpoint = update_phase(
        args.checkpoint,
        args.phase,
        args.status,
        completed=args.completed,
        missing=args.missing,
        ambiguous=args.ambiguous,
        notes=args.note,
    )
    print(json.dumps(checkpoint, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
