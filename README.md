# Tidal Downloader (Docker)

Containerized version of [tiddl](https://github.com/oskvr37/tiddl) — a CLI tool for downloading tracks and exporting collections from Tidal. Runs in OrbStack / Docker.

## Project Structure

```
tiddl/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── data/                    # Persistent data (volume)
│   ├── tiddl/
│   │   ├── config.toml      # tiddl configuration
│   │   ├── auth.json        # Auth tokens (created on login)
│   │   └── api_cache.sqlite # API request cache
│   ├── Music/               # Downloaded music
│   ├── mixes.txt            # Mix URLs for daily export
│   ├── artist_blocklist.txt # Blocked artists (one per line)
│   ├── artist_aliases.txt   # Artist aliases (Name = Alias)
│   ├── all_tracks.txt       # All tracks from mixes (filtered)
│   ├── DailyTidal.txt       # Random selection of 100 tracks
│   └── NewTidal.txt         # New tracks from Tidal Home
└── tiddl/                   # Source code (fork)

External paths (mounted as /music):
├── DailyTidal/              # Downloaded daily tracks (not in library)
├── ReleaseRadar/            # Downloaded radar tracks
├── Playlists/
│   ├── Daily_Tidal.nsp      # Navidrome Smart Playlist
│   └── Release Radar.nsp    # Navidrome Smart Playlist
└── library_index.json       # Existing collection index
```

## Command Reference

All commands run via `docker compose run --rm tiddl`. The `--rm` flag removes the container after execution; data is preserved in `./data/`.

```bash
# Auth
tiddl auth login                                              # First-time login
tiddl auth refresh                                            # Refresh token

# Export
tiddl export daily                                            # My Mix 1-8 → all_tracks.txt + DailyTidal.txt (100 tracks)
tiddl export new-tracks -o NewTidal.txt                       # New Tracks from Tidal Home → NewTidal.txt
tiddl export playlist <url> -o tracks.txt                     # Mix/playlist → text file

# Download
tiddl download url <url>                                      # Track / album / playlist / mix
tiddl download -q normal -p /data/DailyTidal from-file <txt>  # From text file

# Sync (export + library check + download + NSP)
tiddl sync daily                                              # Daily Tidal in one command
tiddl sync radar                                              # Release Radar in one command

# Automation (script)
./sync_daily.sh daily                                         # Run Daily manually
./sync_daily.sh radar                                         # Run Radar manually
./sync_daily.sh all                                           # Both tasks
```

## Getting Started

### Authentication

First-time use requires Tidal authentication:

```bash
docker compose run --rm tiddl auth login
```

A link will appear — open it in a browser and confirm login. The token is saved to `data/tiddl/auth.json` and reused on subsequent runs.

Refresh token:

```bash
docker compose run --rm tiddl auth refresh
```

Logout:

```bash
docker compose run --rm tiddl auth logout
```

### Downloading

Download a track / album / playlist / mix by URL:

```bash
docker compose run --rm tiddl download url "https://tidal.com/browse/track/103805726"
docker compose run --rm tiddl download url "https://tidal.com/browse/album/103805723"
```

Short format is also accepted: `track/103805726`, `album/103805723`.

Additional download options:

```bash
# Quality (low / normal / high / max)
docker compose run --rm tiddl download url <url> -q max

# Custom path
docker compose run --rm tiddl download url <url> -p "/data/Music/Albums"

# Filename template
docker compose run --rm tiddl download url <url> -o "{album.artist}/{album.title}/{item.number:02d}. {item.title}"

# Download from favorites
docker compose run --rm tiddl download fav

# Search and download
docker compose run --rm tiddl download search "Pink Floyd"
```

Music is saved to `data/Music/`.

### Download from Text File

The `download from-file` command reads a file with tracks in `artist - title` format (one per line), searches Tidal for each entry, and downloads the first match.

```bash
# DailyTidal.txt → DailyTidal folder, Normal quality (AAC 320kbps)
docker compose run --rm tiddl download -q normal -p /data/DailyTidal -o "{item.artists} - {item.title}" --dolby-atmos allow from-file DailyTidal.txt

# NewTidal.txt → NewTidal folder, Normal quality
docker compose run --rm tiddl download -q normal -p /data/NewTidal -o "{item.artists} - {item.title}" --dolby-atmos allow from-file NewTidal.txt
```

Download options are set at the `download` command level:

| Option | Description |
|--------|-------------|
| `-q normal` | AAC 320kbps (.m4a) |
| `-q high` | FLAC 16-bit |
| `-q max` | FLAC up to 24-bit |
| `-p /data/name` | Download directory |
| `-o "template"` | Filename template |
| `--dolby-atmos allow` | Don't skip Dolby Atmos tracks |

### Export

The `export` command generates text lists of tracks in `artist - title` format.

#### Export a Playlist or Mix

```bash
# By URL (auto-detects type: playlist / mix)
docker compose run --rm tiddl export playlist "https://tidal.com/mix/002e97fa4491895af2359ec016eb34" -o tracks.txt

# By UUID
docker compose run --rm tiddl export playlist "002e97fa4491895af2359ec016eb34" -o tracks.txt
```

#### Daily Selection from Mixes

Create `data/mixes.txt` with mix URLs (one per line):

```
https://tidal.com/mix/002031a111d26d855f13df60ef8035
https://tidal.com/mix/0020a08efcb74f0b86c8363bf5efae
https://tidal.com/mix/002a3c2e11ce412d0ca12bb451730f
```

Optionally create `data/artist_blocklist.txt` with artist names to exclude (one per line):

```
Taylor Swift
Eminem
```

Run the export:

```bash
docker compose run --rm tiddl export daily
```

Result:
- `data/all_tracks.txt` — unique tracks from all mixes (excluding blocklisted artists)
- `data/DailyTidal.txt` — 100 random tracks from the filtered list

Options:

| Option | Default | Description |
|--------|---------|-------------|
| `-i` | `mixes.txt` | File with URL list |
| `-n` | `100` | Number of tracks in daily selection |
| `-o` | `all_tracks.txt` | File with all tracks |
| `-d` | `DailyTidal.txt` | File with daily selection |
| `-b` | `artist_blocklist.txt` | Artist blocklist file |

Example with custom parameters:

```bash
docker compose run --rm tiddl export daily -i my_mixes.txt -n 50 -o full.txt -d daily50.txt -b my_blocklist.txt
```

#### New Tracks Suggestions

Exports the "New Tracks" list from the Tidal home page:

```bash
docker compose run --rm tiddl export new-tracks -o NewTidal.txt
```

### Sync Daily

The `sync daily` command is a full pipeline for the daily playlist:

1. Reads `DailyTidal.txt` (list of `artist - title`)
2. Checks each track against `library_index.json` — if already in the collection, it's not downloaded but added to the playlist by direct path
3. Missing tracks are searched on Tidal and downloaded to `/music/DailyTidal/`
4. Generates a Navidrome Smart Playlist (`Daily_Tidal.nsp`) with references to both types of tracks

Library matching uses the same normalization as `scan_library.py` from spotify-soulseek-bridge: qualifiers like Remastered, Radio Edit, feat. etc. are stripped, and the key is formed as lowercase `artist - title`.

If an artist has an alternative name (rename, transliteration), create `data/artist_aliases.txt`:

```
Electric Callboy = Eskimo Callboy
```

Format: `Name = Alias`, one pair per line. Aliases are bidirectional.

```bash
docker compose run --rm tiddl sync daily
```

Options:

| Option | Default | Description |
|--------|---------|-------------|
| `-i` | `DailyTidal.txt` | Input file with track list |
| `-l` | `/music/library_index.json` | Path to library index |
| `-a` | `artist_aliases.txt` | Artist aliases file |
| `-p` | `/music/DailyTidal` | Directory for new downloads |
| `--music-base` | `/Volumes/DeliRAID5/Media/Music` | Navidrome base path (stripped from NSP paths) |
| `-n` | `/music/Playlists/Daily_Tidal.nsp` | Path to NSP playlist |
| `-f` | `DailyTidal/` | NSP folder prefix for downloaded tracks |
| `-q` | `normal` | Download quality |
| `-t` | `4` | Concurrent download threads |
| `--dolby-atmos` | `allow` | Dolby Atmos filter |

The playlist contains:
- `startsWith: DailyTidal/` — all downloaded tracks
- `is: <library path>` — tracks found in the collection

### Sync Radar

The `sync radar` command is a pipeline for Release Radar:

1. Fetches "New Tracks" from the Tidal home page (built-in `export new-tracks`)
2. Checks each track against `library_index.json`
3. Downloads missing tracks to `/music/ReleaseRadar/`
4. Updates the NSP playlist

All in one command:

```bash
docker compose run --rm tiddl sync radar
```

Options are the same as `sync daily`, but with different defaults:

| Option | Default | Description |
|--------|---------|-------------|
| `-o` | `NewTidal.txt` | Temp export file |
| `-p` | `/music/ReleaseRadar` | Download directory |
| `-n` | `/music/Playlists/Release Radar.nsp` | Path to NSP |
| `-f` | `ReleaseRadar/` | NSP folder prefix |

## Automation

The `sync_daily.sh` script accepts an argument: `daily`, `radar`, or `all`.

| Task | Schedule | Command |
|------|----------|---------|
| Daily (`export daily` + `sync daily`) | Every day at 5:00, runs every 3 days | `sync_daily.sh daily` |
| Radar (`sync radar`) | Every Sunday at 5:00 | `sync_daily.sh radar` |
| Both | — | `sync_daily.sh all` |

Logs are written to `data/sync.log`.

### Setup via launchd

Two plist files — a separate schedule for each task:

```bash
# Install both
cp com.tiddl.sync-daily.plist com.tiddl.sync-radar.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tiddl.sync-daily.plist
launchctl load ~/Library/LaunchAgents/com.tiddl.sync-radar.plist

# Check status
launchctl list | grep tiddl

# Remove
launchctl unload ~/Library/LaunchAgents/com.tiddl.sync-daily.plist
launchctl unload ~/Library/LaunchAgents/com.tiddl.sync-radar.plist
rm ~/Library/LaunchAgents/com.tiddl.sync-daily.plist ~/Library/LaunchAgents/com.tiddl.sync-radar.plist
```

### Manual Run

```bash
/Volumes/DeliRAID5/Dockers/tiddl/sync_daily.sh daily   # Daily only
/Volumes/DeliRAID5/Dockers/tiddl/sync_daily.sh radar   # Radar only
/Volumes/DeliRAID5/Dockers/tiddl/sync_daily.sh all     # Both tasks
```

## Configuration

File `data/tiddl/config.toml`. Key parameters:

```toml
[download]
track_quality = "high"       # low / normal / high / max
download_path = "/data/Music"
skip_existing = true
threads_count = 4

[metadata]
enable = true
```

Full config example: [docs/config.example.toml](docs/config.example.toml).

## Audio Quality

| Quality | Format | Parameters |
|---------|--------|------------|
| LOW | .m4a | 96 kbps |
| NORMAL | .m4a | 320 kbps |
| HIGH | .flac | 16-bit, 44.1 kHz |
| MAX | .flac | up to 24-bit, 192 kHz |

## Changes from Upstream tiddl

1. **`tiddl/core/auth/models.py`** — made `facebookUid` field optional (`Optional[int] = None`) since Tidal API stopped returning it
2. **`tiddl/cli/commands/export.py`** — added `export` command with subcommands:
   - `playlist` — export playlist/mix to a text file
   - `daily` — export tracks from multiple mixes + random selection
   - `new-tracks` — export "New Tracks" from Tidal home page
3. **`tiddl/cli/commands/subcommands/from_file.py`** — added `download from-file` subcommand: download tracks from a text list `artist - title`
4. **`tiddl/cli/commands/__init__.py`** — registered `export` and `sync` commands
5. **`tiddl/cli/commands/sync.py`** — added `sync daily` and `sync radar` commands: library check via library_index.json, download missing tracks, generate NSP playlists
6. **`Dockerfile`** — updated: Python 3.13 Alpine, ffmpeg, `TIDDL_PATH=/data/tiddl`, `ENTRYPOINT ["tiddl"]`
7. **`docker-compose.yml`** — volumes: `./data:/data`, `/Volumes/DeliRAID5/Media/Music:/music`; tty + stdin_open for interactive mode
8. **`.dockerignore`** — excludes `data/` from build context
9. **`sync_daily.sh`** + **`com.tiddl.sync-*.plist`** — launchd automation: Daily every 3 days, Radar on Sundays

## Disclaimer

This app is for personal use only and is not affiliated with Tidal. Users must ensure their use complies with Tidal's terms of service and local copyright laws. Downloaded tracks are for personal use and may not be shared or redistributed. The developer assumes no responsibility for misuse of this app.
