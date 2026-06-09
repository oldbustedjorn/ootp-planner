from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class EraFactors:
    year: int
    contact: float = 1.0
    gap_power: float = 1.0
    hr_power: float = 1.0
    eye: float = 1.0
    avoid_k: float = 1.0
    stuff: float = 1.0
    movement: float = 1.0
    control: float = 1.0
    speed: float = 1.0
    fielding: float = 1.0


@dataclass(frozen=True)
class ParkFactors:
    year: int
    name: str
    park: str
    ba_lh: float = 1.0
    doubles_lh: float = 1.0
    triples_lh: float = 1.0
    hr_lh: float = 1.0
    ba_rh: float = 1.0
    doubles_rh: float = 1.0
    triples_rh: float = 1.0
    hr_rh: float = 1.0
    ba_overall: float = 1.0
    doubles_overall: float = 1.0
    triples_overall: float = 1.0
    hr_overall: float = 1.0


@dataclass(frozen=True)
class SimulationContext:
    simulation_year: int | None = None
    ballpark: str | None = None
    ballpark_year: int | None = None
    era: EraFactors | None = None
    park: ParkFactors | None = None

    @property
    def is_neutral(self) -> bool:
        return self.era is None and self.park is None

    def summary_rows(self) -> list[tuple[str, str]]:
        if self.is_neutral:
            return [("Simulation context", "Neutral")]

        rows: list[tuple[str, str]] = []

        rows.append(
            (
                "Simulation year",
                "-" if self.simulation_year is None else str(self.simulation_year),
            )
        )

        if self.era is not None:
            rows.append(
                (
                    "Era factors",
                    (
                        f"Contact {self.era.contact:.3f}, Gap {self.era.gap_power:.3f}, "
                        f"HR {self.era.hr_power:.3f}, Stuff {self.era.stuff:.3f}, "
                        f"Control {self.era.control:.3f}"
                    ),
                )
            )

        if self.park is not None:
            rows.append(
                (
                    "Ballpark",
                    f"{self.park.year} {self.park.park}",
                )
            )
            rows.append(
                (
                    "Park factors",
                    (
                        f"BA {self.park.ba_overall:.2f}, 2B {self.park.doubles_overall:.2f}, "
                        f"3B {self.park.triples_overall:.2f}, HR {self.park.hr_overall:.2f}"
                    ),
                )
            )

        return rows


def resolve_simulation_context(
    simulation_year: int | None = None,
    ballpark: str | None = None,
    ballpark_year: int | None = None,
    custom_park_factors: dict[str, Any] | None = None,
) -> SimulationContext:
    simulation_year = none_if_zero(simulation_year)
    ballpark = none_if_blank(ballpark)
    ballpark_year = none_if_zero(ballpark_year)

    era = load_era_factors(simulation_year) if simulation_year is not None else None

    park = None
    if custom_park_factors:
        resolved_park_year = ballpark_year or simulation_year or 0
        park = build_custom_park_factors(
            ballpark=ballpark or "Custom Park",
            year=resolved_park_year,
            factors=custom_park_factors,
        )
        ballpark_year = resolved_park_year or None
    elif ballpark:
        resolved_park_year = ballpark_year or simulation_year
        if resolved_park_year is None:
            raise ValueError(
                "Ballpark was provided without ballpark_year or simulation_year. "
                "Set --ballpark-year or simulation_year."
            )
        park = load_park_factors(ballpark=ballpark, year=resolved_park_year)
        ballpark_year = resolved_park_year

    return SimulationContext(
        simulation_year=simulation_year,
        ballpark=ballpark,
        ballpark_year=ballpark_year,
        era=era,
        park=park,
    )


def build_custom_park_factors(
    ballpark: str,
    year: int,
    factors: dict[str, Any],
) -> ParkFactors:
    ba_lh = factor_value(factors, "ba_lh", "avg_lh", default=1.0)
    ba_rh = factor_value(factors, "ba_rh", "avg_rh", default=ba_lh)
    doubles_lh = factor_value(factors, "doubles_lh", "2b_lh", default=1.0)
    doubles_rh = factor_value(factors, "doubles_rh", "2b_rh", default=doubles_lh)
    triples_lh = factor_value(factors, "triples_lh", "3b_lh", default=1.0)
    triples_rh = factor_value(factors, "triples_rh", "3b_rh", default=triples_lh)
    hr_lh = factor_value(factors, "hr_lh", default=1.0)
    hr_rh = factor_value(factors, "hr_rh", default=hr_lh)

    ba_overall = factor_value(factors, "ba_overall", "avg_overall", default=(ba_lh + ba_rh) / 2.0)
    doubles_overall = factor_value(
        factors,
        "doubles_overall",
        "2b_overall",
        default=(doubles_lh + doubles_rh) / 2.0,
    )
    triples_overall = factor_value(
        factors,
        "triples_overall",
        "3b_overall",
        default=(triples_lh + triples_rh) / 2.0,
    )
    hr_overall = factor_value(
        factors,
        "hr_overall",
        default=(hr_lh + hr_rh) / 2.0,
    )

    return ParkFactors(
        year=year,
        name="Custom",
        park=ballpark,
        ba_lh=ba_lh,
        doubles_lh=doubles_lh,
        triples_lh=triples_lh,
        hr_lh=hr_lh,
        ba_rh=ba_rh,
        doubles_rh=doubles_rh,
        triples_rh=triples_rh,
        hr_rh=hr_rh,
        ba_overall=ba_overall,
        doubles_overall=doubles_overall,
        triples_overall=triples_overall,
        hr_overall=hr_overall,
    )


def factor_value(
    factors: dict[str, Any],
    *keys: str,
    default: float,
) -> float:
    normalized = {normalize_factor_key(key): value for key, value in factors.items()}

    for key in keys:
        normalized_key = normalize_factor_key(key)
        if normalized_key in normalized:
            return float(normalized[normalized_key])

    return float(default)


def normalize_factor_key(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def apply_simulation_context_to_config(
    config: dict[str, Any],
    context: SimulationContext,
) -> dict[str, Any]:
    if context.is_neutral:
        return config

    adjusted = deep_copy_dict(config)
    hitters = adjusted.setdefault("hitters", {})
    pitchers = adjusted.setdefault("pitchers", {})

    era = context.era or EraFactors(year=context.simulation_year or 0)
    park = context.park or ParkFactors(
        year=context.ballpark_year or context.simulation_year or 0,
        name="Neutral",
        park="Neutral",
    )

    ba_factor = conservative_factor(park.ba_overall, strength=0.50, lo=0.85, hi=1.20)
    gap_factor = conservative_factor(
        (park.doubles_overall + park.triples_overall) / 2.0,
        strength=0.50,
        lo=0.85,
        hi=1.20,
    )
    hr_factor = conservative_factor(park.hr_overall, strength=0.60, lo=0.80, hi=1.30)
    fielding_pressure = conservative_factor(
        (park.ba_overall + park.triples_overall) / 2.0,
        strength=0.35,
        lo=0.90,
        hi=1.15,
    )

    hitter_multipliers = {
        "contact": era_factor(era.contact) * ba_factor,
        "gap_power": era_factor(era.gap_power) * gap_factor,
        "power": era_factor(era.hr_power) * hr_factor,
        "eye": era_factor(era.eye),
        "avoid_k": era_factor(era.avoid_k),
        "babip": ba_factor,
        "off_speed": era_factor(era.speed) * gap_factor,
        "pr_speed": era_factor(era.speed) * gap_factor,
        "fld_pos": era_factor(era.fielding) * fielding_pressure,
        "defense_scale": era_factor(era.fielding) * fielding_pressure,
    }

    for key, multiplier in hitter_multipliers.items():
        if key in hitters:
            hitters[key] = float(hitters[key]) * multiplier

    defense_component_keys = [
        "c_framing",
        "c_blocking",
        "c_arm",
        "if_range",
        "if_error",
        "if_arm",
        "turn_dp",
        "of_range",
        "of_error",
        "of_arm",
    ]
    defense_multiplier = era_factor(era.fielding) * fielding_pressure
    for key in defense_component_keys:
        if key in hitters:
            hitters[key] = float(hitters[key]) * defense_multiplier

    pitcher_multipliers = {
        "sp_stuff": era_factor(era.stuff),
        "rp_stuff": era_factor(era.stuff),
        "sp_movement": era_factor(era.movement),
        "rp_movement": era_factor(era.movement),
        "sp_control": era_factor(era.control),
        "rp_control": era_factor(era.control),
        "sp_pbabip": ba_factor,
        "rp_pbabip": ba_factor,
        "sp_hr_rate": era_factor(era.hr_power) * hr_factor,
        "rp_hr_rate": era_factor(era.hr_power) * hr_factor,
    }
    for key, multiplier in pitcher_multipliers.items():
        if key in pitchers:
            pitchers[key] = float(pitchers[key]) * multiplier

    return adjusted


def load_era_factors(year: int) -> EraFactors:
    df = pd.read_csv(data_path("year_era_factors.csv"))
    row = df.loc[pd.to_numeric(df["YEAR"], errors="coerce").eq(year)]

    if row.empty:
        min_year = int(df["YEAR"].min())
        max_year = int(df["YEAR"].max())
        raise ValueError(
            f"Simulation year {year} not found in year era factors. "
            f"Available range: {min_year}-{max_year}."
        )

    item = row.iloc[0]
    return EraFactors(
        year=year,
        contact=float(item["Contact"]),
        gap_power=float(item["Gap Power"]),
        hr_power=float(item["HR Power"]),
        eye=float(item["Eye"]),
        avoid_k=float(item["Avoid K"]),
        stuff=float(item["Stuff"]),
        movement=float(item["Movement"]),
        control=float(item["Control"]),
        speed=float(item["Speed"]),
        fielding=float(item["Fielding"]),
    )


def load_park_factors(ballpark: str, year: int) -> ParkFactors:
    df = pd.read_csv(data_path("park_factors.csv"))
    normalized = normalize_text(ballpark)

    year_rows = df.loc[pd.to_numeric(df["yearID"], errors="coerce").eq(year)].copy()
    matches = year_rows.loc[year_rows["park"].map(normalize_text).eq(normalized)]

    if matches.empty:
        partial = year_rows.loc[
            year_rows["park"].map(normalize_text).str.contains(normalized, regex=False)
            | year_rows["park"].map(lambda value: normalized in value)
        ]
        suggestions = sorted(partial["park"].dropna().astype(str).unique())[:8]
        suggestion_text = (
            f" Possible matches for {year}: {', '.join(suggestions)}."
            if suggestions
            else ""
        )
        raise ValueError(
            f"Ballpark '{ballpark}' not found for park year {year}."
            f"{suggestion_text}"
        )

    item = collapse_park_matches(matches)
    return ParkFactors(
        year=year,
        name=str(item["name"]),
        park=str(item["park"]),
        ba_lh=float(item["BA LH"]),
        doubles_lh=float(item["2B LH"]),
        triples_lh=float(item["3B LH"]),
        hr_lh=float(item["HR LH"]),
        ba_rh=float(item["BA RH"]),
        doubles_rh=float(item["2B RH"]),
        triples_rh=float(item["3B RH"]),
        hr_rh=float(item["HR RH"]),
        ba_overall=float(item["BA Overall"]),
        doubles_overall=float(item["2B Overall"]),
        triples_overall=float(item["3B Overall"]),
        hr_overall=float(item["HR Overall"]),
    )


def collapse_park_matches(matches: pd.DataFrame) -> pd.Series:
    if len(matches) == 1:
        return matches.iloc[0]

    numeric_cols = [
        "BA LH",
        "2B LH",
        "3B LH",
        "HR LH",
        "BA RH",
        "2B RH",
        "3B RH",
        "HR RH",
        "BA Overall",
        "2B Overall",
        "3B Overall",
        "HR Overall",
    ]

    first = matches.iloc[0].copy()
    first["name"] = " / ".join(matches["name"].astype(str).tolist())

    for col in numeric_cols:
        first[col] = pd.to_numeric(matches[col], errors="coerce").mean()

    return first


def era_factor(value: float) -> float:
    return conservative_factor(value, strength=0.25, lo=0.75, hi=1.30)


def conservative_factor(
    value: float,
    strength: float,
    lo: float,
    hi: float,
) -> float:
    adjusted = 1.0 + ((float(value) - 1.0) * strength)
    return max(lo, min(hi, adjusted))


def data_path(filename: str):
    return files("ootp_opt.data").joinpath(filename)


def none_if_zero(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    return int(value)


def none_if_blank(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def normalize_text(value: Any) -> str:
    return " ".join(str(value).lower().strip().split())


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
