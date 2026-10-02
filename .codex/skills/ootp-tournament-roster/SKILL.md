---
name: ootp-tournament-roster
description: Create or resume an OOTP Perfect Team tournament roster using the local planner Full Optimizer and the OOTP desktop application.
---

# OOTP Tournament Roster

Use this skill when the user asks to create, load, synchronize, assign, or resume a
Perfect Team tournament roster. The planner and OOTP run locally. Operate only one
OOTP window controller at a time.

## Boundaries

- Always use the planner's Full Optimizer. Do not use the legacy builder.
- Use the generated automation manifest as the source of truth after planning.
- Use CID plus variant status to identify a card. Physical inventory ID is
  informational and may change between exports.
- Never enter a tournament, pay an entry fee, submit a tournament roster, sell a
  card, or delete an existing roster without a separate explicit user request.
- Do not silently substitute a player or role. Record missing, ambiguous, or
  ineligible assignments in the checkpoint and report them.
- Preserve a usable checkpoint when interrupted. Resume from it rather than
  repeating completed phases.

## Route The Request

Run phases sequentially. Never delegate concurrent control of OOTP.
Read each phase reference immediately before that phase. Do not load all three
references at startup.

- For a new roster or the `plan` phase, read
  [references/plan-phase.md](references/plan-phase.md).
- For card membership or the `sync` phase, read
  [references/roster-sync-phase.md](references/roster-sync-phase.md).
- For pitching, lineups, depth charts, or the `assign` phase, read
  [references/assignment-phase.md](references/assignment-phase.md).
- For status or resume requests, validate the manifest and checkpoint with
  `manage_roster_automation.py`, then read only the reference for the first
  incomplete phase.

## Shared Operating Rules

Prefer structured files and application text over screenshot interpretation.
Capture the smallest useful OOTP region at the start and end of a batch, and on
failure. Do not capture or narrate every click or drag. Perform a batch, verify its
aggregate result, then retry only discrepancies.

Once OOTP auto-refresh is off, treat tournament rows, filters, and settings as
static until this workflow changes them or the user interacts with OOTP. Do not
re-read unchanged tournament state. Within a stable screen, perform related clicks
and drags in one computer-control call, suppress intermediate screenshots and text,
and emit one refreshed state at the end. Aim for one model decision per batch or
completed section, not one decision per control.

For drag-heavy sections, allow roughly 350-450 ms for OOTP to apply each drop.
This is preferable to shorter waits followed by multiple observation and repair
cycles. Keep the OOTP window geometry unchanged throughout the run.

Use the repository-local Python environment:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py validate <manifest>
.\.venv\Scripts\python.exe manage_roster_automation.py init <manifest>
.\.venv\Scripts\python.exe manage_roster_automation.py status <checkpoint>
.\.venv\Scripts\python.exe manage_roster_automation.py actions <manifest> <section>
```

Before mutating OOTP, mark the active phase `in_progress`. On completion or
failure, update the phase once per batch with concise notes. Use `--complete-all`
after aggregate verification rather than printing or passing every candidate ID.
The CLI prints compact summaries by default; use `--json` only when full checkpoint
data is genuinely needed. Finish by reporting the manifest path, checkpoint path,
completed phases, and exceptions.
