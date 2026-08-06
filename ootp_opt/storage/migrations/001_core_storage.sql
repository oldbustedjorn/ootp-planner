CREATE TABLE presets (
    id TEXT PRIMARY KEY,
    command_name TEXT NOT NULL UNIQUE,
    display_title TEXT,
    note TEXT,
    base_profile TEXT NOT NULL,
    build_method TEXT NOT NULL CHECK (build_method IN ('greedy', 'optimizer')),
    rules_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'application',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE builds (
    id TEXT PRIMARY KEY,
    source_record_id TEXT,
    build_number INTEGER,
    preset_id TEXT REFERENCES presets(id) ON DELETE SET NULL,
    roster_name TEXT NOT NULL,
    build_type TEXT NOT NULL,
    build_method TEXT NOT NULL CHECK (build_method IN ('greedy', 'optimizer')),
    status TEXT NOT NULL,
    model_version TEXT NOT NULL,
    request_json TEXT NOT NULL,
    ruleset_json TEXT NOT NULL,
    diagnostics_json TEXT NOT NULL DEFAULT '{}',
    objective_score REAL,
    source_fingerprint TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX builds_preset_created_idx ON builds(preset_id, created_at DESC);
CREATE INDEX builds_roster_created_idx ON builds(roster_name, created_at DESC);
CREATE INDEX builds_source_record_idx ON builds(source_record_id);

CREATE TABLE build_players (
    build_id TEXT NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
    card_id TEXT NOT NULL,
    person_id TEXT,
    player_name TEXT NOT NULL,
    player_type TEXT NOT NULL CHECK (player_type IN ('hitter', 'pitcher')),
    selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
    card_snapshot_json TEXT NOT NULL,
    score_snapshot_json TEXT NOT NULL,
    PRIMARY KEY (build_id, card_id)
);

CREATE INDEX build_players_person_idx ON build_players(person_id);
CREATE INDEX build_players_selected_idx ON build_players(build_id, selected);

CREATE TABLE build_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    assignment_kind TEXT NOT NULL,
    lineup TEXT,
    role TEXT,
    position TEXT,
    score REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (build_id, card_id)
        REFERENCES build_players(build_id, card_id) ON DELETE CASCADE
);

CREATE INDEX build_assignments_build_idx ON build_assignments(build_id);
CREATE INDEX build_assignments_card_idx ON build_assignments(build_id, card_id);

CREATE TABLE build_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id TEXT NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (build_id, artifact_type, path)
);

CREATE INDEX build_artifacts_build_idx ON build_artifacts(build_id);
