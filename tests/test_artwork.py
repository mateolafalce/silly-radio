import threading
import unittest
from unittest.mock import MagicMock, patch

from selecto_radio.artwork import (
    WALLHAVEN_API_URL,
    RandomArtworkPoller,
    fetch_random_artwork,
    parse_artwork_url,
)

FIRST_IMAGE = "https://th.wallhaven.cc/lg/ab/wallhaven-abcdef.jpg"
SECOND_IMAGE = "https://th.wallhaven.cc/lg/xy/wallhaven-xyz123.jpg"


class ArtworkTests(unittest.TestCase):
    def test_parses_first_safe_large_thumbnail(self) -> None:
        payload = (
            b'{"data": ['
            b'{"thumbs": {"large": "https://images.invalid/untrusted.jpg"}},'
            b'{"thumbs": {"large": "https://th.wallhaven.cc/lg/ab/wallhaven-abcdef.jpg"}}'
            b"]}"
        )

        self.assertEqual(parse_artwork_url(payload), FIRST_IMAGE)

    def test_rejects_missing_or_unsafe_wallpapers(self) -> None:
        with self.assertRaisesRegex(ValueError, "no wallpaper list"):
            parse_artwork_url(b'{"data": null}')
        with self.assertRaisesRegex(ValueError, "no safe artwork URL"):
            parse_artwork_url(b'{"data": [{"thumbs": {"large": "http://th.wallhaven.cc/x.jpg"}}]}')

    def test_fetch_uses_wallhaven_api_and_timeout(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"data": [{"thumbs": {"large": "https://th.wallhaven.cc/lg/ab/wallhaven-abcdef.jpg"}}]}'
        )
        with patch("selecto_radio.artwork.urllib.request.urlopen", return_value=response) as urlopen:
            image_url = fetch_random_artwork(WALLHAVEN_API_URL, timeout=1.5)

        self.assertEqual(image_url, FIRST_IMAGE)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, WALLHAVEN_API_URL)
        self.assertEqual(urlopen.call_args.kwargs, {"timeout": 1.5})

    def test_fetch_rejects_non_wallhaven_urls(self) -> None:
        for url in ("http://wallhaven.cc/api/v1/search", "https://example.com/api"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "HTTPS on wallhaven.cc"):
                fetch_random_artwork(url)

    def test_poller_rotates_and_retains_last_image_after_failure(self) -> None:
        failure_observed = threading.Event()
        second_success = threading.Event()
        calls = 0

        class ObservedError(OSError):
            def __str__(self) -> str:
                failure_observed.set()
                return "Wallhaven unavailable"

        def fetcher(url: str, timeout: float) -> str:
            nonlocal calls
            self.assertEqual(url, WALLHAVEN_API_URL)
            self.assertEqual(timeout, 0.5)
            calls += 1
            if calls == 1:
                return FIRST_IMAGE
            if calls == 2:
                raise ObservedError()
            second_success.set()
            return SECOND_IMAGE

        poller = RandomArtworkPoller(interval=0.05, request_timeout=0.5, fetcher=fetcher)
        poller.start()
        self.assertTrue(failure_observed.wait(1.0))
        self.assertEqual(poller.image_url, FIRST_IMAGE)
        self.assertEqual(poller.error, "Wallhaven unavailable")
        self.assertTrue(second_success.wait(1.0))
        poller.close()

        self.assertEqual(poller.image_url, SECOND_IMAGE)
        self.assertEqual(poller.error, "")
        self.assertFalse(poller._thread.is_alive())

    def test_default_rotation_is_one_minute_and_lifecycle_is_idempotent(self) -> None:
        poller = RandomArtworkPoller(fetcher=lambda url, timeout: FIRST_IMAGE)
        self.assertEqual(poller.interval, 60.0)
        poller.close()
        poller.start()
        poller.start()
        poller.close()
        self.assertFalse(poller._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
