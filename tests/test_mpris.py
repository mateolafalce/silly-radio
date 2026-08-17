import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from selecto_radio.mpris import (
    MPRIS_BUS_NAME,
    MPRIS_PATH,
    TRACK_ID,
    MprisCommand,
    MprisService,
    _MediaPlayerInterface,
    _PlayerInterface,
    split_track_title,
)

ARTWORK_URL = "https://th.wallhaven.cc/lg/ab/wallhaven-abcdef.jpg"


class MprisTests(unittest.TestCase):
    def test_splits_conventional_and_fallback_titles(self) -> None:
        self.assertEqual(split_track_title("Artist - Track"), ("Artist", "Track"))
        self.assertEqual(split_track_title("Live Session"), ("Sonido Selecto", "Live Session"))
        self.assertEqual(
            split_track_title("  "),
            ("Sonido Selecto", "Sonido Selecto 102.9"),
        )
        self.assertEqual(split_track_title(" - incomplete"), ("Sonido Selecto", "- incomplete"))

    def test_root_interface_identifies_the_station(self) -> None:
        interface = _MediaPlayerInterface()

        interface.Raise()
        interface.Quit()
        self.assertFalse(interface.CanQuit)
        self.assertFalse(interface.Fullscreen)
        self.assertFalse(interface.CanSetFullscreen)
        self.assertFalse(interface.CanRaise)
        self.assertFalse(interface.HasTrackList)
        self.assertEqual(interface.Identity, "Sonido Selecto 102.9")
        self.assertEqual(interface.DesktopEntry, "")
        self.assertEqual(interface.SupportedUriSchemes, ["http", "https"])
        self.assertIn("audio/mpeg", interface.SupportedMimeTypes)

    def test_player_interface_exposes_metadata_and_capabilities(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        service.update(
            "Artist - Track",
            requested_playing=True,
            is_playing=True,
            volume=65,
            artwork_url=ARTWORK_URL,
        )
        interface = _PlayerInterface(service)

        metadata = interface.Metadata
        self.assertEqual(interface.PlaybackStatus, "Playing")
        self.assertEqual(metadata["mpris:trackid"].value, TRACK_ID)
        self.assertEqual(metadata["xesam:artist"].value, ["Artist"])
        self.assertEqual(metadata["xesam:title"].value, "Track")
        self.assertEqual(metadata["xesam:url"].value, "https://radio.test/stream")
        self.assertEqual(
            metadata["mpris:artUrl"].value,
            ARTWORK_URL,
        )
        self.assertEqual(interface.Volume, 0.65)
        self.assertEqual(interface.LoopStatus, "None")
        self.assertEqual(interface.Rate, 1.0)
        self.assertFalse(interface.Shuffle)
        self.assertEqual(interface.Position, 0)
        self.assertEqual(interface.MinimumRate, 1.0)
        self.assertEqual(interface.MaximumRate, 1.0)
        self.assertFalse(interface.CanGoNext)
        self.assertFalse(interface.CanGoPrevious)
        self.assertTrue(interface.CanPlay)
        self.assertTrue(interface.CanPause)
        self.assertFalse(interface.CanSeek)
        self.assertTrue(interface.CanControl)

    def test_player_methods_become_main_thread_commands(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        interface = _PlayerInterface(service)

        interface.Next()
        interface.Previous()
        interface.Seek(5)
        interface.SetPosition(TRACK_ID, 10)
        interface.OpenUri("https://ignored.test")
        interface.LoopStatus = "Playlist"  # type: ignore[method-assign]
        interface.Shuffle = True  # type: ignore[method-assign]
        interface.Play()
        interface.Pause()
        interface.PlayPause()
        interface.Stop()
        interface.Rate = 0.0  # type: ignore[method-assign]

        self.assertEqual(
            service.drain_commands(),
            [
                MprisCommand("play"),
                MprisCommand("pause"),
                MprisCommand("toggle"),
                MprisCommand("pause"),
                MprisCommand("pause"),
            ],
        )
        self.assertEqual(service.drain_commands(), [])

    def test_desktop_volume_is_clamped_and_enqueued(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        interface = _PlayerInterface(service)
        with patch.object(interface, "emit_properties_changed") as emit:
            interface.Volume = 1.5  # type: ignore[method-assign]
            interface.Volume = -0.2  # type: ignore[method-assign]

        self.assertEqual(service.drain_commands(), [MprisCommand("volume", 100), MprisCommand("volume", 0)])
        self.assertEqual(interface.Volume, 0.0)
        self.assertEqual(emit.call_count, 2)

    def test_state_updates_publish_only_changed_properties(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        interface = _PlayerInterface(service)
        old_state = service._snapshot()
        service.update(
            "Artist - Track",
            requested_playing=True,
            is_playing=True,
            volume=40,
            artwork_url=ARTWORK_URL,
        )
        new_state = service._snapshot()

        with patch.object(interface, "emit_properties_changed") as emit:
            interface.emit_state_changes(old_state, new_state)
            interface.emit_state_changes(new_state, new_state)

        changed = emit.call_args_list[0].args[0]
        self.assertEqual(changed["PlaybackStatus"], "Playing")
        self.assertEqual(changed["Volume"], 0.4)
        self.assertEqual(changed["Metadata"]["xesam:title"].value, "Track")
        self.assertEqual(changed["Metadata"]["mpris:artUrl"].value, ARTWORK_URL)
        emit.assert_called_once()

    def test_update_maps_real_player_states_and_notifies_bus_loop(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        loop = MagicMock()
        loop.is_closed.return_value = False
        interface = MagicMock()
        service._loop = loop
        service._player_interface = interface

        service.update("Track", requested_playing=False, is_playing=False, volume=65)
        self.assertEqual(service._snapshot().playback_status, "Paused")
        service.update("Track", requested_playing=True, is_playing=False, volume=65)
        self.assertEqual(service._snapshot().playback_status, "Stopped")

        self.assertEqual(loop.call_soon_threadsafe.call_count, 2)
        callback = loop.call_soon_threadsafe.call_args.args[0]
        self.assertEqual(callback, interface.emit_state_changes)

    def test_start_and_close_are_idempotent(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        thread = MagicMock()
        with patch("selecto_radio.mpris.threading.Thread", return_value=thread) as thread_factory:
            service.start()
            service.start()

        thread_factory.assert_called_once()
        thread.start.assert_called_once()

        loop = MagicMock()
        loop.is_closed.return_value = False
        stop_event = MagicMock()
        service._loop = loop
        service._stop_event = stop_event
        service.close()
        loop.call_soon_threadsafe.assert_called_once_with(stop_event.set)
        thread.join.assert_called_once_with(timeout=2.0)
        self.assertIsNone(service._thread)

    def test_background_errors_disable_mpris_without_raising(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        with (
            patch.object(service, "_serve", new_callable=MagicMock, return_value=MagicMock()),
            patch("selecto_radio.mpris.asyncio.run", side_effect=OSError("no session bus")),
        ):
            service._run()

        self.assertEqual(service.error, "no session bus")


class MprisAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_exports_both_interfaces_and_releases_the_bus(self) -> None:
        service = MprisService("https://radio.test/stream", 65)
        service._close_requested.set()
        bus = MagicMock()
        bus.request_name = AsyncMock()
        connection = MagicMock()
        connection.connect = AsyncMock(return_value=bus)

        with patch("selecto_radio.mpris.MessageBus", return_value=connection):
            await service._serve()

        exported_paths = [call.args[0] for call in bus.export.call_args_list]
        self.assertEqual(exported_paths, [MPRIS_PATH, MPRIS_PATH])
        bus.request_name.assert_awaited_once_with(f"{MPRIS_BUS_NAME}.instance{os.getpid()}")
        bus.disconnect.assert_called_once_with()
        self.assertIsNone(service._loop)
        self.assertIsNone(service._stop_event)
        self.assertIsNone(service._player_interface)


if __name__ == "__main__":
    unittest.main()
