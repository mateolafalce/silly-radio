# Sonido Selecto CLI

A minimalist terminal radio that plays [Sonido Selecto FM 102.9](https://sonidoselecto.com/radio/). The screen displays only the station name and the currently playing song, centered in black text on the terminal's default background.

## Requirements

- Python 3.10 or later.
- One of these media players available in `PATH`: `mpv`, `ffplay`, or `vlc`.

On Ubuntu or Debian, the smallest option is:

```bash
sudo apt install mpv
```

## Installation

From this directory:

```bash
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/radio
```

Once the virtual environment is active (`source .venv/bin/activate`), the command is simply:

```bash
radio
```

You can also run it without installing the package:

```bash
.venv/bin/python -m selecto_radio
```

Playback starts automatically.

## Docker

An alternative that requires neither Python nor `mpv` on the host — only Docker and Docker Compose:

```bash
docker compose run --rm radio
```

The first run builds the image; later runs start in seconds. Use `run` and not `up`: the interface is curses and needs a real terminal.

Extra CLI options go at the end:

```bash
docker compose run --rm radio --no-audio
docker compose run --rm radio --volume 60 --fps 5
```

The container uses the desktop sound server (PulseAudio or PipeWire) through the `${XDG_RUNTIME_DIR}/pulse/native` socket. For systems without a sound server, `docker-compose.yml` includes a commented-out ALSA variant (`/dev/snd`).

Measured usage while playing: about 45 MiB of RAM and 3% of one core. `docker-compose.yml` caps the container at 128 MiB, half a CPU, and 64 processes, and runs it unprivileged, read-only, and as a non-root user.

## Controls

| Key | Action |
|---|---|
| `Space` | Play or pause |
| `M` | Mute or unmute |
| `+` / `-` | Raise or lower the volume |
| `Q` | Quit |

## Options

```text
--no-audio      Show the station without playing audio
--volume 0-100  Set the initial volume
--stream URL    Play another compatible stream
--fps 1-30      Set the screen refresh rate
```

The stream and metadata are fetched directly from the public services used by the station's website.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the development workflow, test commands, and project conventions. Release changes are documented in [`CHANGELOG.md`](CHANGELOG.md).

## License

MIT. See [`LICENSE`](LICENSE).
