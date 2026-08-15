import unittest
from unittest.mock import MagicMock, patch

from selecto_radio.player import Backend, RadioPlayer, find_backend


class PlayerTests(unittest.TestCase):
    def test_default_volume_is_100(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=None):
            player = RadioPlayer("https://radio.test/stream")
        self.assertEqual(player.volume, 100)

    def test_toggle_mute_restores_previous_volume(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=None):
            player = RadioPlayer("https://radio.test/stream", volume=65)

        player.toggle_mute()
        self.assertEqual(player.volume, 0)

        player.toggle_mute()
        self.assertEqual(player.volume, 65)

    def test_toggle_mute_mutes_again_after_volume_changes(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=None):
            player = RadioPlayer("https://radio.test/stream", volume=65)

        player.toggle_mute()
        player.change_volume(5)
        player.toggle_mute()

        self.assertEqual(player.volume, 0)

    def test_mpv_command(self) -> None:
        command = Backend("/usr/bin/mpv", "mpv").command(
            "https://radio.test/stream", 65, "/tmp/radio-mpv.sock"
        )
        self.assertEqual(command[-1], "https://radio.test/stream")
        self.assertIn("--volume=65", command)
        self.assertIn("--input-ipc-server=/tmp/radio-mpv.sock", command)

    def test_mpv_volume_changes_use_ipc_without_restarting(self) -> None:
        with patch(
            "selecto_radio.player.find_backend", return_value=Backend("/usr/bin/mpv", "mpv")
        ):
            player = RadioPlayer("https://radio.test/stream", volume=65)
        player.process = MagicMock()
        player.process.poll.return_value = None
        player.requested_playing = True

        with patch.object(player, "_send_mpv_volume", return_value=True) as send_volume:
            with patch.object(player, "_restart_if_playing") as restart:
                player.toggle_mute()

        send_volume.assert_called_once_with()
        restart.assert_not_called()
        self.assertEqual(player.volume, 0)
        player.close()

    def test_mpv_ipc_sends_the_current_volume(self) -> None:
        with patch(
            "selecto_radio.player.find_backend", return_value=Backend("/usr/bin/mpv", "mpv")
        ):
            player = RadioPlayer("https://radio.test/stream", volume=65)
        player.process = MagicMock()
        player.process.poll.return_value = None

        with patch("selecto_radio.player.socket.socket") as socket_factory:
            ipc_socket = socket_factory.return_value.__enter__.return_value
            sent = player._send_mpv_volume()

        self.assertTrue(sent)
        ipc_socket.connect.assert_called_once_with(player._ipc_path)
        ipc_socket.sendall.assert_called_once_with(
            b'{"command": ["set_property", "volume", 65]}\n'
        )
        player.close()

    def test_mpv_volume_change_restarts_when_ipc_fails(self) -> None:
        with patch(
            "selecto_radio.player.find_backend", return_value=Backend("/usr/bin/mpv", "mpv")
        ):
            player = RadioPlayer("https://radio.test/stream", volume=65)
        player.process = MagicMock()
        player.process.poll.return_value = None
        player.requested_playing = True

        with patch.object(player, "_send_mpv_volume", return_value=False):
            with patch.object(player, "_restart_if_playing") as restart:
                player.toggle_mute()

        restart.assert_called_once_with()
        player.close()

    def test_find_backend_prefers_mpv(self) -> None:
        with patch(
            "selecto_radio.player.shutil.which",
            side_effect=lambda name: f"/bin/{name}" if name in {"mpv", "ffplay"} else None,
        ):
            backend = find_backend()
        self.assertIsNotNone(backend)
        self.assertEqual(backend.name, "mpv")
