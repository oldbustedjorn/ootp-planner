# Roster Sync Phase

Use this phase to make OOTP roster membership match `roster.membership` in the
automation manifest.

The `sync` metric starts at the plan-to-sync transition. Complete it only after
aggregate membership verification and start `rotation` in the same command.

Use the native helper for text entry and fast batches; do not inspect its source
or replace it with one computer-control call per card:

```powershell
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag type-text --at X,Y --text "CID"
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag filter-batch --field X,Y --activate X,Y --value CID1 --value CID2 --capture-after <path.bmp>
```

1. Validate the manifest and load or initialize its checkpoint. Run
   `manage_roster_automation.py ui-plan <manifest> sync` instead of loading or
   printing the full manifest. The plan separates exact planned variants from
   standard cards and includes aggregate verification counts. Read `mode` before
   mutating OOTP. In `rebuild` mode, `remove` and `add` are the complete
   membership changes and `retained` cards must remain untouched.
2. Open the intended local roster and OOTP's Manage Cards screen.
3. Select the `RosterLoad` view and use the `RosterFilterCID` filter.
4. In `rebuild` mode, process the flat `remove` list first from this same Manage
   Cards screen, then process only `add_passes`. Do not clear the active roster,
   inspect retained cards, or replay unchanged membership. Removal and addition
   both require exact CID plus variant status. In `full` mode, process `passes` as
   before.
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

Do not reopen a successful CID merely to confirm which physical copy was used.
For an inspected CID, make one priority scan and one activation attempt. If the
result remains ambiguous, checkpoint it; do not sort separately by variant,
tournament use, and lock status or cycle through every copy.

Complete the phase only when the active roster count and hitter/pitcher totals
match the manifest and there are no unreported exceptions. A phase may be marked
failed with partial completed results so the next run resumes only missing work.
After final aggregate verification, mark it complete with `--complete-all`.
