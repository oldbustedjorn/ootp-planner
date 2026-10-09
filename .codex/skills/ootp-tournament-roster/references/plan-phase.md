# Plan Phase

Use this phase to turn an OOTP tournament into a planner roster plan. A new build
also creates a blank local OOTP roster; a rebuild keeps the existing local roster.

Start `setup` metrics before service/window orientation. Complete `setup` and
start `plan` when the OOTP window and planner service are ready. Complete `plan`
only after the manifest is valid, the named blank roster exists, and the
checkpoint is initialized. Start `sync` in that same transition command.

1. Before opening or editing the planner form, run
   `manage_roster_automation.py service-check`. If it fails, identify the process
   listening on port 8765 once. Restart it only when its command line confirms it
   is this repository's `launch_gui.py`, then rerun the check once. Do not repeat
   process-discovery commands, launch multiple competing servers, or spend more
   than one bounded recovery attempt on service startup. Do not submit a
   build until the check passes; this prevents building once with stale code and
   rebuilding after detecting an old manifest.
2. Turn auto-refresh off if it is not already off. If the user says it is off,
   accept that state without rechecking it. Otherwise use the initial tournament
   image to locate the control, open it once, select **Off/None**, and verify it
   only in the tournament-rules image. Allow one corrected click if the first
   coordinate was wrong. Do not repeatedly reopen, inspect, or map the refresh
   menu, and do not take a dedicated screenshot solely for auto-refresh.
3. Read the named tournament's visible rules and settings once. Expand only the
   relevant tournament and gather its roster shape and restrictions. Treat the
   captured tournament information as immutable for the rest of the run.
   Map **No LE** or **No Limited Edition** to the planner's **Limited Edition
   (LE)** excluded-card-subtype checkbox. Limited Edition is subtype `LE`; do not
   treat it as a card type or infer it from the card title.
4. Create a new planner roster plan with those settings. Select **Full optimizer**.
   Preserve user-entered park factors and other explicit planner settings.
5. Build the roster. A successful optimizer build writes
   `outputs/<report-name>.automation.json` beside the HTML report.
6. Validate that manifest with `manage_roster_automation.py validate`, then run
   `manage_roster_automation.py ui-plan <manifest> sync
   --require-cid-copy-counts`. Do this before creating the blank OOTP roster. If
   the inventory-count check fails for a newly generated manifest, stop and report
   the contract violation. Do not rebuild automatically because the service passed
   its preflight before the build.
7. Read the sync plan's `mode`. For `full`, create a blank local roster in OOTP
   using the manifest's roster name. Enter the name with `windows_drag type-text`;
   do not depend on the computer-control plugin exposing native desktop typing.
   For `rebuild`, open the existing local roster and require a rebuild delta with
   the preceding manifest ID. Do not create a blank roster or clear the existing
   roster. If an expected rebuild has no delta, stop rather than silently running
   it as a full build. Do not enter or submit the tournament.
8. Initialize the checkpoint. The `plan` phase will be complete and later phases
   pending.

If the tournament rules are unclear, record the ambiguity before building. If the
planner rejects a setting, preserve the form and correct only that field.

Do not return to the tournament screen for confirmation after the settings have
been captured. Completion requires a valid manifest, the intended named OOTP
roster, and a checkpoint.
