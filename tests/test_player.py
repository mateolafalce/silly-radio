import unittest
from unittest.mock import patch

from selecto_radio.player import Backend, RadioPlayer, find_backend


class PlayerTests(unittest.TestCase):
    def test_default_volume_is_100(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=None):
            player = RadioPlayer("https://radio.test/stream")
        self.assertEqual(player.volume, 100)

    def test_mpv_command(self) -> None:
        command = Backend("/usr/bin/mpv", "mpv").command("https://radio.test/stream", 65)
        self.assertEqual(command[-1], "https://radio.test/stream")
        self.assertIn("--volume=65", command)

    def test_find_backend_prefers_mpv(self) -> None:
        with patch(
            "selecto_radio.player.shutil.which",
            side_effect=lambda name: f"/bin/{name}" if name in {"mpv", "ffplay"} else None,
        ):
            backend = find_backend()
        self.assertIsNotNone(backend)
        self.assertEqual(backend.name, "mpv")
