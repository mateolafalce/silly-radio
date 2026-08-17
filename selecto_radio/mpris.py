# mypy: disable-error-code="no-redef,untyped-decorator"
"""MPRIS integration for Linux desktop media controls."""

import asyncio
import os
import threading
from dataclasses import dataclass, replace
from queue import Empty, SimpleQueue
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method
from dbus_next.signature import Variant

# dbus-next reads these annotations as D-Bus signatures at runtime. Static
# checkers instead see the corresponding Python value types.
if TYPE_CHECKING:
    DbusBool: TypeAlias = bool
    DbusDouble: TypeAlias = float
    DbusInt64: TypeAlias = int
    DbusObjectPath: TypeAlias = str
    DbusString: TypeAlias = str
    DbusStringArray: TypeAlias = list[str]
    DbusVariantMap: TypeAlias = dict[str, Variant]
else:
    DbusBool = "b"
    DbusDouble = "d"
    DbusInt64 = "x"
    DbusObjectPath = "o"
    DbusString = "s"
    DbusStringArray = "as"
    DbusVariantMap = "a{sv}"

MPRIS_PATH = "/org/mpris/MediaPlayer2"
MPRIS_BUS_NAME = "org.mpris.MediaPlayer2.sonido_selecto"
TRACK_ID = "/com/sonidoselecto/Radio/CurrentTrack"

CommandName = Literal["play", "pause", "toggle", "volume"]


@dataclass(frozen=True)
class MprisCommand:
    """A desktop media-control request for the main application thread."""

    name: CommandName
    value: int | None = None


@dataclass(frozen=True)
class _MprisState:
    stream_url: str
    title: str
    artwork_url: str
    playback_status: str
    volume: int


def split_track_title(title: str) -> tuple[str, str]:
    """Split the station's conventional ``Artist - Title`` metadata."""
    artist, separator, track = title.partition(" - ")
    if separator and artist.strip() and track.strip():
        return artist.strip(), track.strip()
    return "Sonido Selecto", title.strip() or "Sonido Selecto 102.9"


class _MediaPlayerInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__("org.mpris.MediaPlayer2")

    @method()
    def Raise(self) -> None:
        pass

    @method()
    def Quit(self) -> None:
        pass

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Fullscreen(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanSetFullscreen(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> DbusString:
        return "Sonido Selecto 102.9"

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> DbusString:
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> DbusStringArray:
        return ["http", "https"]

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> DbusStringArray:
        return ["audio/aac", "audio/mpeg", "audio/ogg"]


class _PlayerInterface(ServiceInterface):
    def __init__(self, service: "MprisService") -> None:
        super().__init__("org.mpris.MediaPlayer2.Player")
        self._service = service

    @method()
    def Next(self) -> None:
        pass

    @method()
    def Previous(self) -> None:
        pass

    @method()
    def Pause(self) -> None:
        self._service._enqueue(MprisCommand("pause"))

    @method()
    def PlayPause(self) -> None:
        self._service._enqueue(MprisCommand("toggle"))

    @method()
    def Stop(self) -> None:
        self._service._enqueue(MprisCommand("pause"))

    @method()
    def Play(self) -> None:
        self._service._enqueue(MprisCommand("play"))

    @method()
    def Seek(self, offset: DbusInt64) -> None:
        pass

    @method()
    def SetPosition(self, track_id: DbusObjectPath, position: DbusInt64) -> None:
        pass

    @method()
    def OpenUri(self, uri: DbusString) -> None:
        pass

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> DbusString:
        return self._service._snapshot().playback_status

    @dbus_property()
    def LoopStatus(self) -> DbusString:
        return "None"

    @LoopStatus.setter
    def LoopStatus(self, value: DbusString) -> None:
        pass

    @dbus_property()
    def Rate(self) -> DbusDouble:
        return 1.0

    @Rate.setter
    def Rate(self, value: DbusDouble) -> None:
        if value == 0.0:
            self._service._enqueue(MprisCommand("pause"))

    @dbus_property()
    def Shuffle(self) -> DbusBool:
        return False

    @Shuffle.setter
    def Shuffle(self, value: DbusBool) -> None:
        pass

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> DbusVariantMap:
        state = self._service._snapshot()
        artist, title = split_track_title(state.title)
        metadata = {
            "mpris:trackid": Variant("o", TRACK_ID),
            "xesam:artist": Variant("as", [artist]),
            "xesam:title": Variant("s", title),
            "xesam:url": Variant("s", state.stream_url),
        }
        if state.artwork_url:
            metadata["mpris:artUrl"] = Variant("s", state.artwork_url)
        return metadata

    @dbus_property()
    def Volume(self) -> DbusDouble:
        return self._service._snapshot().volume / 100

    @Volume.setter
    def Volume(self, value: DbusDouble) -> None:
        volume = max(0, min(100, round(value * 100)))
        old_state, new_state = self._service._replace_state(volume=volume)
        if old_state.volume != new_state.volume:
            self.emit_properties_changed({"Volume": new_state.volume / 100})
        self._service._enqueue(MprisCommand("volume", volume))

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> DbusInt64:
        return 0

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> DbusDouble:
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> DbusDouble:
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> DbusBool:
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> DbusBool:
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> DbusBool:
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> DbusBool:
        return True

    def emit_state_changes(self, old_state: _MprisState, new_state: _MprisState) -> None:
        changed: dict[str, Any] = {}
        if old_state.playback_status != new_state.playback_status:
            changed["PlaybackStatus"] = new_state.playback_status
        if (
            old_state.title != new_state.title
            or old_state.stream_url != new_state.stream_url
            or old_state.artwork_url != new_state.artwork_url
        ):
            changed["Metadata"] = self.Metadata
        if old_state.volume != new_state.volume:
            changed["Volume"] = new_state.volume / 100
        if changed:
            self.emit_properties_changed(changed)


class MprisService:
    """Publish the radio to MPRIS-capable Linux desktop environments."""

    def __init__(self, stream_url: str, volume: int) -> None:
        self._state = _MprisState(stream_url, "Sonido Selecto 102.9", "", "Stopped", volume)
        self._state_lock = threading.Lock()
        self._commands: SimpleQueue[MprisCommand] = SimpleQueue()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._player_interface: _PlayerInterface | None = None
        self._close_requested = threading.Event()
        self.error = ""

    def start(self) -> None:
        """Start publishing in a background thread; failures do not stop playback."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="mpris", daemon=True)
        self._thread.start()

    def update(
        self,
        title: str,
        requested_playing: bool,
        is_playing: bool,
        volume: int,
        artwork_url: str = "",
    ) -> None:
        """Synchronize desktop-visible state with the real player."""
        if is_playing:
            playback_status = "Playing"
        elif requested_playing:
            playback_status = "Stopped"
        else:
            playback_status = "Paused"
        old_state, new_state = self._replace_state(
            title=title,
            artwork_url=artwork_url,
            playback_status=playback_status,
            volume=volume,
        )
        with self._state_lock:
            loop = self._loop
            interface = self._player_interface
        if loop is not None and interface is not None and not loop.is_closed():
            loop.call_soon_threadsafe(interface.emit_state_changes, old_state, new_state)

    def drain_commands(self) -> list[MprisCommand]:
        """Return pending desktop requests without blocking the curses loop."""
        commands: list[MprisCommand] = []
        while True:
            try:
                commands.append(self._commands.get_nowait())
            except Empty:
                return commands

    def close(self) -> None:
        """Remove the MPRIS name and stop the service thread."""
        self._close_requested.set()
        with self._state_lock:
            loop = self._loop
            stop_event = self._stop_event
        if loop is not None and stop_event is not None and not loop.is_closed():
            loop.call_soon_threadsafe(stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _enqueue(self, command: MprisCommand) -> None:
        self._commands.put(command)

    def _snapshot(self) -> _MprisState:
        with self._state_lock:
            return self._state

    def _replace_state(
        self,
        *,
        title: str | None = None,
        artwork_url: str | None = None,
        playback_status: str | None = None,
        volume: int | None = None,
    ) -> tuple[_MprisState, _MprisState]:
        with self._state_lock:
            old_state = self._state
            self._state = replace(
                old_state,
                title=old_state.title if title is None else title,
                artwork_url=old_state.artwork_url if artwork_url is None else artwork_url,
                playback_status=(old_state.playback_status if playback_status is None else playback_status),
                volume=old_state.volume if volume is None else volume,
            )
            return old_state, self._state

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:  # D-Bus availability differs across runtime environments.
            self.error = str(exc)

    async def _serve(self) -> None:
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        root_interface = _MediaPlayerInterface()
        player_interface = _PlayerInterface(self)
        bus = await MessageBus().connect()
        bus.export(MPRIS_PATH, root_interface)
        bus.export(MPRIS_PATH, player_interface)
        bus_name = f"{MPRIS_BUS_NAME}.instance{os.getpid()}"
        await bus.request_name(bus_name)
        with self._state_lock:
            self._loop = loop
            self._stop_event = stop_event
            self._player_interface = player_interface
        if self._close_requested.is_set():
            stop_event.set()
        await stop_event.wait()
        bus.disconnect()  # type: ignore[no-untyped-call]
        with self._state_lock:
            self._loop = None
            self._stop_event = None
            self._player_interface = None
