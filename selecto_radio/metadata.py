"""Current-track metadata polling."""

from __future__ import annotations

import json
import threading
import unicodedata
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

METADATA_URL = "https://sonidoselecto.com/get_radio_info.php"
TitleFetcher = Callable[[str, float], str]


def sanitize_title(title: object) -> str:
    """Normalize whitespace and remove terminal control characters."""
    normalized = " ".join(str(title).split())
    return "".join(character for character in normalized if unicodedata.category(character) != "Cc")


def parse_title(payload: bytes) -> str:
    data = json.loads(payload.decode("utf-8"))
    title = data.get("titulo", "")
    return sanitize_title(title)


def fetch_title(url: str = METADATA_URL, timeout: float = 5.0) -> str:
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("metadata URL must use HTTP or HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "SonidoSelectoCLI/1.0"})
    # The explicit scheme allowlist above prevents local-file or custom-scheme access.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        return parse_title(response.read())


class MetadataPoller:
    def __init__(
        self,
        interval: float = 15.0,
        *,
        url: str = METADATA_URL,
        request_timeout: float = 5.0,
        fetcher: TitleFetcher = fetch_title,
    ) -> None:
        self.interval = interval
        self.url = url
        self.request_timeout = request_timeout
        self.title = "Connecting to Sonido Selecto..."
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
            # urlopen is not cancellable, so wait for its bounded request timeout.
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                title = self._fetcher(self.url, self.request_timeout)
                if title:
                    self.title = title
                self.error = ""
            except (OSError, ValueError) as exc:
                self.error = str(exc)
            self._stop.wait(self.interval)
