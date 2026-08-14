# Contributing

## Environment

Always run the project from its local virtual environment. The package is installed in editable mode, so `import selecto_radio` works without changing `PYTHONPATH`.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

> On some machines, the `.venv/bin/pip` executable is broken (`cannot execute: required file not found`). For this reason, all installation commands use `.venv/bin/python -m pip`.

In addition to Python 3.10 or later, one of these media players must be available in `PATH` to play audio: `mpv`, `ffplay`, or `vlc`. The tests do not require one.

## Tests

The suite uses the standard library's `unittest`; pytest is not required.

```bash
# Full suite
.venv/bin/python -m unittest discover -s tests -v

# A single file, class, or test
.venv/bin/python -m unittest tests.test_player
.venv/bin/python -m unittest tests.test_player.PlayerTests.test_mpv_command
```

The tests never access curses or the real network. `test_app.py` injects a `FakeScreen` that implements `getmaxyx` and `addnstr`; `test_player.py` patches `shutil.which`. Follow this pattern when adding new tests.

## Linting and formatting

```bash
.venv/bin/ruff check .
.venv/bin/ruff format .
```

Optionally, install the hooks to run these checks before every commit:

```bash
.venv/bin/pre-commit install
```

## Running the app

```bash
.venv/bin/radio
.venv/bin/python -m selecto_radio --no-audio   # no audio, useful for testing the UI
```

## Conventions

- **Language:** user-facing text (titles, error messages, and argparse help) must be in English, as must code docstrings and comments.
- **Commits:** keep each commit focused on a single change and use an imperative English subject.
- **CI:** every push to `main` and every pull request runs linting, formatting, and tests on Python 3.10 through 3.13. Do not merge while checks are failing.

## Architecture notes

Before changing the code, read `CLAUDE.md`. It explains the three components assembled by `app.py` (`app.py`, `player.py`, and `metadata.py`) and why there is no live volume or pause control.

One potentially surprising detail: the `--seed`, `--segments`, `--camera-speed`, `--orthographic`, and `--reset-pipes` flags do nothing. They are hidden (`argparse.SUPPRESS`) and retained to avoid breaking existing launch scripts, but the animated scenes that used them are no longer part of the project.
