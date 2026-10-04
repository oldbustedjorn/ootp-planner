# Assignment Phase

Use this phase after roster membership matches the manifest.

1. Run `manage_roster_automation.py ui-plan <manifest> pitching`. Capture the
   visible pitcher source rows once, map each planned name to its source-row
   coordinate, and configure rotation order, bullpen roles, usage, and secondary
   roles in one computer-control call. OOTP may reorder bullpen rows after role
   changes, so set row-dependent menus in an order that accounts for that behavior
   and verify pitching once afterward.
2. Open **Lineups**, immediately select **VS RHP**, and do not assign players on
   the default lineup screen. Run `manage_roster_automation.py ui-plan <manifest>
   vs_rhp`, capture the visible hitter source rows once, and build one
   name-to-source-row map.
3. Process `starter_sequence` in ascending batting-order order. For each starter,
   drag the player directly to the planned fielding-position slot. OOTP adds each
   player to the batting order in that insertion order. Do not perform a separate
   batting-order drag pass and do not place any depth or pinch entries until every
   starter and batting position is stable. Start every drag in the source row's
   non-text left gutter, approximately 7.5-8% of the current client width, rather
   than on the player name; name-region drags can open a player profile or tooltip.
4. Add all `depth` entries, then pinch hitters, then pinch runners. Retain 350-450
   ms between drops and verify the complete RHP section once.
5. Select **VS LHP** and run the corresponding plan. Reuse the source-row map only
   if the source list is visibly unchanged. Repeat the same strict sequence:
   starters to positions in batting order, depth, pinch hitters, pinch runners,
   then one verification. Never copy or mutate the RHP lineup into the LHP lineup.
6. Save the local roster. Do not submit or enter the tournament.

Use names only to locate already-synchronized roster members; CID and variant in
the manifest remain the identity source of truth. If OOTP does not expose a
planned player at the expected role or position, do not improvise. Record the
candidate ID, expected assignment, and observed limitation, then continue with
independent assignments.

Group fixed-coordinate actions into one computer-control call per logical section.
Use 350-450 ms drop waits and suppress intermediate state output. Capture one
verification view after pitching, after the complete RHP section, and after the
complete LHP section. Retry only blank or mismatched rows. Mark the phase complete
with `--complete-all` only after pitching, both lineups, depth charts, and pinch
lists have been checked and the roster saved.
