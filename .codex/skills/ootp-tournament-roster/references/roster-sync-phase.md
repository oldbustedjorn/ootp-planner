# Roster Sync Phase

Use this phase to make OOTP roster membership match `roster.membership` in the
automation manifest.

1. Validate the manifest and load or initialize its checkpoint.
2. Open the intended local roster and OOTP's Manage Cards screen.
3. Select the `RosterLoad` view and use the `RosterFilterCID` filter.
4. Process membership in batches. Search by `cid`, then require the manifest's
   `variant` value to match OOTP's PT Variant value.
5. If several physical copies match, prefer a copy already in a tournament, then
   a locked copy, then any remaining copy. Do not rely on exported physical ID.
6. Activate the chosen copy. Record the manifest `candidate_id` as completed.

After each batch, verify aggregate active-roster counts. Use targeted screenshots
only for unresolved rows. Record no match as missing and multiple unresolved
matches as ambiguous; do not guess.

Complete the phase only when the active roster count and hitter/pitcher totals
match the manifest and there are no unreported exceptions. A phase may be marked
failed with partial completed results so the next run resumes only missing work.
