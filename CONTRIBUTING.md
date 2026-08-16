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

The suite uses the standard library's `unittest`; pytest is not required. Branch coverage must remain at or
above 90%.

```bash
# Full suite and coverage gate
.venv/bin/coverage run -m unittest discover -s tests -v
.venv/bin/coverage report

# A single file, class, or test
.venv/bin/python -m unittest tests.test_player
.venv/bin/python -m unittest tests.test_player.PlayerTests.test_backend_commands
```

The tests never access real curses, network services, media players, or subprocesses. Use structural fakes and patch external boundaries.

## Linting and formatting

```bash
.venv/bin/ruff check .
.venv/bin/ruff format .
.venv/bin/mypy
.venv/bin/bandit -c pyproject.toml -r selecto_radio
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
- **CI:** every push to `main` and every pull request runs linting, formatting, strict type checking, security checks, and coverage-enforced tests on Python 3.10 through 3.13. Do not merge while checks are failing.
- **Versioning:** `selecto_radio.__version__` is the single version source. Setuptools reads it dynamically. Release commits must be tagged `vX.Y.Z` with the same value.

## Architecture notes

Before changing the code, read `CLAUDE.md`. It explains the three components assembled by `app.py` (`app.py`, `player.py`, and `metadata.py`), including live `mpv` volume control and play/pause behavior.

One potentially surprising detail: the `--seed`, `--segments`, `--camera-speed`, `--orthographic`, and `--reset-pipes` flags do nothing. They are hidden (`argparse.SUPPRESS`) and temporarily retained for existing launch scripts. They will be removed in 2.0.0, no earlier than 2027-02-16.
