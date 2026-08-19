"""Temporary artwork fetched from Wallhaven for desktop media panels."""

from __future__ import annotations

import json
import threading
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

WALLHAVEN_API_URL = "https://wallhaven.cc/api/v1/search?categories=111&purity=110&sorting=random&order=desc"
ArtworkFetcher = Callable[[str, float], str]


def parse_artwork_url(payload: bytes) -> str:
    """Return the first safe large-thumbnail URL in a Wallhaven response."""
    response = json.loads(payload.decode("utf-8"))
    results = response.get("data") if isinstance(response, dict) else None
    if not isinstance(results, list):
        raise ValueError("Wallhaven response has no wallpaper list")

    for result in results:
        if not isinstance(result, dict):
            continue
        thumbnails = result.get("thumbs")
        candidate = thumbnails.get("large") if isinstance(thumbnails, dict) else None
        if not isinstance(candidate, str):
            continue
        parsed = urlsplit(candidate)
        if parsed.scheme == "https" and parsed.hostname == "th.wallhaven.cc":
            return candidate
    raise ValueError("Wallhaven response has no safe artwork URL")


def fetch_random_artwork(url: str = WALLHAVEN_API_URL, timeout: float = 5.0) -> str:
    """Fetch one random SFW or sketchy wallpaper thumbnail URL from Wallhaven."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "wallhaven.cc":
        raise ValueError("artwork URL must use HTTPS on wallhaven.cc")
    request = urllib.request.Request(url, headers={"User-Agent": "SonidoSelectoCLI/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        return parse_artwork_url(response.read())


class RandomArtworkPoller:
    """Rotate the wallpaper in the background without delaying playback."""

    def __init__(
        self,
        interval: float = 60.0,
        *,
        url: str = WALLHAVEN_API_URL,
        request_timeout: float = 5.0,
        fetcher: ArtworkFetcher = fetch_random_artwork,
    ) -> None:
        self.interval = interval
        self.url = url
        self.request_timeout = request_timeout
        self.image_url = ""
        self.error = ""
        self._fetcher = fetcher
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._started:
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.image_url = self._fetcher(self.url, self.request_timeout)
                self.error = ""
            except (OSError, ValueError) as exc:
                self.error = str(exc)
            self._stop.wait(self.interval)
