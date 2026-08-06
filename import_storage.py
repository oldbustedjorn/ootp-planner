from __future__ import annotations

import argparse

from ootp_opt.storage.import_preview import (
    preview_existing_state,
    render_import_preview,
)
from ootp_opt.storage.importer import (
    StorageImportError,
    import_existing_state,
    verify_imported_state,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview, import, or verify legacy planner state in SQLite."
    )
    parser.add_argument("--config", default="config.toml")
    parser.add_argument(
        "--history", default="outputs/roster_build_registry.json"
    )
    parser.add_argument("--database")
    parser.add_argument("--backup-dir", default="state/backups")
    parser.add_argument("--details", action="store_true")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--apply", action="store_true")
    operation.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify:
            verification = verify_imported_state(
                config_path=args.config,
                history_path=args.history,
                database_path=args.database,
            )
            print_verification(verification)
            return 0 if verification.passed else 1

        preview = preview_existing_state(args.config, args.history)
        print(render_import_preview(preview, details=args.details))
        if not args.apply:
            return 1 if preview.error_count else 0
        result = import_existing_state(
            config_path=args.config,
            history_path=args.history,
            database_path=args.database,
            backup_dir=args.backup_dir,
        )
    except StorageImportError as exc:
        print(f"StorageImportError: {exc}")
        return 1

    print("")
    print(f"Pre-import backup: {result.backup.path}")
    print(f"Database: {result.database_path}")
    print_verification(result.verification)
    print("TOML presets and JSON history remain unchanged and authoritative.")
    return 0


def print_verification(verification) -> None:
    print(f"Presets: {verification.stored_presets}/{verification.expected_presets}")
    print(f"Builds: {verification.stored_builds}/{verification.expected_builds}")
    print(f"Artifacts: {verification.stored_artifacts}/{verification.expected_artifacts}")
    print(f"Preset IDs match: {verification.preset_ids_match}")
    print(f"Build IDs match: {verification.build_ids_match}")
    print(f"Foreign-key errors: {verification.foreign_key_errors}")
    print(f"Integrity check: {verification.integrity_check}")
    print(f"Verification passed: {verification.passed}")


if __name__ == "__main__":
    raise SystemExit(main())
