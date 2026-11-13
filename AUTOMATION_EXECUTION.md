# Resumable rebuild execution

New rebuild manifests embed a normalized baseline (CID plus explicit variant,
assignment targets, and role settings). `init` creates an ordered execution ledger
inside the existing phase checkpoint. New-roster and older checkpoints retain
their existing commands and schema. Run only one OOTP controller at a time.

The sequence is removals, additions, membership verification, pitching and its
verification, each lineup's starters/depth/order/pinch actions and verification,
then local save. Unchanged targets produce no mutations. Native input never
marks an action verified. Completion requires exact active membership, section
verification, no unresolved phase items, and an observed local save confirmation.

## Compact receipts and local data

When opening the intended existing roster, verify its identity from the visible
name and tournament rules/context, then bind its actual local name before input:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution bind-save-name <checkpoint> --name "Wed Ice to See You 1490029" --capture <inspected-roster.bmp> --note "Verified existing roster and matching tournament rules"
```

This explicit controller attestation stores the local name, original manifest
name, capture hash and verification note in the checkpoint journal. It leaves
the manifest, action IDs and completed prefix unchanged. Numeric suffixes are
matching hints, never identity proof. No fuzzy matching or automatic renaming is
performed. Repeating the same binding is harmless; changing it is rejected.
Save observations use the bound name and must match exactly; all membership and
assignment checks still apply. Legacy checkpoints fall back to the manifest name
until explicitly bound. A pending save-name mismatch can be recovered by binding
the verified existing name and reconciling the actual save evidence, without
repeating the save. Binding alone never verifies or completes a save.

`rebuild-execution` and `assignment-drag` now print short text receipts by default:
state, completion counts, pending verification, next action/family, capture path,
and exact discrepancies. The execution engine's full result is unchanged. Use
`--json` when a program needs JSON on stdout, or `--json-output <file>` to keep
the full machine result locally without returning it to the model. Do not parse
the default text as JSON or print full checkpoints to recover routine state.

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution status <checkpoint> --json-output <next-state.json>
```

Assignment coordinates can be serialized from the existing inline flags once:
add `--save-coordinate-map <coords.json>` to the calibrated preflight. For the
remainder, use `--coordinate-map <coords.json>` instead of repeating geometry,
source, and target flags. The file is bound to the manifest fingerprint, section,
and family. Existing geometry checks, action order, preflight, gestures, waits,
and verification still apply. Use a new map if recalibration is needed; files
are never carried into another manifest or section implicitly.

Coordinate-map validation checks binding and bounds; it cannot identify the player
under a supplied point. If a preflight selects a different card, invalidate that
family's saved map and remap all its sources from a fresh client-area capture.
Do not reuse the remaining entries merely because the window geometry is stable.
Retain the unverified action, use only the existing bounded alternate/targeted
repair allowance, and reconcile the actual result before continuing.

The `observation` command replaces handwritten membership/target arrays. It writes
a **draft by default**. Drafts contain expected values, are not live evidence, and
cannot be passed to `rebuild-execution reconcile`.

```powershell
# Optional local draft, without claiming success or changing the checkpoint.
.\.venv\Scripts\python.exe manage_roster_automation.py observation <checkpoint> --scope baseline --output <baseline-draft.json>
# Only AFTER comparing every scoped field with the observed UI:
.\.venv\Scripts\python.exe manage_roster_automation.py observation <checkpoint> --scope baseline --capture <viewed-baseline.bmp> --confirm-matches --output <baseline-observed.json>
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution reconcile <checkpoint> --observation <baseline-observed.json>
```

`--confirm-matches` is an explicit controller attestation after inspecting a
capture, not automatic recognition. It means all fields in the selected scope
match, except any supplied actual overrides. A capture path/hash records provenance;
its existence alone proves nothing about its contents. Native input returning is
not grounds for using this flag. This command never reconciles or completes work.

Scopes are `baseline` (untouched rebuild only), `membership` (membership at current
journal progress), `pending` (issued, unverified/in-flight targets), `pitching`,
`vs_rhp`, `vs_lhp` (complete section), and `save`. For assignment and save scopes,
reuse a membership observation already reconciled in this checkpoint with `--base`.
The helper checks exact CID/variant membership against journal progress. It copies
only that known membership and generates the selected target structure locally.

```powershell
# After the existing family verification; no new screenshot or UI action is added.
.\.venv\Scripts\python.exe manage_roster_automation.py observation <checkpoint> --scope pending --base <verified-membership.json> --capture <viewed-family.bmp> --confirm-matches --output <family-observed.json>
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution reconcile <checkpoint> --observation <family-observed.json>
```

Record real discrepancies with `--actual-target TARGET=JSON`,
`--actual-membership <actual-cards.json>` for membership scopes, or
`--actual-save "actual confirmed roster name"`. Unspecified scoped fields are
attested matches, so compare them before confirming. Blank targets can be recorded
as JSON `null`. Actual mismatches are preserved and still block reconciliation;
the helper never substitutes the planned value for supplied actual data. Existing
manually authored observation files remain supported. JSON output paths cannot
overwrite the checkpoint, manifest, input files, or captures.

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py init <manifest>
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution status <checkpoint>
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution reconcile <checkpoint> --observation <observed.json>
```

Use the checkpoint path printed by `init`. For an older rebuild, opt into the
ledger with `rebuild-execution init <checkpoint>`. This reads its archived prior
manifest if available; otherwise supply `--baseline-manifest <prior-manifest>`.
The prior manifest ID must match the delta's source and its membership must
reconcile through the exact delta to the desired roster. Neither manifest is
rewritten. Completed legacy phases are skipped; notes never establish a local
save in the new protocol. Partially completed legacy batches require reconciliation
with their actual baseline before migration; progress is never guessed from notes.

The controller supplies observations from OOTP, using this shape:

```json
{
  "membership": [{"cid": "85114", "variant": true}],
  "targets": {
    "pitching/rotation_size": 4,
    "pitching/rotation/1": {"cid": "85114", "variant": true},
    "vs_rhp/starters/SS": {"cid": "12345", "variant": false},
    "vs_rhp/depth/SS/1": {
      "card": {"cid": "23456", "variant": false},
      "condition": "If Starter tired"
    },
    "vs_rhp/batting_order": ["CF", "SS", "1B", "DH", "LF", "RF", "3B", "2B", "C"],
    "vs_rhp/pinch_hitters/1": {"cid": "23456", "variant": false}
  },
  "local_save": "exact roster name from OOTP save confirmation"
}
```

Always include **all active cards**, including unexpected ones. A membership count
alone cannot establish identity. The example abbreviates the roster and targets;
section verification requires every target in that section. Target keys and values
use `rebuild_snapshot(manifest)`; bullpen targets are
`pitching/bullpen/<cid>/<true|false>` with `card`, `primary_role`, `usage`, and
`secondary_role`. Batting order contains positions because replacement starters
inherit position slots. Omit `local_save` until OOTP confirms the local save.

## Default: journaled action batches

`rebuild-execution status` returns `next_batch`: the next ordered family of at
most 30 actions. Use one calibrated native command for that family and one
aggregate observation. Per-action intents and returned-input receipts are written
locally inside the command; they do not require model/tool round trips or captures.
Removals, additions, pitching families, each lineup's starters/depth/order/pinch
families, section verification, and local save remain separate boundaries.

Drag families compile directly from the checkpoint with no intermediate JSON:

```powershell
# Host context. First verify one calibrated preflight, then omit --first-only.
.\.venv\Scripts\python.exe manage_roster_automation.py assignment-drag <manifest> vs_rhp starters --checkpoint <checkpoint> --client-geometry LEFT,TOP,WIDTH,HEIGHT --source CID=X,Y --target POS=X,Y --first-only --execute --capture-after <preflight.bmp>
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution reconcile <checkpoint> --observation <observed-preflight.json>
.\.venv\Scripts\python.exe manage_roster_automation.py assignment-drag <manifest> vs_rhp starters --checkpoint <checkpoint> --client-geometry LEFT,TOP,WIDTH,HEIGHT --source CID=X,Y --target POS=X,Y --execute --capture-after <family.bmp>
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution reconcile <checkpoint> --observation <observed-family.json>
```

Repeat source/target flags as needed. Completed actions are excluded automatically;
do not use `--skip-first` with a checkpoint. Supported families are rotation,
starters, depth, pinch hitters, and pinch runners. Depth conditions are part of
verification: dragging a card does not prove its condition is set. Repair only
an observed condition mismatch before reconciling that family.

For calibrated membership/menu transactions, author one file for the family:

```json
{
  "schema_version": 1,
  "manifest_id": "current-manifest-id",
  "section": "sync",
  "client_geometry": [0, 31, 1850, 1062],
  "transactions": [
    {"action_id": "first-id-from-next_batch", "actions": [
      {"op": "filter_batch", "field": [1100, 329], "activate": [1700, 309],
       "apply": [1142, 813], "values": ["first-confirmed-cid"]}
    ]},
    {"action_id": "second-id-from-next_batch", "actions": [
      {"op": "filter_batch", "field": [1100, 329], "activate": [1700, 309],
       "apply": [1142, 813], "values": ["second-confirmed-cid"]}
    ]}
  ]
}
```

Coordinates and CIDs above are illustrative, not reusable calibration. Each
transaction expresses exactly one semantic action (including filter, apply,
activate and confirmation as required); use existing fast-batch operations.
Every transaction is validated before the first input. The IDs must be an ordered
prefix of `next_batch`; at most 50 native operations are allowed in total.
Ambiguous duplicate-card choices still require the inspected single-card path.

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution validate-batch <checkpoint> --batch <family.json>
# Host context; writes one final capture, no captures inside the action loop.
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution run-batch <checkpoint> --batch <family.json> --capture-after <family.bmp>
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution reconcile <checkpoint> --observation <observed-family.json>
```

Returned transactions are `unverified`, distinct from both the interrupted
`in_flight` action and verified `completed` actions. `needs_verification` means
observe the group before executing another. A native failure stops locally at
the exact transaction; later transactions are never issued. Reconciliation can
commit the observed returned prefix and resolve the interrupted action. A
returned transaction with the wrong target blocks the group for a targeted
repair; correct transactions must not be replayed. The ledger never converts
returned input into success without observation.

Reuse the last verified membership while only assignments are changing and no
external roster reload or membership change occurred; do not rescan all active
cards after each drag. Include fresh observations of the affected family targets.
At the section boundary, verify the complete section. If the final aggregate
observation also covers the full section, reuse it for its read-only verification
action in the phase transition; do not take another identical capture.

## Single actions and repairs

For an inspected or isolated semantic action performed through the existing controller:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution begin <checkpoint> --action-id <next-action-id>
# Perform exactly that action through the existing OOTP controller/native helper.
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution reconcile <checkpoint> --observation <observed-after.json>
```

For calibrated native input, `run` wraps the existing geometry-checked executor:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py rebuild-execution run <checkpoint> --action-id <next-action-id> --batch <batch.json> --capture-after <verification.bmp>
```

The batch must match the manifest ID and action section. It expresses exactly one
semantic action, which can require several native operations (for example filter,
deactivate, confirm). The controller remains responsible for the coordinate-to-card
mapping. Use `begin`/`reconcile` for read-only verification actions; `run` refuses
native input for those. Save remains a separate action after section verification.
Existing raw fast-batch and assignment-drag commands without `--checkpoint`
remain available for legacy runs and targeted repairs, and do not advance the ledger.

The checkpoint journal records intent before input, returned/interrupted input,
observations, mismatch diagnostics, and reconciliation decisions. Writes use a
flushed temporary file and atomic replacement; an OS lock serializes execution
writers and releases ownership if a process crashes. A returned single native call
leaves the action in flight; batch receipts remain unverified. Interrupted input blocks subsequent actions until live
evidence establishes its result. Membership actions can resume when the full live
set equals their before or after set. Unknown cards or wrong variants block input;
reconciliation never substitutes players or silently adopts another baseline.

For an assignment proven unchanged from its baseline, explicit
`reconcile --retry-unapplied` permits another attempt. Other partial or ambiguous
assignment failures remain in flight for an exact targeted repair and subsequent
verification. Input actions have at most two attempts. Read-only verification can
be repeated. Reinitializing the same checkpoint preserves the journal. Replaced
manifest revisions and changed action plans are rejected.

No screenshot recognition or automatic baseline substitution is added. The state
machine consumes explicit controller observations and can be tested without
sending input to OOTP. Tournament entry, submission, purchases, and server updates
are outside this protocol.

## Native input environment and coordinates

Execute native input helpers and `rebuild-execution run` in the host command
context (`require_escalated`), outside the command sandbox. The helper checks its
Windows process token and rejects AppContainer input before window activation.
Read-only inspection and captures do not require this input preflight.

An AppContainer rejection returns exit code 75 and a JSON error with
`error=native_input_requires_host`, `input_sent=false`, and
`retryable_in_host=true`. This is a routing rejection before input, not an
interrupted mutation. Retry only that rejected command once through the execution
tool with `sandbox_permissions: "require_escalated"`, using the same controller,
manifest, checkpoint, and action selection. Do not end the run solely because of
this preflight rejection, rerun the optimizer, or replay completed actions. The
permission is a tool argument, not a Python CLI option. Honor an actual approval
rejection; do not retry errors that could follow partial input without observation.
Journaled native `run` checks the host context before recording intent, so this
rejection neither opens an action nor consumes an action attempt.

Native library calls, fast-batch JSON, and assignment-drag maps use client-relative
coordinates, excluding the title bar. The native helper CLI also accepts explicit
`--coordinate-space window` (window frame, including the title bar) or
`--coordinate-space screen` (absolute desktop coordinates); the default remains
`client`. One choice applies to all points in the command, including filter open,
apply, activate, and confirmation points. Do not reuse a screenshot point as a
client point without conversion. Screen points must include the screenshot's
desktop origin when the OOTP window is offset from the desktop origin.

For example, a text field at window point `(1100, 360)` can be addressed with:

```powershell
# Run in the host context. This only enters text; it does not apply or activate.
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag type-text --coordinate-space window --at 1100,360 --text 87326
```

The returned `text_input_sent` receipt reports the converted client point and
`field_verification=required`. Check the field once during preflight before
applying the filter or starting a calibrated batch. A returned input call proves
only that Windows accepted the events. If the field is unchanged, check host
execution and coordinate space before one corrected text-only preflight. Do not
click Apply or Activate while the filter still contains a previous CID.
