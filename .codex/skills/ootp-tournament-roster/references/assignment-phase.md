# Assignment Phase

Use this phase after roster membership matches the manifest.

1. Run `manage_roster_automation.py ui-plan <manifest> pitching`. Capture the
   visible pitcher source rows once, map each planned name to its source-row
   coordinate, and configure rotation order, bullpen roles, usage, and secondary
   roles in one computer-control call. OOTP may reorder bullpen rows after role
   changes, so set row-dependent menus in an order that accounts for that behavior
   and verify pitching once afterward.
2. Run `manage_roster_automation.py ui-plan <manifest> vs_rhp`. Capture the
   visible hitter source rows once and build one name-to-source-row map. Use it to
   configure starters, batting order, depth, and pinch lists in one call, retaining
   350-450 ms between drops. Verify the complete RHP section once.
3. Run the corresponding `vs_lhp` plan. Reuse the source-row map only if the
   source list is visibly unchanged; otherwise capture it once again. Execute and
   verify the complete LHP section once.
4. Save the local roster. Do not submit or enter the tournament.

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
