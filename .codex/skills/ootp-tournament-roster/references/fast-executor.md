# Fast Rebuild Executor

Use this path for deterministic rebuild deltas after the relevant OOTP screen is
open and its geometry has been calibrated. The executor removes model round trips;
it does not make decisions, inspect results, retry, or mark checkpoints complete.

## Journaled batches

For execution-ledger checkpoints, use the repository's
[execution protocol](../../../../AUTOMATION_EXECUTION.md):
`assignment-drag --checkpoint` for drag families and `rebuild-execution run-batch`
for ordered action-ID-bound native transactions. Each command writes durable
per-action intent/returned receipts and one final capture; aggregate-reconcile
once per family. A returned input is not verified success. Do not interpret an
action-level journal as a requirement for a model turn or screenshot per action.

The raw `fast-batch` contract below remains for legacy phase-only runs and exact
targeted repairs; it does not advance the journal by itself.

Compact receipts are now the default. Use `--json-output <file>` to keep
native plans/results locally without printing their full arrays, and `--json`
when a downstream script parses stdout. After the existing visual verification,
use the `observation` helper to serialize confirmed target data, then reconcile;
do not rebuild long roster arrays in inline shell scripts. This changes neither
the number of observations nor native execution timing.

## Assignment Drags

Do not create JSON batch files for rotation, starter, depth, pinch-hitter, or
pinch-runner drags. Compile those families directly from the manifest:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py assignment-drag <manifest> <section> <family> --checkpoint <checkpoint> --client-geometry LEFT,TOP,WIDTH,HEIGHT --source CID=X,Y --target KEY=X,Y --save-coordinate-map <coords.json> --first-only --execute --capture-after <preflight.bmp>
.\.venv\Scripts\python.exe manage_roster_automation.py assignment-drag <manifest> <section> <family> --checkpoint <checkpoint> --coordinate-map <coords.json> --execute --capture-after <final.bmp>
```

Repeat coordinate flags as needed. The compiler reads `ui-plan`, rejects missing
coordinates before input, preserves manifest order, and invokes the native batch
runner directly. Use `--first-only` for the verified preflight and
the same checkpointed command without `--first-only` for the remainder.
If preflight selects a different card, discard that family's saved coordinate
map and remap its source identities from a fresh client capture before any
allowed alternate preflight or targeted repair. Preserve the unverified action;
do not replay the batch or assume the other source rows were correct.

Completed actions are skipped automatically after reconciliation. For legacy
commands without a checkpoint, `--skip-first 1` remains supported. This removes batch-file authoring and a
separate validation turn.

## Batch Contract

Use a run-local JSON file only when an executable section genuinely mixes
operation types, such as filter transactions plus confirmations or menu clicks.
Bind it to the current manifest and locked OOTP client geometry:

```json
{
  "schema_version": 1,
  "manifest_id": "manifest-id-from-ui-plan",
  "section": "vs_rhp",
  "client_geometry": [100, 80, 1600, 1000],
  "actions": [
    {
      "op": "drag_batch",
      "moves": [
        [[320, 420], [980, 260]],
        [[320, 460], [980, 300]]
      ]
    },
    {
      "op": "click_batch",
      "points": [[1100, 300], [1100, 340]]
    },
    {"op": "wait", "ms": 800}
  ]
}
```

Supported operations are:

- `drag_batch`: `moves` contains `[[from_x, from_y], [to_x, to_y]]` entries.
- `click_batch`: `points` contains client-relative click coordinates.
- `type_text`: requires `at` and `text`; `select_all` defaults to true.
- `filter_batch`: requires `field`, `activate`, and `values`; optional `open`,
  `apply`, and `confirm` points use the existing Manage Cards transaction.
- `wait`: `ms` may be at most 5000.

PowerShell may flatten a one-item nested array. The executor accepts either the
ordinary multi-item shape or a flattened singleton for `moves`, `points`, `open`,
and `values`; do not stop a run merely because a singleton was serialized that
way.

Coordinates are client-relative, while `client_geometry` includes the observed
screen origin and client size. The executor checks the full geometry before every
operation and stops if the window moved or resized. It accepts at most 50
operations and 30 items in any action. It cannot run arbitrary commands.

## Execute

Validate the batch before requesting native GUI input:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py fast-batch <manifest> <section> <batch.json>
```

Execute it outside the command sandbox and capture one verification image:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py fast-batch <manifest> <section> <batch.json> --execute --capture-after <verification.bmp>
```

If `--capture-after` is omitted, the CLI automatically writes
`<batch-stem>.verification.bmp` beside the batch file. Do not stop a run merely
because an explicit capture path was omitted; use the reported capture for
aggregate verification.

The manifest ID and section must match. A successful command proves only that the
planned native inputs ran; inspect the final capture before completing the section.

## Rebuild Sequence

1. Emit `ui-plan` for the section and skip it when every mutation list is empty.
2. Capture once and record the current full client geometry and coordinates.
3. For a drag-based family, use `assignment-drag --first-only` for preflight and
   the checkpointed command without `--first-only` for the remainder. Do not create JSON.
4. Put remaining mixed non-drag operations in one JSON batch only when the native
   homogeneous helper cannot express the section directly.
5. Aggregate-verify the section once. Checkpoint it only after verification.
6. On an execution error or mismatch, do not replay the batch. Use the existing
   checkpoint repair gate for only the confirmed discrepancies.

For Manage Cards, removals and additions must remain separate actions because
removals require confirmation. Inspected duplicate CIDs stay on the ordinary
single-card path; do not encode an ambiguous row choice in a fast batch.

Do not combine local save with an assignment batch. Save only after pitching and
both lineup splits are verified.
