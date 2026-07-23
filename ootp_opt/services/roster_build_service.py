from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Literal

from ootp_opt.config import load_config
from ootp_opt.domain.simulation_context import SimulationContext
from ootp_opt.domain.scoring_environment import ScoringEnvironment
from ootp_opt.optimization.candidate_matrices import CandidateMatrices
from ootp_opt.optimization.roster_optimizer import (
    OptimizationSolution,
    OptimizerSettings,
    solve_roster_optimization,
)
from ootp_opt.optimization.solution_adapter import convert_optimization_solution
from ootp_opt.optimization.solver_input import SolverInput
from ootp_opt.roster.builder import (
    build_hitter_roster,
    build_pitcher_roster,
    get_player_covered_positions,
    selected_hitter_roster_keys,
    validate_no_duplicate_players,
)
from ootp_opt.roster.cap_repair import (
    CapRepairResult,
    print_cap_repair_result,
    repair_roster_to_cap,
)
from ootp_opt.roster.cap_report import print_cap_report
from ootp_opt.roster.html_export import export_roster_html
from ootp_opt.roster.lineup import (
    build_lineup_depth_rows,
    build_pinch_hitters,
    build_pinch_runners,
    format_lineup_depth_rows,
)
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.roster_snapshot import (
    build_roster_snapshot,
    compare_snapshots,
    load_snapshot,
    snapshot_path_for_html,
    write_snapshot,
)
from ootp_opt.roster.rules import (
    Ruleset,
    build_ruleset_from_base_profile,
    build_ruleset_from_tournament_preset,
)
from ootp_opt.roster.slots import coverage_summary
from ootp_opt.roster.tier_slot_repair import (
    TierSlotRepairResult,
    print_tier_slot_repair_result,
    repair_roster_to_tier_slots,
)
from ootp_opt.roster.tier_slot_report import print_tier_slot_report
from ootp_opt.roster.variant_repair import (
    VariantRepairResult,
    print_variant_repair_result,
    repair_roster_to_variant_limit,
)
from ootp_opt.roster.variant_report import print_variant_report
from ootp_opt.services.build_timing import BuildTimer, BuildTiming
from ootp_opt.services.candidate_service import (
    BuildContext,
    CandidatePool,
    build_candidate_pool,
    resolve_build_context,
)
from ootp_opt.services.rating_service import rate_cards_service

BuildMethod = Literal["greedy", "optimizer"]
BUILD_METHODS = {"greedy", "optimizer"}


@dataclass(frozen=True)
class RosterBuildRequest:
    config_path: str = "config.toml"
    base_profile: str | None = None
    preset: str | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    html_output: str | None = None
    debug: bool = False
    build_method: BuildMethod | None = None


@dataclass(frozen=True)
class RosterBuildResult:
    config: dict[str, Any]
    context: BuildContext
    candidate_pool: CandidatePool
    candidate_matrices: CandidateMatrices
    solver_input: SolverInput
    ruleset: Ruleset
    simulation_context: SimulationContext
    scoring_environment: ScoringEnvironment
    hitter_roster: HitterRoster
    pitcher_roster: PitcherRoster
    eligibility_summary: dict[str, str]
    html_output: str
    snapshot_path: str
    report_sections: list[tuple[str, str]]
    build_timing: BuildTiming
    build_method: BuildMethod
    optimization_solution: OptimizationSolution | None = None
    variant_repair_result: VariantRepairResult | None = None
    tier_slot_repair_result: TierSlotRepairResult | None = None
    cap_repair_result: CapRepairResult | None = None


def build_roster(request: RosterBuildRequest) -> RosterBuildResult:
    timer = BuildTimer()
    cfg = load_config(request.config_path)
    build_method = resolve_build_method(cfg, request)
    ruleset = build_ruleset(cfg, request)
    context = resolve_build_context(cfg, ruleset)
    report_sections: list[tuple[str, str]] = []

    add_text_section(
        report_sections,
        "BUILD RULESET",
        f"Build method: {build_method}\n{format_ruleset_summary(ruleset)}",
    )

    scoring_environment = context.scoring_environment
    add_text_section(
        report_sections,
        "SCORING ENVIRONMENT",
        format_scoring_environment_summary(scoring_environment),
    )

    simulation_context = context.simulation_context
    add_text_section(
        report_sections,
        "SIMULATION CONTEXT",
        format_simulation_context_summary(simulation_context),
    )
    timer.checkpoint("Configuration and contexts")

    hitters_df = rate_cards_service(
        input_path=cfg["paths"]["hitters_csv"],
        profile="hitters",
        config=context.scoring_config,
    )
    timer.checkpoint("Hitter ingest and scoring")
    pitchers_df = rate_cards_service(
        input_path=cfg["paths"]["pitchers_csv"],
        profile="pitchers",
        config=context.scoring_config,
    )
    timer.checkpoint("Pitcher ingest and scoring")

    if request.debug:
        add_text_section(
            report_sections,
            "INPUT FILES",
            "\n".join(
                [
                    f"Hitters CSV:  {cfg['paths']['hitters_csv']}",
                    f"Pitchers CSV: {cfg['paths']['pitchers_csv']}",
                ]
            ),
        )
        add_text_section(
            report_sections,
            "RAW DATA CHECK",
            format_raw_data_check(hitters_df, pitchers_df),
        )
        timer.checkpoint("Debug input diagnostics")

    candidate_pool = build_candidate_pool(
        source="owned",
        context=context,
        scored_hitters=hitters_df,
        scored_pitchers=pitchers_df,
    )
    eligible_hitters = candidate_pool.eligible_hitters
    eligible_pitchers = candidate_pool.eligible_pitchers

    eligibility_summary = {
        "Build method": build_method,
        "Hitters scored": str(len(hitters_df)),
        "Hitters eligible": str(len(eligible_hitters)),
        "Pitchers scored": str(len(pitchers_df)),
        "Pitchers eligible": str(len(eligible_pitchers)),
    }
    add_text_section(
        report_sections,
        "ELIGIBILITY SUMMARY",
        "\n".join(
            [
                f"Hitters scored:   {len(hitters_df)}",
                f"Hitters eligible: {len(eligible_hitters)}",
                f"Pitchers scored:   {len(pitchers_df)}",
                f"Pitchers eligible: {len(eligible_pitchers)}",
            ]
        ),
    )
    timer.checkpoint("Eligibility filtering")

    candidate_pool.require_eligible_cards()
    candidate_matrices = candidate_pool.build_matrices()
    solver_input = candidate_pool.build_solver_input(candidate_matrices)
    optimizer_summary = [
        *candidate_matrices.summary_rows(),
        *solver_input.summary_rows(),
    ]
    eligibility_summary.update(dict(optimizer_summary))
    add_text_section(
        report_sections,
        "OPTIMIZER INPUT",
        "\n".join(f"{label}: {value}" for label, value in optimizer_summary),
    )
    timer.checkpoint("Optimizer input construction")

    optimization_solution = None
    if build_method == "optimizer":
        optimization_solution = solve_roster_optimization(
            solver_input,
            OptimizerSettings(),
        )
        if not optimization_solution.is_feasible:
            raise ValueError(
                "Roster optimizer did not find a feasible solution: "
                f"{optimization_solution.status}."
            )
        converted = convert_optimization_solution(
            solution=optimization_solution,
            solver_input=solver_input,
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
        )
        hitter_roster = converted.hitter_roster
        pitcher_roster = converted.pitcher_roster
        optimizer_result_rows = optimization_solution_summary_rows(
            optimization_solution
        )
        eligibility_summary.update(dict(optimizer_result_rows))
        add_text_section(
            report_sections,
            "OPTIMIZER RESULT",
            "\n".join(f"{label}: {value}" for label, value in optimizer_result_rows),
        )
        timer.checkpoint("Optimizer solve and conversion")
    else:
        hitter_roster = build_hitter_roster(eligible_hitters, ruleset)
        pitcher_roster = build_pitcher_roster(
            eligible_pitchers,
            ruleset,
            used_player_names=selected_hitter_roster_keys(hitter_roster),
        )
        timer.checkpoint("Initial roster selection")

    validate_no_duplicate_players(hitter_roster, pitcher_roster)

    add_captured_section(
        report_sections,
        "VARIANT REPORT",
        print_variant_report,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        variant_limit=ruleset.variant_limit,
    )

    if ruleset.tier_slots:
        add_captured_section(
            report_sections,
            "TIER SLOT REPORT",
            print_tier_slot_report,
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            tier_slots=ruleset.tier_slots,
        )
    timer.checkpoint("Initial constraint diagnostics")

    variant_result = None
    if build_method == "greedy" and ruleset.variant_limit is not None:
        variant_result = repair_roster_to_variant_limit(
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
            ruleset=ruleset,
        )
        add_captured_section(
            report_sections,
            "VARIANT REPAIR",
            print_variant_repair_result,
            variant_result,
        )
        hitter_roster = variant_result.hitter_roster
        pitcher_roster = variant_result.pitcher_roster
        validate_no_duplicate_players(hitter_roster, pitcher_roster)
        add_captured_section(
            report_sections,
            "VARIANT REPORT AFTER REPAIR",
            print_variant_report,
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            variant_limit=ruleset.variant_limit,
        )
    timer.checkpoint("Variant repair")

    tier_slot_result = None
    if build_method == "greedy" and ruleset.tier_slots:
        tier_slot_result = repair_roster_to_tier_slots(
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
            ruleset=ruleset,
        )
        add_captured_section(
            report_sections,
            "TIER SLOT REPAIR",
            print_tier_slot_repair_result,
            tier_slot_result,
        )
        hitter_roster = tier_slot_result.hitter_roster
        pitcher_roster = tier_slot_result.pitcher_roster
        validate_no_duplicate_players(hitter_roster, pitcher_roster)
        add_captured_section(
            report_sections,
            "TIER SLOT REPORT AFTER REPAIR",
            print_tier_slot_report,
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            tier_slots=ruleset.tier_slots,
        )
    timer.checkpoint("Tier slot repair")

    add_captured_section(
        report_sections,
        "CAP REPORT",
        print_cap_report,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        point_cap_total=ruleset.point_cap_total,
    )

    cap_result = None
    if build_method == "greedy" and ruleset.point_cap_total is not None:
        cap_result = repair_roster_to_cap(
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            eligible_hitters=eligible_hitters,
            eligible_pitchers=eligible_pitchers,
            ruleset=ruleset,
        )
        add_captured_section(
            report_sections,
            "CAP REPAIR",
            print_cap_repair_result,
            cap_result,
        )
        hitter_roster = cap_result.hitter_roster
        pitcher_roster = cap_result.pitcher_roster
        validate_no_duplicate_players(hitter_roster, pitcher_roster)
        add_captured_section(
            report_sections,
            "CAP REPORT AFTER REPAIR",
            print_cap_report,
            hitter_roster=hitter_roster,
            pitcher_roster=pitcher_roster,
            point_cap_total=ruleset.point_cap_total,
        )

        if ruleset.tier_slots:
            add_captured_section(
                report_sections,
                "TIER SLOT REPORT AFTER CAP REPAIR",
                print_tier_slot_report,
                hitter_roster=hitter_roster,
                pitcher_roster=pitcher_roster,
                tier_slots=ruleset.tier_slots,
            )

        if ruleset.variant_limit is not None:
            add_captured_section(
                report_sections,
                "VARIANT REPORT AFTER CAP REPAIR",
                print_variant_report,
                hitter_roster=hitter_roster,
                pitcher_roster=pitcher_roster,
                variant_limit=ruleset.variant_limit,
            )
    timer.checkpoint("Cap validation and repair")

    html_output = request.html_output or build_output_name(ruleset, request.overrides)
    snapshot_path = snapshot_path_for_html(html_output)
    old_snapshot = load_snapshot(snapshot_path)
    new_snapshot = build_roster_snapshot(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
    )
    change_statuses = compare_snapshots(
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
    )
    timer.checkpoint("Snapshot comparison")

    export_roster_html(
        path=html_output,
        ruleset=ruleset,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        eligibility_summary=eligibility_summary,
        change_statuses=change_statuses,
        tier_slot_repair_result=tier_slot_result,
        simulation_context=simulation_context,
        scoring_environment=scoring_environment,
        build_timing_rows=timer.snapshot().summary_rows(
            total_label="Pre-export subtotal"
        ),
        optimizer_summary_rows=(
            optimization_solution_summary_rows(optimization_solution)
            if optimization_solution is not None
            else None
        ),
    )
    write_snapshot(snapshot_path, new_snapshot)
    timer.checkpoint("HTML and snapshot export")

    add_text_section(
        report_sections,
        "OUTPUT",
        "\n".join(
            [
                f"HTML roster written to: {html_output}",
                f"Roster snapshot written to: {snapshot_path}",
            ]
        ),
    )
    add_roster_summary_sections(report_sections, hitter_roster, pitcher_roster, ruleset)
    timer.checkpoint("Report summary preparation")
    build_timing = timer.snapshot()
    add_text_section(
        report_sections,
        "BUILD TIMINGS",
        format_build_timing_summary(build_timing),
    )

    return RosterBuildResult(
        config=cfg,
        context=context,
        candidate_pool=candidate_pool,
        candidate_matrices=candidate_matrices,
        solver_input=solver_input,
        ruleset=ruleset,
        simulation_context=simulation_context,
        scoring_environment=scoring_environment,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        eligibility_summary=eligibility_summary,
        html_output=html_output,
        snapshot_path=snapshot_path,
        report_sections=report_sections,
        build_timing=build_timing,
        build_method=build_method,
        optimization_solution=optimization_solution,
        variant_repair_result=variant_result,
        tier_slot_repair_result=tier_slot_result,
        cap_repair_result=cap_result,
    )


def resolve_build_method(
    cfg: dict[str, Any],
    request: RosterBuildRequest,
) -> BuildMethod:
    value = request.build_method
    if value is None and request.preset:
        value = (
            cfg.get("tournament_presets", {})
            .get(request.preset, {})
            .get("build_method")
        )
    value = value or "greedy"
    if value not in BUILD_METHODS:
        raise ValueError(
            f"Unknown build method '{value}'. Expected one of: "
            f"{', '.join(sorted(BUILD_METHODS))}."
        )
    return value


def optimization_solution_summary_rows(
    solution: OptimizationSolution,
) -> list[tuple[str, str]]:
    return [
        ("Optimizer status", solution.status),
        ("Optimizer optimal", "yes" if solution.is_optimal else "no"),
        (
            "Optimizer objective",
            (
                "-"
                if solution.objective_value is None
                else f"{solution.objective_value:.2f}"
            ),
        ),
        (
            "Optimizer best bound",
            (
                "-"
                if solution.best_objective_bound is None
                else f"{solution.best_objective_bound:.2f}"
            ),
        ),
        ("Optimizer solve time", f"{solution.wall_time_seconds:.3f} s"),
    ]


def build_ruleset(cfg: dict[str, Any], request: RosterBuildRequest) -> Ruleset:
    if request.preset:
        return build_ruleset_from_tournament_preset(
            cfg,
            preset_name=request.preset,
            overrides=request.overrides,
        )

    return build_ruleset_from_base_profile(
        cfg,
        base_profile_name=request.base_profile,
        overrides=request.overrides,
    )


def build_output_name(ruleset: Ruleset, overrides: dict[str, Any]) -> str:
    parts = [ruleset.name]

    if "dh_enabled" in overrides:
        parts.append("dh" if ruleset.dh_enabled else "no_dh")
    if ruleset.tier_min:
        parts.append(f"tier_min_{ruleset.tier_min}")
    if ruleset.tier_max:
        parts.append(f"tier_max_{ruleset.tier_max}")
    if ruleset.card_value_min is not None:
        parts.append(f"cv_min_{ruleset.card_value_min}")
    if ruleset.card_value_max is not None:
        parts.append(f"cv_max_{ruleset.card_value_max}")
    if ruleset.live_mode != "all":
        parts.append(ruleset.live_mode)
    if ruleset.allowed_card_types:
        parts.append("types_" + "_".join(ruleset.allowed_card_types))
    if ruleset.excluded_card_types:
        parts.append("exclude_types_" + "_".join(ruleset.excluded_card_types))
    if ruleset.card_year_min is not None:
        parts.append(f"year_min_{ruleset.card_year_min}")
    if ruleset.card_year_max is not None:
        parts.append(f"year_max_{ruleset.card_year_max}")
    if ruleset.scoring_environment not in (None, "auto"):
        parts.append(f"score_{ruleset.scoring_environment}")

    safe_name = "_".join(parts)
    safe_name = safe_name.replace(" ", "_").replace("/", "_")

    return f"outputs/roster_build_{safe_name}.html"


def format_ruleset_summary(ruleset: Ruleset) -> str:
    lines = [
        f"Base profile: {ruleset.name}",
        f"Hitters/Pitchers: {ruleset.hitter_count}/{ruleset.pitcher_count}",
        f"DH enabled: {ruleset.dh_enabled}",
        f"Tier min/max: {ruleset.tier_min} / {ruleset.tier_max}",
        f"Card value min/max: {ruleset.card_value_min} / {ruleset.card_value_max}",
        f"Live mode: {ruleset.live_mode}",
        f"Allowed card types: {ruleset.allowed_card_types or '-'}",
        f"Excluded card types: {ruleset.excluded_card_types or '-'}",
        f"Card year min/max: {ruleset.card_year_min} / {ruleset.card_year_max}",
        f"Simulation year: {ruleset.simulation_year or '-'}",
        f"Ballpark: {ruleset.ballpark or '-'}",
        f"Ballpark year: {ruleset.ballpark_year or '-'}",
        f"Custom park factors: {ruleset.custom_park_factors or '-'}",
        f"Variant limit: {ruleset.variant_limit}",
        f"Scoring environment: {ruleset.scoring_environment or 'auto'}",
    ]
    if ruleset.slot_plan is not None:
        lines.extend(
            [
                f"Lineup assignments: {ruleset.slot_plan.lineup_summary()}",
                f"Pitcher groups: {ruleset.slot_plan.pitcher_group_summary()}",
                "Lineup bench coverage: "
                f"{coverage_summary(ruleset.lineup_coverage_requirements)}",
            ]
        )
    return "\n".join(lines)


def format_simulation_context_summary(simulation_context: SimulationContext) -> str:
    return "\n".join(
        f"{label}: {value}" for label, value in simulation_context.summary_rows()
    )


def format_scoring_environment_summary(
    scoring_environment: ScoringEnvironment,
) -> str:
    return "\n".join(
        f"{label}: {value}" for label, value in scoring_environment.summary_rows()
    )


def format_build_timing_summary(build_timing: BuildTiming) -> str:
    return "\n".join(
        f"{label}: {value}" for label, value in build_timing.summary_rows()
    )


def format_raw_data_check(hitters_df, pitchers_df) -> str:
    lines = [
        f"Hitters rows:  {len(hitters_df)}",
        f"Pitchers rows: {len(pitchers_df)}",
    ]

    if "position" in hitters_df.columns:
        lines.extend(
            [
                "",
                "Hitter position counts:",
                hitters_df["position"].value_counts(dropna=False).head(12).to_string(),
            ]
        )

    if "position" in pitchers_df.columns:
        lines.extend(
            [
                "",
                "Pitcher position counts:",
                pitchers_df["position"].value_counts(dropna=False).head(12).to_string(),
            ]
        )

    if "stamina" in pitchers_df.columns:
        lines.extend(
            [
                "",
                "Pitcher stamina sanity:",
                pitchers_df["stamina"].describe().to_string(),
            ]
        )

    lines.extend(
        [
            "",
            "Hitter sample:",
            hitters_df[["name"]].head(5).to_string(index=False),
            "",
            "Pitcher sample:",
            pitchers_df[["name"]].head(5).to_string(index=False),
        ]
    )

    return "\n".join(lines)


def add_roster_summary_sections(
    report_sections: list[tuple[str, str]],
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    ruleset: Ruleset,
) -> None:
    if hitter_roster.starters_by_split:
        for split, label in (("vs_rhp", "VS RHP"), ("vs_lhp", "VS LHP")):
            starters = hitter_roster.starters_for_split(split)
            lines = []
            for position, row in starters.items():
                score_col = (
                    f"batting_score_{split}"
                    if position == "DH"
                    else f"score_{position}_{split}"
                )
                lines.append(f"{position:>2}  {row['name']:<25}  {row[score_col]:.2f}")
            add_text_section(report_sections, f"STARTERS {label}", "\n".join(lines))

            lines = []
            for _, row in hitter_roster.bench_for_split(split).iterrows():
                covered = sorted(get_player_covered_positions(row, ruleset))
                lines.append(
                    f"{row['name']:<25}  bat={row[f'batting_score_{split}']:.2f}  "
                    f"covers={covered}"
                )
            add_text_section(report_sections, f"BENCH {label}", "\n".join(lines))
    else:
        lines = []
        for position, row in hitter_roster.starters_by_position.items():
            score_col = (
                "batting_score_overall"
                if position == "DH"
                else f"score_{position}_overall"
            )
            lines.append(f"{position:>2}  {row['name']:<25}  {row[score_col]:.2f}")
        add_text_section(report_sections, "STARTERS", "\n".join(lines))

        lines = []
        for _, row in hitter_roster.bench_players.iterrows():
            covered = sorted(get_player_covered_positions(row, ruleset))
            lines.append(
                f"{row['name']:<25}  bat={row['batting_score_overall']:.2f}  "
                f"covers={covered}"
            )
        add_text_section(report_sections, "BENCH", "\n".join(lines))

    rhp_rows = build_lineup_depth_rows(hitter_roster, ruleset, split="vs_rhp")
    add_text_section(
        report_sections,
        "LINEUP VS RHP / DEPTH",
        format_lineup_depth_rows(rhp_rows),
    )

    lhp_rows = build_lineup_depth_rows(hitter_roster, ruleset, split="vs_lhp")
    add_text_section(
        report_sections,
        "LINEUP VS LHP / DEPTH",
        format_lineup_depth_rows(lhp_rows),
    )

    pinch_hitters_rhp = build_pinch_hitters(
        hitter_roster.bench_for_split("vs_rhp"), split="vs_rhp"
    )
    add_text_section(
        report_sections,
        "PINCH HITTERS VS RHP",
        format_ranked_rows(pinch_hitters_rhp, "batting_score_vs_rhp"),
    )

    pinch_hitters_lhp = build_pinch_hitters(
        hitter_roster.bench_for_split("vs_lhp"), split="vs_lhp"
    )
    add_text_section(
        report_sections,
        "PINCH HITTERS VS LHP",
        format_ranked_rows(pinch_hitters_lhp, "batting_score_vs_lhp"),
    )

    pinch_runners = build_pinch_runners(hitter_roster.bench_for_split("vs_rhp"))
    add_text_section(
        report_sections,
        "PINCH RUNNERS",
        format_ranked_rows(pinch_runners, "pinch_run_score"),
    )

    add_text_section(
        report_sections,
        "ROTATION",
        pitcher_roster.rotation[["name", "starter_score_overall"]].to_string(
            index=False
        ),
    )
    add_text_section(
        report_sections,
        "MIDDLE RELIEF",
        pitcher_roster.bullpen[["name", "reliever_score_overall"]].to_string(
            index=False
        ),
    )
    add_text_section(
        report_sections,
        "LEFTY SPECIALIST",
        pitcher_roster.lefty_specialist[["name", "reliever_score_vs_lhb"]].to_string(
            index=False
        ),
    )
    add_text_section(
        report_sections,
        "LONG RELIEF",
        pitcher_roster.long_man[["name", "starter_score_overall"]].to_string(
            index=False
        ),
    )


def format_ranked_rows(rows, score_col: str) -> str:
    lines = []
    for idx, (_, row) in enumerate(rows.iterrows(), start=1):
        lines.append(f"{idx}. {row['name']:<25} {row[score_col]:.2f}")
    return "\n".join(lines)


def add_text_section(
    report_sections: list[tuple[str, str]],
    title: str,
    text: str,
) -> None:
    report_sections.append((title, text.strip()))


def add_captured_section(
    report_sections: list[tuple[str, str]],
    title: str,
    func,
    *args,
    **kwargs,
) -> None:
    buffer = StringIO()
    with redirect_stdout(buffer):
        func(*args, **kwargs)
    add_text_section(report_sections, title, buffer.getvalue())
