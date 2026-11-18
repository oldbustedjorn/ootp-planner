# Roster Sync Phase

Use this phase to make OOTP roster membership match `roster.membership` in the
automation manifest.

The `sync` metric starts at the plan-to-sync transition. Complete it only after
aggregate membership verification and start `rotation` in the same command.

Native input commands must run in the host context (`require_escalated`),
outside the command sandbox. For full-window screenshot coordinates, pass
`--coordinate-space window` to the native helper; its default coordinates are
client-relative and exclude the title bar. The same coordinate space applies to
every filter-batch point. Calibrate and verify one text-only entry before applying
the filter. If a helper reports sent input but the field stays unchanged, check
execution context and coordinate space before one corrected text-only preflight.
Do not apply the old CID or activate an unrelated result.

If a native helper rejects AppContainer execution before sending input, retry
only that rejected command once with the execution tool argument
`sandbox_permissions: "require_escalated"`. Keep the existing controller and
checkpoint and continue on success. This preflight routing correction does not
require stopping the turn. An actual approval rejection or possible partial input
still uses the normal stop and reconciliation rules. Never replay already
completed removals or additions to correct the execution context.

Use the native helper for text entry and fast batches; do not inspect its source
or replace it with one computer-control call per card:

```powershell
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag type-text --at X,Y --text "CID"
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag filter-batch --field X,Y --activate X,Y --value CID1 --value CID2 --capture-after <path.bmp>
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag filter-batch --field X,Y --activate X,Y --confirm X,Y --value CID1 --value CID2 --capture-after <path.bmp>
```

For checkpoints with an execution ledger, group unambiguous removals or
additions from `next_batch` into `run-batch` transactions and reconcile one
aggregate observation. The native command journals per-card intents and returned
inputs locally; do not make one model/tool/observation cycle per card. Exact
duplicate-row choices still use the inspected single-card path. Returned inputs
are unverified until reconciliation, and an interrupted transaction blocks later
transactions. Use the ledger's returned prefix and interrupted action instead of
reconstructing progress from checkpoint notes. Do not rescan unchanged members
after each action. The older raw batch guidance below is for phase-only runs.

## Run-local filter profile

Use `membership-filter` for stable journaled removals/additions instead of
handwriting transaction arrays. Calibrate the Manage Cards view, status categories,
CID dialog route, field, Apply, activation and removal Proceed points once per
unchanged layout. Record the checked status categories and known menu/transition points
in the profile note. Inspect a representative menu only when its mapping is
unknown; retain that mapping throughout the run. Do not toggle checkboxes blindly:
these controls can leave no categories selected. Close the menu only after the
required categories are selected. `all` means all applicable card-status categories
are included, not an empty selection. The active roster view must exclude reserves.

Keep the known `RosterLoad`/`RosterFilterCID` view through each family. Set active
status once for removals/baseline, inactive or all statuses once for additions,
and active once for final verification. Use cached menu points for these
transitions; do not reopen or inspect the same known menu per CID or batch. The
profile's CID `--open` route must start and finish at the same Manage Cards screen;
it must not contain status toggles. Verify one native text-only CID entry at initial
calibration. After one inspected removal establishes Proceed, save its mapping
for the remaining removals. A first addition preflight is available with
`--first-only`; after successful observation/reconciliation reuse the profile for
the remainder. Do not add another preflight if that operation was already verified.

Create each run-local profile from observed client-relative coordinates, using an
existing inspected calibration capture (no extra capture solely to save a file):

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py membership-filter <checkpoint> --save-profile <run-remove.profile.json> --client-geometry LEFT,TOP,WIDTH,HEIGHT --screen-status active --field X,Y --apply X,Y --activate X,Y --confirm X,Y --open X,Y --open X,Y --capture <viewed-calibration.bmp> --note "RosterLoad; active selected; CID text/Apply and Proceed verified; status-menu transition points ..." --confirm-calibration --execute --capture-after <removals.bmp>
```

### Correct checkbox selections within the current turn

Active, Reserve and Inactive are independent checkboxes. An `Active, Inactive`
caption means a mixed selection to inspect, not roster drift and not grounds by
itself to stop or ask permission. Correcting these read-only settings is already
authorized. Open the menu once, read all actual checkmarks and change only those
that differ from the required mode. Use this read-only helper for a mixed state:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py status-selection --observed active,inactive --desired inactive
```

The output says which categories to turn on/off and leave checked. Supply the
actual checked categories (`none` only when none are checked), not the caption
`Eligible Only`. Active-only excludes Reserve and Inactive; inactive-only excludes
Active and Reserve; all includes all three. Do not click a correct checkbox or
cycle modes to guess their state. Perform one correction pass and inspect the
result. If a click did not take effect, remap that checkbox from the fresh menu
and make one corrected pass; do not loop. Once correct, continue the required
filter-only preflight in the same turn, preserving all completed actions.

Pause only if checkmarks/options remain unreadable, the corrected state cannot
be established after that bounded recovery, or observed CID/variant/membership
differs from the plan. An unexpected card/filter result blocks activation while
the read-only filter is corrected; it does not require ending the turn at the
first recoverable selection error. Retain individual inspected additions after
a filter failure; do not return to a rejected/unverified multi-card repair batch.

### Status changes require a filter-only preflight

The recent failures typed a CID while the dialog was closed and selected
**Filter: None** from an incorrect menu row. Do not assume a status change itself
proves the filter or its cached open route remains correct. A selected saved
filter and its **Customize** dialog are separate steps: selecting `RosterFilterCID`
does not by itself open the editable CID field. `None` is not a reset that may be
followed immediately by an activation.

After changing active/reserve/inactive categories, first close the status menu,
confirm `RosterLoad` and the actual filter label, select `RosterFilterCID` if
needed, then open **Customize**. Use observed labels/menu rows; never reuse a saved
filter's row number or type at a remembered field coordinate while its dialog is
closed. The menu contents can differ between `None` and a selected saved filter.
If the expected route does not open the dialog, inspect that menu once and remap
only its route; do not keep toggling statuses to repair a CID-selection problem.

The helper has a filter-only path for the next pending membership CID. It sends
only dialog navigation, CID text and Apply, with no activation/Proceed step and
no journal progress. Use it from a closed-menu Manage Cards screen only when
the route for the currently selected filter is known:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py membership-filter <checkpoint> --profile <run-remove.profile.json> --screen-status all --prepare-only --capture-after <addition-filter-result.bmp>
```

Inspect that capture: require the intended CID and exact variant in the filtered
row, with the required categories selected. If it shows the previous CID, `None`,
an unfiltered collection, no match or unresolved copies, do not activate a row or
approve a batch. Open Customize and verify the actual field value before Apply;
use the inspected single-card path if calibration is invalid. Never infer
successful text entry from the native return receipt alone.

Only after that check may a removal-to-addition profile inherit unchanged CID
controls. A fresh result capture and explicit confirmation are required; the old
calibration image (or a copy of it) is rejected. This reuses the necessary filter
preflight image rather than adding another calibration image:

```powershell
.\.venv\Scripts\python.exe manage_roster_automation.py membership-filter <checkpoint> --save-profile <run-add.profile.json> --reuse-calibration <run-remove.profile.json> --screen-status all --capture <addition-filter-result.bmp> --confirm-filter-result --note "Exact pending CID/variant inspected; same view/geometry; dialog route valid under current saved filter and status" --confirm-calibration --first-only --execute --capture-after <first-addition.bmp>
```

Use `inactive` instead of `all` only when it is the verified selection. Inspect
and reconcile the first addition before reusing the new profile for the remainder.
If any coordinates or route changed, create a fresh addition profile with the
observed controls/capture instead of inheriting them. An inspected duplicate card
still uses the individual path. No membership changes means no filter profiles.
Batching may resume only while view, filter label, status categories and route
stay known; another status transition requires another filter-only check.

`--screen-status` attests the currently known state; it neither sets nor detects
it. Never claim it while a status menu is unknown or external input may have
changed it. The compiler selects only the next ordered unambiguous journal prefix;
it stops before an inspected/duplicate card. Reconcile the family, inspect that
card through the existing single-action path, then reuse calibration only if the
screen is still unchanged. Zero remaining actions mean no command/calibration.

The profile is bound to this checkpoint, manifest, operation and client geometry.
Discard/recreate it on another controller session/resume, roster/window reload,
unplanned view/filter change, geometry change, unexpected CID results or membership counts,
or external/manual UI input. Never infer a live state from a saved file. Restore
the known screen and reverify only the affected mapping; do not inspect all
previously verified cards or replay a family. Native errors still retain pending
journal actions and require observed reconciliation before more input.

Keep exact baseline and final CID/variant membership checks, aggregate pass
verification and individual ambiguous-card inspection. Emit routine sync images
only for initial calibration/baseline and the required family/pass/final aggregate
observations. Reuse one suitable inspected capture for both serialization and
reconciliation; do not add screenshots merely because commands return. For an
unexpected result, inspect the affected filter/row or use a targeted capture;
a full roster image remains required when the complete membership must be read.
The profile does not change waits or count native input as observed success.

### Observation reuse at known controls

At initial calibration record a compact ledger: current view, selected status
categories, CID-dialog open/Apply route and status-menu option points. While these
remain known, carry out the complete planned navigation transition in one
controller call or calibrated native click batch. Do not append `getAXState()`
and `getScreenshot()` to each known click or reopen the menu only to confirm its
unchanged option order. At a required read/verification boundary, use one suitable
representation (normally the screenshot for OOTP's custom UI); request the other
only if the first cannot resolve the specific field. Unknown menus/ambiguous rows
still require inspection before input.

Use each post-input family/preflight capture for its aggregate observation and
profile evidence whenever it covers those fields. Do not issue another native
capture solely for profile creation, observation-file serialization, or a second
view of an unchanged result. Keep the exact baseline, first-item capability,
required pass/family and final membership observations. A narrow exception image
is appropriate for an unresolved row/menu; it does not replace a complete
membership observation. A CID value change within the same verified status/filter can reuse geometry.
A status transition requires the filter-only check above even if geometry is
unchanged; an unexpected layout/state invalidates the affected route. Recalibrate only what changed,
preserving the original pending journal and all verified membership work.


1. Validate the manifest and load or initialize its checkpoint. Run
   `manage_roster_automation.py ui-plan <manifest> sync` instead of loading or
   printing the full manifest. The plan separates exact planned variants from
   standard cards and includes aggregate verification counts. Read `mode` before
   mutating OOTP. In `rebuild` mode, `remove` and `add` are the complete
   membership changes and `retained` cards must remain untouched.
2. Open the intended existing local roster. Verify its identity using the roster
   name and tournament rules/context; a trailing tournament number is only a
   matching hint and may change between instances. Preserve its actual local
   name, including abbreviations. For a rebuild ledger, record the exact visible
   name before membership changes (even when it matches the planner name):
   `rebuild-execution bind-save-name <checkpoint> --name "<existing OOTP name>"
   --capture <inspected-roster.bmp> --note "<identity verification>"`.
   This records a separate checkpoint binding, not a rename or save. Keep the
   planner/manifest name intact. Then open OOTP's Manage Cards screen.
3. Select the `RosterLoad` view and use the `RosterFilterCID` filter. Establish
   and retain the run-local status/CID calibration above.
4. In `rebuild` mode, process the flat `remove` list first from this same Manage
   Cards screen, then process only `add_passes`. Do not clear the active roster,
   inspect retained cards, or replay unchanged membership. Removal and addition
   both require exact CID plus variant status. Every removal opens a confirmation
   modal. Calibrate its **Proceed** button once, then use one native
   `filter-batch --confirm <proceed-point>` command for the remaining confirmed
   removal CIDs. The helper completes filter, deactivate, and confirmation as one
   transaction per CID before advancing. Never use ordinary `filter-batch` for
   multiple removals because the first modal blocks all later coordinates. In
   `full` mode, process `passes` as before.
5. Process the plan's variant pass first. Every card in it requires PT Variant
   `Y`; the optimizer has already enforced whether variants are allowed and how
   many fit, so do not make a second variant-cap decision in OOTP. Verify the
   planned variant count before continuing with the standard pass, where every
   card requires PT Variant `N`.
6. Each add pass contains `fast_batches` and `inspect`. A fast-batch card has exactly
   one physical inventory row across all versions of that CID, so its required
   variant status is unambiguous. Process all 6-8 cards in a fast batch in one
   native `windows_drag filter-batch` command: enter CID, wait for the filter,
   activate the sole row, and continue without emitting intermediate states. A successful mutation call
   and expected filter behavior are enough to checkpoint the batch; do not request
   or forward a screenshot after each fast batch.
7. Process every `inspect` card individually. Search by `cid` and scan only the
   returned rows. Among rows with the exact required variant status, prefer a copy
   already in a tournament, then a locked copy, then the first remaining copy. Do
   not repeatedly re-sort for these priorities and do not rely on exported
   physical ID. Cards from older manifests with no CID-wide copy count deliberately
   use this inspected path.
   Enter each inspected CID with `windows_drag type-text`; native OOTP text entry
   must not depend on the computer-control plugin's keyboard capabilities.
8. Refresh internally only as required for OOTP to apply the filter or activation;
   do not emit intermediate screenshots or accessibility text for successful fast
   cards.

Checkpoint once per batch, not once per card. Verify the aggregate active-roster
count after the complete variant pass when variants exist, and once after the
complete standard pass. Along with the initial Manage Cards calibration, these
are the only routine sync images. If an aggregate count is wrong, inspect only the
affected pass and use targeted screenshots for unresolved rows; do not replay a
successful earlier pass. Record no match as missing and multiple unresolved
matches as ambiguous; do not guess.

If a removal batch is interrupted, do not replay the entire `remove` list. Record
the exact confirmed CIDs in the checkpoint note, inspect only the unresolved
removal CIDs, and resume with those remaining values. A successful helper call
using `--confirm` proves each listed confirmation was clicked; an approval or
controller failure does not.

Do not reopen a successful CID merely to confirm which physical copy was used.
For an inspected CID, make one priority scan and one activation attempt. If the
result remains ambiguous, checkpoint it; do not sort separately by variant,
tournament use, and lock status or cycle through every copy.

Complete the phase only when the active roster count and hitter/pitcher totals
match the manifest and there are no unreported exceptions. A phase may be marked
failed with partial completed results so the next run resumes only missing work.
After final aggregate verification, mark it complete with `--complete-all`.
