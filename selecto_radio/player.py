"""Audio playback through a small external media player."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Backend:
    executable: str
    name: str

    def command(self, stream_url: str, volume: int) -> list[str]:
        if self.name == "mpv":
            return [
                self.executable,
                "--no-video",
                "--really-quiet",
                "--no-terminal",
                f"--volume={volume}",
                stream_url,
            ]
        if self.name == "ffplay":
            return [
                self.executable,
                "-nodisp",
                "-loglevel",
                "quiet",
                "-volume",
                str(volume),
                stream_url,
            ]
        return [
            self.executable,
            "--intf",
            "dummy",
            "--play-and-exit",
            f"--gain={volume / 100:.2f}",
            stream_url,
        ]


def find_backend() -> Backend | None:
    """Return the first supported player found in PATH."""
    for executable, name in (("mpv", "mpv"), ("ffplay", "ffplay"), ("cvlc", "vlc"), ("vlc", "vlc")):
        path = shutil.which(executable)
        if path:
            return Backend(path, name)
    return None


class RadioPlayer:
    """Manage a live stream process.

    Restarting a live stream is equivalent to resuming it at the current live
    position. This keeps controls consistent across all supported backends.
    """

    def __init__(self, stream_url: str, volume: int = 100) -> None:
        self.stream_url = stream_url
        self.volume = max(0, min(100, volume))
        self.previous_volume = self.volume or 100
        self.backend = find_backend()
        self.process: subprocess.Popen[bytes] | None = None
        self.requested_playing = False
        self.error = ""

    @property
    def is_playing(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def backend_name(self) -> str:
        return self.backend.name if self.backend else "no player"

    def play(self) -> bool:
        self.requested_playing = True
        if self.backend is None:
            self.error = "Install mpv, ffplay, or vlc to listen to the station"
            return False
        if self.is_playing:
            return True
        if self.process is not None:
            self.process.wait()
            self.process = None
        try:
            self.process = subprocess.Popen(
                self.backend.command(self.stream_url, self.volume),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            self.error = f"Could not start {self.backend.name}: {exc}"
            self.process = None
            return False
        self.error = ""
        return True

    def pause(self) -> None:
        self.requested_playing = False
        self._stop_process()

    def toggle(self) -> None:
        if self.requested_playing:
            self.pause()
        else:
            self.play()

    def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, volume))
        if volume > 0:
            self.previous_volume = volume
        if volume == self.volume:
            return
        self.volume = volume
        self._restart_if_playing()

    def change_volume(self, delta: int) -> None:
        self.set_volume(self.volume + delta)

    def toggle_mute(self) -> None:
        self.set_volume(self.previous_volume if self.volume == 0 else 0)

    def close(self) -> None:
        self.requested_playing = False
        self._stop_process()

    def _restart_if_playing(self) -> None:
        if not self.requested_playing:
            return
        self._stop_process()
        self.play()

    def _stop_process(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1.0)
        self.process = None
