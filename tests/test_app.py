import unittest
from contextlib import redirect_stderr
from io import StringIO

from selecto_radio.app import MARQUEE_SEPARATOR, _draw_centered_line, build_parser, marquee_frame


class FakeScreen:
    def __init__(self, height: int, width: int) -> None:
        self.height = height
        self.width = width
        self.drawn: list[tuple[int, int, str, int]] = []

    def getmaxyx(self) -> tuple[int, int]:
        return self.height, self.width

    def addnstr(self, y: int, x: int, text: str, length: int, attr: int) -> None:
        self.drawn.append((y, x, text[:length], attr))


class AppTests(unittest.TestCase):
    def test_draws_text_centered(self) -> None:
        screen = FakeScreen(height=10, width=40)

        _draw_centered_line(screen, 4, "RADIO", 7)

        self.assertEqual(screen.drawn, [(4, 17, "RADIO", 7)])

    def test_centered_text_is_shortened_to_terminal_width(self) -> None:
        screen = FakeScreen(height=2, width=10)

        _draw_centered_line(screen, 1, "A very long song")

        self.assertEqual(screen.drawn, [(1, 0, "A very...", 0)])

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

    def test_default_volume_is_100(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.volume, 100)

    def test_default_pipe_options(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.seed, 99)
        self.assertEqual(args.segments, 600)
        self.assertEqual(args.camera_speed, 4.0)
        self.assertFalse(args.orthographic)

    def test_rejects_out_of_range_camera_speed(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["--camera-speed", "10.1"])
