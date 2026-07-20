from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class BuildTimingStage:
    name: str
    seconds: float


@dataclass(frozen=True)
class BuildTiming:
    stages: tuple[BuildTimingStage, ...]
    total_seconds: float

    def summary_rows(self, total_label: str = "Total build time") -> list[tuple[str, str]]:
        rows = [(stage.name, format_duration(stage.seconds)) for stage in self.stages]
        rows.append((total_label, format_duration(self.total_seconds)))
        return rows


class BuildTimer:
    def __init__(self, clock: Callable[[], float] = perf_counter) -> None:
        self._clock = clock
        self._started_at = clock()
        self._checkpoint_at = self._started_at
        self._stages: list[BuildTimingStage] = []

    def checkpoint(self, name: str) -> None:
        now = self._clock()
        self._stages.append(BuildTimingStage(name=name, seconds=now - self._checkpoint_at))
        self._checkpoint_at = now

    def snapshot(self) -> BuildTiming:
        return BuildTiming(
            stages=tuple(self._stages),
            total_seconds=self._clock() - self._started_at,
        )


def format_duration(seconds: float) -> str:
    if seconds < 0.001:
        return "<0.001 s"
    return f"{seconds:.3f} s"
