# OOTP Planner — Roster Builder Spec v1

## Purpose

Define a first-pass roster construction system that can:

- build a standard Perfect Team roster
- build tournament-legal rosters under configurable constraints
- reuse existing scoring outputs
- stay heuristic-first rather than optimization-first
- leave room for future platoon and optimizer support

This spec focuses on the model and interfaces, not implementation details.

---

## Core Design Principles

### 1. Keep scoring separate from roster logic
Scoring answers: how good is a player?

Roster logic answers:
- is this player eligible?
- where should this player be assigned?
- does this roster satisfy the rules?
- how strong is the finished roster?

Tournament rules must not change scoring formulas. They change eligibility and construction.

### 2. Build around a ruleset
A ruleset defines:
- which cards are eligible
- what roster shape is required
- what hard constraints apply
- what construction heuristics to use

### 3. Use deterministic heuristics first
Version 1 should build a usable roster automatically without full optimization.

### 4. Design for future GUI and CLI use
The same ruleset model should support:
- config-file-based builds
- CLI overrides
- future GUI form selection

---

## High-Level Pipeline

1. Load scored hitters and pitchers
2. Load roster build ruleset
3. Filter eligible cards
4. Build hitter roster heuristically
5. Build pitcher roster heuristically
6. Validate roster against hard constraints
7. Evaluate roster strength and diagnostics
8. Export results

---

## Main Concepts

## Ruleset

A ruleset is the central input for roster building.

It should support three categories:

### A. Eligibility constraints
Applied per card.

Examples:
- card tier allowed
- max tier allowed
- live only
- historical only
- overall range
- series whitelist or blacklist
- team / league / nation filters
- year range
- point value availability

### B. Aggregate roster constraints
Applied to the full roster.

Examples:
- total point cap <= 1400
- exactly 13 hitters
- exactly 13 pitchers
- at most 4 perfect cards
- at most 3 diamonds
- exactly N cards from each tier bucket
- DH enabled / disabled

### C. Construction policy
Not legal requirements, but builder behavior.

Examples:
- starter fill order
- minimum defensive thresholds by position
- required coverage count by position
- platoons allowed true/false
- handedness shares for evaluation
- bench template policy
- pitcher template policy

---

## Ruleset fields (conceptual)

### Identity
- `name`
- `description`
- `mode` = `standard_pt` or `tournament`

### Roster shape
- `hitter_count` (default 13)
- `pitcher_count` (default 13)
- `starter_positions` (default C, 1B, 2B, 3B, SS, LF, CF, RF, DH)
- `dh_enabled` (bool)

### Eligibility filters
- `allowed_tiers`
- `max_tier`
- `live_only`
- `historical_only`
- `min_overall`
- `max_overall`
- `allowed_card_types`
- `excluded_card_types`
- `team_filters`
- `league_filters`
- `nation_filters`
- `year_min`
- `year_max`

### Aggregate constraints
- `point_cap_total`
- `tier_slot_caps`
- `tier_slot_exact`
- `max_duplicate_cards`

### Construction policy
- `lineup_fill_order`
- `coverage_targets`
- `platoons_allowed`
- `bench_roles_enabled`
- `opponent_lhp_share`
- `opponent_rhp_share`

### Pitcher construction policy
- `rotation_size` (default 5)
- `primary_rp_count` (default 6)
- `specialist_lhp_count` (default 1)
- `long_man_count` (default 1)

---

## CoverageTarget

A coverage target defines what counts as acceptable backup coverage at a position.

Fields:
- `position`
- `min_defense_score`
- `required_count`

Example intent:
- C needs 2 playable options above threshold X
- SS needs 2 playable options above threshold Y
- CF needs 2 playable options above threshold Z

For version 1, a standard roster should generally target at least 2 playable options at every field position.

---

## Eligible player pool

After scoring, cards are filtered into an eligible pool.

The eligible pool should expose helper attributes used by the builder.

### Hitter helper attributes
- player/card id
- name
- card tier
- card value for cap systems
- live flag
- batting scores overall / vs LHP / vs RHP
- positional scores overall
- playable positions
- fielding-by-position values
- pinch run score

### Pitcher helper attributes
- player/card id
- name
- card tier
- card value for cap systems
- live flag
- starter scores overall / vs LHB / vs RHB
- reliever scores overall / vs LHB / vs RHB
- stamina / pitch depth helpers

---

## Candidate roster model

## HitterRoster

Represents final hitter assignments.

Fields:
- `starters_by_position`
- `bench_players`
- `coverage_map`
- `unused_eligible_hitters`

### starters_by_position
Maps each starting slot to one player.

Version 1:
- one player per position
- no platoons yet

Future:
- allow either single-player assignment or platoon assignment

### bench_players
List of assigned bench players with notes on likely role.

Likely roles in v1:
- backup catcher
- backup infielder
- backup outfielder
- utility / gap filler / best remaining bat

### coverage_map
For each position, track:
- how many rostered players can cover the position at or above threshold
- which players provide that coverage

---

## PitcherRoster

Represents final pitcher assignments.

Fields:
- `rotation`
- `bullpen`
- `lefty_specialists`
- `long_man`
- `unused_eligible_pitchers`

Version 1 should treat these mostly as labels assigned by heuristic, not deep role simulation.

---

## Roster

Top-level completed roster object.

Fields:
- `ruleset_name`
- `hitter_roster`
- `pitcher_roster`
- `validation_result`
- `evaluation_result`

---

## Builder behavior

## Hitter builder heuristic v1

### Stage 1: choose starters
Fill starting positions in this order by best available overall positional score:

1. C
2. SS
3. CF
4. 2B
5. 3B
6. LF
7. RF
8. 1B
9. DH

Selection rule:
- consider only eligible unassigned hitters
- choose the best candidate for the current slot
- use current positional score for that slot
- for DH, use offense-only logic or best designated DH logic if available

Rationale:
- secure scarce and defense-sensitive positions first

### Stage 2: choose bench
Fill remaining hitter slots using coverage-aware offense.

Bench selection goal:
- maximize remaining offensive value
- while meeting coverage targets across all field positions

Bench selection pattern for v1:
1. choose best remaining catcher who improves C coverage
2. choose best remaining infielder who improves weakest infield coverage
3. choose best remaining outfielder who improves weakest outfield coverage
4. choose best remaining hitter who fills remaining coverage gaps or provides best utility value

This is heuristic, not globally optimal.

### Stage 3: coverage pass
After bench is filled, compute whether every position meets its coverage target.

If not, the builder may either:
- mark roster as coverage-deficient
- or run a simple repair pass later

Version 1 can stop at diagnostics if repair logic is not yet implemented.

---

## Pitcher builder heuristic v1

Build pitchers using this manual-style order:

1. pick the 5 best SPs using starter overall score
2. pick the 6 best RPs using reliever overall score
3. pick the best remaining RP vs LHB as the lefty specialist
4. pick the best remaining SP as the long man

Assumptions:
- overall SP score already reflects combined split value
- overall RP score already reflects combined split value
- lefty specialist uses reliever vs LHB score
- long man uses next-best starter-style candidate

This is intentionally simple and mirrors current manual workflow.

---

## Validator behavior

The validator checks whether a finished roster obeys the ruleset.

## Hard validation checks

### Count checks
- hitter count matches ruleset
- pitcher count matches ruleset
- starters fully assigned

### Eligibility checks
- all cards satisfy per-card rules

### Aggregate constraint checks
- total cap value within limit
- tier slot rules satisfied
- duplicate rules satisfied

### Coverage checks
- each field position meets required backup count threshold

Version 1 decision:
- hard legal violations should invalidate the roster
- coverage failures may either invalidate or produce warnings depending on settings

---

## Evaluation behavior

The evaluator scores the finished roster and explains why it scored that way.

## Hitter evaluation components
- starter lineup total
- bench offensive total
- coverage completeness diagnostics
- optional pinch run / utility notes later

## Pitcher evaluation components
- rotation total
- bullpen total
- specialist / long-man notes

## Validation summary
- cap used
- tier slots used
- failed constraints
- weak coverage positions

The evaluator should return both:
- numeric totals
- readable diagnostics

---

## Tournament profile configuration

Version 1 should support defining named roster-build profiles outside code.

Possible approach:
- a separate config file for build profiles
- or a new section in existing config

Recommended concept:

```toml
[roster_profiles.standard_pt]
mode = "standard_pt"
hitter_count = 13
pitcher_count = 13
dh_enabled = true
platoons_allowed = false

[roster_profiles.gold_cap_live_1400]
mode = "tournament"
max_tier = "gold"
live_only = true
point_cap_total = 1400
hitter_count = 13
pitcher_count = 13
platoons_allowed = false

[roster_profiles.diamond_and_lower]
mode = "tournament"
allowed_tiers = ["diamond", "gold", "silver", "bronze", "iron"]
hitter_count = 13
pitcher_count = 13
```

This lets the user maintain a small set of focused target builds.

---

## CLI concept

The builder should support either:
- profile-first usage
- or profile plus a few simple overrides

### Preferred usage

```bash
python -m ootp_opt.cli --build-roster --profile gold_cap_live_1400
```

### Optional override style

```bash
python -m ootp_opt.cli --build-roster --profile tournament_base --max-tier gold --point-cap 1400 --live-only
```

Recommendation:
- prefer named profiles for repeatable builds
- use CLI overrides only for small adjustments

This keeps the command line manageable and prepares naturally for a future GUI where the same underlying fields are selected from form controls.

---

## Future extensions

Not in v1, but the model should support them later.

### Platoons
Allow a starting slot to be filled by:
- one player
- or a two-player platoon assignment

This must consume roster space and interact with coverage constraints.

### Ballpark / era environments
Allow build profiles to specify environment assumptions used in evaluation.

### Repair pass / local search
After heuristic construction, attempt simple swaps to improve cap fit or coverage.

### Full optimizer
Later, use the same ruleset, models, validator, and evaluator under a more advanced search method.

---

## Recommended v1 implementation order

1. ruleset model
2. eligibility filtering
3. hitter builder
4. pitcher builder
5. validator
6. evaluator
7. profile-based CLI integration

---

## Summary

Version 1 should be a ruleset-driven, heuristic roster builder.

It should:
- support both standard and tournament builds
- build full 13/13 rosters
- use deterministic starter and bench heuristics
- use deterministic pitcher heuristics
- validate caps / tier rules / eligibility
- report coverage and roster quality

It should not yet:
- optimize globally
- search all combinations
- support full platoon assignment

But it should be designed so those features can be added later without changing the core model.

---

## Implementation checklist v1

This section converts the spec into an initial coding plan.

### Milestone 1
Goal:
- given a named roster profile
- load scored hitters and pitchers
- filter to legal cards
- build one full hitter roster and one full pitcher roster
- validate basic legality
- export readable output

Target CLI shape:

```bash
python -m ootp_opt.cli --build-roster --profile gold_cap_live_1400
```

---

## Module-by-module plan

## `ootp_opt/roster/rules.py`

Purpose:
- load and normalize roster build profiles
- convert raw config into a ruleset object the rest of the system can consume

Primary responsibilities:
- parse roster profile config
- apply defaults
- normalize simple user-friendly config into explicit fields
- expose helper methods for constraints

Conceptual objects:
- `Ruleset`
- `CoverageTarget`
- optional small helpers for tier/cap normalization

Suggested first functions:
- `load_roster_profile(config: dict, profile_name: str) -> Ruleset`
- `build_ruleset(profile_cfg: dict, base_cfg: dict | None = None) -> Ruleset`
- `normalize_coverage_targets(raw_cfg: dict) -> dict[str, CoverageTarget]`

Suggested `Ruleset` fields for first implementation:
- `name`
- `mode`
- `hitter_count`
- `pitcher_count`
- `starter_positions`
- `dh_enabled`
- `allowed_tiers`
- `max_tier`
- `live_only`
- `point_cap_total`
- `tier_slot_caps`
- `tier_slot_exact`
- `lineup_fill_order`
- `coverage_targets`
- `platoons_allowed`
- `rotation_size`
- `primary_rp_count`
- `specialist_lhp_count`
- `long_man_count`

Implementation note:
- keep this module purely about translating config into a clean internal ruleset
- do not put filtering or roster logic here

---

## `ootp_opt/roster/eligibility.py`

Purpose:
- filter scored players to the legal pool for a given ruleset

Primary responsibilities:
- apply per-card constraints to hitters and pitchers
- annotate records with helper attributes if needed
- split by hitter / pitcher while preserving shared legality logic where possible

Suggested first functions:
- `filter_eligible_hitters(df, ruleset)`
- `filter_eligible_pitchers(df, ruleset)`
- `is_card_eligible(row, ruleset) -> bool`
- `summarize_pool(df, ruleset) -> dict`

Checks to support first:
- allowed tiers
- max tier
- live only
- point-cap value present when cap mode is used

Implementation note:
- this module should answer only: “is this card legal for this ruleset?”
- it should not decide whether a player makes the roster

---

## `ootp_opt/roster/models.py`

Purpose:
- define the data structures passed between builder, validator, evaluator, and exporter

Suggested first objects:
- `HitterRoster`
- `PitcherRoster`
- `RosterBuildResult`
- `ValidationResult`

Suggested first fields:

### `HitterRoster`
- `starters_by_position`
- `bench_players`
- `coverage_map`
- `unused_players`

### `PitcherRoster`
- `rotation`
- `bullpen`
- `lefty_specialists`
- `long_man`
- `unused_players`

### `ValidationResult`
- `is_valid`
- `errors`
- `warnings`
- `cap_used`
- `tier_counts`

### `RosterBuildResult`
- `ruleset_name`
- `hitter_roster`
- `pitcher_roster`
- `validation_result`
- optional `notes`

Implementation note:
- use lightweight dataclasses or similar simple structures
- avoid embedding heavy logic in model objects

---

## `ootp_opt/roster/builder.py`

Purpose:
- construct one deterministic roster from the eligible pool

This is the heart of the first usable system.

Suggested public entrypoint:
- `build_roster(eligible_hitters, eligible_pitchers, ruleset) -> RosterBuildResult`

Suggested internal steps:
- `build_hitter_roster(...)`
- `build_pitcher_roster(...)`
- validator call after construction

### Hitter builder functions
Suggested first functions:
- `build_hitter_roster(df, ruleset) -> HitterRoster`
- `select_hitter_starters(df, ruleset) -> tuple[dict, DataFrame]`
- `select_hitter_bench(df_remaining, starters, ruleset) -> tuple[list, dict]`
- `compute_coverage_map(rostered_hitters, ruleset) -> dict`

Starter logic:
- fill positions in ruleset lineup order
- choose best unused player for each position
- use positional score column for that slot
- for DH use offense-only score if appropriate

Bench logic v1:
- choose best remaining catcher improving C coverage
- choose best remaining infielder improving weakest infield coverage
- choose best remaining outfielder improving weakest outfield coverage
- choose best remaining hitter that fills remaining coverage gap or gives best utility value

Keep this deterministic and readable.

### Pitcher builder functions
Suggested first functions:
- `build_pitcher_roster(df, ruleset) -> PitcherRoster`
- `select_rotation(df, ruleset) -> tuple[list, DataFrame]`
- `select_primary_bullpen(df_remaining, ruleset) -> tuple[list, DataFrame]`
- `select_lefty_specialist(df_remaining, ruleset)`
- `select_long_man(df_remaining, ruleset)`

Pitcher logic:
- pick top 5 SP by starter overall
- pick top 6 RP by reliever overall
- pick best remaining RP vs LHB
- pick next best remaining SP as long man

Implementation note:
- builder should not enforce every hard rule itself
- construct first, then validate cleanly

---

## `ootp_opt/roster/validator.py`

Purpose:
- check whether the finished roster obeys the ruleset

Suggested first function:
- `validate_roster(result: RosterBuildResult, ruleset: Ruleset) -> ValidationResult`

Suggested internal checks:
- `validate_counts(...)`
- `validate_eligibility(...)`
- `validate_point_cap(...)`
- `validate_tier_constraints(...)`
- `validate_coverage(...)`

First-pass validation behavior:
- hard legal failures go to `errors`
- weaker coverage issues can start as `warnings`

Example checks:
- exactly 13 hitters and 13 pitchers
- every rostered card is legal under the ruleset
- cap used <= cap limit
- tier slot caps or exact counts satisfied
- positions meet target backup count where configured

---

## `ootp_opt/roster/export.py` or existing export integration

Purpose:
- write human-readable roster results

Suggested outputs for v1:
- starters table
- bench table
- rotation table
- bullpen table
- validation summary
- cap usage
- tier counts
- warnings / errors

Suggested first function:
- `export_roster_build(result, output_dir, profile_name)`

Implementation note:
- keep export separate from builder so results remain testable without file output

---

## CLI integration plan

Likely place:
- `ootp_opt/cli.py`

Suggested first CLI behavior:
- existing rating flow remains intact
- optional new mode builds a roster from already scored data or from just-generated scored data

Suggested first flags:
- `--build-roster`
- `--profile PROFILE_NAME`

Possible later overrides:
- `--point-cap`
- `--max-tier`
- `--live-only`

Recommendation for v1:
- support only profile-first usage initially
- add overrides later if needed

---

## Minimal end-to-end implementation order

### Step 1
Create roster profile config and `rules.py`

Success check:
- load a named profile and print normalized ruleset

### Step 2
Create `eligibility.py`

Success check:
- given scored hitters/pitchers and a profile, print count of eligible hitters/pitchers

### Step 3
Create pitcher builder in `builder.py`

Success check:
- output 5 SP + 6 RP + 1 LHP specialist + 1 long man from eligible pitchers

### Step 4
Create hitter starter builder

Success check:
- output a full 9-man starting lineup from eligible hitters

### Step 5
Create hitter bench builder

Success check:
- output 4 bench players and a coverage map

### Step 6
Create validator

Success check:
- report counts, cap usage, and tier counts, plus warnings/errors

### Step 7
Add CLI entry and export output

Success check:
- single command builds one full roster and writes readable output

---

## First milestone deliverable

At the end of the first coding pass, the project should be able to do this:

- load scored hitters and pitchers
- load profile `gold_cap_live_1400`
- filter to legal cards
- build one hitter roster and one pitcher roster
- report whether the roster is legal
- write the roster to output files

That should be considered enough to start testing and refining the heuristics.

---

## Suggested testing approach

For each stage, manually inspect outputs before overbuilding test scaffolding.

Recommended early checks:
- does tier filtering match expectations?
- are the correct pitchers being chosen by role?
- are scarce defensive positions filled sensibly?
- does the bench actually improve weak coverage?
- does cap usage look correct?

Once the flow stabilizes, add targeted tests around:
- ruleset parsing
- eligibility filtering
- cap validation
- lineup fill order
- pitcher role selection

---

## Important restraint

Do not add optimizer logic during this first implementation pass.

If a build looks imperfect, prefer to:
- inspect the intermediate data
- refine the heuristic
- improve validation/diagnostics

Only move toward swaps or search after the deterministic baseline works.

