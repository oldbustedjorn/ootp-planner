from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ootp_opt.roster.rules import Ruleset, deep_merge_dicts

SCORING_ENVIRONMENT_ORDER = ["iron", "bronze", "silver", "gold", "diamond", "open"]
AUTO_SCORING_ENVIRONMENT = "auto"
NONE_SCORING_ENVIRONMENT = "none"


@dataclass(frozen=True)
class ScoringEnvironment:
    name: str
    source: str
    config: dict[str, Any]

    def summary_rows(self) -> list[tuple[str, str]]:
        hitter_cfg = self.config.get("hitters", {})
        pitcher_cfg = self.config.get("pitchers", {})
        rows = [
            ("Scoring environment", self.name),
            ("Scoring environment source", self.source),
        ]

        if hitter_cfg:
            for key in [
                "power_midpoint",
                "avoid_k_midpoint",
                "babip_midpoint",
                "gap_midpoint",
                "eye_midpoint",
            ]:
                if key in hitter_cfg:
                    rows.append((f"Scoring hitter {key}", str(hitter_cfg[key])))

        if pitcher_cfg:
            for key in [
                "vs_rhb_weight",
                "vs_lhb_weight",
                "rp_stuff_midpoint",
                "sp_stuff_midpoint",
                "hra_midpoint",
                "pbabip_midpoint",
                "control_midpoint",
            ]:
                if key in pitcher_cfg:
                    rows.append((f"Scoring {key}", str(pitcher_cfg[key])))

        return rows


def resolve_scoring_environment(
    cfg: dict[str, Any],
    ruleset: Ruleset,
) -> ScoringEnvironment:
    requested = ruleset.scoring_environment or AUTO_SCORING_ENVIRONMENT
    normalized = str(requested).strip().lower()

    if normalized in {"", AUTO_SCORING_ENVIRONMENT}:
        name = infer_scoring_environment_name(ruleset)
        source = "auto"
    elif normalized == NONE_SCORING_ENVIRONMENT:
        name = NONE_SCORING_ENVIRONMENT
        source = "explicit"
    else:
        name = normalized
        source = "explicit"

    if name == NONE_SCORING_ENVIRONMENT:
        return ScoringEnvironment(name=name, source=source, config={})

    environments = cfg.get("scoring_environments", {})
    if not environments and source == "auto":
        return ScoringEnvironment(
            name=NONE_SCORING_ENVIRONMENT,
            source="auto",
            config={},
        )

    if name not in environments:
        available = ", ".join(sorted(environments.keys())) or "(none)"
        raise ValueError(
            f"Scoring environment '{name}' not found under "
            f"[scoring_environments]. Available environments: {available}"
        )

    return ScoringEnvironment(
        name=name,
        source=source,
        config=dict(environments[name]),
    )


def infer_scoring_environment_name(ruleset: Ruleset) -> str:
    if ruleset.tier_max:
        return normalize_scoring_environment_name(ruleset.tier_max)

    if ruleset.card_value_max is not None:
        return infer_from_card_value_max(ruleset.card_value_max)

    return "open"


def normalize_scoring_environment_name(value: object) -> str:
    text = str(value).strip().lower()
    aliases = {
        "i": "iron",
        "iron": "iron",
        "b": "bronze",
        "bronze": "bronze",
        "s": "silver",
        "silver": "silver",
        "g": "gold",
        "gold": "gold",
        "d": "diamond",
        "diamond": "diamond",
        "p": "open",
        "perfect": "open",
        "open": "open",
        "pt": "open",
    }
    return aliases.get(text, text)


def infer_from_card_value_max(card_value_max: int) -> str:
    if card_value_max <= 59:
        return "iron"
    if card_value_max <= 69:
        return "bronze"
    if card_value_max <= 79:
        return "silver"
    if card_value_max <= 89:
        return "gold"
    if card_value_max <= 99:
        return "diamond"
    return "open"


def apply_scoring_environment_to_config(
    cfg: dict[str, Any],
    environment: ScoringEnvironment,
) -> dict[str, Any]:
    if not environment.config:
        return deep_merge_dicts(cfg, {})

    return deep_merge_dicts(cfg, environment.config)
