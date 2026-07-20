from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from ootp_opt.domain.scoring_environment import (
    ScoringEnvironment,
    apply_scoring_environment_to_config,
    resolve_scoring_environment,
)
from ootp_opt.domain.simulation_context import (
    SimulationContext,
    apply_simulation_context_to_config,
    resolve_simulation_context,
)
from ootp_opt.roster.eligibility import (
    filter_eligible_hitters,
    filter_eligible_pitchers,
)
from ootp_opt.roster.rules import Ruleset

CandidateSource = Literal["owned", "store"]


@dataclass(frozen=True)
class BuildContext:
    ruleset: Ruleset
    scoring_environment: ScoringEnvironment
    simulation_context: SimulationContext
    scoring_config: dict[str, Any]


@dataclass(frozen=True)
class CandidatePool:
    source: CandidateSource
    context: BuildContext
    scored_hitters: pd.DataFrame
    scored_pitchers: pd.DataFrame
    eligible_hitters: pd.DataFrame
    eligible_pitchers: pd.DataFrame

    @property
    def scored_counts(self) -> tuple[int, int]:
        return len(self.scored_hitters), len(self.scored_pitchers)

    @property
    def eligible_counts(self) -> tuple[int, int]:
        return len(self.eligible_hitters), len(self.eligible_pitchers)

    def require_eligible_cards(self) -> None:
        if self.eligible_hitters.empty:
            raise ValueError("No eligible hitters after applying filters.")
        if self.eligible_pitchers.empty:
            raise ValueError("No eligible pitchers after applying filters.")


def resolve_build_context(
    cfg: dict[str, Any],
    ruleset: Ruleset,
) -> BuildContext:
    scoring_environment = resolve_scoring_environment(cfg, ruleset)
    environment_cfg = apply_scoring_environment_to_config(cfg, scoring_environment)

    simulation_context = resolve_simulation_context(
        simulation_year=ruleset.simulation_year,
        ballpark=ruleset.ballpark,
        ballpark_year=ruleset.ballpark_year,
        custom_park_factors=ruleset.custom_park_factors,
    )
    scoring_config = apply_simulation_context_to_config(
        environment_cfg,
        simulation_context,
    )

    return BuildContext(
        ruleset=ruleset,
        scoring_environment=scoring_environment,
        simulation_context=simulation_context,
        scoring_config=scoring_config,
    )


def build_candidate_pool(
    *,
    source: CandidateSource,
    context: BuildContext,
    scored_hitters: pd.DataFrame,
    scored_pitchers: pd.DataFrame,
) -> CandidatePool:
    return CandidatePool(
        source=source,
        context=context,
        scored_hitters=scored_hitters,
        scored_pitchers=scored_pitchers,
        eligible_hitters=filter_eligible_hitters(scored_hitters, context.ruleset),
        eligible_pitchers=filter_eligible_pitchers(scored_pitchers, context.ruleset),
    )
