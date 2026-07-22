# OOTP Planner Code Map

This is a curated reference to the main modules and responsibilities.

## Top-Level Files

### `config.toml`

Primary configuration file.

Contains:

- local OOTP export paths
- hitter and pitcher scoring weights
- simulation year and ballpark settings
- position blends
- roster base profiles
- tournament presets
- cap, variant, card type, year, tier, and tier slot settings

### `build_roster.py`

Thin command-line wrapper for roster builds.

Responsibilities:

- parse CLI options and overrides
- call `ootp_opt.services.roster_build_service.build_roster`
- print returned report sections

Roster construction, repair, HTML export, and snapshot writing live in the service layer so the future UI can reuse them directly.

### `launch_gui.py`

Starts the local web UI.

Run with:

```powershell
.\.venv\Scripts\python.exe launch_gui.py
```

### `find_store_upgrades.py`

Store upgrade command-line script.

Responsibilities:

- parse base profile, preset, eligibility filters, and simulation context
- build the current roster using environment-adjusted scoring
- score and filter store candidates with the same base eligibility rules
- write store upgrade HTML

Current limitation:

- replacement legality does not model cap or tier-slot changes candidate by candidate

### `compare_headers.py`

Utility for comparing old/new OOTP export headers.

### `requirements.txt`

Python dependencies for the project venv.

## Package: `ootp_opt`

### `ootp_opt/config.py`

Loads TOML config.

Key function:

- `load_config(path)`

### `ootp_opt/cli.py`

Original ratings/shortlist CLI.

Use this for generating ratings CSVs and hitter shortlists.

## Package: `ootp_opt.gui`

### `ootp_opt.gui.server`

Dependency-free local web UI built on Python's standard-library HTTP server.

Responsibilities:

- render a roster-build form
- map form fields into `RosterBuildRequest`
- support standard PT, playoff-style PT, and PT tournament builds
- list configured tournament presets and show preset details
- delegate preset and build-history persistence to `preset_service`
- call `ootp_opt.services.roster_build_service.build_roster`
- call `ootp_opt.services.store_upgrade_service.find_store_upgrades`
- serve generated HTML reports from `outputs/`

## Package: `ootp_opt.ingest`

### `ootp_opt.ingest.pt_hitters`

Loads owned-card hitter exports.

Responsibilities:

- map raw OOTP hitter columns to normalized names
- handle OOTP 26/27 fielding column differences
- normalize trainability flags
- normalize `VAR` to boolean `is_variant`
- expose `CType` as `pt_type`

Key function:

- `load_pt_cards_csv(path)`

### `ootp_opt.ingest.pt_pitchers`

Loads owned-card pitcher exports.

Responsibilities:

- map raw OOTP pitcher columns to normalized names
- handle `HRR`/`HRA`
- handle `P.1`/`P_1`
- normalize `VAR` to boolean `is_variant`
- expose `CType` as `pt_type`

Key function:

- `load_pt_pitchers_csv(path)`

### `ootp_opt.ingest.pt_store`

Loads PT store card-list exports.

Responsibilities:

- normalize store columns to the same downstream names used by owned-card exports
- split hitters and pitchers by store position
- map numeric store `Card Type` codes to owned-card `pt_type` codes
- preserve raw store classification fields as debug columns
- normalize handedness, prices, ownership, tiers, and trainability flags

Key functions:

- `load_pt_store_csv(path)`
- `split_store_hitters_pitchers(df)`
- `load_pt_store_hitters_pitchers(path)`

## Package: `ootp_opt.domain`

### `ootp_opt.domain.simulation_context`

Loads and resolves simulation context.

Responsibilities:

- load `ootp_opt/data/year_era_factors.csv`
- load `ootp_opt/data/park_factors.csv`
- keep simulation year and ballpark year independent
- support direct custom park-factor overrides when a tournament park is missing from the CSV
- apply conservative era and park multipliers to scoring config

Key functions:

- `resolve_simulation_context(...)`
- `apply_simulation_context_to_config(...)`
- `load_era_factors(year)`
- `load_park_factors(ballpark, year)`

### `ootp_opt.domain.rating`

Core scoring formulas.

Key classes:

- `RatingWeights`
- `HitterRoleWeights`
- `PitcherRatingWeights`
- `PitcherRoleWeights`

Key functions:

- `rate_hitters_basic(df, weights)`
- `rate_pitchers_basic(df, weights)`
- `add_hitter_and_position_scores(df, weights)`
- `add_pitcher_role_scores(df, weights)`

### `ootp_opt.domain.hitter_transforms`

Nonlinear hitter rating transforms.

### `ootp_opt.domain.pitcher_transforms`

Nonlinear pitcher rating transforms.

### `ootp_opt.domain.candidate_identity`

Canonical identities for selectable roster assets and the people represented by
those assets.

Responsibilities:

- assign one stable `candidate_id` to each selectable card or player record
- assign one `person_key` used by duplicate-player constraints
- keep identity independent from candidate source such as owned or store data
- retain the export-specific identifier separately as `source_record_id`
- provide a PT card schema and a save-scoped base-game schema factory
- derive deterministic fallback candidate IDs when a source ID is unavailable

Key classes and functions:

- `CandidateIdentitySchema`
- `PT_CARD_IDENTITY_SCHEMA`
- `build_base_game_identity_schema(...)`
- `attach_candidate_identities(...)`

## Package: `ootp_opt.services`

### `ootp_opt.services.candidate_service`

Resolved build context and candidate-pool contracts shared by roster builds and
store analysis.

Responsibilities:

- resolve scoring environment and simulation context once per build
- produce the final scoring configuration used by every candidate source
- retain scored hitter and pitcher populations for diagnostics
- expose ruleset-eligible hitter and pitcher subsets to selection code
- attach canonical candidate and person identities before filtering
- validate that required candidate groups are non-empty

Key classes:

- `BuildContext`
- `CandidatePool`

Key functions:

- `resolve_build_context(...)`
- `build_candidate_pool(...)`

### `ootp_opt.services.build_timing`

Ordered build-stage timing diagnostics.

Responsibilities:

- record elapsed time between named build checkpoints
- expose immutable stage and total timing results
- format short durations consistently for CLI and HTML reporting

Key classes:

- `BuildTimer`
- `BuildTiming`
- `BuildTimingStage`

### `ootp_opt.services.preset_service`

Reusable preset and build-history persistence layer.

Responsibilities:

- record and load GUI build history
- create presets from build-history records
- update preset display titles and notes while preserving stable preset IDs
- resolve the roster identity and report path used when rebuilding a preset
- delete preset TOML blocks and their owned output files
- provide stable preset roster and upgrade report paths

Key functions:

- `append_build_record(...)`
- `append_history_record_as_preset(...)`
- `resolve_preset_build_metadata(...)`
- `update_preset_notes(...)`
- `delete_preset(...)`

### `ootp_opt.services.rating_service`

Scoring orchestration layer.

Responsibilities:

- build weight objects from config
- call ingest functions
- call scoring functions
- sort scored DataFrames
- write shortlist output as part of hitter scoring
- score already-loaded store DataFrames

Key functions:

- `rate_cards_service(input_path, profile, config=None)`
- `rate_hitters_df(df, config)`
- `rate_pitchers_df(df, config)`

### `ootp_opt.services.roster_build_service`

Reusable roster build orchestration layer.

Responsibilities:

- load config and resolve base profile or tournament preset
- resolve one `BuildContext` and prepare one owned-card `CandidatePool`
- apply direct overrides from CLI or future UI requests
- resolve simulation year and ballpark context
- score owned hitters and pitchers
- filter eligible cards
- build hitter and pitcher rosters
- run duplicate-player validation
- report and repair variant limits, tier slots, and point caps
- record ordered stage timings for build diagnostics and performance baselines
- write roster HTML and snapshot files
- return structured build results plus report sections

Key classes:

- `RosterBuildRequest`
- `RosterBuildResult`

Key functions:

- `build_roster(request)`
- `build_ruleset(cfg, request)`
- `build_output_name(ruleset, overrides)`

### `ootp_opt.services.shortlist_service`

Creates hitter shortlist views.

Key function:

- `generate_hitter_shortlists(df, top_n=15)`

### `ootp_opt.services.store_upgrade_service`

Reusable store-upgrade orchestration layer.

Responsibilities:

- resolve base profile or tournament preset rulesets
- reuse one `BuildContext` for owned and store candidate pools
- apply direct overrides from CLI or future UI requests
- resolve simulation year and ballpark context
- score owned cards and store candidates
- build the fresh comparison roster
- find hitter and pitcher upgrades
- write store upgrade HTML reports

Key classes:

- `StoreUpgradeRequest`
- `StoreUpgradeResult`

Key functions:

- `find_store_upgrades(request)`
- `build_ruleset(cfg, request)`
- `build_output_name(ruleset)`

## Package: `ootp_opt.roster`

### `ootp_opt.roster.models`

Lightweight data containers.

Key classes:

- `HitterRoster`
- `PitcherRoster`

### `ootp_opt.roster.rules`

Ruleset parsing and normalization.

Responsibilities:

- build rulesets from base profiles
- build rulesets from tournament presets
- merge defaults, base profile settings, preset overrides, and CLI overrides
- normalize optional fields such as tiers, card values, live mode, card types, years, simulation context, caps, variant limits, and tier slots

Key classes:

- `Ruleset`
- `BenchRoleRequirement`

Key functions:

- `build_ruleset_from_base_profile(...)`
- `build_ruleset_from_tournament_preset(...)`

### `ootp_opt.roster.slots`

Optimizer-facing lineup assignment and pitcher-allocation contracts.

Responsibilities:

- define separate position assignments for the vs-RHP and vs-LHP lineups
- attach the correct split position score, or split batting score for DH
- keep bench status derived from selection and each split lineup assignment
- define split-specific bench coverage outside the slot plan
- keep pitcher role groups configurable and validate them against roster size
- allow future pitching groups such as setup, closer, or stopper

Key classes:

- `LineupAssignmentSlot`
- `LineupCoverageRequirement`
- `PitcherRoleGroup`
- `RosterSlotPlan`

Key function:

- `build_current_roster_slot_plan(...)`
- `build_lineup_coverage_requirements(...)`

### `ootp_opt.roster.eligibility`

Filters scored players to cards legal for a ruleset.

Supported filters:

- tier min/max
- card value min/max
- live/non-live mode
- allowed/excluded card types
- card year min/max

Key functions:

- `filter_eligible_hitters(df, ruleset)`
- `filter_eligible_pitchers(df, ruleset)`
- `filter_eligible_players(df, ruleset)`

### `ootp_opt.optimization.candidate_matrices`

Builds sparse, solver-ready relations from the eligible `CandidatePool`.

Responsibilities:

- map each hitter to every defensive position where the configured starter
  threshold is met
- map qualified hitters to split-specific lineup assignments and scores
- retain split pinch-hitting and pinch-running values as secondary utilities
- map pitchers to configurable role groups using current role scores
- validate identities, required score columns, duplicate edges, and empty roles
- intentionally omit bench assignments; bench status is derived by the solver

Key class:

- `CandidateMatrices`

Key function:

- `build_candidate_matrices(...)`

### `ootp_opt.optimization.solver_input`

Builds solver-neutral constraint vectors from a `CandidatePool`, its matrices,
and the resolved ruleset.

Responsibilities:

- unify hitter and pitcher exports into one selectable-card universe
- expose person membership for duplicate-player constraints
- expose card value, variant, tier, and hitter/pitcher capability vectors
- define split lineup, pitcher-group, and lineup-coverage requirements
- translate tier slots into cumulative perfect-through-bronze limits
- retain lineup split weights for the future objective
- validate active constraint metadata and coarse roster feasibility

Key classes:

- `SolverInput`
- `SolverLimits`

Key function:

- `build_solver_input(...)`

### `ootp_opt.roster.builder`

Deterministic roster construction.

Responsibilities:

- select starters by position scores
- optimize starter assignments among chosen hitters
- select bench players by configured bench role requirements
- select rotation, middle relief, lefty specialist, and long relief
- prevent duplicate people through canonical person keys
- continue using legacy bench roles until optimizer selection derives the bench

Key functions:

- `build_hitter_roster(df, ruleset)`
- `build_pitcher_roster(df, ruleset)`
- `validate_no_duplicate_players(hitter_roster, pitcher_roster)`

### `ootp_opt.roster.lineup`

Lineup, depth chart, pinch hitter, and pinch runner helpers.

Key functions:

- `build_lineup_order(...)`
- `build_lineup_depth_rows(...)`
- `assign_position_backups(...)`
- `build_pinch_hitters(...)`
- `build_pinch_runners(...)`

### `ootp_opt.roster.cap_report`

Point-cap reporting helpers.

Key functions:

- `iter_roster_rows(...)`
- `build_cap_summary(...)`
- `build_cap_table(...)`
- `print_cap_report(...)`

### `ootp_opt.roster.cap_repair`

Greedy point-cap repair.

Responsibilities:

- find lower card-value slot-for-slot replacements
- preserve duplicate-player prevention
- preserve bench role requirements
- respect variant limit while repairing cap

Key function:

- `repair_roster_to_cap(...)`

### `ootp_opt.roster.variant_report`

Variant count reporting.

Key functions:

- `is_variant_card(row)`
- `build_variant_summary(...)`
- `build_variant_table(...)`
- `print_variant_report(...)`

### `ootp_opt.roster.variant_repair`

Greedy variant-limit repair.

Key function:

- `repair_roster_to_variant_limit(...)`

### `ootp_opt.roster.tier_slot_report`

Rollover tier slot reporting.

Tier slot legality is cumulative:

- Perfect <= P
- Perfect + Diamond <= P + D
- Perfect + Diamond + Gold <= P + D + G

Key functions:

- `build_tier_slot_rows(...)`
- `tier_slots_satisfied(...)`
- `highest_violated_tier(...)`
- `print_tier_slot_report(...)`

### `ootp_opt.roster.tier_slot_repair`

Greedy tier slot repair.

Responsibilities:

- identify the highest cumulative tier violation
- replace selected cards from that tier-or-better group with lower-tier legal candidates
- preserve duplicate-player prevention
- preserve bench role requirements
- respect variant limit

Key functions:

- `repair_roster_to_tier_slots(...)`
- `find_tier_slot_repair_options(...)`
- `print_tier_slot_repair_result(...)`

### `ootp_opt.roster.html_export`

Writes roster HTML reports.

Includes:

- build summary
- tier slot summary
- tier slot repair swap diagnostics
- roster checklist
- rotation and bullpen
- lineups and depth charts
- pinch hitter and pinch runner panels

Key function:

- `export_roster_html(...)`

### `ootp_opt.roster.roster_snapshot`

Roster comparison persistence. Bench, middle relief, lefty specialist, and long
relief are compared by pool membership, while starting positions and rotation
order remain assignment-sensitive. Old `RP1` snapshot keys remain compatible.

Key functions:

- `build_roster_snapshot(...)`
- `compare_snapshots(...)`
- `snapshot_path_for_html(...)`
- `load_snapshot(...)`
- `write_snapshot(...)`

### `ootp_opt.roster.upgrade_finder`

Finds potential store upgrades against current roster slots.

Key functions:

- `find_hitter_upgrades(...)`
- `find_pitcher_upgrades(...)`

### `ootp_opt.roster.upgrade_html_export`

Writes store upgrade analysis HTML.

Key function:

- `export_upgrade_html(...)`

## Package: `ootp_opt.export`

### `ootp_opt.export.csv_export`

CSV writer helper.

Key function:

- `write_csv(df, path)`

## Tests and Harnesses

The repo currently has focused tests plus ad hoc scripts.

Focused tests:

- `test_card_type_filter.py`
- `test_store_card_type_mapping.py`
- `test_tier_slot_report.py`
- `test_tier_slot_repair.py`
- `test_simulation_context.py`

Ad hoc/manual scripts:

- `test_rules.py`
- `test_eligibility.py`
- `test_hitter_starters.py`
- `test_pitcher_builder.py`
- `test_tournament_presets.py`
- `test_store_ingest.py`
- `test_store_scoring.py`
- `test_upgrade_finder.py`

## Important Current Rule

Do not duplicate scoring logic downstream.

Roster building, repair, upgrade analysis, and future UI should reuse:

- normalized ingest
- domain scoring
- ruleset parsing
- roster models and shared report helpers
