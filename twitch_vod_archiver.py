#!/usr/bin/env python3
import os
import time
import subprocess
import datetime
import pathlib
import sys
import smtplib
import ssl
import traceback

def log(msg: str) -> None:
    now = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"[{now}] {msg}", flush=True)

def get_channels():
    raw = os.getenv("CHANNELS", "")
    channels = [c.strip() for c in raw.split(",") if c.strip()]
    if not channels:
        log("ERROR: No CHANNELS specified; set CHANNELS env var (comma-separated).")
        sys.exit(1)
    return channels

BASE_DIR = pathlib.Path(os.getenv("DATA_DIR", "/data")).resolve()

def ensure_base_dir():
    try:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        log(f"Using base data directory: {BASE_DIR}")
    except Exception as e:
        log(f"ERROR: Failed to create base directory {BASE_DIR}: {e}")
        sys.exit(1)

def seconds_to_next_run(hour: int = 3, minute: int = 0) -> int:
    now = datetime.datetime.now()
    run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run <= now:
        run += datetime.timedelta(days=1)
    delta = run - now
    return int(delta.total_seconds())

def send_email(subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("SMTP_FROM") or username
    to_addr = os.getenv("SMTP_TO") or username

    if not (host and port and username and password and from_addr and to_addr):
        log("EMAIL: SMTP not fully configured; skipping email notification.")
        return

    msg = f"From: {from_addr}\r\nTo: {to_addr}\r\nSubject: {subject}\r\n\r\n{body}"

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            server.starttls(context=context)
            server.login(username, password)
            server.sendmail(from_addr, [to_addr], msg.encode("utf-8"))
        log(f"Email notification sent to {to_addr}.")
    except Exception as e:
        log(f"ERROR: Failed to send email: {e}")

def read_archive_lines(path: pathlib.Path):
    if not path.exists():
        return set()
    try:
        with path.open("r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except Exception as e:
        log(f"WARNING: Failed to read archive {path}: {e}")
        return set()

def parse_vod_id(entry: str) -> str:
    parts = entry.split()
    if len(parts) == 2:
        return parts[1]
    return entry

def run_once(channels):
    log("Starting VOD sync run...")
    new_downloads = []

    for ch in channels:
        ch_dir = BASE_DIR / ch
        ch_dir.mkdir(parents=True, exist_ok=True)
        archive = ch_dir / "archive.txt"
        url = f"https://www.twitch.tv/{ch}/videos/all"
        log(f"Checking channel '{ch}' at {url}")

        before = read_archive_lines(archive)

        cmd = [
            "yt-dlp", url,
            "--download-archive", str(archive),
            "--paths", str(ch_dir),
            "--output", "%(upload_date>%Y-%m-%d)s_%(id)s_%(title)s.%(ext)s",
            "--restrict-filenames",
            "--retries", "10",
            "--no-overwrites",
        ]

        try:
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                log(f"WARNING: yt-dlp exited with code {result.returncode} for channel '{ch}'.")
        except Exception as e:
            log(f"ERROR running yt-dlp for '{ch}': {e}")
            log(traceback.format_exc())

        after = read_archive_lines(archive)
        added_entries = after - before
        added_ids = [parse_vod_id(e) for e in added_entries]

        if added_ids:
            for vid in added_ids:
                new_downloads.append((ch, vid))
            log(f"Channel '{ch}': {len(added_ids)} new VOD(s).")
        else:
            log(f"Channel '{ch}': no new VODs.")

    if new_downloads:
        per_channel = {}
        for ch, vid in new_downloads:
            per_channel.setdefault(ch, []).append(vid)

        lines = []
        for ch, vids in per_channel.items():
            lines.append(f"{ch}: {len(vids)} new VOD(s): " + ", ".join(vids))

        body = "New Twitch VODs downloaded this run:\n\n" + "\n".join(lines)
        send_email("[twitch-vod-downloader] New VODs downloaded", body)
    else:
        log("No new VODs this run; no email sent.")

    log("VOD sync run complete.")
    return new_downloads

def main():
    channels = get_channels()
    ensure_base_dir()
    log("Configured channels: " + ", ".join(channels))
    log("Running initial sync on startup...")
    run_once(channels)

    while True:
        sleep_for = seconds_to_next_run()
        log(f"Sleeping {sleep_for} seconds until next 03:00 run...")
        time.sleep(sleep_for)
        log("Starting scheduled daily sync...")
        run_once(channels)

if __name__ == "__main__":
    main()
