# OOTP Planner

A modular Python tool for analyzing and optimizing Out of the Park Baseball (OOTP) Perfect Team rosters.

---

## Current Capabilities

* Load OOTP 26 and OOTP 27 CSV exports (hitters and pitchers)
* Normalize differences between game versions
* Generate:

  * Hitter batting scores (overall + vs LHP/RHP)
  * Position-based scores (offense + defense)
  * Pitcher starter and reliever role scores
* Produce shortlist outputs to assist with manual lineup and roster decisions

---

## Planned Features

* Lineup / bench / pitching staff optimizer
* Store upgrade finder (value vs cost)
* Tournament and Perfect Draft helpers
* GUI or improved front-end presentation

---

## Run

From the repo root, run:
python -m ootp_opt.cli

Outputs will be written to:

* outputs/ratings_hitters.csv
* outputs/ratings_pitchers.csv
* outputs/shortlists_hitters.csv

---

## Setup & Environment (new machine)

From the repo root, run:

py -3 -m venv .venv
..venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

If PowerShell blocks venv activation, run:

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

---

## Git Sync Workflow

### Verify repo is up to date with GitHub

git fetch origin
git status

Expected when synced:

* Your branch is up to date with 'origin/main'
* nothing to commit, working tree clean

---

### If you're ahead (local commits not on GitHub)

git push

---

### If you're behind (GitHub has commits you don't)

git pull --ff-only

---

### Verify local matches GitHub exactly

git fetch origin
git rev-parse HEAD
git rev-parse origin/main

If hashes match → local == GitHub

---

### Verify two PCs match each other

On each PC:

git fetch origin
git rev-parse HEAD

If both hashes match and git status is clean → identical environments

---

## Notes

* `.venv/` is local to each machine and is intentionally not committed
* Outputs are generated locally and not tracked in Git

---

## Development Context

For deeper architectural details, scoring logic, and current design direction, see:

* PROJECT_CONTEXT.md
* CODE_MAP.md

These files are designed to be pasted into a new ChatGPT session to quickly resume development context.

---

## Project Structure (high level)

ootp_opt/

* cli.py
* config.py
* domain/ (scoring logic)
* ingest/ (OOTP CSV loaders)
* services/ (orchestration + shortlists)
* export/ (CSV output helpers)

Future planned:

* ootp_opt/roster/ (lineup, bench, and staff logic)

---

## Workflow Summary

1. Export data from OOTP
2. Run the CLI
3. Review generated CSV outputs
4. Use shortlists to build roster decisions

---

## Status

The project is actively evolving from:

“script-based analysis”

into:

“a structured roster optimization system”

Current priority:

* refining rating weights
* preparing for roster-building and optimization modules

---