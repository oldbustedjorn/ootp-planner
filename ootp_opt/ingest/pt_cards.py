from pathlib import Path
from typing import Sequence

import pandas as pd

# For now, just a toy schema. We'll adapt this to real PT exports later.
REQUIRED_COLUMNS: Sequence[str] = ["player_name", "position", "contact", "power", "eye"]


def load_pt_cards_csv(path: Path) -> pd.DataFrame:
    """Load a PT-style cards CSV and validate basic columns.

    Later, this can become:
      - load different PT CSV variants
      - normalize funky column names
      - handle tournaments vs regular, etc.
    """
    df = pd.read_csv(path)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in {path}: {missing}")

    return df
