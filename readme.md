# OOTP Planner

A Python tool for building and inspecting OOTP Perfect Team rosters from local OOTP exports.

The project currently focuses on:

- ingesting owned-card hitter and pitcher exports
- ingesting store card-list exports for upgrade analysis
- scoring hitters and pitchers from configurable weights
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

[tournament_presets.example.tier_slots]
P = 2
D = 1
G = 1
S = 12
B = 6
I = 5
```

Common preset fields:

- `base_profile`: `standard_pt` or `playoff_pt`
- `dh_enabled`: `true` or `false`
- `tier_min`, `tier_max`: `iron`, `bronze`, `silver`, `gold`, `diamond`, `perfect`
- `card_value_min`, `card_value_max`
- `live_mode`: `all`, `live`, `non_live`
- `allowed_card_types`, `excluded_card_types`
- `card_year_min`, `card_year_max`
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

The current milestone is a usable roster builder with tournament-style filters and repairs. The next high-priority area is scoring review and tuning, especially whether the rating weights match observed OOTP Perfect Team usefulness.
