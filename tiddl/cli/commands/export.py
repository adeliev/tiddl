import random
import typer
from pathlib import Path
from logging import getLogger
from rich.console import Console
from rich.progress import Progress
from typing_extensions import Annotated

from tiddl.cli.ctx import Context
from tiddl.cli.commands.auth import refresh
from tiddl.core.api.client import API_URL
from tiddl.core.api.models.base import MixItems, PlaylistItems
from tiddl.core.api.models.resources import Track

export_command = typer.Typer(name="export")

log = getLogger(__name__)
console = Console()


@export_command.callback(no_args_is_help=True)
def export_callback(ctx: Context):
    """
    Export Tidal data.
    """

    ctx.invoke(refresh)


@export_command.command()
def playlist(
    ctx: Context,
    playlist_id: Annotated[
        str,
        typer.Argument(help="Playlist/Mix UUID or URL."),
    ],
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Output text file path."),
    ] = Path("playlist.txt"),
):
    """
    Export playlist or mix tracks to a text file as 'artist - title'.
    """

    raw_id = _extract_id(playlist_id)
    resource_type, resource_id = _detect_type(playlist_id, raw_id)

    api = ctx.obj.api

    if resource_type == "mix":
        tracks = _get_mix_tracks(api, resource_id)
        label = f"Mix {resource_id}"
    else:
        playlist_info = api.get_playlist(resource_id)
        total = playlist_info.numberOfTracks
        ctx.obj.console.print(
            f"[cyan]Playlist:[/cyan] {playlist_info.title} ({total} tracks)"
        )
        tracks = _get_playlist_tracks(api, resource_id, total)
        label = playlist_info.title

    _write_tracks(tracks, output)

    ctx.obj.console.print(
        f"[bold green]Exported {len(tracks)} tracks from '{label}' to {output}[/bold green]"
    )


@export_command.command()
def daily(
    ctx: Context,
    input: Annotated[
        Path,
        typer.Option("-i", "--input", help="Text file with mix/playlist URLs, one per line."),
    ] = Path("mixes.txt"),
    count: Annotated[
        int,
        typer.Option("-n", "--count", help="Number of random tracks for daily selection."),
    ] = 100,
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Output file with all collected tracks."),
    ] = Path("all_tracks.txt"),
    daily: Annotated[
        Path,
        typer.Option("-d", "--daily", help="Output file with random daily selection."),
    ] = Path("DailyTidal.txt"),
    blocklist: Annotated[
        Path,
        typer.Option("-b", "--blocklist", help="Text file with blocked artist names, one per line."),
    ] = Path("artist_blocklist.txt"),
):
    """
    Export tracks from multiple mixes/playlists, then pick random tracks for a daily list.
    """

    if not input.exists():
        ctx.obj.console.print(f"[bold red]File not found: {input}[/bold red]")
        raise typer.Exit(1)

    urls = [line.strip() for line in input.read_text().splitlines() if line.strip()]
    if not urls:
        ctx.obj.console.print(f"[bold red]No URLs found in {input}[/bold red]")
        raise typer.Exit(1)

    ctx.obj.console.print(f"[cyan]Found {len(urls)} URLs in {input}[/cyan]")

    blocked_artists: set[str] = set()
    if blocklist.exists():
        blocked_artists = {
            line.strip().lower()
            for line in blocklist.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        if blocked_artists:
            ctx.obj.console.print(
                f"[cyan]Loaded {len(blocked_artists)} blocked artists from {blocklist}[/cyan]"
            )
    else:
        ctx.obj.console.print(
            f"[dim]No blocklist file at {blocklist}, skipping artist filtering[/dim]"
        )

    api = ctx.obj.api
    all_tracks: list[Track] = []
    seen_ids: set[int] = set()

    with Progress() as progress:
        task = progress.add_task("[cyan]Fetching tracks...[/cyan]", total=len(urls))

        for i, url in enumerate(urls):
            raw_id = _extract_id(url)
            resource_type, resource_id = _detect_type(url, raw_id)

            try:
                if resource_type == "mix":
                    tracks = _get_mix_tracks(api, resource_id)
                else:
                    playlist_info = api.get_playlist(resource_id)
                    tracks = _get_playlist_tracks(
                        api, resource_id, playlist_info.numberOfTracks
                    )
            except Exception as e:
                ctx.obj.console.print(f"[yellow]Skipping {url}: {e}[/yellow]")
                progress.advance(task)
                continue

            new = 0
            for t in tracks:
                if t.id not in seen_ids:
                    seen_ids.add(t.id)
                    all_tracks.append(t)
                    new += 1

            progress.advance(task)
            progress.update(
                task,
                description=f"[cyan]Fetched {i+1}/{len(urls)} — {new} new, {len(all_tracks)} total[/cyan]",
            )

    if blocked_artists:
        filtered_tracks = [
            t for t in all_tracks
            if not any(a.name.lower() in blocked_artists for a in t.artists)
        ]
        removed = len(all_tracks) - len(filtered_tracks)
        ctx.obj.console.print(
            f"[cyan]Blocked {removed} tracks by blocklisted artists, {len(filtered_tracks)} remaining[/cyan]"
        )
        all_tracks = filtered_tracks

    _write_tracks(all_tracks, output)
    ctx.obj.console.print(
        f"[bold green]Exported {len(all_tracks)} unique tracks to {output}[/bold green]"
    )

    pick_count = min(count, len(all_tracks))
    picked = random.sample(all_tracks, pick_count)
    _write_tracks(picked, daily)
    ctx.obj.console.print(
        f"[bold green]Daily selection: {pick_count} tracks saved to {daily}[/bold green]"
    )


@export_command.command(name="new-tracks")
def new_tracks(
    ctx: Context,
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Output text file path."),
    ] = Path("NewTidal.txt"),
):
    """
    Export 'New Tracks' suggestions from Tidal home page.
    """

    client = ctx.obj.api.client

    res = client.session.get(
        f"{API_URL}/pages/home",
        params={
            "countryCode": ctx.obj.api.country_code,
            "deviceType": "BROWSER",
            "locale": "en_US",
        },
    )

    if res.status_code != 200:
        ctx.obj.console.print(f"[bold red]Failed to load home page: {res.status_code}[/bold red]")
        raise typer.Exit(1)

    home_data = res.json()

    data_api_path = None
    total_items = 0

    for row in home_data.get("rows", []):
        for mod in row.get("modules", []):
            if mod.get("type") == "TRACK_LIST" and "new" in mod.get("title", "").lower():
                pl = mod.get("pagedList", {})
                data_api_path = pl.get("dataApiPath")
                total_items = pl.get("totalNumberOfItems", 0)
                break
        if data_api_path:
            break

    if not data_api_path:
        ctx.obj.console.print("[bold red]'New Tracks' module not found on home page[/bold red]")
        raise typer.Exit(1)

    ctx.obj.console.print(f"[cyan]Found 'New Tracks' — {total_items} items[/cyan]")

    tracks = _get_page_tracks(client, data_api_path, ctx.obj.api.country_code, total_items)

    _write_tracks(tracks, output)
    ctx.obj.console.print(
        f"[bold green]Exported {len(tracks)} new tracks to {output}[/bold green]"
    )


def _extract_id(raw: str) -> str:
    if "/" in raw:
        return raw.rsplit("/", 1)[-1].strip()
    return raw


def _detect_type(raw_url: str, resource_id: str) -> tuple[str, str]:
    lower = raw_url.lower()
    if "/mix/" in lower or lower.startswith("mix/"):
        return "mix", resource_id
    return "playlist", resource_id


def _write_tracks(tracks: list[Track] | list[dict], path: Path) -> None:
    lines = []
    for t in tracks:
        if isinstance(t, dict):
            artist = ", ".join(a["name"] for a in t.get("artists", []))
            lines.append(f"{artist} - {t['title']}")
        else:
            artist = ", ".join(a.name for a in t.artists)
            lines.append(f"{artist} - {t.title}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_playlist_tracks(api, playlist_uuid: str, total: int) -> list[Track]:
    from tiddl.core.api.api import Limits

    tracks: list[Track] = []
    offset = 0
    limit = Limits.PLAYLIST_ITEMS_MAX

    while offset < total:
        page: PlaylistItems = api.get_playlist_items(
            playlist_uuid, limit=limit, offset=offset
        )
        for item in page.items:
            if item.type == "track":
                tracks.append(item.item)
        offset += limit

    return tracks


def _get_mix_tracks(api, mix_id: str) -> list[Track]:
    from tiddl.core.api.api import Limits

    tracks: list[Track] = []
    offset = 0
    limit = Limits.MIX_ITEMS_MAX

    while True:
        page: MixItems = api.get_mix_items(mix_id, limit=limit, offset=offset)
        for item in page.items:
            tracks.append(item.item)
        if offset + limit >= page.totalNumberOfItems:
            break
        offset += limit

    return tracks


def _get_page_tracks(client, data_api_path: str, country_code: str, total: int) -> list[dict]:
    tracks: list[dict] = []
    offset = 0
    limit = 50

    while offset < total:
        res = client.session.get(
            f"{API_URL}/{data_api_path}",
            params={
                "countryCode": country_code,
                "deviceType": "BROWSER",
                "locale": "en_US",
                "limit": limit,
                "offset": offset,
            },
        )

        if res.status_code != 200:
            break

        data = res.json()
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            tracks.append(item)

        offset += limit

    return tracks
