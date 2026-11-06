---
name: ootp-tournament-roster
description: Create, rebuild, resume, or audit an OOTP Perfect Team tournament roster using the local planner Full Optimizer and the OOTP desktop application. Also applies to terse requests beginning with "OOTP create:", "OOTP rebuild:", "OOTP resume:", or "OOTP audit tournaments".
---

# OOTP Tournament Roster

Use this skill for a local Perfect Team tournament roster. Operate only one OOTP
window controller at a time.

## Controller Lock

Use `mcp__cua_repl` as the only computer-control session for navigation and
semantic UI interaction. Initialize it once and retain that binding for the
entire run. Never invoke `node_repl`, `@oai/sky`, another computer-use skill, or a
second controller after `mcp__cua_repl` has been initialized. Assignment drags
and fixed-coordinate batches still use the repository's native
`ootp_opt.automation.windows_drag` helper as specified by the assignment
reference; that helper is input execution, not a second observation/controller
session.

On Windows, initialize with `cua.getState()`, locate the unique open window whose
title is `Out of the Park Baseball 27`, and bind it with
`cua.getApp({ windowId: <inventory-window-id> })`. Never select OOTP by display
name, executable path, or Start-menu alias. The inventory can expose multiple
aliases for the same process, while the window ID is unambiguous. If a name-based
app selection is rejected before any UI input, retry once in the same controller
with the unique inventory window ID; this read-only binding correction is not a
mutation failure and does not require stopping the run. Stop only when there is
no unique OOTP window to bind.

Do not load the general computer-use `SKILL.md`, API manual, guidance,
confirmation documentation, or bootstrap documentation during a routine run or
resume. The initial `mcp__cua_repl` response is the complete controller contract
for this workflow. If one required controller operation is genuinely unknown,
request only that operation's documentation; do not reload the full manuals.

## Short Invocations

The user may invoke the workflow without preserving an old task prompt:

- `OOTP create: <current tournament name>` creates a roster only when no matching
  active planner definition exists.
- `OOTP rebuild: <planner plan or local roster name>` preserves the existing plan
  and roster and applies only the Full Optimizer delta. Run the saved plan with
  `manage_roster_automation.py build-plan` directly; do not open the planner in a
  browser or require its HTTP service for a routine rebuild.
- `OOTP resume: <tournament name or checkpoint>` resumes the first incomplete
  checkpoint phase without replaying completed work.
- `OOTP audit tournaments` performs a read-only comparison of currently visible
  tournament names and rules against active planner definitions. Report matching,
  changed, missing, and new definitions; do not build, edit, enter, or submit.

An OOTP tournament ID identifies a scheduled tournament instance, not the reusable
tournament definition. A changed ID alone must not create another planner plan.
Match by normalized tournament name and material rules first; retain the current
instance ID only as observed metadata for locating that listing.

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

For `OOTP resume:` with an explicit checkpoint, the first tool call must be only:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py status <checkpoint>
```

Treat that checkpoint and its referenced manifest as authoritative. When `plan`
and `sync` are already complete and `assign` is incomplete, skip planner service
checks, planner/browser navigation, plan generation, membership inspection, and
the plan/sync references. Read only `assignment-phase.md`, emit only the relevant
`ui-plan` section, initialize `mcp__cua_repl` once, and continue from the OOTP
screen already left open. Do not repeat setup merely because the request is in a
new model turn. A missing or invalid checkpoint is the only reason to fall back
to normal request routing.

Run `plan -> sync -> assign` sequentially. Read only the reference for the phase
being executed:

- New roster, rebuild, or plan:
  [references/plan-phase.md](references/plan-phase.md)
- Card membership: [references/roster-sync-phase.md](references/roster-sync-phase.md)
- Pitching, lineups, depth, and pinch lists:
  [references/assignment-phase.md](references/assignment-phase.md)
- Deterministic rebuild batches:
  [references/fast-executor.md](references/fast-executor.md), read only when a
  rebuild section has two or more stable native actions.
- Resume: use `status`, then read only the first incomplete phase reference.

Do not preload all references. A routine run must not read repository source,
`MEMORY.md`, old session logs, or prior manifests to rediscover commands or
coordinates. Use CLI `--help` for an unknown command. Inspect implementation or
historical logs only after a concrete failure that the compact status, plan, or
phase reference cannot explain. Do not load the full computer-control API manual
for a routine run; consult only the required bootstrap or a specific unknown API.
Do not reread this entrypoint on resume within the same chat.

If a model/tool/approval failure interrupts a run, stop that turn without
switching controllers. On the next turn, run checkpoint `status` once and resume
the first incomplete phase. Do not reconstruct the run from conversation
history, reopen planner pages, or repeat successful calibration and completed
sections.

## Efficient Execution

Prefer compact structured output over source inspection and screenshots:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py service-check
.\.venv\Scripts\python.exe manage_roster_automation.py validate <manifest>
.\.venv\Scripts\python.exe manage_roster_automation.py init <manifest>
.\.venv\Scripts\python.exe manage_roster_automation.py status <checkpoint>
.\.venv\Scripts\python.exe manage_roster_automation.py ui-plan <manifest> <section>
```

The non-JSON `init` output prints the exact checkpoint path. Use that path
directly for every subsequent command. Do not scan the filesystem, glob for a
checkpoint, or reconstruct its name after initialization. A successful `init`
means the checkpoint exists; continue with `status` on the printed path.

Run `service-check` in the host network context, outside the command sandbox.
The Windows scheduled service listens on the host loopback interface, so a
sandboxed connection failure is not evidence that the planner service is down.
Start or inspect the `OOTP Planner Service` scheduled task in the same host
context.

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

For rebuild drag families, use `manage_roster_automation.py assignment-drag` so
the manifest compiles the exact ordered moves directly from one source and target
coordinate map. Execute one verified `--first-only` preflight, then the remaining
moves with `--skip-first 1`; do not create intermediary assignment JSON files.
Use the manifest-bound JSON `fast-batch` executor only when one section genuinely
combines different operation types such as filters, confirmations, and clicks.
Read `references/fast-executor.md` for both contracts and stop rules. Do not use a
fast path for an ambiguous duplicate-card choice, unknown menu mapping, or a
targeted repair.

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
