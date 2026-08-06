# OOTP Planner

A Python tool for building and inspecting OOTP Perfect Team rosters from local OOTP exports.

The project currently focuses on:

- ingesting owned-card hitter and pitcher exports
- ingesting store card-list exports for upgrade analysis
- scoring hitters and pitchers from configurable weights
- adjusting scoring for simulation year and ballpark context
- building deterministic rosters from base profiles and tournament presets
- repairing rosters for caps, variant limits, and tier slot rules
- exporting roster HTML reports and snapshots

## Setup

From the repo root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the project venv when running validation:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider test_card_type_filter.py test_store_card_type_mapping.py test_tier_slot_report.py test_tier_slot_repair.py
.\.venv\Scripts\python.exe -m ruff check --no-cache .
```

## Data Paths

OOTP export paths live in `config.toml` under `[paths]`:

- `hitters_csv`
- `pitchers_csv`
- `store_csv`
- `output_dir`

These point at local OOTP files and may need to be changed per machine.

Local application state will use SQLite at the configured `[storage]` path:

```toml
[storage]
database_path = "state/ootp_planner.sqlite3"
```

The database file is local and ignored by Git. It is the authoritative store for
GUI presets and build history. `config.toml` remains authoritative for static
settings such as paths, scoring, base profiles, and storage location. When the
database exists, roster builds and store-upgrade analysis resolve named presets
from SQLite; the legacy TOML preset blocks are ignored.

Preview the current presets and GUI build history before any future import:

```powershell
.\.venv\Scripts\python.exe preview_storage_import.py
```

Add `--details` to list every candidate preset and build. The preview validates
records, reports legacy duplicate IDs and deleted-preset references, checks roster
report/snapshot availability, and generates deterministic future database IDs.
It never initializes or writes the configured SQLite database.

Preview cleanup of legacy history and artifacts:

```powershell
.\.venv\Scripts\python.exe cleanup_legacy_history.py
```

The cleanup retains the newest successful build for every active preset and only
targets artifacts referenced exclusively by removed history records. Use
`--details` to list every proposed deletion. Nothing changes without `--apply`.

```powershell
.\.venv\Scripts\python.exe cleanup_legacy_history.py --apply
```

Apply mode verifies that the previewed sources have not changed, creates and
validates a timestamped ZIP under `state/backups/`, atomically rewrites the JSON
registry, and then removes approved orphan files. The backup contains the full
original config, history registry, affected artifacts, and a cleanup manifest.
The local backup directory is ignored by Git.

Import the previewed presets and retained build history into SQLite:

```powershell
.\.venv\Scripts\python.exe import_storage.py --apply
```

The importer creates and verifies a pre-import backup first, initializes schema
migrations, inserts all application rows in one transaction, verifies counts,
identities, foreign keys, and database integrity, and rolls back application rows
if verification fails. It rejects a nonempty target rather than merging silently.
`config.toml` and the JSON registry remain unchanged as migration sources. After
import, SQLite becomes authoritative for presets and build history.

Verify the committed import independently:

```powershell
.\.venv\Scripts\python.exe import_storage.py --verify
```

Create and verify general storage backups:

```powershell
.\.venv\Scripts\python.exe manage_storage_backup.py backup
.\.venv\Scripts\python.exe manage_storage_backup.py verify state\backups\BACKUP.zip
```

Restore preview is non-writing. Add `--apply` to restore the archived database;
add `--include-sources` only when the archived config and JSON history should also
replace current files. Every applied restore first creates another safety backup.

```powershell
.\.venv\Scripts\python.exe manage_storage_backup.py restore state\backups\BACKUP.zip
.\.venv\Scripts\python.exe manage_storage_backup.py restore state\backups\BACKUP.zip --apply
```

Database capture and restore use SQLite's online backup API and run integrity
checks instead of copying a potentially active database file directly.

Simulation data lives in package data files:

- `ootp_opt/data/year_era_factors.csv`
- `ootp_opt/data/park_factors.csv`

## Rating Exports

To run the original ratings/shortlist flow:

```powershell
.\.venv\Scripts\python.exe -m ootp_opt.cli
```

Typical outputs:

- `outputs/ratings_hitters.csv`
- `outputs/ratings_pitchers.csv`
- `outputs/shortlists_hitters.csv`

## Roster Builds

Roster builds are implemented through `ootp_opt.services.roster_build_service`.
The `build_roster.py` script is a thin command-line wrapper around that service.
The GUI calls the service directly rather than shelling out to the script.
SQLite preset and build-history persistence is provided by
`ootp_opt.services.application_state_service` so another web or desktop UI can
reuse it. Legacy naming, report-path, and migration helpers remain in
`ootp_opt.services.preset_service`.
Roster builds and store analysis resolve environment settings into one
`BuildContext`, then expose scored and ruleset-eligible cards through reusable
`CandidatePool` objects. Candidate pools attach two identities before filtering:
`candidate_id` identifies the selectable card or player record, while
`person_key` prevents selecting multiple cards representing the same player.
The same PT card receives the same candidate identity in owned and store data.
Configured rulesets also expose a `RosterSlotPlan`. Each field position has a
separate assignment for the vs-RHP and vs-LHP lineups, using its split position
score; DH uses split batting score. Bench status is derived independently for
each lineup from selected hitters who are not starting. Split-specific coverage
constraints require qualified bench options while allowing one versatile player
to cover multiple positions. Pitcher jobs remain configurable role groups.
`CandidateMatrices` converts each eligible pool into sparse position-capability,
lineup-assignment, hitter-utility, and pitcher-role edges. These are reported by
roster builds but do not yet change the greedy selection algorithm.
`SolverInput` then unifies each card's hitter and pitcher records and exposes
solver-neutral person, cap, variant, cumulative tier-slot, lineup, coverage,
pitcher-group, and split-weight constraint data.

## Local GUI

Launch the local web UI:

```powershell
.\.venv\Scripts\python.exe launch_gui.py
```

Then open:

```text
http://127.0.0.1:8765
```

The GUI supports standard Perfect Team, playoff-style Perfect Team, and Perfect
Team tournament roster builds. It writes generated reports to `outputs/` and
tracks GUI-launched builds in the configured SQLite database. The GUI requires
an imported database and reports the restore/import command at startup if it is
missing.
Leave the OOTP roster name blank to generate a deterministic name capped at the
game's 30-character roster-name limit. Generated names include a three-digit
planner reference, such as `T-042-Gmax-v84-NL`, so the full build details can be
looked up in the GUI history.

The Presets panel lists tournament presets from SQLite. Selecting a preset shows
the saved requirements and can:

- rebuild the roster to a stable preset report path
- run store upgrade analysis for that preset
- reopen the latest preset roster and upgrade reports
- save a display title and note, such as the in-game tournament name, without
  changing the stable preset ID used by commands and report paths

Completed GUI builds show their total elapsed time. Generated roster HTML also
includes a Build Timings section covering ingest and scoring, eligibility,
initial roster selection, constraint diagnostics and repairs, and output
preparation. CLI builds include the complete timing breakdown in their report.

Build from the default base profile:

```powershell
.\.venv\Scripts\python.exe build_roster.py
```

Build from a tournament preset:

```powershell
.\.venv\Scripts\python.exe build_roster.py --preset my_slot_test --html-output outputs\my_slot_test.html
```

Build with direct CLI filters instead of a preset:

```powershell
.\.venv\Scripts\python.exe build_roster.py --base-profile playoff_pt --card-types AS,FL,HaH,Leg,NeL,RS,Snap,UnH,VET --html-output outputs\card_type_test.html
```

Build with simulation context:

```powershell
.\.venv\Scripts\python.exe build_roster.py --base-profile playoff_pt --simulation-year 1919 --ballpark "Dodger Stadium" --ballpark-year 1962 --html-output outputs\sim_test.html
```

Use direct park factors when a tournament uses a park that is not in `park_factors.csv`:

```powershell
.\.venv\Scripts\python.exe build_roster.py --base-profile playoff_pt --simulation-year 1919 --ballpark "Swampoodle Grounds" --ballpark-year 1886 --park-ba-lh 0.975 --park-ba-rh 0.975 --park-hr-lh 0.975 --park-hr-rh 0.975 --park-2b 1.000 --park-3b 1.000
```

Roster build outputs include:

- HTML roster report
- snapshot JSON used to mark changed/new roster slots in later HTML reports

## Store Upgrades

Find store upgrades with the same filters and simulation context used by roster builds:

```powershell
.\.venv\Scripts\python.exe find_store_upgrades.py --base-profile playoff_pt --tier-max gold --min-gain 5 --html-output outputs\store_upgrades_gold.html
```

For presets saved with `build_method = "optimizer"`, the finder builds an owned-card
optimizer baseline and compares every available store card against its actual split
lineups and pitching groups. The broad report is sorted by current purchase price per
estimated objective gain. Active sell orders are required by default.

Use a price ceiling for practical shopping and optionally validate the first few
cost-efficient candidates with full roster re-solves:

```powershell
.\.venv\Scripts\python.exe find_store_upgrades.py --preset my_optimizer_preset --max-price 50000 --exact-results 2
```

Exact checks annotate the broad rows with whole-roster objective gain, cards removed
and added, acquired-card usage in both lineups, and assignment changes. Use
`--include-unlisted` to include cards without an active sell order.

Simulation context works the same way:

```powershell
.\.venv\Scripts\python.exe find_store_upgrades.py --base-profile playoff_pt --tier-max gold --simulation-year 1919 --ballpark "Swampoodle Grounds" --ballpark-year 1886 --park-ba-lh 0.975 --park-ba-rh 0.975 --park-hr-lh 0.975 --park-hr-rh 0.975 --park-2b 1.000 --park-3b 1.000
```

Exact optimizer checks enforce the preset's roster-wide cap, variant, and tier-slot
constraints. Broad comparisons are estimates against current assignments; greedy
presets retain the original isolated role comparison.

## Tournament Presets

Tournament presets are named build recipes in `config.toml`.

Example:

```toml
[tournament_presets.example]
base_profile = "playoff_pt"
tier_max = "gold"
live_mode = "non_live"
point_cap_total = 1580
variant_limit = 10
dh_enabled = true
simulation_year = 1919
ballpark = "Dodger Stadium"
ballpark_year = 1962

[tournament_presets.example.tier_slots]
P = 2
D = 1
G = 1
S = 12
B = 6
I = 5

[tournament_presets.example.custom_park_factors]
ba_lh = 0.975
ba_rh = 0.975
hr_lh = 0.975
hr_rh = 0.975
doubles_overall = 1.000
triples_overall = 1.000
```

Common preset fields:

- `base_profile`: `standard_pt` or `playoff_pt`
- `dh_enabled`: `true` or `false`
- `tier_min`, `tier_max`: `iron`, `bronze`, `silver`, `gold`, `diamond`, `perfect`
- `card_value_min`, `card_value_max`
- `live_mode`: `all`, `live`, `non_live`
- `allowed_card_types`, `excluded_card_types`
- `card_year_min`, `card_year_max`
- `simulation_year`
- `ballpark`
- `ballpark_year`
- `custom_park_factors`
- `point_cap_total`
- `variant_limit`
- `tier_slots`
- `build_method`: `greedy` or `optimizer`

Card type codes:

- `2026Live`: MLB 2026 Live
- `AS`: Historical All-Star
- `FL`: Future Legend
- `HaH`: Hardware Heroes
- `Leg`: All-Time Legend
- `NeL`: Negro League Star
- `RS`: Rookie Sensation
- `Snap`: Snapshot
- `UnH`: Unsung Heroes
- `VET`: Veteran Presence

## Build Behavior

`build_method = "optimizer"` selects the best combined split lineups, bench coverage,
pitcher groups, and legal roster under the configured constraints. The `greedy` method
remains available for quick builds and uses the repair passes below.

After the initial build, the script can repair:

- variant count, using normalized `is_variant` from the OOTP `VAR` column
- tier slot limits with rollover from unused high-tier slots to lower tiers
- point cap totals

Tier slot legality is cumulative. For example, `P = 2`, `D = 1`, `G = 1` means:

- Perfect cards <= 2
- Perfect + Diamond cards <= 3
- Perfect + Diamond + Gold cards <= 4

Unused high-tier slots can be spent on lower-tier cards.

## Simulation Context

`simulation_year` and `ballpark_year` are intentionally separate. A tournament can simulate games in one era while using park factors from a different historical park year.

The first-pass scoring adjustment is conservative. It changes scoring weights, not raw player ratings:

- era factors adjust hitter and pitcher trait weights
- park BA/2B/3B/HR factors adjust contact/BABIP/gap/power, defense pressure, pBABIP, and HRA prevention
- missing simulation context leaves scoring neutral
- unknown named parks fail unless direct `custom_park_factors` are supplied

## Git Sync

Check local state:

```powershell
git status
```

Update from GitHub:

```powershell
git pull --ff-only
```

Push local commits:

```powershell
git push
```

## Current Direction

The current milestone is a usable optimizer-backed roster builder with
tournament filters, simulation-context scoring, preset management, build
history, store-upgrade analysis, and a functional local web UI. SQLite storage
scaffolding is now available for the next architecture milestone: durable build
snapshots and feedback data followed by a more capable application interface.
