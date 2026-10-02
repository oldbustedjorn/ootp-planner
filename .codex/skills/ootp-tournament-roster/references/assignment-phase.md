# Assignment Phase

Use this phase after roster membership matches the manifest.

1. Run `manage_roster_automation.py actions <manifest> pitching`. Configure
   rotation order, primary role, usage, and secondary role in one section batch,
   then verify pitching once.
2. Run `manage_roster_automation.py actions <manifest> vs_rhp`. Configure the RHP
   starters as one batch, then verify the entire lineup.
3. Configure its `depth` entries and `bench_actions.vs_rhp` pinch lists, then
   verify the section.
4. Run the corresponding `vs_lhp` action view and repeat for LHP.
5. Save the local roster. Do not submit or enter the tournament.

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
