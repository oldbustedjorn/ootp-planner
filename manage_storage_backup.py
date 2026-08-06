from __future__ import annotations

import argparse
from pathlib import Path

from ootp_opt.config import load_config
from ootp_opt.storage.backup import (
    StorageBackupError,
    create_storage_backup,
    restore_storage_backup,
    verify_storage_backup,
)
from ootp_opt.storage.database import database_path_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up or restore planner storage.")
    parser.add_argument("operation", choices=("backup", "verify", "restore"))
    parser.add_argument("archive", nargs="?")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument(
        "--history", default="outputs/roster_build_registry.json"
    )
    parser.add_argument("--database")
    parser.add_argument("--backup-dir", default="state/backups")
    parser.add_argument("--include-sources", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = resolve_database_path(args.config, args.database)
    try:
        if args.operation == "backup":
            backup = create_storage_backup(
                config_path=args.config,
                history_path=args.history,
                database_path=database_path,
                backup_dir=args.backup_dir,
            )
            print(f"Backup written: {backup.path}")
            print(f"Database included: {backup.includes_database}")
            return 0
        if not args.archive:
            parser_error("verify and restore require an archive path")
        backup = verify_storage_backup(args.archive)
        print(f"Backup verified: {backup.path}")
        print(f"Purpose: {backup.manifest.get('purpose')}")
        print(f"Created: {backup.manifest.get('created_at')}")
        print(f"Database included: {backup.includes_database}")
        if args.operation == "verify" or not args.apply:
            if args.operation == "restore":
                print("No files changed. Add --apply to restore this archive.")
            return 0
        result = restore_storage_backup(
            backup.path,
            config_path=args.config,
            history_path=args.history,
            database_path=database_path,
            backup_dir=args.backup_dir,
            include_sources=args.include_sources,
        )
    except StorageBackupError as exc:
        print(f"StorageBackupError: {exc}")
        return 1

    print(f"Database restored: {result.database_restored}")
    print(f"Config/history restored: {result.sources_restored}")
    print(f"Pre-restore safety backup: {result.safety_backup_path}")
    return 0


def parser_error(message: str) -> None:
    raise StorageBackupError(message)


def resolve_database_path(config_path: str, explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path)
    configured = database_path_from_config(load_config(config_path))
    if configured.is_absolute():
        return configured
    return Path(config_path).parent / configured


if __name__ == "__main__":
    raise SystemExit(main())
