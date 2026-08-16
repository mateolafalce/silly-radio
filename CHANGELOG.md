# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- The currently playing song, on the line below the station name, scrolls from right to left in an endless loop when it does not fit on the line. The track is also published in the terminal's own title bar.
- `radio` console script as the primary command. `sonido-selecto` is kept as an alias so existing launch scripts keep working; the argparse `prog` and the image's `ENTRYPOINT` now use `radio`.
- MIT license in the `LICENSE` file, which had previously only been declared in `pyproject.toml`.
- Development dependencies (`ruff`, `pre-commit`) in the `dev` extra in `pyproject.toml`.
- Ruff configuration for linting and formatting.
- Continuous integration with GitHub Actions: linting, formatting, and tests on Python 3.10 through 3.13.
- `CONTRIBUTING.md` with the project's workflow and conventions.
- `.editorconfig` and `.pre-commit-config.yaml`.
- Multi-stage `Dockerfile` (Alpine + `mpv`) and `docker-compose.yml` so the player can be run with `docker compose run --rm radio`, with the host sound server exposed through the PulseAudio socket and the container limited to 128 MiB, half a CPU, and 64 processes.
- `.dockerignore` restricting the build context to `pyproject.toml`, `README.md`, and the package itself.
- This changelog.
- Strict mypy checking for production code and tests, Bandit security checks, and branch coverage reporting with a 90% CI gate.
- Lifecycle tests for the curses loop, subprocess termination and kill escalation, and metadata polling retries and shutdown.
- Dependabot configuration, pip caching in CI, and immutable SHA pins for GitHub Actions.

### Changed

- The two lines on screen are drawn without `A_BOLD`, because bold turns `COLOR_BLACK` into bright black (gray) on most terminals and they must be 100% black.
- The song line no longer carries the `Now playing:` prefix, so the whole width is available for the scrolling title.
- Playback backends now encapsulate their commands and live-control capabilities instead of being selected by repeated name comparisons.
- Package metadata reads its version dynamically from `selecto_radio.__version__`; the Docker image no longer duplicates the version in its name.
- Metadata shutdown now waits for the bounded in-flight request, and transient failures retain the last valid title while retrying.

### Fixed

- Player and metadata errors are now rendered in the interface.
- Control characters are removed from metadata and terminal-title output to prevent escape-sequence injection.
- Corrected stale development and architecture guidance in `CLAUDE.md` and `CONTRIBUTING.md`.

### Removed

- The `--fps` option and configurable refresh rate. The redraw interval is now the internal `FRAME_INTERVAL` constant, fixed at twice `MARQUEE_SPEED`.
- The `castle.py` and `pipes.py` modules and their tests. They were animated scenes from earlier versions of the display that were no longer imported.
- The `selecto_radio/assets/castle.png` asset, which was only used by `castle.py`.
- The `Pillow` dependency, which was only used by `castle.py`. The project now has no runtime dependencies outside the standard library.

### Intentionally unchanged

- The `--seed`, `--segments`, `--camera-speed`, `--orthographic`, and `--reset-pipes` flags remain accepted as hidden no-ops to avoid breaking existing launch scripts.
  They are scheduled for removal in 2.0.0, no earlier than 2027-02-16.

## [1.0.0] - 2026-08-14

### Added

- Curses-based terminal player for the Sonido Selecto FM 102.9 stream.
- Playback through an external media player (`mpv`, `ffplay`, or `vlc`, in that order of preference) launched as a subprocess.
- Background metadata polling every 15 seconds to display the currently playing title.
- Keyboard controls for play/pause, mute, volume up/down, and quit.
- `--no-audio`, `--volume`, `--stream`, and `--fps` command-line options.
