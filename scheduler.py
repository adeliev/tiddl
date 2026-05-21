#!/usr/bin/env python3
"""Tiddl Scheduler - runs export and sync commands on schedule."""

import subprocess
import time
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/data")
MARKER_DAILY = DATA_DIR / ".last_daily"
MARKER_RADAR = DATA_DIR / ".last_radar"
LOG_FILE = DATA_DIR / "sync.log"

DAILY_INTERVAL_DAYS = 3

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def should_run_daily() -> bool:
    if not MARKER_DAILY.exists():
        return True
    try:
        last = float(MARKER_DAILY.read_text().strip())
        elapsed = (time.time() - last) / 86400
        if elapsed < DAILY_INTERVAL_DAYS:
            log(f"Daily: skipping ({elapsed:.1f}d < {DAILY_INTERVAL_DAYS}d)")
            return False
    except Exception:
        pass
    return True

def should_run_radar() -> bool:
    now = datetime.now()
    if now.weekday() != 0:
        return False
    if now.hour < 6:
        return False
    if MARKER_RADAR.exists():
        try:
            last = float(MARKER_RADAR.read_text().strip())
            elapsed = (time.time() - last) / 86400
            if elapsed < 6:
                return False
        except Exception:
            pass
    return True

def run_cmd(args: list[str]):
    log(f"Running: {' '.join(args)}")
    result = subprocess.run(args, cwd="/data", capture_output=False, text=True)
    return result.returncode

def run_daily():
    log("=== Starting daily sync ===")
    rc1 = run_cmd(["tiddl", "export", "daily"])
    if rc1 != 0:
        log("Export daily failed")
        return
    rc2 = run_cmd(["tiddl", "sync", "daily"])
    if rc2 != 0:
        log("Sync daily failed")
        return
    MARKER_DAILY.write_text(str(time.time()))
    log("=== Daily sync done ===")

def run_radar():
    log("=== Starting radar sync ===")
    rc = run_cmd(["tiddl", "sync", "radar"])
    if rc != 0:
        log("Radar sync failed")
        return
    MARKER_RADAR.write_text(str(time.time()))
    log("=== Radar sync done ===")

def main():
    log("Scheduler started")
    while True:
        try:
            if should_run_daily():
                run_daily()

            if should_run_radar():
                run_radar()
        except Exception as e:
            log(f"Error: {e}")

        log("Waiting 12 hours before next schedule check...")
        time.sleep(43200)

if __name__ == "__main__":
    main()
