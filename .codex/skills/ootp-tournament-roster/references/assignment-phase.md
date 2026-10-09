# Assignment Phase

Use this phase after roster membership matches the manifest. Mark `assign`
`in_progress` before the first pitching action. Complete the sections strictly in
this order: `pitching`, `vs_rhp`, `vs_lhp`. Do not leave an incomplete section to
work on a later one.

Metric boundaries follow the same order. At each verified transition, complete
the current metric and start the next one in the same shell call. Start `rotation`
when opening pitching assignments; after the rotation is verified, complete it
and start `bullpen`. Complete `bullpen` before opening VS RHP. After LHP
verification, complete `vs_lhp` and start `save`. Complete `save` only after OOTP
confirms the local save and the checkpoint shows every phase complete. Generate
the metrics report in the following tool call, not in the save-marker call.

Use the repository's deterministic native helper for all assignment input. Run it
outside the command sandbox because Windows blocks sandboxed GUI input. Coordinates
are relative to the current captured OOTP client area:

```powershell
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag capture <path.bmp>
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag drag --from X,Y --to X,Y --hold-ms 400 --move-ms 1000 --settle-ms 300 --steps 30
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag batch --move X1,Y1:X2,Y2 --move X3,Y3:X4,Y4 --hold-ms 400 --move-ms 1000 --settle-ms 300 --steps 30 --post-drop-ms 450 --capture-after <path.bmp>
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag click-batch --at X1,Y1 --at X2,Y2 --post-click-ms 300 --capture-after <path.bmp>
.\.venv\Scripts\python.exe -m ootp_opt.automation.windows_drag type-text --at X,Y --text "roster name"
```

Use `drag` for the first capability preflight or one isolated repair, `batch` for
two or more stable assignments, and `click-batch` after one menu calibration. The
helper owns all fixed waits. Do not add caller-side sleeps, wrap individual drags
in a subprocess loop, or inspect helper source during a routine run.

1. Run `manage_roster_automation.py ui-plan <manifest> pitching` and follow its
   `execution.required_sequence`. In `rebuild` mode, assign only the listed
   rotation and bullpen changes and preserve the reported unchanged assignments.
   Configure rotation size only when `rotation_size_changed` is true; a full build
   configures it from `execution.rotation_size` before attempting any pitcher drag.
   An empty rotation or bullpen list means no work or calibration for that family;
   follow the rebuild plan's shortened `required_sequence`.
   Map every pitcher
   in the stable upper pitcher list. Use the visible player-name text there as the
   default source for every rotation assignment. OOTP reorders the lower rotation
   and bullpen rows as assignments are made, so never batch from cached lower-row
   coordinates. A freshly remapped lower-pane player name is a single-item fallback
   only. Use `ootp_opt.automation.windows_drag` with the
   timing above. Run the first planned starter as the
   drag-capability preflight, drop into rotation slot 1, and confirm that the
   intended slot changed. If both source-family attempts fail, checkpoint the exact target and pause in
   place without claiming a pitching repair batch. After success, configure the
   remaining rotation in one computer-control call, then verify the complete
   rotation before opening any bullpen menu. If a starter is missing, remap the
   stable upper pitcher list before using a lower-name fallback. Claim exact
   targets with `repair-attempt
   <checkpoint> pitching --item <target> --strategy <strategy>` (repeat `--item`
   for independent mismatches), repair them together, and verify once. Only after
   the rotation is stable, use one calibration image to open one representative
   primary-role menu, one usage menu, and one secondary-role menu. Record their
   option order and vertical offsets in a run-local geometry ledger; that mapping
   remains authoritative while the client geometry is unchanged. Close the last
   open menu, then assign all known dropdown selections with native
   `windows_drag click-batch` calls. Each dropdown selection is an adjacent pair:
   open the row's dropdown, then click the cached option offset. Do not refresh
   state between those two clicks or between rows. OOTP may reorder bullpen rows
   after primary-role changes, so apply primary roles in an order that preserves
   the remaining row map. If a role change actually reorders rows, take at most
   one remap image after the primary-role batch; reuse the cached menu option
   offsets and complete usage/secondary selections without reopening menus for
   inspection. Verify pitching once. Pitching must be complete before
   opening **Lineups**.
2. Open **Lineups**, immediately select **VS RHP**, and do not assign players on
   the default lineup screen. Run `manage_roster_automation.py ui-plan <manifest>
   vs_rhp`, capture the visible hitter rows once, and build one name-to-source-row
   map. Every source coordinate must be inside the visible player-name text, never
   the position marker, rating columns, whitespace, or general row midpoint.
3. Follow `execution.required_sequence`. Drag the first starter from the center of
   the upper row's visible player-name text to the planned fielding-position slot
   using the held-drag helper. Refresh
   once and require both the player's name and position to appear in the lineup.
   If it fails, try once from the right half of the same player-name text. If both attempts fail,
   checkpoint the blocked split and pause immediately. Give the user one complete
   table covering every remaining RHP and LHP starter, depth entry, pinch hitter,
   and pinch runner; do not make them resume once per family. Do not begin a
   context-menu lineup build after a failed drag preflight.
4. After a successful preflight, drag the remaining starters directly to their
   planned fielding-position slots in batting-order order. OOTP adds them to the
   lineup in insertion order. Add all depth entries, then pinch hitters, then
   pinch runners, in one native `windows_drag batch` invocation per family. Never
   spawn one helper process per drag. Use the helper's 400 ms hold, 1000 ms
   movement, 300 ms settle, 30 movement steps, and 450 ms post-drop verification
   delay, which the helper applies internally. Do not add a caller-side sleep.
   Use `--capture-after` on the final batch for aggregate verification. Verify
   the complete RHP section once. A right-click assignment menu is permitted only
   for one isolated mismatch after direct dragging has succeeded on this screen.
   If more than one mismatch remains, checkpoint and hand off the full remaining
   checklist instead of starting a menu-driven repair loop.
   In `rebuild` mode, never use **Clear Lineup** or **Clear Depth**. Complete every
   listed starter-position replacement and backup-depth change in the depth-chart
   area first. Then, only when `batting_order_strategy` is
   `reorder_after_depth_chart_updates`, apply the complete `batting_order` list to
   the lineup rows. Finally update only the listed pinch slots. Leave every other
   assignment untouched. Empty lists mean no work for that family and require no
   calibration or screenshot.
5. Select **VS LHP** only after RHP is complete and run the corresponding plan.
   Reuse source-row and target geometry only if the controls and row geometry
   are visibly unchanged; otherwise recalibrate only the changed family. Repeat
   the same strict sequence: direct-drag starters to positions in batting order,
   depth, pinch hitters, the 800 ms family transition, pinch runners, then one
   verification. If discrepancies
   remain, claim only their exact
   targets with `repair-attempt <checkpoint> vs_lhp --item <target> --strategy
   <strategy>`, repair those entries with a distinct source or inward target, and
   verify once. Never copy or mutate the RHP lineup into the LHP lineup.
6. Save the local roster once. Perform one targeted confirmation check. Do not
   click save a second time unless that check clearly shows the roster remains
   unsaved. Do not submit or enter the tournament.

Use names only to locate already-synchronized roster members; CID and variant in
the manifest remain the identity source of truth. If OOTP does not expose a
planned player at the expected role or position, do not improvise. Record the
candidate ID, expected assignment, and observed limitation, then continue with
independent assignments.

Use `windows_drag capture` plus `view_image` for assignment geometry and aggregate
verification. Reserve computer-control screenshots for menus and controls that
must be operated through computer control. Group fixed-coordinate actions into
one command per logical section. Use 450 ms drop waits and suppress intermediate
state output. Capture one
verification view after pitching, after the complete RHP section, and after the
complete LHP section. Retry only blank or mismatched rows. Mark the phase complete
with `--complete-all` only after pitching, both lineups, depth charts, and pinch
lists have been checked and the roster saved.

On each lineup split, the initial calibration image and final aggregate image are
the only routine visual reads. Do not pause to inspect the screen between starter,
depth, pinch-hitter, and pinch-runner batches when commands succeed. Pitching may
use one initial image, one post-rotation image before bullpen menus, and one final
image. Exceed these limits only for a specific observed mismatch.

Assignment execution must use the held-drag helper's native batch mode, not a loop
that starts one helper process per item. The helper owns all fixed timing.
Do not call `get_window_state`, screenshots, `ck`, or any equivalent observation
or click-verification helper inside a starter, depth, pinch, rotation, or bullpen
loop. Calibration checks occur between target-family batches, never inside them.
Do not use separate computer-control calls titled "map menu" for individual
bullpen rows. A successful pitching section has one menu-calibration decision,
at most one row-remap decision if OOTP demonstrably reordered the bullpen, and
one final aggregate verification decision.
If aggregate verification finds discrepancies, use the checkpoint repair gate and
repair all independent confirmed mismatches together in one batch. A section may
use at most three repair batches, and an exact target may be attempted at most
twice with distinct strategies. Merely changing a few pixels on the same source
row is not a distinct strategy. Verify once after each batch. If only one slot is
missing, repair only that slot. If it remains blocked, update the checkpoint and
pause with OOTP left on that assignment screen so the user can correct it and
resume. Do not save, exit, rename, or otherwise add navigation work unless the user
requests it or the application is about to close. Stop when the gate rejects the
same target or the section batch limit is reached rather than beginning another
general repair cycle.

Never use the coordinate repair gate to diagnose whether an assignment method
works at all. Repairs address one isolated mismatch only after a successful
preflight proved the current screen's method. If a drag opens a player profile,
return to the assignment screen and use the one allowed alternate source zone.
If that also fails, record the unassigned targets and pause rather than replaying
the batch or switching the whole section to context menus.
