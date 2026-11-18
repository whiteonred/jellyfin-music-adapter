import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adapter import JellyfinClient, QueueStore


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        import json
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class JellyfinClientTests(unittest.TestCase):
    def test_audio_item_becomes_track_with_stream_url(self):
        client = JellyfinClient("http://jellyfin:8096", "secret", "user-1")
        item = {
            "Id": "track-1",
            "Name": "Song",
            "RunTimeTicks": 25_000_000,
            "Album": "Album",
            "AlbumArtists": [{"Id": "artist-1", "Name": "Artist"}],
            "ImageTags": {"Primary": "cover"},
            "ProductionYear": 2024,
        }

        track = client.to_track(item, include_url=True)

        self.assertEqual(track["id"], "track-1")
        self.assertEqual(track["title"], "Song")
        self.assertEqual(track["durationMs"], 2500)
        self.assertEqual(track["artists"][0]["name"], "Artist")
        self.assertIn("api_key=secret", track["url"])
        self.assertIn("track-1", track["url"])


class QueueStoreTests(unittest.TestCase):
    def test_forward_and_backward_are_scoped_to_device_queue(self):
        store = QueueStore()
        tracks = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        store.set("station-a", tracks, "b")
        store.set("station-b", tracks, "a")

        store.forward("station-a")
        store.backward("station-b")

        self.assertEqual(store.current("station-a")["id"], "c")
        self.assertEqual(store.current("station-b")["id"], "a")


if __name__ == "__main__":
    unittest.main()
