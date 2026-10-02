# Assignment Phase

Use this phase after roster membership matches the manifest.

1. Load `pitching.rotation` and `pitching.bullpen`. Configure rotation order,
   primary role, usage, and secondary role exactly as represented.
2. Configure `lineups.vs_rhp.starters` as one batch, then verify the entire lineup.
3. Configure its `depth` entries and `bench_actions.vs_rhp` pinch lists, then
   verify the section.
4. Repeat for `vs_lhp`.
5. Save the local roster. Do not submit or enter the tournament.

Use names only to locate already-synchronized roster members; CID and variant in
the manifest remain the identity source of truth. If OOTP does not expose a
planned player at the expected role or position, do not improvise. Record the
candidate ID, expected assignment, and observed limitation, then continue with
independent assignments.

Capture one verification view per completed section rather than after each drag.
Retry only blank or mismatched rows. Mark the phase complete only after pitching,
both lineups, depth charts, and pinch lists have been checked and the roster saved.
