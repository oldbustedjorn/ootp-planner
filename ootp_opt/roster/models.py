from __future__ import annotations

from dataclasses import dataclass, field
import pandas as pd


@dataclass
class PitcherRoster:
    rotation: pd.DataFrame
    bullpen: pd.DataFrame
    lefty_specialist: pd.DataFrame
    long_man: pd.DataFrame
    unused_players: pd.DataFrame
    groups_by_key: dict[str, pd.DataFrame] = field(default_factory=dict)


@dataclass
class HitterRoster:
    starters_by_position: dict[str, pd.Series]
    bench_players: pd.DataFrame
    unused_players: pd.DataFrame
    starters_by_split: dict[str, dict[str, pd.Series]] = field(default_factory=dict)
    bench_by_split: dict[str, pd.DataFrame] = field(default_factory=dict)

    def starters_for_split(self, split: str) -> dict[str, pd.Series]:
        return self.starters_by_split.get(split, self.starters_by_position)

    def bench_for_split(self, split: str) -> pd.DataFrame:
        return self.bench_by_split.get(split, self.bench_players)
