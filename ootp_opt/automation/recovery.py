"""Read-only status correction plans and checkpoint-derived resume instructions."""
from pathlib import Path

from ootp_opt.automation.checkpoint import PHASES, load_checkpoint
from ootp_opt.automation.execution import execution_status


STATUS_CATEGORIES = ("active", "reserve", "inactive")


def status_selection(observed: str, desired: str) -> dict:
    """Caller supplies all checked categories from an inspected menu, not its caption."""
    checked = [part.strip().lower() for part in observed.split(",")]
    if checked == ["none"]:
        checked = []
    if len(checked) != len(set(checked)) or set(checked) - set(STATUS_CATEGORIES):
        raise ValueError("Observed status must list checked active,reserve,inactive categories, or none")
    if desired not in ("active", "inactive", "all"):
        raise ValueError("Desired status must be active, inactive or all")
    wanted = set(STATUS_CATEGORIES) if desired == "all" else {desired}
    actual = set(checked)
    return {
        "turn_on": [k for k in STATUS_CATEGORIES if k in wanted - actual],
        "turn_off": [k for k in STATUS_CATEGORIES if k in actual - wanted],
        "leave_on": [k for k in STATUS_CATEGORIES if k in wanted & actual],
        "desired_checked": [k for k in STATUS_CATEGORIES if k in wanted],
    }


def resume_prompt(path: str | Path) -> str:
    checkpoint = load_checkpoint(path)
    phases = checkpoint["phases"]
    execution = checkpoint.get("execution")
    status = execution_status(path) if execution else None
    complete = (status["state"] == "complete" if status else all(
        record["status"] == "complete" and not record["missing"] and not record["ambiguous"]
        for record in phases.values()
    ))
    if complete:
        count = f" ({status['completed']}/{status['total']} actions)" if status else ""
        return f"Checkpoint is complete{count}: {Path(path).resolve()}\nNo resume work remains; do not replay actions or start another rebuild.\n"
    lines = [
        f"OOTP resume: {Path(path).resolve()}", "",
        "Use the current ootp-tournament-roster skill. First read this checkpoint's status;",
        "prefer its current state over this snapshot and all earlier chat instructions.",
        f"Snapshot updated at: {checkpoint['updated_at']}. Manifest: {checkpoint['manifest_path']}.",
        "Do not reuse old remaining-card lists, counts or assumptions about the filtered card.",
    ]
    if status:
        lines.append(f"Snapshot: {status['completed']}/{status['total']} verified; "
                     f"{len(status['unverified'])} unverified; in flight: {status['in_flight'] or 'none'}.")
        if status["unverified"] or status["in_flight"]:
            lines.append("Observe and reconcile the existing pending actions before any new input; never replay the batch.")
        index = len(execution["completed"])
        if index < len(execution["actions"]):
            action = execution["actions"][index]
            lines.append(f"First unfinished action: {action['id']} {action['operation']} {action['target']}.")
            if action["operation"] == "save":
                lines.append("Save verification is next. Reconcile existing confirmed save evidence before clicking Save again.")
        if status["state"] == "needs_baseline":
            if execution["completed"]:
                lines.append("Reconcile exact current CID/variant membership at journal progress; do not restore the original baseline or make unplanned changes.")
            else:
                lines.append("Verify exact live baseline CID/variant membership before mutation; report actual drift without unplanned changes.")
    first = next((p for p in PHASES if phases[p]["status"] != "complete"
                  or phases[p]["missing"] or phases[p]["ambiguous"]), None)
    if first == "assign":
        lines.append("Plan and membership sync are complete. Skip optimizer generation, planner setup and membership actions; resume assignments/save.")
    elif first == "sync":
        lines.append("The plan is complete. Continue only unfinished membership work, then assignments/save; do not regenerate the plan.")
    else:
        lines.append("Continue the first incomplete phase from the checkpoint; preserve the existing plan and roster.")
    if any(r["missing"] or r["ambiguous"] for r in phases.values()):
        lines.append("Resolve recorded missing/ambiguous items from observed facts before further mutation; do not clear them just to advance.")
    if first == "sync":
        lines.extend([
            "Correct known read-only status checkbox selections in this turn, then perform the required filter-only preflight.",
            "Retain individual inspected additions after a filter failure; inspect each exact CID/variant before activation.",
        ])
    lines.extend([
        "For a controller failure confirmed to have sent no input, use the skill's one bounded rebind in the same controller.",
        "If input may have occurred, preserve pending actions and reconcile before more input; do not replay it.",
        "Preserve completed work and the existing local save name. Finish verification, local save, checkpoint and metrics.",
        "Do not create a duplicate plan/roster, enter or submit a tournament.",
    ])
    return "\n".join(lines) + "\n"
