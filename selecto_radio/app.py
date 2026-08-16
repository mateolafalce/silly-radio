"""Curses application entry point."""

from __future__ import annotations

import argparse
import curses
import locale
import sys
import time
from typing import Protocol, cast

from . import __version__
from .metadata import MetadataPoller, sanitize_title
from .player import RadioPlayer

STREAM_URL = "https://radios.solumedia.com:6590/stream"
# Text inserted between two passes of the title so the loop is readable.
MARQUEE_SEPARATOR = "   ***   "
# Scrolling speed in characters per second.
MARQUEE_SPEED = 6.0
# Seconds between redraws. The marquee offset only advances MARQUEE_SPEED times
# per second, so a faster loop would redraw identical frames and a slower one
# would make the scroll skip characters; twice MARQUEE_SPEED also keeps key
# latency low, because getch() is polled once per pass.
FRAME_INTERVAL = 1 / (MARQUEE_SPEED * 2)


class DrawingScreen(Protocol):
    """Small curses surface used by the rendering helpers."""

    def getmaxyx(self) -> tuple[int, int]: ...

    def addnstr(self, y: int, x: int, text: str, length: int, attr: int = 0) -> None: ...


class CursesScreen(DrawingScreen, Protocol):
    """Curses operations required by the application loop."""

    def nodelay(self, flag: bool) -> None: ...

    def keypad(self, flag: bool) -> None: ...

    def getch(self) -> int: ...

    def erase(self) -> None: ...

    def refresh(self) -> None: ...


class AppArgs(Protocol):
    stream: str
    volume: int
    no_audio: bool


def _camera_speed(value: str) -> float:
    speed = float(value)
    if not 0.0 <= speed <= 10.0:
        raise argparse.ArgumentTypeError("must be between 0 and 10")
    return speed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radio",
        description="Minimalist Sonido Selecto FM player.",
    )
    parser.add_argument("--stream", default=STREAM_URL, help="audio stream URL")
    parser.add_argument("--volume", type=int, choices=range(0, 101), default=100, metavar="0-100")
    # Kept as hidden no-op options so existing launch scripts do not break after
    # replacing the old pipes scene.
    parser.add_argument("--seed", type=int, default=99, help=argparse.SUPPRESS)
    parser.add_argument(
        "--segments",
        type=int,
        choices=range(20, 5001),
        default=600,
        metavar="20-5000",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--camera-speed",
        type=_camera_speed,
        default=4.0,
        metavar="0-10",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--orthographic", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--reset-pipes", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-audio", action="store_true", help="show the station without playing audio")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _init_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, -1)


def _fit(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    return text[: max(0, width - 3)] + ("..." if width >= 3 else "")


def _safe_addstr(screen: DrawingScreen, y: int, x: int, text: str, attr: int = 0) -> None:
    height, width = screen.getmaxyx()
    if not (0 <= y < height and 0 <= x < width):
        return
    try:
        screen.addnstr(y, x, text, max(0, width - x - 1), attr)
    except curses.error:
        pass


def _draw_centered_line(
    screen: DrawingScreen,
    y: int,
    text: str,
    attr: int = 0,
) -> None:
    _, width = screen.getmaxyx()
    visible_text = _fit(text, max(0, width - 1))
    x = max(0, (width - len(visible_text)) // 2)
    _safe_addstr(screen, y, x, visible_text, attr)


def marquee_frame(text: str, width: int, offset: int) -> str:
    """Return the `width` characters of `text` visible at `offset`.

    The text scrolls from right to left in an endless loop. If it already fits
    on the line it is centered and stays still.
    """
    if width <= 0:
        return ""
    text = " ".join(text.split())
    if not text:
        return " " * width
    if len(text) <= width:
        padding = width - len(text)
        left = padding // 2
        return " " * left + text + " " * (padding - left)
    loop = text + MARQUEE_SEPARATOR
    start = offset % len(loop)
    repeats = (start + width) // len(loop) + 1
    return (loop * repeats)[start : start + width]


def _draw_marquee_line(
    screen: DrawingScreen,
    y: int,
    text: str,
    elapsed: float,
    attr: int = 0,
) -> None:
    _, width = screen.getmaxyx()
    offset = int(elapsed * MARQUEE_SPEED)
    _safe_addstr(screen, y, 0, marquee_frame(text, max(0, width - 1), offset), attr)


def _set_terminal_title(text: str) -> None:
    """Publish the track in the terminal's own title bar (ignored if unsupported)."""
    try:
        sys.stdout.write(f"\033]2;{sanitize_title(text)}\007")
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def run(screen: CursesScreen, args: AppArgs) -> None:
    locale.setlocale(locale.LC_ALL, "")
    curses.curs_set(0)
    screen.nodelay(True)
    screen.keypad(True)
    _init_colors()

    player = RadioPlayer(args.stream, args.volume)
    metadata = MetadataPoller()
    metadata.start()
    if not args.no_audio:
        player.play()

    start_time = time.monotonic()
    shown_title = ""
    try:
        while True:
            started = time.monotonic()
            key = screen.getch()
            if key in (ord("q"), ord("Q"), 27):
                break
            if key == ord(" ") and not args.no_audio:
                player.toggle()
            elif key in (ord("m"), ord("M")) and not args.no_audio:
                player.toggle_mute()
            elif key in (ord("+"), ord("="), curses.KEY_UP) and not args.no_audio:
                player.change_volume(5)
            elif key in (ord("-"), ord("_"), curses.KEY_DOWN) and not args.no_audio:
                player.change_volume(-5)

            height, _ = screen.getmaxyx()
            screen.erase()
            if not player.error and player.requested_playing and not player.is_playing and not args.no_audio:
                player.play()

            # No A_BOLD: bold turns COLOR_BLACK into bright black (gray) on most
            # terminals, and both lines must stay 100% black.
            text_attr = curses.color_pair(1) if curses.has_colors() else 0
            title = metadata.title
            if title != shown_title:
                shown_title = title
                _set_terminal_title(title)
            errors = [message for message in (player.error, metadata.error) if message]
            top = max(0, (height - (3 if errors else 2)) // 2)
            _draw_centered_line(screen, top, "SONIDO SELECTO 102.9", text_attr)
            _draw_marquee_line(screen, top + 1, title, started - start_time, text_attr)
            if errors:
                _draw_centered_line(screen, top + 2, f"Error: {' | '.join(errors)}", text_attr)
            screen.refresh()

            elapsed = time.monotonic() - started
            time.sleep(max(0.0, FRAME_INTERVAL - elapsed))
    finally:
        metadata.close()
        player.close()


def main(argv: list[str] | None = None) -> None:
    args = cast(AppArgs, build_parser().parse_args(argv))
    try:
        curses.wrapper(run, args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
