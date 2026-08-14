# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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

### Removed

- The `castle.py` and `pipes.py` modules and their tests. They were animated scenes from earlier versions of the display that were no longer imported.
- The `selecto_radio/assets/castle.png` asset, which was only used by `castle.py`.
- The `Pillow` dependency, which was only used by `castle.py`. The project now has no runtime dependencies outside the standard library.

### Intentionally unchanged

- The `--seed`, `--segments`, `--camera-speed`, `--orthographic`, and `--reset-pipes` flags remain accepted as hidden no-ops to avoid breaking existing launch scripts.

## [1.0.0] - 2026-08-14

### Added

- Curses-based terminal player for the Sonido Selecto FM 102.9 stream.
- Playback through an external media player (`mpv`, `ffplay`, or `vlc`, in that order of preference) launched as a subprocess.
- Background metadata polling every 15 seconds to display the currently playing title.
- Keyboard controls for play/pause, mute, volume up/down, and quit.
- `--no-audio`, `--volume`, `--stream`, and `--fps` command-line options.
