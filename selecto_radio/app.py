"""Curses application entry point."""

from __future__ import annotations

import argparse
import curses
import locale
import time

from . import __version__
from .metadata import MetadataPoller
from .player import RadioPlayer

STREAM_URL = "https://radios.solumedia.com:6590/stream"


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
    parser.add_argument("--fps", type=int, choices=range(1, 31), default=10, metavar="1-30")
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


def _safe_addstr(screen: curses.window, y: int, x: int, text: str, attr: int = 0) -> None:
    height, width = screen.getmaxyx()
    if not (0 <= y < height and 0 <= x < width):
        return
    try:
        screen.addnstr(y, x, text, max(0, width - x - 1), attr)
    except curses.error:
        pass


def _draw_centered_line(
    screen: curses.window,
    y: int,
    text: str,
    attr: int = 0,
) -> None:
    _, width = screen.getmaxyx()
    visible_text = _fit(text, max(0, width - 1))
    x = max(0, (width - len(visible_text)) // 2)
    _safe_addstr(screen, y, x, visible_text, attr)


def run(screen: curses.window, args: argparse.Namespace) -> None:
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

            text_attr = curses.color_pair(1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
            top = max(0, (height - 2) // 2)
            _draw_centered_line(screen, top, "SONIDO SELECTO 102.9", text_attr)
            _draw_centered_line(screen, top + 1, f"Now playing: {metadata.title}", text_attr)
            screen.refresh()

            elapsed = time.monotonic() - started
            time.sleep(max(0.0, 1 / args.fps - elapsed))
    finally:
        metadata.close()
        player.close()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        curses.wrapper(run, args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
