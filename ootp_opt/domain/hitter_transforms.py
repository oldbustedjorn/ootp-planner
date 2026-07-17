from __future__ import annotations

import math
from typing import Any


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default

        result = float(value)

        if math.isnan(result):
            return default

        return result
    except (TypeError, ValueError):
        return default


def logistic_value(
    rating: float,
    midpoint: float,
    steepness: float,
    output_max: float = 100.0,
) -> float:
    x = safe_float(rating)
    return output_max / (1.0 + math.exp(-steepness * (x - midpoint)))


def power_value(power: object, midpoint: float | None = None) -> float:
    """Power appears to have accelerating returns."""
    if midpoint is not None:
        return environment_power_value(power, midpoint=midpoint)

    x = clamp(safe_float(power), 0.0, 200.0)
    n = x / 100.0
    value = 100.0 * (n**1.45)
    return clamp(value, 0.0, 180.0)


def environment_power_value(power: object, midpoint: float) -> float:
    """Power value centered on the expected opposing HRA environment."""
    x = clamp(safe_float(power), 0.0, 250.0)
    center = clamp(safe_float(midpoint, 80.0), 20.0, 180.0)
    value = logistic_value(
        rating=x,
        midpoint=center,
        steepness=0.035,
        output_max=180.0,
    )
    return clamp(value, 0.0, 180.0)


def avoid_k_value(avoid_k: object, midpoint: float | None = None) -> float:
    """Avoid K appears threshold-like: low values are very costly."""
    x = clamp(safe_float(avoid_k), 0.0, 200.0)
    value = logistic_value(
        rating=x,
        midpoint=80.0 if midpoint is None else safe_float(midpoint, 80.0),
        steepness=0.055,
        output_max=100.0,
    )
    return clamp(value, 0.0, 100.0)


def eye_value(eye: object, midpoint: float | None = None) -> float:
    """Eye has a strong smooth positive relationship with walk rate."""
    x = clamp(safe_float(eye), 0.0, 200.0)
    value = logistic_value(
        rating=x,
        midpoint=75.0 if midpoint is None else safe_float(midpoint, 75.0),
        steepness=0.045,
        output_max=115.0,
    )
    return clamp(value, 0.0, 115.0)


def gap_value(gap: object, midpoint: float | None = None) -> float:
    """Gap has positive but diminishing returns."""
    if midpoint is not None:
        return environment_gap_value(gap, midpoint=midpoint)

    x = clamp(safe_float(gap), 0.0, 200.0)
    value = 115.0 * (1.0 - math.exp(-0.018 * x))
    return clamp(value, 0.0, 115.0)


def environment_gap_value(gap: object, midpoint: float) -> float:
    """Gap value centered on the expected opposing pBABIP environment."""
    x = clamp(safe_float(gap), 0.0, 250.0)
    center = clamp(safe_float(midpoint, 80.0), 20.0, 180.0)
    value = logistic_value(
        rating=x,
        midpoint=center,
        steepness=0.032,
        output_max=115.0,
    )
    return clamp(value, 0.0, 115.0)


def babip_value(babip: object, midpoint: float | None = None) -> float:
    """BABIP matters, but the relationship is noisy and should be moderate."""
    x = clamp(safe_float(babip), 0.0, 200.0)
    value = logistic_value(
        rating=x,
        midpoint=75.0 if midpoint is None else safe_float(midpoint, 75.0),
        steepness=0.035,
        output_max=110.0,
    )
    return clamp(value, 0.0, 110.0)
