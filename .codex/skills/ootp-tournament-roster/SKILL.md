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

A native helper rejection with `error=native_input_requires_host` and
`input_sent=false` is a preflight routing error before OOTP input, not a mutation
failure. Retry only that rejected command once in the host context using
`tools.exec_command` with `sandbox_permissions: "require_escalated"`. Keep the
same controller, checkpoint, manifest, and next action. Do not end the run solely
because this preflight rejection occurred, replay completed actions, or rerun the
optimizer. `require_escalated` is an execution-tool argument, not a Python option.
This exception also applies to older AppContainer preflight errors explicitly
raised by `require_host_input` before activation. It does not apply to actual
approval rejections, input failures, geometry failures, or errors with uncertain
side effects.

If a model/tool/approval failure could have interrupted input, or approval was
rejected, stop that turn without switching controllers. On the next turn, run
checkpoint `status` once and resume the first incomplete phase. Do not reconstruct
the run from conversation history, reopen planner pages, or repeat successful
calibration and completed sections.

## Journaled Rebuild Checkpoints

When `status` includes `Rebuild actions`, use the journaled batch path by default.
Read the repository's [execution protocol](../../../AUTOMATION_EXECUTION.md) for
the exact contracts. Continue the existing manifest/checkpoint without regenerating
the optimizer plan. `needs_baseline` means collect exact active CID/variant
membership, not that a mismatch exists. Assignment targets are verified later.

`rebuild-execution status` prints compact state/counts and the next family.
Use `--json-output <next-state.json>` for local machine access to `next_batch`, or
`--json` only when stdout must be JSON. Do not print full status/checkpoint data
or reconstruct long shell arrays for routine execution.
Use `assignment-drag --checkpoint <checkpoint>` for drag families; this compiles
only remaining actions, journals each locally, and takes one final capture.
Use `--first-only` once for a calibrated preflight, reconcile it, then run the
same checkpointed command without that flag for the remainder. Do not use
`--skip-first` with a checkpoint; completed work is excluded automatically.

For membership and menu families, use `rebuild-execution validate-batch` followed
by host-context `run-batch` with ordered action-ID-bound `transactions`. Each
transaction expresses one exact semantic action; the native command journals all
actions without model/tool or observation calls inside the loop. Keep removals,
additions, pitching groups, starters, depth, batting order, and pinch families at
their respective boundaries. Ambiguous duplicate-card choices remain inspected
single-card work; do not guess a row to batch them.

Observe once after the family and run `rebuild-execution reconcile`. Returned
inputs remain `unverified`; only observed results become `completed`. On failure,
the journal retains the returned prefix plus the one interrupted `in_flight`
action. Stop the batch, observe, and repair only exact discrepancies; never replay
the group. `needs_verification` means reconcile returned inputs before more input.
Reuse known membership while only assignments change and no roster reload or
external membership change occurred; do not rescan all cards after every drag.

Verify the complete section at its read-only verification boundary. If the final
aggregate observation covers the complete section, reuse that observation for
`begin`/`reconcile` of the verification action in the same transition call, without
another capture. Keep local save separate. Per-action `begin`/`run` remains for
inspected cards, isolated repairs, verification, and local save; do not use a model
loop of begin-click-observe-reconcile for a stable calibrated family.

## Compact execution data

Keep the existing UI actions, waits, preflights, screenshots, and verification.
Only the data plumbing changes: `rebuild-execution` and `assignment-drag` print
compact receipts by default, including exact discrepancies. Full results remain
available with `--json` or local `--json-output <file>`; add `--json` to existing
scripts that parse stdout. Do not print full JSON merely to obtain routine counts.

Save inline assignment calibration once with `--save-coordinate-map <coords.json>`
on the first preflight, then use `--coordinate-map <coords.json>` instead of
repeating geometry/source/target flags for the remainder. The file must match the
manifest fingerprint, section, and family; geometry checks and preflight remain
unchanged. Recalibrate explicitly if the source layout changes.

Use `manage_roster_automation.py observation` to serialize observation data locally
instead of generating long PowerShell/Python roster arrays. It creates a draft by
default: a draft is expected data, never evidence, and cannot be reconciled. Only
after visually comparing every selected field, pass `--confirm-matches` and
`--capture <viewed.bmp>` to attest the observed matches. A native success receipt,
an existing screenshot file, or the desired manifest is not verification.

Use `--scope baseline` for the initial membership check, `--scope membership` for
current membership, `--scope pending` for issued family targets, the section name
for final section verification, and `--scope save` for save confirmation.
Assignment/save scopes require `--base <already-reconciled-membership.json>`;
membership identity is checked against current journal progress. Save with
`--output <observed.json>`, then invoke the existing `rebuild-execution reconcile`
in the same shell/tool call when appropriate. Observation generation never
advances the checkpoint itself.

Use `--actual-target TARGET=JSON`, `--actual-membership <actual-cards.json>`, and
`--actual-save "actual confirmed name"` for discrepancies; the helper preserves
them and reconciliation still blocks. Unspecified fields are attested matches,
so inspect them before confirming. See the repository execution protocol for
examples. Do not change observation frequency, batching, or gesture timing as part
of this token-focused data change.

## Efficient Execution

Run every native input command (`windows_drag` mutations, executing `fast-batch`,
`assignment-drag`, and journaled `run`) outside the command sandbox in the host
context (`require_escalated`). The helper rejects AppContainer input before
activation. Read-only inspection and capture may run inside the sandbox.


Use the execution tool's host permission argument on every native input call:

```javascript
const result = await tools.exec_command({
  cmd: "./.venv/Scripts/python.exe -m ootp_opt.automation.windows_drag type-text --coordinate-space window --at X,Y --text CID",
  sandbox_permissions: "require_escalated",
  justification: "Perform the next authorized OOTP native input in the host context."
});
text(result.output);
```

Do not omit `sandbox_permissions` after a resume. The default command context is
the sandbox even when OOTP was already opened successfully by the UI controller.

Coordinate spaces must be explicit when transferring screenshot points to native
input. Full-window screenshot points include the title bar: use native helper
`--coordinate-space window`. Absolute desktop points use `--coordinate-space screen`.
The default helper space, native library calls, fast-batch JSON, and assignment-drag
maps remain client-relative, excluding the title bar. Convert coordinates using
the observed geometry; do not copy window screenshot points into client maps.
For screenshot regions, include their offset before using full-window coordinates.

A `text_input_sent` receipt means events were sent, not that the CID field changed.
Verify the field once during text-entry preflight before applying the filter or
activating a card. If unchanged, check host execution and coordinate space, then
perform one corrected text-only preflight. Never apply a stale CID or replay
membership mutations as a text-entry repair.

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
calls do not require an intermediate observation. Capture the smallest useful region for
calibration, aggregate verification, or one exact discrepancy. Never observe
inside an assignment loop.

For rebuild drag families, use `manage_roster_automation.py assignment-drag`
with `--checkpoint` for journaled runs, so the manifest and journal compile only
remaining ordered moves from one source and target coordinate map. Execute one
verified `--first-only` preflight, then omit that flag for the remainder; do not
create intermediary assignment JSON files. Legacy commands without a checkpoint
retain `--skip-first 1` for the remainder.
Use the manifest-bound JSON `fast-batch` executor only when one section genuinely
combines different operation types such as filters, confirmations, and clicks.
Read `references/fast-executor.md` for both contracts and stop rules. Do not use a
fast path for an ambiguous duplicate-card choice, unknown menu mapping, or a
targeted repair.

Journaled execution marks the phase and action intents automatically, then
requires aggregate reconciliation; do not bypass the ledger with `--complete-all`.
For legacy checkpoints, mark the phase `in_progress` before mutation and update
completion with `--complete-all` after aggregate batch verification.
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
