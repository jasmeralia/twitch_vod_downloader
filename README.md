# twitch_vod_downloader

Automatically downloads Twitch VODs for one or more creators on a daily schedule, stores them in separate directories (great for Plex), and optionally sends an email when new VODs are detected.

This project is designed for TrueNAS SCALE, Docker Compose, or any Linux host.

## Features

- Automatic Twitch VOD downloads using yt-dlp
- Runs immediately on container start, then daily at 3:00 AM Pacific Time
- Supports multiple Twitch channels via CHANNELS env var
- Saves each channel's VODs into its own directory
- Uses download-archive to avoid re-downloading duplicates
- Sends a single email summary when new VODs are downloaded
- Simple Alpine-based Python container

## Directory Structure

```
/mnt/myzmirror/twitch_vods/
    username1/
        archive.txt
        YYYY-MM-DD_<vodid>_<title>.mp4
    username2/
        archive.txt
        YYYY-MM-DD_<vodid>_<title>.mp4
```

## Environment Variables

| Variable | Required | Description |
|---------|----------|-------------|
| CHANNELS | Yes | Comma-separated Twitch channel names |
| TZ | Recommended | Timezone (`America/Los_Angeles`) |
| SMTP_HOST | No | SMTP server hostname |
| SMTP_PORT | No | SMTP port |
| SMTP_USERNAME | No | SMTP username |
| SMTP_PASSWORD | No | SMTP app password |
| SMTP_FROM | No | From address |
| SMTP_TO | No | Recipient address |
| DATA_DIR | No | Override default `/data` |

## Email Notifications

A single email is sent per run if new VODs are detected.

## docker-compose.yml

```yaml
version: "3.8"

services:
  twitch-vod-downloader:
    build: .
    container_name: twitch-vod-downloader
    restart: unless-stopped
    environment:
      - TZ=America/Los_Angeles
      - CHANNELS=username1,username2
      - SMTP_HOST=smtp.gmail.com
      - SMTP_PORT=587
      - SMTP_USERNAME=morgan@windsofstorm.net
      - SMTP_PASSWORD=your_app_password_here
      - SMTP_FROM=morgan@windsofstorm.net
      - SMTP_TO=morgan@windsofstorm.net
    volumes:
      - /mnt/myzmirror/twitch_vods:/data
```

## Build & Run

```bash
docker compose build
docker compose up -d
docker logs -f twitch-vod-downloader
```

## Development

### Installing development dependencies

```bash
pip install -r requirements-dev.txt
```

This installs:
- `mypy` for static type checking
- `ruff` for linting and code formatting

### Running type checks

```bash
mypy .
```

### Running linter

```bash
ruff check .
```

To automatically fix issues:

```bash
ruff check --fix .
```

## Troubleshooting

- Ensure yt-dlp extractor is updated.
- Gmail requires an App Password.
- Verify container timezone: `docker exec -it twitch-vod-downloader date`.

## License

MIT License.
