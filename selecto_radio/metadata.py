"""Current-track metadata polling."""

from __future__ import annotations

import json
import threading
import urllib.request

METADATA_URL = "https://sonidoselecto.com/get_radio_info.php"


def parse_title(payload: bytes) -> str:
    data = json.loads(payload.decode("utf-8"))
    title = data.get("titulo", "")
    return " ".join(str(title).split())


def fetch_title(url: str = METADATA_URL, timeout: float = 5.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "SonidoSelectoCLI/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_title(response.read())


class MetadataPoller:
    def __init__(self, interval: float = 15.0) -> None:
        self.interval = interval
        self.title = "Connecting to Sonido Selecto..."
        self.error = ""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=0.2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                title = fetch_title()
                if title:
                    self.title = title
                self.error = ""
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.error = str(exc)
            self._stop.wait(self.interval)
