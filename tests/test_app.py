import curses
import unittest
from contextlib import redirect_stderr
from dataclasses import dataclass
from io import StringIO
from unittest.mock import patch

from selecto_radio.app import (
    FRAME_INTERVAL,
    MARQUEE_SEPARATOR,
    _draw_centered_line,
    _safe_addstr,
    _set_terminal_title,
    build_parser,
    main,
    marquee_frame,
    run,
)


class FakeScreen:
    def __init__(self, height: int, width: int, keys: list[int] | None = None) -> None:
        self.height = height
        self.width = width
        self.keys = iter(keys or [])
        self.drawn: list[tuple[int, int, str, int]] = []
        self.nodelay_enabled = False
        self.keypad_enabled = False
        self.erase_count = 0
        self.refresh_count = 0

    def getmaxyx(self) -> tuple[int, int]:
        return self.height, self.width

    def addnstr(self, y: int, x: int, text: str, length: int, attr: int = 0) -> None:
        self.drawn.append((y, x, text[:length], attr))

    def nodelay(self, flag: bool) -> None:
        self.nodelay_enabled = flag

    def keypad(self, flag: bool) -> None:
        self.keypad_enabled = flag

    def getch(self) -> int:
        return next(self.keys)

    def erase(self) -> None:
        self.erase_count += 1

    def refresh(self) -> None:
        self.refresh_count += 1


@dataclass
class FakeArgs:
    stream: str = "https://radio.test/stream"
    volume: int = 60
    no_audio: bool = False


class FakePlayer:
    instances: list["FakePlayer"] = []

    def __init__(self, stream: str, volume: int) -> None:
        self.stream = stream
        self.volume = volume
        self.error = ""
        self.requested_playing = False
        self.is_playing = False
        self.events: list[object] = []
        self.instances.append(self)

    def play(self) -> bool:
        self.events.append("play")
        self.requested_playing = True
        self.is_playing = True
        return True

    def toggle(self) -> None:
        self.events.append("toggle")
        self.requested_playing = not self.requested_playing
        self.is_playing = self.requested_playing

    def toggle_mute(self) -> None:
        self.events.append("mute")

    def change_volume(self, delta: int) -> None:
        self.events.append(("volume", delta))

    def close(self) -> None:
        self.events.append("close")


class FakeMetadata:
    instances: list["FakeMetadata"] = []

    def __init__(self) -> None:
        self.title = "Artist - Track"
        self.error = ""
        self.started = False
        self.closed = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True


class AppTests(unittest.TestCase):
    def test_draws_text_centered(self) -> None:
        screen = FakeScreen(height=10, width=40)

        _draw_centered_line(screen, 4, "RADIO", 7)

        self.assertEqual(screen.drawn, [(4, 17, "RADIO", 7)])

    def test_centered_text_is_shortened_to_terminal_width(self) -> None:
        screen = FakeScreen(height=2, width=10)

        _draw_centered_line(screen, 1, "A very long song")

        self.assertEqual(screen.drawn, [(1, 0, "A very...", 0)])

    def test_safe_draw_ignores_out_of_bounds_and_curses_errors(self) -> None:
        screen = FakeScreen(height=2, width=10)
        _safe_addstr(screen, 3, 0, "outside")
        with patch.object(screen, "addnstr", side_effect=curses.error):
            _safe_addstr(screen, 0, 0, "ignored")

        self.assertEqual(screen.drawn, [])

    def test_short_title_is_centered_without_scrolling(self) -> None:
        first = marquee_frame("RADIO", width=11, offset=0)
        later = marquee_frame("RADIO", width=11, offset=37)

        self.assertEqual(first, "   RADIO   ")
        self.assertEqual(later, first)

    def test_long_title_scrolls_right_to_left(self) -> None:
        title = "A very long song title"

        self.assertEqual(marquee_frame(title, width=10, offset=0), "A very lon")
        self.assertEqual(marquee_frame(title, width=10, offset=1), " very long")

    def test_scrolling_wraps_around_through_the_separator(self) -> None:
        title = "Song title"
        loop = title + MARQUEE_SEPARATOR

        frame = marquee_frame(title, width=8, offset=len(title))

        self.assertEqual(frame, (loop * 2)[len(title) : len(title) + 8])
        self.assertEqual(marquee_frame(title, width=8, offset=len(loop)), "Song tit")

    def test_marquee_pads_empty_titles_and_ignores_empty_width(self) -> None:
        self.assertEqual(marquee_frame("  ", width=4, offset=3), "    ")
        self.assertEqual(marquee_frame("Song", width=0, offset=0), "")

    def test_terminal_title_filters_injected_control_characters(self) -> None:
        output = StringIO()
        with patch("selecto_radio.app.sys.stdout", output):
            _set_terminal_title("Song\x1b]2;pwned\x07")

        self.assertEqual(output.getvalue(), "\x1b]2;Song]2;pwned\x07")

    def test_run_handles_controls_and_always_closes_resources(self) -> None:
        screen = FakeScreen(
            height=12,
            width=80,
            keys=[ord(" "), ord("m"), ord("+"), ord("-"), ord("q")],
        )
        with (
            patch("selecto_radio.app.RadioPlayer", FakePlayer),
            patch("selecto_radio.app.MetadataPoller", FakeMetadata),
            patch("selecto_radio.app.curses.curs_set"),
            patch("selecto_radio.app.curses.has_colors", return_value=False),
            patch("selecto_radio.app.locale.setlocale"),
            patch("selecto_radio.app.time.monotonic", return_value=1.0),
            patch("selecto_radio.app.time.sleep") as sleep,
            patch("selecto_radio.app._set_terminal_title") as set_title,
        ):
            run(screen, FakeArgs())

        player = FakePlayer.instances[-1]
        metadata = FakeMetadata.instances[-1]
        self.assertEqual(
            player.events,
            ["play", "toggle", "mute", ("volume", 5), ("volume", -5), "close"],
        )
        self.assertTrue(metadata.started)
        self.assertTrue(metadata.closed)
        self.assertTrue(screen.nodelay_enabled)
        self.assertTrue(screen.keypad_enabled)
        self.assertEqual(screen.refresh_count, 4)
        self.assertEqual(sleep.call_count, 4)
        sleep.assert_called_with(FRAME_INTERVAL)
        set_title.assert_called_once_with("Artist - Track")

    def test_run_relaunches_an_unexpectedly_exited_player(self) -> None:
        class CrashingPlayer(FakePlayer):
            def play(self) -> bool:
                self.events.append("play")
                self.requested_playing = True
                self.is_playing = False
                return True

        screen = FakeScreen(10, 60, keys=[-1, ord("q")])
        with (
            patch("selecto_radio.app.RadioPlayer", CrashingPlayer),
            patch("selecto_radio.app.MetadataPoller", FakeMetadata),
            patch("selecto_radio.app.curses.curs_set"),
            patch("selecto_radio.app.curses.has_colors", return_value=False),
            patch("selecto_radio.app.locale.setlocale"),
            patch("selecto_radio.app.time.monotonic", return_value=1.0),
            patch("selecto_radio.app.time.sleep"),
            patch("selecto_radio.app._set_terminal_title"),
        ):
            run(screen, FakeArgs())

        self.assertEqual(CrashingPlayer.instances[-1].events, ["play", "play", "close"])

    def test_loop_sleeps_a_fixed_frame_interval(self) -> None:
        screen = FakeScreen(10, 60, keys=[-1, ord("q")])
        with (
            patch("selecto_radio.app.RadioPlayer", FakePlayer),
            patch("selecto_radio.app.MetadataPoller", FakeMetadata),
            patch("selecto_radio.app.curses.curs_set"),
            patch("selecto_radio.app.curses.has_colors", return_value=False),
            patch("selecto_radio.app.locale.setlocale"),
            patch("selecto_radio.app.time.monotonic", return_value=1.0),
            patch("selecto_radio.app.time.sleep") as sleep,
            patch("selecto_radio.app._set_terminal_title"),
        ):
            run(screen, FakeArgs())

        # The redraw rate is an internal constant, independent of CLI arguments.
        sleep.assert_called_once_with(FRAME_INTERVAL)

    def test_run_displays_player_and_metadata_errors(self) -> None:
        class ErrorPlayer(FakePlayer):
            def play(self) -> bool:
                self.events.append("play")
                self.requested_playing = True
                self.error = "player unavailable"
                return False

        class ErrorMetadata(FakeMetadata):
            def __init__(self) -> None:
                super().__init__()
                self.error = "metadata unavailable"

        screen = FakeScreen(10, 120, keys=[-1, ord("q")])
        with (
            patch("selecto_radio.app.RadioPlayer", ErrorPlayer),
            patch("selecto_radio.app.MetadataPoller", ErrorMetadata),
            patch("selecto_radio.app.curses.curs_set"),
            patch("selecto_radio.app.curses.has_colors", return_value=False),
            patch("selecto_radio.app.locale.setlocale"),
            patch("selecto_radio.app.time.monotonic", return_value=1.0),
            patch("selecto_radio.app.time.sleep"),
            patch("selecto_radio.app._set_terminal_title"),
        ):
            run(screen, FakeArgs())

        rendered = " ".join(text for _, _, text, _ in screen.drawn)
        self.assertIn("Error: player unavailable | metadata unavailable", rendered)

    def test_no_audio_mode_ignores_playback_keys(self) -> None:
        screen = FakeScreen(10, 60, keys=[ord(" "), ord("m"), ord("+"), ord("-"), ord("q")])
        with (
            patch("selecto_radio.app.RadioPlayer", FakePlayer),
            patch("selecto_radio.app.MetadataPoller", FakeMetadata),
            patch("selecto_radio.app.curses.curs_set"),
            patch("selecto_radio.app.curses.has_colors", return_value=False),
            patch("selecto_radio.app.locale.setlocale"),
            patch("selecto_radio.app.time.monotonic", return_value=1.0),
            patch("selecto_radio.app.time.sleep"),
            patch("selecto_radio.app._set_terminal_title"),
        ):
            run(screen, FakeArgs(no_audio=True))

        self.assertEqual(FakePlayer.instances[-1].events, ["close"])

    def test_default_volume_is_100(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.volume, 100)

    def test_legacy_no_op_options_remain_accepted(self) -> None:
        args = build_parser().parse_args(
            [
                "--seed",
                "1",
                "--segments",
                "20",
                "--camera-speed",
                "0",
                "--orthographic",
            ]
        )
        self.assertEqual(args.seed, 1)
        self.assertEqual(args.segments, 20)
        self.assertEqual(args.camera_speed, 0.0)
        self.assertTrue(args.orthographic)

    def test_rejects_out_of_range_camera_speed(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["--camera-speed", "10.1"])

    def test_rejects_removed_fps_option(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["--fps", "10"])

    def test_main_delegates_to_curses_and_ignores_keyboard_interrupt(self) -> None:
        with patch("selecto_radio.app.curses.wrapper", side_effect=KeyboardInterrupt) as wrapper:
            main(["--no-audio"])

        wrapper.assert_called_once()
