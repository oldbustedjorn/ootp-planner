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
Preset and build-history persistence is provided separately by
`ootp_opt.services.preset_service` so another web or desktop UI can reuse it.

## Local GUI

Launch the local web UI:

```powershell
.\.venv\Scripts\python.exe launch_gui.py
```

Then open:

```text
http://127.0.0.1:8765
```

The first GUI pass supports standard Perfect Team, playoff-style Perfect Team,
and Perfect Team tournament roster builds. It writes generated reports to
`outputs/` and tracks GUI-launched builds in `outputs/roster_build_registry.json`.
Leave the OOTP roster name blank to generate a deterministic name capped at the
game's 30-character roster-name limit. Generated names include a three-digit
planner reference, such as `T-042-Gmax-v84-NL`, so the full build details can be
looked up in the GUI history.

The Presets panel lists configured tournament presets from `config.toml`. Selecting
a preset shows the saved requirements and can:

- rebuild the roster to a stable preset report path
- run store upgrade analysis for that preset
- reopen the latest preset roster and upgrade reports
- save a display title and note, such as the in-game tournament name, without
  changing the stable preset ID used by commands and report paths

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

Simulation context works the same way:

```powershell
.\.venv\Scripts\python.exe find_store_upgrades.py --base-profile playoff_pt --tier-max gold --simulation-year 1919 --ballpark "Swampoodle Grounds" --ballpark-year 1886 --park-ba-lh 0.975 --park-ba-rh 0.975 --park-hr-lh 0.975 --park-hr-rh 0.975 --park-2b 1.000 --park-3b 1.000
```

Upgrade legality currently focuses on base eligibility filters such as tier, card value, card year, live mode, and card type. It does not enforce changing cap or tier-slot constraints for each candidate replacement.

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

## Repair Behavior

Roster construction is still heuristic, not a full optimizer.

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

The current milestone is a usable roster builder with tournament-style filters,
repairs, simulation-context scoring, a local UI, preset management, build
history, and store-upgrade actions. The next architecture milestone is separating
candidate scoring from roster selection and defining the input contract for a
full optimizer.
