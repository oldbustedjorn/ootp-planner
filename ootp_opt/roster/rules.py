from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchRoleRequirement:
    required_positions: list[str] = field(default_factory=list)
    required_positions_any: list[str] = field(default_factory=list)
    preferred_positions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Ruleset:
    name: str
    mode: str
    hitter_count: int
    pitcher_count: int
    dh_enabled: bool
    platoons_allowed: bool

    lineup_fill_order: list[str]

    rotation_size: int
    primary_rp_count: int
    specialist_lhp_count: int
    long_man_count: int

    bench_roles: list[str]
    min_defense_by_position: dict[str, float]
    bench_role_requirements: dict[str, BenchRoleRequirement]

    # Tournament / build override fields. These are generic values that can
    # later come from config, CLI flags, or a GUI.
    tier_min: str | None = None
    tier_max: str | None = None
    card_value_min: int | None = None
    card_value_max: int | None = None
    variant_limit: int | None = None
    live_mode: str = "all"  # "all", "live", or "non_live"
    card_year_min: int | None = None
    card_year_max: int | None = None
    simulation_year: int | None = None
    point_cap_total: int | None = None
    tier_slots: dict[str, int] = field(default_factory=dict)


def build_ruleset_from_base_profile(
    config: dict[str, Any],
    base_profile_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> Ruleset:
    """Build a Ruleset from one base roster profile plus optional overrides.

    Base profiles define roster shape and construction policy. Overrides are
    generic tournament/settings values such as tier limits, card-year limits,
    live mode, card-value limits, DH changes, and caps.
    """
    roster_cfg = config.get("roster", {})
    base_profiles = config.get("roster_base_profiles", {})

    resolved_name = base_profile_name or roster_cfg.get("default_base_profile")
    if not resolved_name:
        raise ValueError(
            "No base roster profile name provided and no "
            "[roster].default_base_profile set."
        )

    profile_cfg = base_profiles.get(resolved_name)
    if not profile_cfg:
        available = ", ".join(sorted(base_profiles.keys())) or "(none)"
        raise ValueError(
            f"Base roster profile '{resolved_name}' not found under "
            f"[roster_base_profiles]. Available profiles: {available}"
        )

    # Defaults are applied first, then the base profile overrides defaults,
    # then explicit caller overrides beat both.
    merged_cfg = deep_merge_dicts(
        config.get("roster_build_defaults", {}),
        profile_cfg,
    )

    if overrides:
        merged_cfg = deep_merge_dicts(merged_cfg, overrides)

    return build_ruleset(resolved_name, merged_cfg)


# Backward-compatible wrapper for older test scripts/call sites.
def load_roster_profile(
    config: dict[str, Any], profile_name: str | None = None
) -> Ruleset:
    return build_ruleset_from_base_profile(config, profile_name)


def build_ruleset(profile_name: str, profile_cfg: dict[str, Any]) -> Ruleset:
    mode = str(profile_cfg.get("mode", "standard_pt"))
    hitter_count = int(profile_cfg.get("hitter_count", 13))
    pitcher_count = int(profile_cfg.get("pitcher_count", 13))
    dh_enabled = bool(profile_cfg.get("dh_enabled", True))
    platoons_allowed = bool(profile_cfg.get("platoons_allowed", False))

    lineup_fill_order = [str(pos) for pos in profile_cfg.get("lineup_fill_order", [])]

    rotation_size = int(profile_cfg.get("rotation_size", 5))
    primary_rp_count = int(profile_cfg.get("primary_rp_count", 6))
    specialist_lhp_count = int(profile_cfg.get("specialist_lhp_count", 1))
    long_man_count = int(profile_cfg.get("long_man_count", 1))

    bench_roles = [str(role) for role in profile_cfg.get("bench_roles", [])]

    min_defense_raw = profile_cfg.get("min_defense_by_position", {})
    min_defense_by_position = {
        str(position): float(value) for position, value in min_defense_raw.items()
    }

    bench_role_requirements = parse_bench_role_requirements(
        profile_cfg.get("bench_role_requirements", {})
    )

    tier_min = none_if_blank(profile_cfg.get("tier_min"))
    tier_max = none_if_blank(profile_cfg.get("tier_max"))
    card_value_min = none_if_zero(profile_cfg.get("card_value_min"))
    card_value_max = none_if_zero(profile_cfg.get("card_value_max"))
    variant_limit = none_if_zero(profile_cfg.get("variant_limit"))
    live_mode = str(profile_cfg.get("live_mode", "all")).lower()
    card_year_min = none_if_zero(profile_cfg.get("card_year_min"))
    card_year_max = none_if_zero(profile_cfg.get("card_year_max"))
    simulation_year = none_if_zero(profile_cfg.get("simulation_year"))
    point_cap_total = none_if_zero(profile_cfg.get("point_cap_total"))

    tier_slots_raw = profile_cfg.get("tier_slots", {})
    tier_slots = {str(tier): int(count) for tier, count in tier_slots_raw.items()}

    validate_ruleset_config(
        profile_name=profile_name,
        lineup_fill_order=lineup_fill_order,
        bench_roles=bench_roles,
        bench_role_requirements=bench_role_requirements,
        live_mode=live_mode,
    )

    return Ruleset(
        name=profile_name,
        mode=mode,
        hitter_count=hitter_count,
        pitcher_count=pitcher_count,
        dh_enabled=dh_enabled,
        platoons_allowed=platoons_allowed,
        lineup_fill_order=lineup_fill_order,
        rotation_size=rotation_size,
        primary_rp_count=primary_rp_count,
        specialist_lhp_count=specialist_lhp_count,
        long_man_count=long_man_count,
        bench_roles=bench_roles,
        min_defense_by_position=min_defense_by_position,
        bench_role_requirements=bench_role_requirements,
        tier_min=tier_min,
        tier_max=tier_max,
        card_value_min=card_value_min,
        card_value_max=card_value_max,
        variant_limit=variant_limit,
        live_mode=live_mode,
        card_year_min=card_year_min,
        card_year_max=card_year_max,
        simulation_year=simulation_year,
        point_cap_total=point_cap_total,
        tier_slots=tier_slots,
    )


def validate_ruleset_config(
    profile_name: str,
    lineup_fill_order: list[str],
    bench_roles: list[str],
    bench_role_requirements: dict[str, BenchRoleRequirement],
    live_mode: str,
) -> None:
    if not lineup_fill_order:
        raise ValueError(f"Roster profile '{profile_name}' has no lineup_fill_order.")

    if not bench_roles:
        raise ValueError(f"Roster profile '{profile_name}' has no bench_roles.")

    missing_roles = [
        role for role in bench_roles if role not in bench_role_requirements
    ]
    if missing_roles:
        raise ValueError(
            f"Roster profile '{profile_name}' is missing "
            f"bench_role_requirements for: {missing_roles}"
        )

    valid_live_modes = {"all", "live", "non_live"}
    if live_mode not in valid_live_modes:
        raise ValueError(
            f"Roster profile '{profile_name}' has invalid live_mode '{live_mode}'. "
            f"Expected one of: {sorted(valid_live_modes)}"
        )


def parse_bench_role_requirements(
    raw_requirements: dict[str, Any],
) -> dict[str, BenchRoleRequirement]:
    parsed: dict[str, BenchRoleRequirement] = {}

    for role_name, role_cfg in raw_requirements.items():
        if not isinstance(role_cfg, dict):
            raise ValueError(
                f"bench_role_requirements.{role_name} must be a table/dict, "
                f"got {type(role_cfg).__name__}"
            )

        parsed[str(role_name)] = BenchRoleRequirement(
            required_positions=[
                str(pos) for pos in role_cfg.get("required_positions", [])
            ],
            required_positions_any=[
                str(pos) for pos in role_cfg.get("required_positions_any", [])
            ],
            preferred_positions=[
                str(pos) for pos in role_cfg.get("preferred_positions", [])
            ],
        )

    return parsed


def none_if_zero(value: Any) -> int | None:
    if value in (None, 0, "0", ""):
        return None
    return int(value)


def none_if_blank(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).lower()


def deep_copy_dict(value: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}

    for key, item in value.items():
        if isinstance(item, dict):
            copied[key] = deep_copy_dict(item)
        elif isinstance(item, list):
            copied[key] = item.copy()
        else:
            copied[key] = item

    return copied


def deep_merge_dicts(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = deep_copy_dict(base)

    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        elif isinstance(value, list):
            merged[key] = value.copy()
        else:
            merged[key] = value

    return merged
