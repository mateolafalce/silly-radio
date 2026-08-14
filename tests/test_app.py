import unittest
from contextlib import redirect_stderr
from io import StringIO

from selecto_radio.app import _draw_centered_line, build_parser


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
