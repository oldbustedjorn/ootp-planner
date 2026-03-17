# OOTP Planner — Project Context

## Purpose
OOTP Planner is a modular Python tool for OOTP Perfect Team and, later, regular game modes.

The current focus is:
- ingesting OOTP CSV exports
- normalizing ratings and metadata
- scoring hitters and pitchers
- generating shortlist-style outputs to help with lineup/staff decisions

Future goals include:
- lineup / bench / staff optimization
- store upgrade analysis
- tournament and perfect draft support
- a GUI or better front-end presentation layer

---

## Current Status
The project is working well enough to:
- load hitter and pitcher exports
- score players
- generate ratings outputs
- generate hitter shortlists
- support both OOTP 26 and OOTP 27 export differences

Recent milestone:
- Successfully used the scripts to help build a first lineup in the launched game.

---

## High-Level Architecture
The intended structure is:

UI → Services → Domain → Adapters

### UI
- CLI now
- GUI later

### Services
- orchestrate loading, scoring, and exporting
- should stay thin

### Domain
- scoring formulas
- role scores
- later roster evaluation and optimization logic

### Adapters
- ingest OOTP CSV exports
- export CSV outputs
- later store/tournament data adapters

---

## Current Major Modules

### `ootp_opt/cli.py`
Main command-line entrypoint.

Responsibilities:
- load config
- run hitters / pitchers / both
- trigger outputs

### `ootp_opt/config.py`
Loads `config.toml`.

Responsibilities:
- provide config dictionary
- centralize path and weight configuration

### `ootp_opt/ingest/pt_hitters.py`
Loads Perfect Team hitter exports.

Responsibilities:
- support OOTP 26 and 27 header differences
- normalize hitter columns
- map duplicate / renamed position fields into stable names

### `ootp_opt/ingest/pt_pitchers.py`
Loads Perfect Team pitcher exports.

Responsibilities:
- support OOTP 26 and 27 header differences
- normalize pitcher columns
- map HRR/HRA and P/P_1 style changes

### `ootp_opt/domain/rating.py`
Core scoring formulas.

Responsibilities:
- hitter batting scores
- hitter positional scores
- pinch run score
- pitcher starter/reliever role scores
- config-driven weighting

### `ootp_opt/services/rating_service.py`
Main orchestration layer for scoring.

Responsibilities:
- build weight objects from config
- call ingest + domain logic
- write shortlist output for hitters
- return scored DataFrames

### `ootp_opt/services/shortlist_service.py`
Creates hitter shortlist output.

Responsibilities:
- top N by position
- top bats vs LHP / RHP
- position summaries for manual lineup building

### `ootp_opt/export/csv_export.py`
CSV writer helper.

### `compare_headers.py`
Utility script for comparing OOTP export headers between versions.

---

## Current Outputs

### Hitters output
Main ratings file includes:
- batting scores
- position scores
- pinch run score
- fielding / eligibility info
- PT metadata

Important hitter-style columns:
- `batting_score_vs_lhp`
- `batting_score_vs_rhp`
- `batting_score_overall`
- `score_C_overall`, `score_SS_overall`, etc.
- `pinch_run_score`

### Pitchers output
Main ratings file includes:
- starter and reliever scores
- split role scores
- pitch-count helper columns
- PT metadata

Important pitcher-style columns:
- `starter_score_vs_lhb`
- `starter_score_vs_rhb`
- `starter_score_overall`
- `reliever_score_vs_lhb`
- `reliever_score_vs_rhb`
- `reliever_score_overall`
- `starter_pitch_count_good`

### Hitter shortlist output
Includes:
- top players per position
- top bats vs LHP
- top bats vs RHP
- playable positions with ratings
- best positions by score

---

## Current Modeling Direction

### Hitters
Current focus:
- pure batting score
- positional score built from offense + defense
- pinch run role score

Important current beliefs:
- pure batting splits are useful
- platoon logic should wait until a real optimizer exists
- defense / offense balance still needs tuning
- Contact may be redundant in modern PT when BABIP + Avoid K are already present

### Pitchers
Current focus:
- starter vs reliever role scoring
- starter gating by stamina and pitch depth
- separate starter and reliever weighting

Important current beliefs:
- PBABIP is likely the most important SP trait
- HRA next
- Stuff next
- Control after that
- movement/contact-style hybrid ratings may need to be de-emphasized or zeroed when decomposed ratings are available

---

## Config Strategy
The project uses `config.toml` for:
- file paths
- output defaults
- hitter weights
- pitcher weights
- position blends
- starter gating thresholds

The goal is to keep tuning out of the code as much as possible.

---

## Recent Version-Compatibility Work
The ingest layer was patched to handle OOTP 26 → 27 export changes.

### Hitters
Supported changes include:
- duplicate position columns becoming explicit `_1` columns

### Pitchers
Supported changes include:
- `HRR` becoming `HRA`
- duplicate `P` fielding columns becoming `P_1`

---

## Current Pain Points
1. Ratings/weights still need significant tuning.
2. It is still a lot of work to manually build a full lineup and bench.
3. A full optimizer is desired, but should not be rushed blindly.
4. Store output / cheap-upgrade analysis has not been built yet.
5. Tournament / draft support will eventually be important.

---

## Current Strategic Decision
Do **not** jump straight into a full optimizer yet.

Instead, next discussion should focus on:
- understanding the future `roster/` architecture
- separating scoring from roster decision logic
- deciding whether the next code step should be:
  - more ratings tuning, or
  - a roster evaluator / greedy builder

---

## Likely Next Architecture Area
A future `roster/` package is expected, likely containing:

- models
- eligibility helpers
- evaluator logic
- greedy roster-building heuristics

This will be the bridge between:
- current scores
- future optimizer
- store-upgrade analysis
- tournament helpers

---

## Current Known Good Workflow
1. Update config paths if needed.
2. Run:
   `python -m ootp_opt.cli`
3. Review:
   - `ratings_hitters.csv`
   - `ratings_pitchers.csv`
   - `shortlists_hitters.csv`

---

## Notes for New Chats
When resuming in a new chat:
- paste this file
- optionally paste `CODE_MAP.md`
- then explain the immediate next decision or question

The next discussion should assume:
- scoring works
- OOTP 26 and 27 ingest works
- the major question is what to build next and how to structure it cleanly