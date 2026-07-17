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


def stuff_value(stuff: Any, midpoint: float | None = None) -> float:
    """Stuff drives strikeouts, but with diminishing returns."""
    if midpoint is not None:
        return environment_stuff_value(stuff, midpoint=midpoint)

    x = clamp(safe_float(stuff), 0.0, 200.0)
    value = 135.0 * (1.0 - math.exp(-0.018 * x))
    return clamp(value, 0.0, 135.0)


def environment_stuff_value(stuff: Any, midpoint: float) -> float:
    """Stuff value centered on the expected opposing Avoid K environment."""
    x = clamp(safe_float(stuff), 0.0, 250.0)
    center = clamp(safe_float(midpoint, 90.0), 30.0, 180.0)
    value = 145.0 / (1.0 + math.exp(-0.035 * (x - center)))
    return clamp(value, 0.0, 145.0)


def hr_rate_value(hr_rate: Any, midpoint: float | None = None) -> float:
    """HRA/HR rating is a floor stat. Low values should be punished hard."""
    x = clamp(safe_float(hr_rate), 0.0, 200.0)
    center = 82.0 if midpoint is None else safe_float(midpoint, 82.0)
    value = 125.0 / (1.0 + math.exp(-0.050 * (x - center)))
    return clamp(value, 0.0, 125.0)


def control_value(control: Any, midpoint: float | None = None) -> float:
    """Control has threshold behavior: bad control is very costly."""
    x = clamp(safe_float(control), 0.0, 200.0)
    center = 72.0 if midpoint is None else safe_float(midpoint, 72.0)
    value = 115.0 / (1.0 + math.exp(-0.050 * (x - center)))
    return clamp(value, 0.0, 115.0)


def pbabip_value(pbabip: Any, midpoint: float | None = None) -> float:
    """pBABIP is useful but noisy, so use a moderate smooth curve."""
    x = clamp(safe_float(pbabip), 0.0, 200.0)
    center = 82.0 if midpoint is None else safe_float(midpoint, 82.0)
    value = 110.0 / (1.0 + math.exp(-0.035 * (x - center)))
    return clamp(value, 0.0, 110.0)
