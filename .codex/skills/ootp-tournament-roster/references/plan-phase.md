# Plan Phase

Use this phase to turn an OOTP tournament into a planner roster plan and a blank
local OOTP roster.

1. Read the named tournament's visible rules and settings in OOTP. Expand only
   the relevant tournament and gather its roster shape and restrictions.
2. Create a new planner roster plan with those settings. Select **Full optimizer**.
   Preserve user-entered park factors and other explicit planner settings.
3. Build the roster. A successful optimizer build writes
   `outputs/<report-name>.automation.json` beside the HTML report.
4. Validate that manifest with `manage_roster_automation.py validate`.
5. Create a blank local roster in OOTP using the manifest's roster name. Do not
   enter or submit the tournament.
6. Initialize the checkpoint. The `plan` phase will be complete and later phases
   pending.

If the tournament rules are unclear, record the ambiguity before building. If the
planner rejects a setting, preserve the form and correct only that field.

Completion requires a valid manifest, a blank named OOTP roster, and a checkpoint.
