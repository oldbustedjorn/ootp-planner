# OOTP Planner Project Context

## Purpose

OOTP Planner is a Python tool for OOTP Perfect Team roster planning.

It ingests local OOTP exports, normalizes card metadata and ratings, scores hitters and pitchers, builds roster candidates from configurable rules, repairs common tournament constraints, and writes human-readable reports.

The project is intentionally still heuristic. It is not a full optimizer yet.

## Current Status

Current working capabilities:

- load owned-card hitter and pitcher CSV exports
- load store card-list CSV exports
- normalize OOTP 26/27 export differences
- normalize variant status from `VAR` into boolean `is_variant`
- normalize owned-card `CType` into `pt_type`
- normalize store `Card Type` numeric codes into the same `pt_type` codes
- score hitters and pitchers from config-driven weights
- adjust scoring for simulation year and ballpark context
- generate ratings and shortlist CSV outputs
- build deterministic rosters from base profiles and tournament presets
- run roster builds through a reusable service layer
- prevent duplicate-player selections by normalized player name
- produce lineup, depth chart, pinch hitter, pinch runner, rotation, bullpen, specialist, and long-man outputs
- export roster HTML reports
- write roster snapshots and mark changed/new roster slots in later HTML reports
- analyze store upgrades
- find store upgrades using roster filters and simulation context
- launch a first-pass local web UI for standard PT and PT tournament builds
- browse configured tournament presets in the local UI
- rebuild preset rosters and run preset store-upgrade reports from the UI
- label presets with GUI-only display titles and notes while keeping stable preset IDs

Recent milestone:

- tournament preset support now covers card type filtering, variant limits, point caps, and rollover tier slot rules
- greedy repair exists for variant limits, tier slots, and point caps
- tier slot repair and swap diagnostics appear in HTML output
- simulation year and ballpark context can now affect scoring
- roster building has a service layer used by both CLI and GUI entry points
- store upgrade analysis has a service layer used by both CLI and GUI entry points

## Current Workflow

Use the project venv:

```powershell
.\.venv\Scripts\python.exe ...
```

Run ratings/shortlists:

```powershell
.\.venv\Scripts\python.exe -m ootp_opt.cli
```

Run a roster build:

```powershell
.\.venv\Scripts\python.exe build_roster.py --preset my_slot_test --html-output outputs\my_slot_test.html
```

`build_roster.py` is intentionally a thin wrapper. Application code and the
future local UI should call `ootp_opt.services.roster_build_service.build_roster`
with a `RosterBuildRequest`.

Launch the local GUI:

```powershell
.\.venv\Scripts\python.exe launch_gui.py
```

Then open `http://127.0.0.1:8765`.

Run a simulation-context build:

```powershell
.\.venv\Scripts\python.exe build_roster.py --base-profile playoff_pt --simulation-year 1919 --ballpark "Dodger Stadium" --ballpark-year 1962 --html-output outputs\sim_test.html
```

Run store upgrade search:

```powershell
.\.venv\Scripts\python.exe find_store_upgrades.py --base-profile playoff_pt --tier-max gold --min-gain 5 --html-output outputs\store_upgrades_gold.html
```

Run focused validation:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider test_card_type_filter.py test_store_card_type_mapping.py test_tier_slot_report.py test_tier_slot_repair.py
.\.venv\Scripts\python.exe -m ruff check --no-cache .
```

## Architecture

The intended dependency direction is:

UI / scripts -> services -> domain -> ingest/export adapters

Important rule:

- downstream tools should reuse normalized ingest and domain scoring
- do not duplicate scoring logic inside roster repair, upgrade search, or future UI layers
- future UI code should call service functions instead of shelling out to scripts
- preset and build-history persistence belongs in `ootp_opt.services.preset_service`,
  not in an HTTP or desktop-client adapter

## Important Data Columns

Card identity and metadata:

- `name`
- `player_id`
- `pt_tier`
- `card_value`
- `pt_year`
- `pt_type`
- `pt_subtype`
- `is_variant`

`pt_type` comes from owned-card `CType`.

Known `pt_type` values:

- `2026Live`
- `AS`
- `FL`
- `HaH`
- `Leg`
- `NeL`
- `RS`
- `Snap`
- `UnH`
- `VET`

`pt_subtype` is separate from variant status. Subtypes include values such as `BBR`, `HOF`, `ME`, `UTIL`, `VB`, and `WBC`.

Variant status uses normalized boolean `is_variant` from OOTP `VAR`. `pt_subtype` is not variant status.

## Scoring Outputs

Hitter score columns:

- `batting_score_overall`
- `batting_score_vs_lhp`
- `batting_score_vs_rhp`
- `score_C_overall`, `score_SS_overall`, `score_CF_overall`, etc.
- `pinch_run_score`

Pitcher score columns:

- `starter_score_overall`
- `starter_score_vs_lhb`
- `starter_score_vs_rhb`
- `reliever_score_overall`
- `reliever_score_vs_lhb`
- `reliever_score_vs_rhb`

These naming conventions should be preserved.

## Roster Rules

Base profiles define roster shape:

- `standard_pt`: 13 hitters, 13 pitchers
- `playoff_pt`: 14 hitters, 12 pitchers, 4-man rotation, extra bench slot

Tournament presets are named build recipes, not tournament names. They wrap a base profile and add filters/constraints.

Supported preset fields include:

- `base_profile`
- `dh_enabled`
- `platoons_allowed`
- `tier_min`
- `tier_max`
- `card_value_min`
- `card_value_max`
- `live_mode`
- `allowed_card_types`
- `excluded_card_types`
- `card_year_min`
- `card_year_max`
- `simulation_year`
- `ballpark`
- `ballpark_year`
- `custom_park_factors`
- `point_cap_total`
- `variant_limit`
- `tier_slots`

Tier slot rules use cumulative rollover logic. For `P = 2`, `D = 1`, `G = 1`:

- Perfect cards <= 2
- Perfect + Diamond cards <= 3
- Perfect + Diamond + Gold cards <= 4

Unused higher-tier slots can be used by lower-tier cards.

## Simulation Context

Simulation year and ballpark year are separate.

Example: a tournament can use `simulation_year = 1919` while playing at an `1886` park. Named park lookup uses `ootp_opt/data/park_factors.csv`. If a tournament park is not in the CSV, use direct custom park factors from tournament text.

Supported custom park factor keys include:

- `ba_lh`, `ba_rh`
- `hr_lh`, `hr_rh`
- `doubles_overall`
- `triples_overall`

The first-pass implementation applies conservative multipliers to scoring weights. It does not mutate raw ratings.

## Repair Behavior

Repairs are greedy heuristics, not optimization.

Current repair order in `build_roster.py`:

1. Build initial hitter and pitcher rosters.
2. Validate no duplicate players.
3. Report variant count.
4. If `variant_limit` is set, greedily repair variants.
5. If `tier_slots` are set, greedily repair tier slot violations.
6. Report cap usage.
7. If `point_cap_total` is set, greedily repair cap overage.
8. Write HTML and snapshot.

Important limitation:

- cap repair happens after tier slot repair and may change the tier mix
- current code reports tier slots again after cap repair when slots exist
- deeper interaction among cap, tier slots, and score quality eventually belongs in an optimizer

## Current Modeling Decisions

Defensive scoring:

- uses `fld_POS` as the primary position defensive input
- avoids recomposing defense from component ratings to prevent double counting
- component ratings may still be useful later as small adjustments

Platoon handling:

- current build uses overall position scores for roster construction
- lineup output includes batting splits vs RHP/LHP
- true platoon-aware roster construction is deferred

Cap repair:

- greedy slot-for-slot replacement
- chooses lower card-value replacements by score-loss efficiency

Variant repair:

- greedy replacement of selected variants with non-variants
- uses normalized `is_variant`

Tier slot repair:

- greedy demotion from the highest violated cumulative tier
- chooses lower-tier replacements by protected role priority and score loss
- preserves duplicate-player prevention and bench role requirements

Simulation context:

- era and park factors adjust scoring weights before roster construction
- raw player ratings are unchanged
- early-era factors are clamped into modest multipliers to avoid huge table values dominating immediately

Store upgrades:

- `find_store_upgrades.py` mirrors the useful roster-build filters and simulation context
- store candidates are filtered by tier/card value/year/live/card type
- cap and tier-slot replacement legality is intentionally not modeled yet

## Current Pain Points

1. Simulation context multipliers need validation and tuning.
2. Scoring weights need a deeper review.
3. Greedy roster construction can spend scarce resources in the wrong roles.
4. Tier slot repair works, but a full optimizer would make better global tradeoffs.
5. Cap, tier slot, and variant constraints can interact in ways greedy repair cannot fully optimize.
6. HTML diagnostics are useful but still utilitarian.
7. Command-line roster building is too slow to operate manually for frequent tournament entry.

## Next Priority

The local UI supports standard Perfect Team, playoff-style Perfect Team, and
Perfect Team tournament roster builds, including build history, saved presets,
preset rebuilds, store upgrades, display notes, and stable OOTP roster identity.
Preset and history persistence is now reusable outside the web server through
`ootp_opt.services.preset_service`, which prepares the project for a stronger web
UI or a local desktop client.

The next major architecture work is to separate candidate scoring from roster
selection and define a structured optimizer input before implementing a full
optimizer.

Good starting questions:

- Are hitter batting weights valuing modern PT traits correctly?
- Should Contact remain zero when BABIP and Avoid K are available?
- Are defense thresholds and position blends producing believable starters and bench coverage?
- Are pitcher starter/reliever weights aligned with observed game performance?
- Are stamina and pitch-depth gates too harsh or too lenient?
- Are era and park multipliers changing rosters in believable ways?

Do not jump to a full optimizer until scoring feels more trustworthy.

## Notes for Future Chats

When resuming in a new Codex or ChatGPT session:

- use this file as current context
- optionally include `CODE_MAP.md`
- mention the immediate next task
- assume roster building, card type filters, cap repair, variant repair, tier slot repair, simulation context scoring, HTML output, snapshots, and store ingest all exist
