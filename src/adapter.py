"""Jellyfin implementation of the v3rt3p BasicMusicBackend HTTP API."""

import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, user_id: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": (
                'MediaBrowser Client="v3rt3p Jellyfin Adapter", '
                'Device="Jellyfin Adapter", DeviceId="v3rt3p-jellyfin-adapter", '
                f'Version="1.0", Token="{self.api_key}"'
            ),
        }

    def get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urlencode({k: v for k, v in query.items() if v is not None})
        request = Request(url, headers=self._headers())
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode(),
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read() or b"{}")

    def image_url(self, item_id: str) -> str:
        return f"{self.base_url}/Items/{quote(item_id)}/Images/Primary?api_key={quote(self.api_key)}"

    def stream_url(self, item_id: str) -> str:
        return f"{self.base_url}/Audio/{quote(item_id)}/universal?api_key={quote(self.api_key)}"

    def to_artist(self, item: dict[str, Any]) -> dict[str, Any]:
        result = {"id": item["Id"], "name": item.get("Name", item["Id"])}
        if item.get("ImageTags", {}).get("Primary"):
            result["imageUrl"] = self.image_url(item["Id"])
        return result

    def to_album(self, item: dict[str, Any]) -> dict[str, Any]:
        artists = [self.to_artist(a) for a in item.get("AlbumArtists", [])]
        if not artists and item.get("ArtistItems"):
            artists = [self.to_artist(a) for a in item["ArtistItems"]]
        result = {
            "id": item.get("AlbumId", item["Id"]),
            "name": item.get("Album", item.get("Name", item["Id"])),
            "artists": artists,
            "genre": (item.get("Genres") or [""])[0],
            "type": item.get("AlbumType", "Album"),
            "year": int(item.get("ProductionYear") or 0),
        }
        image_id = item.get("AlbumId", item["Id"])
        if item.get("ImageTags", {}).get("Primary"):
            result["imageUrl"] = self.image_url(image_id)
        return result

    def to_track(self, item: dict[str, Any], include_url: bool = False) -> dict[str, Any]:
        result = {
            "id": item["Id"],
            "title": item.get("Name", item["Id"]),
            "durationMs": int(item.get("RunTimeTicks") or 0) // 10_000,
            "artists": [self.to_artist(a) for a in item.get("ArtistItems", item.get("AlbumArtists", []))],
            "albums": [self.to_album(item)] if item.get("Album") else [],
        }
        if item.get("ImageTags", {}).get("Primary"):
            result["imageUrl"] = self.image_url(item["Id"])
        if include_url:
            result.update({"format": "mp3", "url": self.stream_url(item["Id"])})
        return result

    def item(self, item_id: str) -> dict[str, Any]:
        return self.get(f"/Items/{quote(item_id)}", {"UserId": self.user_id or None})

    def audio_items(self, query: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {
            "UserId": self.user_id or None,
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "SearchTerm": query or None,
            "Fields": "Genres,DateCreated,MediaSources",
        }
        if extra:
            params.update(extra)
        return self.get("/Items", params)


@dataclass
class Queue:
    tracks: list[dict[str, Any]]
    index: int = 0


class QueueStore:
    def __init__(self):
        self.queues: dict[str, Queue] = {}

    def set(self, device_id: str, tracks: list[dict[str, Any]], start_id: str | None = None) -> None:
        if not tracks:
            raise ValueError("queue requires at least one track")
        index = next((i for i, track in enumerate(tracks) if track["id"] == start_id), 0)
        self.queues[device_id] = Queue(tracks, index)

    def current(self, device_id: str) -> dict[str, Any] | None:
        queue = self.queues.get(device_id)
        return queue.tracks[queue.index] if queue else None

    def forward(self, device_id: str) -> None:
        queue = self.queues.get(device_id)
        if queue:
            queue.index = min(queue.index + 1, len(queue.tracks) - 1)

    def backward(self, device_id: str) -> None:
        queue = self.queues.get(device_id)
        if queue:
            queue.index = max(queue.index - 1, 0)


class AdapterHandler(BaseHTTPRequestHandler):
    client: JellyfinClient
    queues: QueueStore

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def json_response(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path
            if path == "/health":
                self.json_response(200, {"status": "ok"})
                return
            if path.startswith("/queue/") and path.endswith("/current"):
                device = path.split("/")[2]
                track = self.queues.current(device)
                self.json_response(200 if track else 404, track or {"error": "queue is empty"})
                return
            if path.startswith("/music/artist/"):
                rest = path.removeprefix("/music/artist/")
                artist_id, _, suffix = rest.partition("/")
                if suffix == "tracks":
                    data = self.client.audio_items(extra={"ArtistIds": artist_id})
                    self.json_response(200, {"total": data.get("TotalRecordCount", 0), "tracks": [self.client.to_track(x) for x in data.get("Items", [])]})
                    return
                if suffix == "albums":
                    data = self.client.get("/Items", {"IncludeItemTypes": "MusicAlbum", "ArtistIds": artist_id})
                    self.json_response(200, {"total": data.get("TotalRecordCount", 0), "albums": [self.client.to_album(x) for x in data.get("Items", [])]})
                    return
                self.json_response(200, {"artist": self.client.to_artist(self.client.item(artist_id))})
                return
            if path.startswith("/music/album/"):
                rest = path.removeprefix("/music/album/")
                album_id, _, suffix = rest.partition("/")
                if suffix == "tracks":
                    data = self.client.audio_items(extra={"AlbumIds": album_id})
                    self.json_response(200, {"total": data.get("TotalRecordCount", 0), "tracks": [self.client.to_track(x) for x in data.get("Items", [])]})
                    return
                self.json_response(200, {"album": self.client.to_album(self.client.item(album_id))})
                return
            self.json_response(404, {"error": "not found"})
        except Exception as error:
            self.json_response(500, {"error": str(error)})

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            if path == "/music/search":
                body = self.body()
                data = self.client.audio_items(body.get("query", ""))
                tracks = [self.client.to_track(x) | {"searchPosition": i} for i, x in enumerate(data.get("Items", []))]
                self.json_response(200, {"tracks": tracks})
                return
            if path.startswith("/queue/") and path.endswith("/create"):
                device = path.split("/")[2]
                body = self.body()
                root = self.client.item(body["itemId"])
                if root.get("Type") == "Audio":
                    items = [root]
                else:
                    items = self.client.audio_items(extra={"ParentId": root["Id"]}).get("Items", [])
                tracks = [self.client.to_track(x, include_url=True) for x in items]
                if body.get("doShuffle"):
                    import random
                    random.shuffle(tracks)
                self.queues.set(device, tracks, body.get("startFromItemId"))
                self.json_response(200, {})
                return
            if path.startswith("/queue/") and path.endswith("/forward"):
                self.queues.forward(path.split("/")[2]); self.json_response(200, {}); return
            if path.startswith("/queue/") and path.endswith("/backward"):
                self.queues.backward(path.split("/")[2]); self.json_response(200, {}); return
            self.json_response(404, {"error": "not found"})
        except (KeyError, ValueError) as error:
            self.json_response(400, {"error": str(error)})
        except Exception as error:
            self.json_response(500, {"error": str(error)})


def secret_from_environment(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    file_name = os.getenv(f"{name}_FILE")
    if file_name:
        return open(file_name, encoding="utf-8").read().strip()
    raise KeyError(name)


def main() -> None:
    base_url = os.environ["JELLYFIN_URL"]
    api_key = secret_from_environment("JELLYFIN_API_KEY")
    port = int(os.getenv("PORT", "8080"))
    AdapterHandler.client = JellyfinClient(base_url, api_key, os.getenv("JELLYFIN_USER_ID", ""))
    AdapterHandler.queues = QueueStore()
    ThreadingHTTPServer(("0.0.0.0", port), AdapterHandler).serve_forever()


if __name__ == "__main__":
    main()
