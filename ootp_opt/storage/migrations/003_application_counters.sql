CREATE TABLE application_counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL CHECK (value >= 0),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO application_counters (name, value)
SELECT
    'roster_reference',
    COALESCE(MAX(reference_number), 0)
FROM (
    SELECT build_number AS reference_number
    FROM builds
    WHERE build_number IS NOT NULL

    UNION ALL

    SELECT CAST(json_extract(rules_json, '$._gui_build_number') AS INTEGER)
    FROM presets
    WHERE json_extract(rules_json, '$._gui_build_number') IS NOT NULL
);
