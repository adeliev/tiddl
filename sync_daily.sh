#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Volumes/DeliRAID5/Dockers/tiddl"
LOG_FILE="$PROJECT_DIR/data/sync.log"

TASK="${1:-all}"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"; }

cd "$PROJECT_DIR"

case "$TASK" in
    daily)
        MARKER="$PROJECT_DIR/data/.last_daily"
        INTERVAL=3
        now=$(date +%s)
        if [ -f "$MARKER" ]; then
            elapsed=$(( (now - $(cat "$MARKER")) / 86400 ))
            if [ "$elapsed" -lt "$INTERVAL" ]; then
                log "Daily: skipping (${elapsed}d < ${INTERVAL}d)"
                exit 0
            fi
        fi
        log "=== Starting daily sync ==="
        docker compose run --rm tiddl export daily
        docker compose run --rm tiddl sync daily
        echo "$now" > "$MARKER"
        log "=== Daily sync done ==="
        ;;
    radar)
        log "=== Starting radar sync ==="
        docker compose run --rm tiddl sync radar
        log "=== Radar sync done ==="
        ;;
    all)
        "$0" daily
        "$0" radar
        ;;
    *)
        echo "Usage: $0 {daily|radar|all}" >&2
        exit 1
        ;;
esac
