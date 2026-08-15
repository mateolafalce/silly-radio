# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Run everything from the project's virtual environment (`.venv/bin/python`). The package is installed in editable mode, so `import selecto_radio` works without adjusting `PYTHONPATH`.

Note: `.venv/bin/pip` is broken on this machine (`cannot execute: required file not found`). Use `.venv/bin/python -m pip ...` to install packages.

## Commands

```bash
# Full suite (pytest is not installed; use unittest)
.venv/bin/python -m unittest discover -s tests -v

# A single file / class / test
.venv/bin/python -m unittest tests.test_player
.venv/bin/python -m unittest tests.test_player.PlayerTests.test_mpv_command

# Run the app
.venv/bin/radio
.venv/bin/python -m selecto_radio --no-audio      # no audio, useful for testing the UI
```

No linter or formatter is configured.

## Architecture

A curses-based terminal app that plays the Sonido Selecto FM 102.9 stream. `app.py` assembles three independent components:

- **`app.py`** — argument parsing, curses loop, and rendering. The loop makes a single pass per frame: read key → apply action → clear screen → draw the centered station name and, below it, the song line → sleep for the remaining time needed to maintain `--fps`. All writes go through `_safe_addstr`, which ignores `curses.error` and truncates to the available width so resizing the terminal never breaks rendering. The song line is rendered by `marquee_frame`, a pure function that takes the elapsed time (not the frame number) so scrolling stays at `MARQUEE_SPEED` characters per second regardless of `--fps`; a title that fits on the line is centered and does not scroll. Every time the track changes, `_set_terminal_title` also writes it to the terminal's own title bar with an OSC escape sequence. Both lines use `color_pair(1)` without `A_BOLD`: bold turns `COLOR_BLACK` into bright black (gray) on most terminals.
- **`player.py`** — audio is not controlled from Python: an external media player (`mpv` → `ffplay` → `cvlc`/`vlc`, in that order of preference) is launched as a subprocess with `start_new_session=True`. As a design consequence, **there is no live volume or pause control**; pausing kills the process, and changing the volume restarts it with a different flag. This is acceptable for a live stream because resuming simply reconnects at the current broadcast position. `requested_playing` stores the user's intent, and the `app.py` loop uses it to relaunch the process if the external player exits unexpectedly.
- **`metadata.py`** — a daemon thread polls `get_radio_info.php` every 15 seconds and publishes the title to `MetadataPoller.title`. The UI reads that attribute without blocking or locking; errors are stored in `.error`, and the last valid title is retained.

There are no external runtime dependencies; everything uses the standard library.

### No-op flags

These CLI flags do nothing and are hidden (`argparse.SUPPRESS`); they are retained to avoid breaking existing launch scripts: `--seed`, `--segments`, `--camera-speed`, `--orthographic`, and `--reset-pipes`. They are remnants of the animated scenes (`castle.py` and `pipes.py`) that the project previously included and that have since been removed. `test_app.py` still verifies that the parser accepts them and validates their ranges.

If a scene is ever added, the insertion point is the drawing block inside `run()` in `app.py`.

### Conventions

- User-facing text (titles, error messages, and argparse help), docstrings, and comments are in English.
- Tests do not use curses or the real network: `test_app.py` injects a `FakeScreen` with `getmaxyx`/`addnstr`, and `test_player.py` patches `shutil.which`. Follow that pattern when adding tests.
