from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dataclasses import asdict


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


def load_roster_profile(
    config: dict[str, Any], profile_name: str | None = None
) -> Ruleset:
    roster_cfg = config.get("roster", {})
    profiles = config.get("roster_profiles", {})

    resolved_name = profile_name or roster_cfg.get("default_profile")
    if not resolved_name:
        raise ValueError(
            "No roster profile name provided and no [roster].default_profile set."
        )

    profile_cfg = profiles.get(resolved_name)
    if not profile_cfg:
        available = ", ".join(sorted(profiles.keys())) or "(none)"
        raise ValueError(
            f"Roster profile '{resolved_name}' not found under [roster_profiles]. "
            f"Available profiles: {available}"
        )

    return build_ruleset(resolved_name, profile_cfg)


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

    # --- basic validation (v1) ---

    if not lineup_fill_order:
        raise ValueError(f"Roster profile '{profile_name}' has no lineup_fill_order.")

    if not bench_roles:
        raise ValueError(f"Roster profile '{profile_name}' has no bench_roles.")

    missing_roles = [
        role for role in bench_roles if role not in bench_role_requirements
    ]
    if missing_roles:
        raise ValueError(
            f"Roster profile '{profile_name}' is missing bench_role_requirements for: {missing_roles}"
        )

    # --- basic validation (v1) ---

    if not lineup_fill_order:
        raise ValueError(f"Roster profile '{profile_name}' has no lineup_fill_order.")

    if not bench_roles:
        raise ValueError(f"Roster profile '{profile_name}' has no bench_roles.")

    missing_roles = [
        role for role in bench_roles if role not in bench_role_requirements
    ]
    if missing_roles:
        raise ValueError(
            f"Roster profile '{profile_name}' is missing bench_role_requirements for: {missing_roles}"
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
    )


def parse_bench_role_requirements(
    raw_requirements: dict[str, Any],
) -> dict[str, BenchRoleRequirement]:
    parsed: dict[str, BenchRoleRequirement] = {}

    for role_name, role_cfg in raw_requirements.items():
        if not isinstance(role_cfg, dict):
            raise ValueError(
                f"bench_role_requirements.{role_name} must be a table/dict, got {type(role_cfg).__name__}"
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
