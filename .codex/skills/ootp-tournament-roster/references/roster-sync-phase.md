# Roster Sync Phase

Use this phase to make OOTP roster membership match `roster.membership` in the
automation manifest.

1. Validate the manifest and load or initialize its checkpoint. Run
   `manage_roster_automation.py ui-plan <manifest> sync` instead of loading or
   printing the full manifest. The plan separates exact planned variants from
   standard cards and includes aggregate verification counts.
2. Open the intended local roster and OOTP's Manage Cards screen.
3. Select the `RosterLoad` view and use the `RosterFilterCID` filter.
4. Process the plan's variant pass first. Every card in it requires PT Variant
   `Y`; the optimizer has already enforced whether variants are allowed and how
   many fit, so do not make a second variant-cap decision in OOTP. Verify the
   planned variant count before continuing with the standard pass, where every
   card requires PT Variant `N`.
5. Search by `cid` and scan only the few returned rows. Among rows with the exact
   required variant status, prefer a copy already in a tournament, then a locked
   copy, then the first remaining copy. Do not repeatedly re-sort for these
   priorities and do not rely on exported physical ID. Sorting once may reduce
   scanning, but row inspection remains the correctness check.
6. Activate the chosen copy. Refresh internally only as required for OOTP to apply
   the filter or activation; do not emit intermediate screenshots or accessibility
   text for successful cards.

After each batch, emit one state and verify the aggregate active-roster count.
Checkpoint once per batch, not once per card. Use targeted screenshots only for
unresolved rows. Record no match as missing and multiple unresolved matches as
ambiguous; do not guess.

Complete the phase only when the active roster count and hitter/pitcher totals
match the manifest and there are no unreported exceptions. A phase may be marked
failed with partial completed results so the next run resumes only missing work.
After final aggregate verification, mark it complete with `--complete-all`.
