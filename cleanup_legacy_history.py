from __future__ import annotations

import argparse

from ootp_opt.storage.legacy_cleanup import (
    CleanupError,
    apply_legacy_cleanup,
    plan_legacy_cleanup,
    render_cleanup_plan,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or safely clean legacy GUI build history."
    )
    parser.add_argument("--config", default="config.toml")
    parser.add_argument(
        "--history", default="outputs/roster_build_registry.json"
    )
    parser.add_argument("--backup-dir", default="state/backups")
    parser.add_argument("--details", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create a ZIP backup, rewrite history, and delete orphan artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = plan_legacy_cleanup(args.config, args.history)
        print(render_cleanup_plan(plan, details=args.details))
        if not args.apply:
            return 1 if plan.error_count else 0
        result = apply_legacy_cleanup(plan, args.backup_dir)
    except CleanupError as exc:
        print(f"CleanupError: {exc}")
        return 1

    print("")
    print(f"Backup written: {result.backup_path}")
    print(f"History records retained: {result.retained_record_count}")
    print(f"History records removed: {result.removed_record_count}")
    print(f"Files deleted: {len(result.deleted_paths)}")
    print(f"Files that could not be deleted: {len(result.failed_paths)}")
    return 1 if result.failed_paths else 0


if __name__ == "__main__":
    raise SystemExit(main())
