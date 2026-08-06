from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from importlib import resources

MIGRATION_FILE_PATTERN = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")
MIGRATION_PACKAGE = "ootp_opt.storage.migrations"


class MigrationError(RuntimeError):
    """Raised when the database schema cannot be migrated safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def discover_migrations() -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    migration_root = resources.files(MIGRATION_PACKAGE)

    for entry in migration_root.iterdir():
        match = MIGRATION_FILE_PATTERN.match(entry.name)
        if not match:
            continue
        migrations.append(
            Migration(
                version=int(match.group(1)),
                name=match.group(2),
                sql=entry.read_text(encoding="utf-8"),
            )
        )

    migrations.sort(key=lambda migration: migration.version)
    versions = [migration.version for migration in migrations]
    expected = list(range(1, len(migrations) + 1))
    if versions != expected:
        raise MigrationError(
            f"Migration versions must be contiguous from 1; found {versions}."
        )
    return tuple(migrations)


MIGRATIONS = discover_migrations()
LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version if MIGRATIONS else 0


def current_schema_version(connection: sqlite3.Connection) -> int:
    table_exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'schema_migrations'
        """
    ).fetchone()
    if table_exists is None:
        return 0

    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
    ).fetchone()
    return int(row[0])


def migrate_database(connection: sqlite3.Connection) -> int:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    connection.commit()

    current_version = current_schema_version(connection)
    if current_version > LATEST_SCHEMA_VERSION:
        raise MigrationError(
            "Database schema version "
            f"{current_version} is newer than supported version "
            f"{LATEST_SCHEMA_VERSION}."
        )

    for migration in MIGRATIONS:
        if migration.version <= current_version:
            continue
        _apply_migration(connection, migration)
        current_version = migration.version

    return current_version


def _apply_migration(
    connection: sqlite3.Connection,
    migration: Migration,
) -> None:
    safe_name = migration.name.replace("'", "''")
    script = f"""
    BEGIN IMMEDIATE;
    {migration.sql}
    INSERT INTO schema_migrations (version, name)
    VALUES ({migration.version}, '{safe_name}');
    COMMIT;
    """
    try:
        connection.executescript(script)
    except sqlite3.Error as exc:
        if connection.in_transaction:
            connection.rollback()
        raise MigrationError(
            f"Failed to apply migration {migration.version:03d}_{migration.name}: {exc}"
        ) from exc
