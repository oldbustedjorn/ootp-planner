---
name: ootp-tournament-roster
description: Create or resume an OOTP Perfect Team tournament roster using the local planner Full Optimizer and the OOTP desktop application.
---

# OOTP Tournament Roster

Use this skill for a local Perfect Team tournament roster. Operate only one OOTP
window controller at a time.

## Boundaries

- Always use the planner's Full Optimizer, never the legacy builder.
- After planning, treat the automation manifest as the source of truth.
- Identify cards by CID plus variant status. Physical inventory ID may change.
- Never enter a tournament, pay a fee, submit a roster, sell a card, or delete an
  existing roster without a separate explicit request.
- Do not silently substitute a player or role. Checkpoint missing, ambiguous, or
  ineligible work and report it.
- Preserve and resume checkpoints instead of replaying completed phases.
- On a rebuild, preserve unchanged roster members and assignments. Use the
  manifest's rebuild delta; do not reconstruct differences from the screen.
- Never clear a lineup during a rebuild. Finish all changed starter-position and
  backup-depth slots first, then apply the separate batting-order plan if present.

## Route The Request

Run `plan -> sync -> assign` sequentially. Read only the reference for the phase
being executed:

- New roster, rebuild, or plan:
  [references/plan-phase.md](references/plan-phase.md)
- Card membership: [references/roster-sync-phase.md](references/roster-sync-phase.md)
- Pitching, lineups, depth, and pinch lists:
  [references/assignment-phase.md](references/assignment-phase.md)
- Resume: use `status`, then read only the first incomplete phase reference.

Do not preload all references. A routine run must not read repository source,
`MEMORY.md`, old session logs, or prior manifests to rediscover commands or
coordinates. Use CLI `--help` for an unknown command. Inspect implementation or
historical logs only after a concrete failure that the compact status, plan, or
phase reference cannot explain. Do not load the full computer-control API manual
for a routine run; consult only the required bootstrap or a specific unknown API.
Do not reread this entrypoint on resume within the same chat.

## Efficient Execution

Prefer compact structured output over source inspection and screenshots:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py service-check
.\.venv\Scripts\python.exe manage_roster_automation.py validate <manifest>
.\.venv\Scripts\python.exe manage_roster_automation.py init <manifest>
.\.venv\Scripts\python.exe manage_roster_automation.py status <checkpoint>
.\.venv\Scripts\python.exe manage_roster_automation.py ui-plan <manifest> <section>
```

Use `ui-plan`, not the full manifest or `actions`, for routine mutations. The CLI
prints compact summaries by default; request JSON only when a downstream command
needs it. Bound shell output and image detail to what the current phase requires.
Do not print helper source to verify a supported option.

At run start, activate the single OOTP window once and record its client origin
and size. Geometry can change between runs but is fixed within a run. Stop before
the next mutation if the window moved, resized, or left the expected screen.
Treat tournament state as static after auto-refresh is off unless this workflow or
the user changes it.

Perform related fixed-geometry actions in a batch. Use one model decision per
batch or completed section, not per click, card, or drag. Successful native helper
calls do not require an observation. Capture the smallest useful region for
calibration, aggregate verification, or one exact discrepancy. Never observe
inside an assignment loop.

Before OOTP mutation, mark the phase `in_progress`. Checkpoint once per successful
batch and update completion with `--complete-all` after aggregate verification.
Use the repair gate only for exact confirmed mismatches:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py repair-attempt <checkpoint> <section> --item <target> --strategy <distinct-strategy>
```

Do not replay correct work or begin an open-ended repair loop. Keep OOTP on the
blocked screen when pausing so the user can repair and resume.

## Run Metrics

Instrument new and resumed runs with `setup`, `plan`, `sync`, `rotation`,
`bullpen`, `vs_rhp`, `vs_lhp`, and `save`:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py metric-marker <run-id> <stage> start
.\.venv\Scripts\python.exe manage_roster_automation.py metric-marker <run-id> <stage> complete
```

Use `<tournament-id>-<UTC-start-time>` and retain it across resumes. Put a closing
marker and next opening marker in the existing phase-transition shell call; never
create a model turn only for metrics. On resume, start the incomplete stage again.

After `save complete` has returned, generate the report in the next tool call:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py metric-report --run-id <run-id> --html outputs/<manifest-stem>.metrics.html --json-output outputs/<manifest-stem>.metrics.json
```

Report the manifest, checkpoint, metrics path, completed phases, and exceptions.
Completion requires plan, sync, and assign complete; zero missing or ambiguous
items; and a confirmed local save. Do not infer phase cost from the whole run when
marker data exists.
