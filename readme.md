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

The current milestone is a usable roster builder with tournament-style filters, repairs, and first-pass simulation context scoring. The next high-priority area is validating and tuning the environment multipliers against observed results.
