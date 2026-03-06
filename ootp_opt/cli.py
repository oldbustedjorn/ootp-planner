from __future__ import annotations

from pathlib import Path
from typing import Literal

import typer
from rich.console import Console

from ootp_opt.config import load_config
from ootp_opt.export.csv_export import write_csv
from ootp_opt.services.rating_service import rate_cards_service

app = typer.Typer(help="OOTP Optimizer")
console = Console()

Profile = Literal["hitters", "pitchers", "both"]


def _default_output(output_dir: Path, profile: str) -> Path:
    if profile == "hitters":
        return output_dir / "ratings_hitters.csv"
    if profile == "pitchers":
        return output_dir / "ratings_pitchers.csv"
    raise ValueError(f"Unsupported profile for default output: {profile}")


@app.command()
def rate_cards(
    input: Path | None = typer.Argument(None, help="Path to PT export CSV"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output CSV path"),
    profile: Profile | None = typer.Option(None, "--profile", help="hitters|pitchers|both"),
    config_path: Path = typer.Option(Path("config.toml"), "--config", help="Path to config TOML"),
) -> None:
    """Rate cards from CSVs and output ranked CSVs."""
    config = load_config(config_path)

    paths = config.get("paths", {})
    defaults = config.get("defaults", {})

    if profile is None:
        profile = defaults.get("profile", "both")

    output_dir = Path(paths.get("output_dir", "outputs"))

    if profile == "hitters":
        input_path = input or Path(paths["hitters_csv"])
        output_path = output or _default_output(output_dir, "hitters")

        console.print(f"[cyan]Reading hitters[/] {input_path}")
        df = rate_cards_service(input_path=input_path, profile="hitters", config=config)
        write_csv(df, output_path)
        console.print(f"[green]Wrote[/] {len(df)} rows → {output_path}")

    elif profile == "pitchers":
        input_path = input or Path(paths["pitchers_csv"])
        output_path = output or _default_output(output_dir, "pitchers")

        console.print(f"[cyan]Reading pitchers[/] {input_path}")
        df = rate_cards_service(input_path=input_path, profile="pitchers", config=config)
        write_csv(df, output_path)
        console.print(f"[green]Wrote[/] {len(df)} rows → {output_path}")

    elif profile == "both":
        hitters_input = Path(paths["hitters_csv"])
        pitchers_input = Path(paths["pitchers_csv"])

        hitters_output = output_dir / "ratings_hitters.csv"
        pitchers_output = output_dir / "ratings_pitchers.csv"

        console.print(f"[cyan]Reading hitters[/] {hitters_input}")
        hitters_df = rate_cards_service(input_path=hitters_input, profile="hitters", config=config)
        write_csv(hitters_df, hitters_output)
        console.print(f"[green]Wrote[/] {len(hitters_df)} rows → {hitters_output}")

        console.print(f"[cyan]Reading pitchers[/] {pitchers_input}")
        pitchers_df = rate_cards_service(input_path=pitchers_input, profile="pitchers", config=config)
        write_csv(pitchers_df, pitchers_output)
        console.print(f"[green]Wrote[/] {len(pitchers_df)} rows → {pitchers_output}")

    else:
        raise ValueError(f"Unknown profile: {profile}")


if __name__ == "__main__":
    app()