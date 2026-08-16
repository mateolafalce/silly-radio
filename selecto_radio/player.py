"""Audio playback through a small external media player."""

from __future__ import annotations

import json
import shutil
import socket

# External playback is this module's purpose; process creation never invokes a shell.
import subprocess  # nosec B404
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class Backend(ABC):
    """Playback backend with its own command and optional live controls."""

    executable: str
    name: ClassVar[str]
    uses_control_socket: ClassVar[bool] = False

    @abstractmethod
    def command(self, stream_url: str, volume: int, control_path: str | None = None) -> list[str]:
        """Build the subprocess command for this backend."""

    def set_live_volume(self, control_path: str | None, volume: int) -> bool:
        """Apply a volume change without restarting, if supported."""
        return False


@dataclass(frozen=True)
class MpvBackend(Backend):
    name: ClassVar[str] = "mpv"
    uses_control_socket: ClassVar[bool] = True

    def command(self, stream_url: str, volume: int, control_path: str | None = None) -> list[str]:
        command = [
            self.executable,
            "--no-video",
            "--really-quiet",
            "--no-terminal",
            f"--volume={volume}",
        ]
        if control_path is not None:
            command.append(f"--input-ipc-server={control_path}")
        command.append(stream_url)
        return command

    def set_live_volume(self, control_path: str | None, volume: int) -> bool:
        if control_path is None:
            return False

        message = json.dumps({"command": ["set_property", "volume", volume]}) + "\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as ipc_socket:
                ipc_socket.settimeout(0.2)
                ipc_socket.connect(control_path)
                ipc_socket.sendall(message.encode("utf-8"))
        except OSError:
            return False
        return True


@dataclass(frozen=True)
class FfplayBackend(Backend):
    name: ClassVar[str] = "ffplay"

    def command(self, stream_url: str, volume: int, control_path: str | None = None) -> list[str]:
        return [
            self.executable,
            "-nodisp",
            "-loglevel",
            "quiet",
            "-volume",
            str(volume),
            stream_url,
        ]


@dataclass(frozen=True)
class VlcBackend(Backend):
    name: ClassVar[str] = "vlc"

    def command(self, stream_url: str, volume: int, control_path: str | None = None) -> list[str]:
        return [
            self.executable,
            "--intf",
            "dummy",
            "--play-and-exit",
            f"--gain={volume / 100:.2f}",
            stream_url,
        ]


BACKEND_CANDIDATES: Sequence[tuple[str, type[Backend]]] = (
    ("mpv", MpvBackend),
    ("ffplay", FfplayBackend),
    ("cvlc", VlcBackend),
    ("vlc", VlcBackend),
)


def find_backend() -> Backend | None:
    """Return the first supported player found in PATH."""
    for executable, backend_type in BACKEND_CANDIDATES:
        path = shutil.which(executable)
        if path:
            return backend_type(path)
    return None


class RadioPlayer:
    """Manage a live stream process.

    mpv supports live volume changes through JSON IPC. Other backends restart
    the live stream when the volume changes.
    """

    def __init__(self, stream_url: str, volume: int = 100) -> None:
        self.stream_url = stream_url
        self.volume = max(0, min(100, volume))
        self.previous_volume = self.volume or 100
        self.backend = find_backend()
        self._ipc_directory: tempfile.TemporaryDirectory[str] | None = None
        self._ipc_path: str | None = None
        if self.backend is not None and self.backend.uses_control_socket:
            self._ipc_directory = tempfile.TemporaryDirectory(prefix="silly-radio-")
            self._ipc_path = str(Path(self._ipc_directory.name) / "mpv.sock")
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
            # The executable is resolved from BACKEND_CANDIDATES, a fixed allowlist.
            self.process = subprocess.Popen(  # nosec B603
                self.backend.command(self.stream_url, self.volume, self._ipc_path),
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
        self._apply_volume_if_playing()

    def change_volume(self, delta: int) -> None:
        self.set_volume(self.volume + delta)

    def toggle_mute(self) -> None:
        self.set_volume(self.previous_volume if self.volume == 0 else 0)

    def close(self) -> None:
        self.requested_playing = False
        self._stop_process()

        if self._ipc_directory is not None:
            self._ipc_directory.cleanup()
            self._ipc_directory = None
            self._ipc_path = None

    def _apply_volume_if_playing(self) -> None:
        if not self.requested_playing:
            return
        if self._send_live_volume():
            return
        self._restart_if_playing()

    def _send_live_volume(self) -> bool:
        if not self.is_playing or self.backend is None:
            return False
        return self.backend.set_live_volume(self._ipc_path, self.volume)

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
        if self._ipc_path is not None:
            Path(self._ipc_path).unlink(missing_ok=True)
