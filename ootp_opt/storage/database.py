from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ootp_opt.storage.migrator import migrate_database

DEFAULT_DATABASE_PATH = Path("state") / "ootp_planner.sqlite3"


def database_path_from_config(config: dict[str, Any] | None = None) -> Path:
    storage = (config or {}).get("storage", {})
    return Path(storage.get("database_path", DEFAULT_DATABASE_PATH))


def connect_database(path: str | Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    database_path = Path(path)
    if database_path != Path(":memory:"):
        database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database(path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    connection = connect_database(path)
    try:
        return migrate_database(connection)
    finally:
        connection.close()
