# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Run everything from the project's virtual environment (`.venv/bin/python`). The package is installed in editable mode, so `import selecto_radio` works without adjusting `PYTHONPATH`.

Note: `.venv/bin/pip` is broken on this machine (`cannot execute: required file not found`). Use `.venv/bin/python -m pip ...` to install packages.

## Commands

```bash
# Full suite with the enforced coverage threshold
.venv/bin/coverage run -m unittest discover -s tests -v
.venv/bin/coverage report

# A single file / class / test
.venv/bin/python -m unittest tests.test_player
.venv/bin/python -m unittest tests.test_player.PlayerTests.test_backend_commands

# Static checks
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/bandit -c pyproject.toml -r selecto_radio

# Run the app
.venv/bin/radio
.venv/bin/python -m selecto_radio --no-audio      # no audio, useful for testing the UI
```

Ruff provides linting and formatting, mypy checks all production and test annotations in strict mode,
Bandit checks common security mistakes, and coverage enforces at least 90% branch coverage. CI runs all of them.

## Architecture

A curses-based terminal app that plays the Sonido Selecto FM 102.9 stream. `app.py` assembles three independent components:

- **`app.py`** — argument parsing, curses loop, and rendering. The curses surface is described by small `Protocol` interfaces so rendering and the full loop can be tested with structural fakes. The loop makes a single pass per frame: read key → apply action → clear screen → draw the station, track, and any player/metadata error → sleep for the rest of `FRAME_INTERVAL`. The redraw rate is fixed at twice `MARQUEE_SPEED` and is not configurable: the marquee offset only advances `MARQUEE_SPEED` times per second, so a faster loop would redraw identical frames and a slower one would make the scroll skip characters. It also bounds key latency, because `getch()` is polled once per pass. All writes go through `_safe_addstr`, which ignores `curses.error` and truncates to the available width. The song line uses elapsed time, not the frame number, so scrolling speed stays constant. Track changes update the terminal title after control characters have been removed.
- **`player.py`** — an external media player (`mpv` → `ffplay` → `cvlc`/`vlc`) is launched as a subprocess with `start_new_session=True`. Each backend class owns its command and optional live-volume implementation; `RadioPlayer` does not branch on backend names. `mpv` changes volume through JSON IPC, while `ffplay` and VLC restart as a compatibility fallback. Pausing terminates the process, escalating to `kill` after a timeout. `requested_playing` stores user intent, and the app relaunches a player that exits unexpectedly.
- **`metadata.py`** — a daemon thread polls `get_radio_info.php` every 15 seconds and publishes a sanitized title. Transient failures retain the last valid title and expose the error to the UI. `close()` interrupts interval waits and then joins the poller, including an in-flight request bounded by its network timeout.

There are no external runtime dependencies; everything uses the standard library.

### No-op flags

These CLI flags do nothing and are hidden (`argparse.SUPPRESS`); they are retained to avoid breaking existing launch scripts: `--seed`, `--segments`, `--camera-speed`, `--orthographic`, and `--reset-pipes`. They are remnants of removed animated scenes. They are scheduled for removal in 2.0.0, no earlier than 2027-02-16. Until then, tests verify that the parser keeps accepting them.

If a scene is ever added, the insertion point is the drawing block inside `run()` in `app.py`.

### Conventions

- User-facing text (titles, error messages, and argparse help), docstrings, and comments are in English.
- Tests do not use real curses, network, or subprocesses: inject structural fakes and patch only the external boundary.
