import asyncio
import json
import re
import typer
from pathlib import Path
from logging import getLogger
from rich.console import Console
from rich.progress import Progress
from typing_extensions import Annotated

from tiddl.cli.ctx import Context
from tiddl.cli.commands.auth import refresh
from tiddl.cli.commands.download.downloader import Downloader
from tiddl.cli.commands.download.output import RichOutput
from tiddl.cli.config import CONFIG, TRACK_QUALITY_LITERAL, ATMOS_FILTER_LITERAL
from tiddl.core.api.models.resources import Track
from tiddl.core.utils.format import format_template
from tiddl.core.metadata import add_track_metadata, Cover

sync_command = typer.Typer(name="sync")

log = getLogger(__name__)
console = Console()


def _clean_string(text: str) -> str:
    if not text:
        return ""
    keywords = (
        r"\bradio\b|\bedit\b|\bmix\b|\bremix\b|\bremaster\b|\bfeat\b"
        r"|\bft\.?|\bfeature\b|\bextended\b|\bclub\b|\boriginal\b"
        r"|\bvocal\b|\bversion\b|\blive\b"
    )
    pattern = r"\s*[(\[][^\x29\x5D]*?(?:" + keywords + r")[^\x29\x5D]*?[)\x5D]"
    prev = None
    while text != prev:
        prev = text
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*-\s*.*?(?:" + keywords + r").*?$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:feat|ft\.|feature)\.?\s+.*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _make_key(artist: str, title: str) -> str:
    a = re.sub(r'[<>:"/\\|?*]', '', _clean_string(artist)).strip()
    t = re.sub(r'[<>:"/\\|?*]', '', _clean_string(title)).strip()
    return f"{a} - {t}".lower()


def _load_library_index(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_artist_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    aliases: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                left, right = line.split("=", 1)
                aliases[left.strip()] = right.strip()
                aliases[right.strip()] = left.strip()
    except Exception:
        pass
    return aliases


def _parse_track_line(line: str) -> tuple[str, str]:
    line = re.sub(r"\.(mp3|flac|wav|m4a)$", "", line, flags=re.IGNORECASE).strip()
    if " - " in line:
        artist, title = line.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", line.strip()


def _lookup_in_library(
    artist: str, title: str, lib_idx: dict, aliases: dict[str, str]
) -> str | None:
    artist_variants = [artist]
    if artist in aliases:
        artist_variants.append(aliases[artist])

    for a in artist_variants:
        key = _make_key(a, title)
        if key in lib_idx:
            return lib_idx[key]["path"]

    return None


def _write_nsp(
    nsp_path: Path,
    name: str,
    folder_prefix: str,
    library_paths: list[str],
    music_base: str,
) -> None:
    any_entries = [{"startsWith": {"filepath": folder_prefix}}]
    for lp in library_paths:
        nsp_path_val = lp
        if music_base and nsp_path_val.startswith(music_base):
            nsp_path_val = nsp_path_val[len(music_base):].lstrip("/")
        any_entries.append({"is": {"filepath": nsp_path_val}})
    data = {"name": name, "any": any_entries, "sort": "random"}
    nsp_path.parent.mkdir(parents=True, exist_ok=True)
    nsp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _search_and_download(
    ctx: Context,
    to_download: list[tuple[str, str]],
    search_hits: list[Track],
    download_dir: Path,
    quality: TRACK_QUALITY_LITERAL,
    threads: int,
    dolby_atmos: ATMOS_FILTER_LITERAL,
) -> None:
    if not search_hits:
        return

    ctx.obj.console.print("[cyan]Starting downloads...[/cyan]")

    rich_output = RichOutput(ctx.obj.console)

    downloader = Downloader(
        tidal_api=ctx.obj.api,
        threads_count=threads,
        rich_output=rich_output,
        track_quality=quality,
        video_quality="fhd",
        videos_filter="none",
        skip_existing=True,
        download_path=download_dir,
        scan_path=download_dir,
        match_existing_path_case=False,
        dolby_atmos_filter=dolby_atmos,
    )

    async def download_all():
        from rich.live import Live

        with Live(
            rich_output.group,
            refresh_per_second=10,
            console=ctx.obj.console,
            transient=True,
        ):
            futures = []
            for track in search_hits:
                template = "{item.artists} - {item.title}"
                try:
                    file_path = format_template(
                        template=template,
                        item=track,
                        quality=quality.upper(),
                    )
                except Exception:
                    raw_name = f"{', '.join(a.name for a in track.artists)} - {track.title}"
                    safe_name = re.sub(r'[<>:"/\\|?*]', '', raw_name).strip()
                    file_path = Path(safe_name)

                async def _dl(item=track, fp=file_path):
                    try:
                        path, was_downloaded = await downloader.download(item=item, file_path=Path(fp))
                        if (
                            CONFIG.metadata.enable
                            and path
                            and was_downloaded
                        ):
                            try:
                                cover = None
                                if item.album.cover and CONFIG.metadata.cover:
                                    cover = Cover(item.album.cover)
                                    if cover.data is None:
                                        cover.fetch_data()
                                add_track_metadata(
                                    path=path,
                                    track=item,
                                    cover_data=cover.data if cover else None,
                                )
                            except Exception as e:
                                log.error(f"Metadata error for {item.title}: {e}")
                    except Exception as e:
                        ctx.obj.console.print(f"[red]Download error: {item.title}: {e}[/red]")

                futures.append(_dl())

            await asyncio.gather(*futures)

        rich_output.show_stats()

    asyncio.run(download_all())


def _resolve_tracks(
    ctx: Context,
    lines: list[str],
    lib_idx: dict,
    aliases: dict[str, str],
) -> tuple[list[tuple[str, str]], list[str]]:
    to_download: list[tuple[str, str]] = []
    lib_matches: list[str] = []

    for line in lines:
        artist, title = _parse_track_line(line)
        if not artist or not title:
            ctx.obj.console.print(f"[yellow]Skipping malformed line: {line}[/yellow]")
            continue

        lib_path = _lookup_in_library(artist, title, lib_idx, aliases)
        if lib_path:
            lib_matches.append(lib_path)
            continue

        to_download.append((artist, title))

    return to_download, lib_matches


def _search_tidal(
    ctx: Context,
    to_download: list[tuple[str, str]],
) -> list[Track]:
    if not to_download:
        return []

    api = ctx.obj.api
    search_hits: list[Track] = []

    with Progress() as progress:
        task = progress.add_task("[cyan]Searching Tidal...[/cyan]", total=len(to_download))

        for i, (artist, title) in enumerate(to_download):
            query = f"{artist} {title}"
            try:
                results = api.get_search(query=query)
                track_hits = results.tracks.items
                if track_hits:
                    search_hits.append(track_hits[0])
                else:
                    ctx.obj.console.print(f"[yellow]  Not found: {artist} - {title}[/yellow]")
            except Exception as e:
                ctx.obj.console.print(f"[yellow]  Search error: {artist} - {title}: {e}[/yellow]")

            progress.advance(task)

    ctx.obj.console.print(
        f"[cyan]Found {len(search_hits)}/{len(to_download)} on Tidal[/cyan]"
    )
    return search_hits


@sync_command.callback(no_args_is_help=True)
def sync_callback(ctx: Context):
    pass


@sync_command.command()
def daily(
    ctx: Context,
    input: Annotated[
        Path,
        typer.Option("-i", "--input", help="Text file with 'artist - title' lines."),
    ] = Path("DailyTidal.txt"),
    library_index: Annotated[
        Path,
        typer.Option("-l", "--library", help="Path to library_index.json."),
    ] = Path("/music/library_index.json"),
    aliases_path: Annotated[
        Path,
        typer.Option("-a", "--aliases", help="Artist aliases file (Name = Alias)."),
    ] = Path("artist_aliases.txt"),
    download_dir: Annotated[
        Path,
        typer.Option("-p", "--path", help="Directory for downloading new tracks."),
    ] = Path("/music/DailyTidal"),
    music_base: Annotated[
        str,
        typer.Option(
            "--music-base",
            help="Navidrome music folder path to strip from library paths in NSP.",
        ),
    ] = "/Volumes/DeliRAID5/Media/Music",
    nsp_path: Annotated[
        Path,
        typer.Option("-n", "--nsp", help="Path to output .nsp playlist file."),
    ] = Path("/music/Playlists/Daily_Tidal.nsp"),
    nsp_folder: Annotated[
        str,
        typer.Option("-f", "--folder", help="NSP folder prefix for downloaded tracks."),
    ] = "DailyTidal/",
    quality: Annotated[
        TRACK_QUALITY_LITERAL,
        typer.Option("-q", "--quality", help="Download quality."),
    ] = "normal",
    threads: Annotated[
        int,
        typer.Option("-t", "--threads", help="Concurrent download threads."),
    ] = 4,
    dolby_atmos: Annotated[
        ATMOS_FILTER_LITERAL,
        typer.Option("--dolby-atmos", help="Dolby Atmos filter."),
    ] = "allow",
):
    """
    Sync daily playlist: check library, download missing tracks, build NSP playlist.
    """

    ctx.invoke(refresh)

    if not input.exists():
        ctx.obj.console.print(f"[bold red]File not found: {input}[/bold red]")
        raise typer.Exit(1)

    lines = [l.strip() for l in input.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        ctx.obj.console.print(f"[bold red]No entries found in {input}[/bold red]")
        raise typer.Exit(1)

    ctx.obj.console.print(f"[cyan]Loaded {len(lines)} tracks from {input}[/cyan]")

    lib_idx = _load_library_index(library_index)
    if lib_idx:
        ctx.obj.console.print(f"[cyan]Library index: {len(lib_idx)} tracks[/cyan]")
    else:
        ctx.obj.console.print("[yellow]Library index not found or empty, all tracks will be downloaded[/yellow]")

    aliases = _load_artist_aliases(aliases_path)
    if aliases:
        ctx.obj.console.print(f"[cyan]Loaded {len(aliases)} artist aliases[/cyan]")

    to_download, lib_matches = _resolve_tracks(ctx, lines, lib_idx, aliases)

    ctx.obj.console.print(
        f"[cyan]Library hits: {len(lib_matches)}, to download: {len(to_download)}[/cyan]"
    )

    search_hits = _search_tidal(ctx, to_download)
    _search_and_download(ctx, to_download, search_hits, download_dir, quality, threads, dolby_atmos)

    _write_nsp(nsp_path, "Daily Tidal", nsp_folder, lib_matches, music_base)
    ctx.obj.console.print(
        f"[bold green]Playlist saved to {nsp_path} "
        f"({len(lib_matches)} library + {nsp_folder}folder)[/bold green]"
    )


@sync_command.command(name="radar")
def radar(
    ctx: Context,
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Temp file for new-tracks export."),
    ] = Path("NewTidal.txt"),
    library_index: Annotated[
        Path,
        typer.Option("-l", "--library", help="Path to library_index.json."),
    ] = Path("/music/library_index.json"),
    aliases_path: Annotated[
        Path,
        typer.Option("-a", "--aliases", help="Artist aliases file (Name = Alias)."),
    ] = Path("artist_aliases.txt"),
    download_dir: Annotated[
        Path,
        typer.Option("-p", "--path", help="Directory for downloading new tracks."),
    ] = Path("/music/ReleaseRadar"),
    music_base: Annotated[
        str,
        typer.Option(
            "--music-base",
            help="Navidrome music folder path to strip from library paths in NSP.",
        ),
    ] = "/Volumes/DeliRAID5/Media/Music",
    nsp_path: Annotated[
        Path,
        typer.Option("-n", "--nsp", help="Path to output .nsp playlist file."),
    ] = Path("/music/Playlists/Release Radar.nsp"),
    nsp_folder: Annotated[
        str,
        typer.Option("-f", "--folder", help="NSP folder prefix for downloaded tracks."),
    ] = "ReleaseRadar/",
    quality: Annotated[
        TRACK_QUALITY_LITERAL,
        typer.Option("-q", "--quality", help="Download quality."),
    ] = "normal",
    threads: Annotated[
        int,
        typer.Option("-t", "--threads", help="Concurrent download threads."),
    ] = 4,
    dolby_atmos: Annotated[
        ATMOS_FILTER_LITERAL,
        typer.Option("--dolby-atmos", help="Dolby Atmos filter."),
    ] = "allow",
):
    """
    Sync Release Radar: fetch new tracks from Tidal, check library, download missing, build NSP.
    """

    from tiddl.core.api.client import API_URL

    ctx.invoke(refresh)

    ctx.obj.console.print("[cyan]Fetching new tracks from Tidal home...[/cyan]")

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

    lines: list[str] = []
    offset = 0
    limit = 50

    while offset < total_items:
        page_res = client.session.get(
            f"{API_URL}/{data_api_path}",
            params={
                "countryCode": ctx.obj.api.country_code,
                "deviceType": "BROWSER",
                "locale": "en_US",
                "limit": limit,
                "offset": offset,
            },
        )
        if page_res.status_code != 200:
            break
        items = page_res.json().get("items", [])
        if not items:
            break
        for item in items:
            artist = ", ".join(a["name"] for a in item.get("artists", []))
            title = item.get("title", "")
            if artist and title:
                lines.append(f"{artist} - {title}")
        offset += limit

    if not lines:
        ctx.obj.console.print("[bold red]No new tracks found[/bold red]")
        raise typer.Exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ctx.obj.console.print(f"[cyan]Exported {len(lines)} new tracks to {output}[/cyan]")

    lib_idx = _load_library_index(library_index)
    if lib_idx:
        ctx.obj.console.print(f"[cyan]Library index: {len(lib_idx)} tracks[/cyan]")
    else:
        ctx.obj.console.print("[yellow]Library index not found or empty, all tracks will be downloaded[/yellow]")

    aliases = _load_artist_aliases(aliases_path)
    if aliases:
        ctx.obj.console.print(f"[cyan]Loaded {len(aliases)} artist aliases[/cyan]")

    to_download, lib_matches = _resolve_tracks(ctx, lines, lib_idx, aliases)

    ctx.obj.console.print(
        f"[cyan]Library hits: {len(lib_matches)}, to download: {len(to_download)}[/cyan]"
    )

    search_hits = _search_tidal(ctx, to_download)
    _search_and_download(ctx, to_download, search_hits, download_dir, quality, threads, dolby_atmos)

    _write_nsp(nsp_path, "Release Radar", nsp_folder, lib_matches, music_base)
    ctx.obj.console.print(
        f"[bold green]Playlist saved to {nsp_path} "
        f"({len(lib_matches)} library + {nsp_folder}folder)[/bold green]"
    )
