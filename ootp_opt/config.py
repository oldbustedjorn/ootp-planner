from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib


def load_config(path: str | Path = "config.toml") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with config_path.open("rb") as f:
        return tomllib.load(f)
