# Twitch VOD Downloader

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
| VOD_REAL_PATH | No | Replace the `DATA_DIR` prefix in email notifications with a host path (for example `/mnt/myzmirror/twitch_vods`) |
| RUN_ONCE | No | Set to `1` to run a single sync and exit instead of the self-scheduling daemon loop (equivalent to the `--once` CLI flag) |

## Email Notifications

A single email is sent per run if new VODs are detected. The email lists each downloaded file as its own bullet with the full path. If your host path differs from the container mount, set `VOD_REAL_PATH` so the email shows the host path instead of the container's `DATA_DIR` path.

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

## Running a single sync (native cron / uv)

By default the app runs an initial sync on startup and then self-schedules a
daily run at 3:00 AM Pacific Time — this is the behavior used by the Docker
container above. For deployments driven by an external scheduler (such as a
native TrueNAS cron job invoking the app via `uv`), pass `--once` or set
`RUN_ONCE=1` to run a single sync and exit instead:

```bash
uv run python -m twitch_vod_downloader --once
```

```bash
RUN_ONCE=1 uv run python -m twitch_vod_downloader
```

`pyproject.toml`/`uv.lock` describe the runtime dependencies for this mode.
`requirements.txt` remains the source of truth for the Docker image build; the
two are kept in sync manually.

## Development

### Installing development dependencies

```bash
pip install -r requirements-dev.txt
```

This installs:
- `mypy` for static type checking
- `ruff` for linting and code formatting
- `pytest` and `pytest-cov` for tests and Codecov reporting

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

Run `make test` to execute the tests and write `coverage.xml`. Codecov enforces
an 80% coverage target for both the overall project and each patch; pull
requests that drop below this threshold will fail the Codecov status checks.

## Troubleshooting

- Ensure yt-dlp extractor is updated.
- Gmail requires an App Password.
- Verify container timezone: `docker exec -it twitch-vod-downloader date`.

## License

MIT License.

## Using a .env file

Rather than embedding credentials in your `docker-compose.yml`, you can store them in a `.env` file and bind-mount it into the container:

```bash
cp .env.example .env
# edit .env with your values
```

```yaml
services:
  app:
    image: ghcr.io/jasmeralia/twitch-vod-downloader:latest
    volumes:
      - /path/to/your/.env:/app/.env:ro
```

The app loads `/app/.env` automatically on startup. Any value in `.env` can still be overridden by an explicit `environment:` entry in your Compose file.
