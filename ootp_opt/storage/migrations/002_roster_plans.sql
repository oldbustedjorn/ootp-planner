ALTER TABLE presets ADD COLUMN plan_type TEXT NOT NULL DEFAULT 'pt_tournament';
ALTER TABLE presets ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'active'
    CHECK (lifecycle_status IN ('draft', 'active', 'archived'));
ALTER TABLE presets ADD COLUMN validation_errors_json TEXT NOT NULL DEFAULT '{}';

UPDATE presets
SET plan_type = COALESCE(
    NULLIF(json_extract(rules_json, '$._gui_build_type'), ''),
    'pt_tournament'
);

INSERT INTO presets (
    id,
    command_name,
    display_title,
    note,
    base_profile,
    build_method,
    rules_json,
    source,
    plan_type,
    lifecycle_status,
    validation_errors_json,
    created_at,
    updated_at
)
SELECT
    'legacy-plan-' || id,
    'roster_' || COALESCE(printf('%03d', build_number), 'unknown') || '_' || substr(id, 1, 8),
    roster_name,
    'Created automatically from legacy build history.',
    COALESCE(NULLIF(json_extract(request_json, '$.base_profile'), ''), 'playoff_pt'),
    build_method,
    json_set(
        COALESCE(json_extract(request_json, '$.overrides'), '{}'),
        '$.base_profile', COALESCE(NULLIF(json_extract(request_json, '$.base_profile'), ''), 'playoff_pt'),
        '$.build_method', build_method,
        '$._gui_title', roster_name,
        '$._gui_roster_name', roster_name,
        '$._gui_build_type', build_type,
        '$._gui_build_number', build_number
    ),
    'legacy-build-adoption',
    build_type,
    'active',
    '{}',
    created_at,
    created_at
FROM builds
WHERE preset_id IS NULL;

UPDATE builds
SET preset_id = 'legacy-plan-' || id
WHERE preset_id IS NULL;

CREATE VIEW roster_plans AS
SELECT
    id,
    command_name AS plan_key,
    display_title,
    note,
    base_profile,
    build_method,
    rules_json,
    source,
    plan_type,
    lifecycle_status,
    validation_errors_json,
    created_at,
    updated_at
FROM presets;

CREATE VIEW build_runs AS
SELECT
    id,
    source_record_id,
    build_number,
    preset_id AS roster_plan_id,
    roster_name,
    build_type,
    build_method,
    status,
    model_version,
    request_json,
    ruleset_json,
    diagnostics_json,
    objective_score,
    source_fingerprint,
    created_at
FROM builds;
