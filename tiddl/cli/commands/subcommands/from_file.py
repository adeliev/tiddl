import typer
from pathlib import Path
from typing_extensions import Annotated

from tiddl.cli.ctx import Context
from tiddl.cli.utils.resource import TidalResource


from_file_subcommand = typer.Typer()


@from_file_subcommand.command()
def from_file(
    ctx: Context,
    input: Annotated[
        Path,
        typer.Argument(help="Text file with 'artist - title' lines, one per line."),
    ],
):
    """
    Download tracks from a text file. Each line must be 'artist - title'.

    Searches Tidal for each entry and picks the best match.

    Use download-level options to control quality and path:

        tiddl download -q normal -p /data/DailyTidal from-file DailyTidal.txt
    """

    if not input.exists():
        ctx.obj.console.print(f"[bold red]File not found: {input}[/bold red]")
        raise typer.Exit(1)

    lines = [line.strip() for line in input.read_text().splitlines() if line.strip()]
    if not lines:
        ctx.obj.console.print(f"[bold red]No entries found in {input}[/bold red]")
        raise typer.Exit(1)

    ctx.obj.console.print(f"[cyan]Searching {len(lines)} tracks from {input}[/cyan]")

    api = ctx.obj.api
    found = 0
    missed = 0

    for i, line in enumerate(lines, 1):
        results = api.get_search(query=line)

        track_hits = results.tracks.items
        if not track_hits:
            ctx.obj.console.print(f"[yellow]  {i}. Not found: {line}[/yellow]")
            missed += 1
            continue

        track = track_hits[0]
        ctx.obj.resources.append(TidalResource(type="track", id=str(track.id)))
        found += 1

        ctx.obj.console.print(
            f"[dim]  {i}. {', '.join(a.name for a in track.artists)} - {track.title}[/dim]"
        )

    ctx.obj.console.print(
        f"[bold green]Found {found}/{len(lines)} tracks ({missed} not found)[/bold green]"
    )
