# Roster Sync Phase

Use this phase to make OOTP roster membership match `roster.membership` in the
automation manifest.

1. Validate the manifest and load or initialize its checkpoint. Run
   `manage_roster_automation.py actions <manifest> sync` instead of loading or
   printing the full manifest.
2. Open the intended local roster and OOTP's Manage Cards screen.
3. Select the `RosterLoad` view and use the `RosterFilterCID` filter.
4. Process membership in batches of roughly 6-8 cards. Search by `cid`, then
   require the manifest's `variant` value to match OOTP's PT Variant value. Keep
   each batch in one computer-control call when the screen geometry remains stable.
5. If several physical copies match, prefer a copy already in a tournament, then
   a locked copy, then any remaining copy. Do not rely on exported physical ID.
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
