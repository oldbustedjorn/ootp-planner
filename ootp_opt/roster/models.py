from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class PitcherRoster:
    rotation: pd.DataFrame
    bullpen: pd.DataFrame
    lefty_specialist: pd.DataFrame
    long_man: pd.DataFrame
    unused_players: pd.DataFrame


@dataclass
class HitterRoster:
    starters_by_position: dict[str, pd.Series]
    bench_players: pd.DataFrame
    unused_players: pd.DataFrame
