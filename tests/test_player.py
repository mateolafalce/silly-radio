import subprocess
import unittest
from unittest.mock import MagicMock, patch

from selecto_radio.player import FfplayBackend, MpvBackend, RadioPlayer, VlcBackend, find_backend


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

    def test_backend_commands(self) -> None:
        stream = "https://radio.test/stream"
        mpv = MpvBackend("/usr/bin/mpv").command(stream, 65, "/tmp/radio-mpv.sock")
        ffplay = FfplayBackend("/usr/bin/ffplay").command(stream, 65)
        vlc = VlcBackend("/usr/bin/vlc").command(stream, 65)

        self.assertEqual(mpv[-1], stream)
        self.assertIn("--volume=65", mpv)
        self.assertIn("--input-ipc-server=/tmp/radio-mpv.sock", mpv)
        self.assertEqual(ffplay[-3:], ["-volume", "65", stream])
        self.assertIn("--gain=0.65", vlc)

    def test_play_reports_missing_backend(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=None):
            player = RadioPlayer("https://radio.test/stream")

        self.assertFalse(player.play())
        self.assertTrue(player.requested_playing)
        self.assertIn("Install mpv", player.error)

    def test_backend_name_reports_selected_or_missing_player(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=None):
            missing = RadioPlayer("https://radio.test/stream")
        with patch("selecto_radio.player.find_backend", return_value=VlcBackend("/bin/vlc")):
            selected = RadioPlayer("https://radio.test/stream")

        self.assertEqual(missing.backend_name, "no player")
        self.assertEqual(selected.backend_name, "vlc")

    def test_play_starts_backend_and_clears_previous_error(self) -> None:
        backend = FfplayBackend("/usr/bin/ffplay")
        with (
            patch("selecto_radio.player.find_backend", return_value=backend),
            patch("selecto_radio.player.subprocess.Popen") as popen,
        ):
            player = RadioPlayer("https://radio.test/stream", 45)
            player.error = "old error"
            started = player.play()

        self.assertTrue(started)
        self.assertEqual(player.process, popen.return_value)
        self.assertEqual(player.error, "")
        popen.assert_called_once_with(
            backend.command("https://radio.test/stream", 45),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def test_play_does_not_duplicate_a_running_process(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream")
        process = MagicMock()
        process.poll.return_value = None
        player.process = process

        with patch("selecto_radio.player.subprocess.Popen") as popen:
            self.assertTrue(player.play())

        popen.assert_not_called()

    def test_is_playing_is_false_without_a_live_process(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=None):
            player = RadioPlayer("https://radio.test/stream")
        self.assertFalse(player.is_playing)

        process = MagicMock()
        process.poll.return_value = 1
        player.process = process
        self.assertFalse(player.is_playing)

    def test_play_reaps_an_exited_process_before_restarting(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream")
        old_process = MagicMock()
        old_process.poll.return_value = 1
        player.process = old_process

        with patch("selecto_radio.player.subprocess.Popen") as popen:
            self.assertTrue(player.play())

        old_process.wait.assert_called_once_with()
        self.assertEqual(player.process, popen.return_value)

    def test_play_reports_process_start_errors(self) -> None:
        with (
            patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/missing/ffplay")),
            patch("selecto_radio.player.subprocess.Popen", side_effect=OSError("not found")),
        ):
            player = RadioPlayer("https://radio.test/stream")
            self.assertFalse(player.play())

        self.assertIsNone(player.process)
        self.assertEqual(player.error, "Could not start ffplay: not found")

    def test_pause_terminates_a_running_process(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream")
        process = MagicMock()
        process.poll.return_value = None
        player.process = process
        player.requested_playing = True

        player.pause()

        self.assertFalse(player.requested_playing)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=1.0)
        self.assertIsNone(player.process)

    def test_stop_kills_a_process_that_ignores_terminate(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream")
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("ffplay", 1.0), 0]
        player.process = process

        player._stop_process()

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)
        self.assertIsNone(player.process)

    def test_stop_reaps_an_already_exited_process_without_terminating(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream")
        process = MagicMock()
        process.poll.return_value = 0
        player.process = process

        player._stop_process()

        process.terminate.assert_not_called()
        self.assertIsNone(player.process)

    def test_toggle_resumes_after_pause(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream")
        with patch.object(player, "play", return_value=True) as play:
            player.toggle()
        play.assert_called_once_with()

    def test_mpv_volume_changes_use_ipc_without_restarting(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=MpvBackend("/usr/bin/mpv")):
            player = RadioPlayer("https://radio.test/stream", volume=65)
        player.process = MagicMock()
        player.process.poll.return_value = None
        player.requested_playing = True

        with patch.object(MpvBackend, "set_live_volume", return_value=True) as send_volume:
            with patch.object(player, "_restart_if_playing") as restart:
                player.toggle_mute()

        send_volume.assert_called_once_with(player._ipc_path, 0)
        restart.assert_not_called()
        self.assertEqual(player.volume, 0)
        player.close()

    def test_mpv_ipc_sends_the_current_volume(self) -> None:
        backend = MpvBackend("/usr/bin/mpv")

        with patch("selecto_radio.player.socket.socket") as socket_factory:
            ipc_socket = socket_factory.return_value.__enter__.return_value
            sent = backend.set_live_volume("/tmp/mpv.sock", 65)

        self.assertTrue(sent)
        ipc_socket.connect.assert_called_once_with("/tmp/mpv.sock")
        ipc_socket.sendall.assert_called_once_with(b'{"command": ["set_property", "volume", 65]}\n')

    def test_mpv_ipc_requires_a_path_and_handles_socket_errors(self) -> None:
        backend = MpvBackend("/usr/bin/mpv")

        self.assertFalse(backend.set_live_volume(None, 65))
        with patch("selecto_radio.player.socket.socket", side_effect=OSError("unavailable")):
            self.assertFalse(backend.set_live_volume("/tmp/mpv.sock", 65))

    def test_mpv_volume_change_restarts_when_ipc_fails(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=MpvBackend("/usr/bin/mpv")):
            player = RadioPlayer("https://radio.test/stream", volume=65)
        player.process = MagicMock()
        player.process.poll.return_value = None
        player.requested_playing = True

        with patch.object(MpvBackend, "set_live_volume", return_value=False):
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
        self.assertIsInstance(backend, MpvBackend)
        self.assertEqual(backend.name if backend else None, "mpv")

    def test_find_backend_returns_none_when_no_candidate_exists(self) -> None:
        with patch("selecto_radio.player.shutil.which", return_value=None):
            self.assertIsNone(find_backend())

    def test_volume_changes_restart_backends_without_live_control(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream", 50)
        player.requested_playing = True
        with patch.object(player, "_restart_if_playing") as restart:
            player.set_volume(150)
            player.set_volume(100)

        self.assertEqual(player.volume, 100)
        restart.assert_called_once_with()

    def test_volume_change_does_nothing_while_paused(self) -> None:
        with patch("selecto_radio.player.find_backend", return_value=FfplayBackend("/bin/ffplay")):
            player = RadioPlayer("https://radio.test/stream", 50)
        with patch.object(player, "_restart_if_playing") as restart:
            player.set_volume(-10)

        self.assertEqual(player.volume, 0)
        restart.assert_not_called()
