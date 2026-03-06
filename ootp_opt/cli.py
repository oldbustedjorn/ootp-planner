from __future__ import annotations

from pathlib import Path
from typing import Literal

import typer
from rich.console import Console

from ootp_opt.export.csv_export import write_csv
from ootp_opt.services.rating_service import rate_cards_service

app = typer.Typer(help="OOTP Optimizer")
console = Console()

Profile = Literal["hitters", "pitchers"]


@app.command("rate-cards")
def rate_cards(
    input: Path = typer.Argument(..., help="Path to PT export CSV"),
    output: Path = typer.Option(
        Path("outputs/ratings.csv"),
        "--output",
        "-o",
        help="Output CSV path",
    ),
    profile: Profile = typer.Option(
        "hitters",
        "--profile",
        help="Which export type to parse: hitters|pitchers",
    ),
) -> None:
    """Rate cards from a CSV and output a ranked CSV."""
    console.print(f"[cyan]Reading[/] {input}")
    df = rate_cards_service(input_path=input, profile=profile)
    write_csv(df, output)
    console.print(f"[green]Wrote[/] {len(df)} rows → {output}")


if __name__ == "__main__":
    app()