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
5. Each pass contains `fast_batches` and `inspect`. A fast-batch card has exactly
   one physical inventory row across all versions of that CID, so its required
   variant status is unambiguous. Process all 6-8 cards in a fast batch in one
   computer-control call: enter CID, wait for the filter, activate the sole row,
   and continue without emitting intermediate states. Emit one state afterward
   and verify that the active-roster count increased by the batch size.
6. Process every `inspect` card individually. Search by `cid` and scan the few
   returned rows. Among rows with the exact required variant status, prefer a copy
   already in a tournament, then a locked copy, then the first remaining copy. Do
   not repeatedly re-sort for these priorities and do not rely on exported
   physical ID. Cards from older manifests with no CID-wide copy count deliberately
   use this inspected path.
7. Refresh internally only as required for OOTP to apply the filter or activation;
   do not emit intermediate screenshots or accessibility text for successful fast
   cards.

After each batch, emit one state and verify the aggregate active-roster count.
Checkpoint once per batch, not once per card. Use targeted screenshots only for
unresolved rows. Record no match as missing and multiple unresolved matches as
ambiguous; do not guess.

Complete the phase only when the active roster count and hitter/pitcher totals
match the manifest and there are no unreported exceptions. A phase may be marked
failed with partial completed results so the next run resumes only missing work.
After final aggregate verification, mark it complete with `--complete-all`.
