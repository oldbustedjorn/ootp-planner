"""SQLite storage primitives for durable planner state."""

from ootp_opt.storage.database import (
    DEFAULT_DATABASE_PATH,
    connect_database,
    database_path_from_config,
    initialize_database,
)
from ootp_opt.storage.backup import (
    StorageBackup,
    StorageBackupError,
    create_storage_backup,
    restore_storage_backup,
    verify_storage_backup,
)
from ootp_opt.storage.importer import (
    ImportVerification,
    StorageImportError,
    StorageImportResult,
    import_existing_state,
    verify_imported_state,
)
from ootp_opt.storage.migrator import (
    LATEST_SCHEMA_VERSION,
    MigrationError,
    current_schema_version,
    migrate_database,
)
from ootp_opt.storage.models import BuildRecord, PresetRecord
from ootp_opt.storage.repositories import (
    BuildRepository,
    PresetRepository,
    SqliteBuildRepository,
    SqlitePresetRepository,
)

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "LATEST_SCHEMA_VERSION",
    "MigrationError",
    "ImportVerification",
    "StorageBackup",
    "StorageBackupError",
    "StorageImportError",
    "StorageImportResult",
    "BuildRecord",
    "BuildRepository",
    "PresetRecord",
    "PresetRepository",
    "SqliteBuildRepository",
    "SqlitePresetRepository",
    "connect_database",
    "create_storage_backup",
    "current_schema_version",
    "database_path_from_config",
    "initialize_database",
    "import_existing_state",
    "migrate_database",
    "restore_storage_backup",
    "verify_imported_state",
    "verify_storage_backup",
]
