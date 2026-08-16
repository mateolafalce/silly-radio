import threading
import unittest
from unittest.mock import MagicMock, patch

from selecto_radio.metadata import MetadataPoller, fetch_title, parse_title


class MetadataTests(unittest.TestCase):
    def test_parse_title_normalizes_whitespace(self) -> None:
        self.assertEqual(parse_title(b'{"titulo": "DJ  Name\\nLive"}'), "DJ Name Live")

    def test_parse_title_rejects_invalid_json(self) -> None:
        with self.assertRaises(ValueError):
            parse_title(b"not json")

    def test_parse_title_removes_terminal_control_characters(self) -> None:
        payload = b'{"titulo": "Song\\u001b]2;pwned\\u0007"}'

        self.assertEqual(parse_title(payload), "Song]2;pwned")

    def test_fetch_title_uses_configured_url_and_timeout(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"titulo": "Track"}'
        with patch("selecto_radio.metadata.urllib.request.urlopen", return_value=response) as urlopen:
            title = fetch_title("https://metadata.test/title", timeout=1.5)

        self.assertEqual(title, "Track")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://metadata.test/title")
        self.assertEqual(urlopen.call_args.kwargs, {"timeout": 1.5})

    def test_fetch_title_rejects_non_http_urls(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTP or HTTPS"):
            fetch_title("file:///etc/passwd")

    def test_poller_retries_retains_title_and_clears_error_after_success(self) -> None:
        failure_observed = threading.Event()
        allow_success = threading.Event()
        success_applied = threading.Event()
        calls = 0

        class ObservedError(OSError):
            def __str__(self) -> str:
                failure_observed.set()
                return "metadata unavailable"

        def fetcher(url: str, timeout: float) -> str:
            nonlocal calls
            self.assertEqual(url, "https://metadata.test/title")
            self.assertEqual(timeout, 0.5)
            calls += 1
            if calls == 1:
                return "First track"
            if calls == 2:
                raise ObservedError()
            if calls == 3:
                allow_success.wait(1.0)
                return "Second track"
            success_applied.set()
            return ""

        poller = MetadataPoller(
            interval=0.01,
            url="https://metadata.test/title",
            request_timeout=0.5,
            fetcher=fetcher,
        )
        poller.start()
        self.assertTrue(failure_observed.wait(1.0))
        self.assertEqual(poller.title, "First track")
        self.assertEqual(poller.error, "metadata unavailable")

        allow_success.set()
        self.assertTrue(success_applied.wait(1.0))
        self.assertEqual(poller.title, "Second track")
        self.assertEqual(poller.error, "")
        poller.close()
        self.assertFalse(poller._thread.is_alive())

    def test_close_waits_for_an_in_flight_request_and_stops_thread(self) -> None:
        fetch_started = threading.Event()
        release_fetch = threading.Event()

        def fetcher(url: str, timeout: float) -> str:
            fetch_started.set()
            release_fetch.wait(timeout)
            return "Track"

        poller = MetadataPoller(request_timeout=1.0, fetcher=fetcher)
        poller.start()
        self.assertTrue(fetch_started.wait(1.0))

        closer = threading.Thread(target=poller.close)
        closer.start()
        self.assertTrue(closer.is_alive())
        release_fetch.set()
        closer.join(1.0)

        self.assertFalse(closer.is_alive())
        self.assertFalse(poller._thread.is_alive())

    def test_start_and_close_are_idempotent(self) -> None:
        poller = MetadataPoller(fetcher=lambda url, timeout: "")
        poller.close()
        poller.start()
        poller.start()
        poller.close()
