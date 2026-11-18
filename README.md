# Jellyfin Music Adapter for v3rt3p

A local, privacy-first adapter that lets [v3rt3p quasar-server](https://github.com/v3rt3p/quasar-server) use a Jellyfin music library through its `BasicMusicBackend` API.

It translates the music/search/queue API expected by `quasar-server` into Jellyfin API calls and maintains an independent in-memory queue for every speaker.

## Features

- Search Jellyfin audio items
- Browse artists and albums
- Create a queue from a track or container
- Next and previous track per speaker
- Direct Jellyfin stream URLs for Station playback
- No cloud service, telemetry, or database
- Uses a Jellyfin API key from an environment variable or Docker secret file

## Quick start

Create a dedicated Jellyfin API key in **Dashboard → Advanced → API Keys**. Do not reuse a personal user token.

```yaml
services:
  jellyfin-music-adapter:
    image: ghcr.io/your-user/jellyfin-music-adapter:latest
    # Or use: build: ./jellyfin-music-adapter
    restart: unless-stopped
    environment:
      JELLYFIN_URL: http://192.168.0.5:8096
      JELLYFIN_API_KEY_FILE: /run/secrets/jellyfin_api_key
    secrets:
      - jellyfin_api_key

  quasar-server:
    environment:
      MUSIC_SERVICE_BASIC_URL: http://jellyfin-music-adapter:8080

secrets:
  jellyfin_api_key:
    file: ./secrets/jellyfin_api_key
```

The adapter exposes no host ports. It only needs to share a Docker network with `quasar-server` and be able to reach Jellyfin.

## Configuration

- `JELLYFIN_URL` — required Jellyfin base URL, such as `http://192.168.0.5:8096`
- `JELLYFIN_API_KEY` — Jellyfin API key (use this or the file variant)
- `JELLYFIN_API_KEY_FILE` — path to a file containing the key, recommended with Docker secrets
- `JELLYFIN_USER_ID` — optional Jellyfin user ID when a server requires it for library filtering
- `PORT` — listening port; default `8080`

## API compatibility

Implements the endpoints consumed by `BasicMusicBackend` in `quasar-server`:

- `POST /music/search`
- `GET /music/artist/:id`, `/tracks`, `/albums`
- `GET /music/album/:id`, `/tracks`
- `POST /queue/:device/create`
- `GET /queue/:device/current`
- `POST /queue/:device/forward`, `/backward`
- `GET /health`

The queue is intentionally in memory. A container restart clears active queues and playback resumes only after a new selection.

## Security

The direct stream URL contains the Jellyfin API key because a Yandex Station cannot attach Jellyfin authentication headers to an audio request. Keep the adapter and Jellyfin on a trusted LAN/private Docker network. Use a dedicated, revocable Jellyfin API key with the minimum practical access.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile src/adapter.py
docker build -t jellyfin-music-adapter .
```

## License

MIT.
