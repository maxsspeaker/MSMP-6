import sys
import logging
import threading
import asyncio

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal
from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
)

class MprisCommandBridge(QObject):
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    next_requested = Signal()
    previous_requested = Signal()
    raise_requested = Signal()
    quit_requested = Signal()
    seek_requested = Signal(int)
    set_position_requested = Signal(int)
    open_uri_requested = Signal(str)
    loop_status_requested = Signal(str)
    shuffle_requested = Signal(bool)
    volume_requested = Signal(float)


class MprisRootInterface(ServiceInterface):
    def __init__(self, server: "MprisServer") -> None:
        super().__init__("org.mpris.MediaPlayer2")
        self.server = server

    @method()
    def Raise(self) -> "":
        self.server.bridge.raise_requested.emit()

    @method()
    def Quit(self) -> "":
        self.server.bridge.quit_requested.emit()

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":
        return "MSMP5"

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":
        return "msmp5"

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":
        return ["file", "http", "https"]

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":
        return ["audio/mpeg", "audio/mp4", "audio/ogg", "audio/x-wav"]


class MprisPlayerInterface(ServiceInterface):
    def __init__(self, server: "MprisServer") -> None:
        super().__init__("org.mpris.MediaPlayer2.Player")
        self.server = server

    @method()
    def Next(self) -> "":
        self.server.bridge.next_requested.emit()

    @method()
    def Previous(self) -> "":
        self.server.bridge.previous_requested.emit()

    @method()
    def Pause(self) -> "":
        self.server.bridge.pause_requested.emit()

    @method()
    def PlayPause(self) -> "":
        if self.server.get("PlaybackStatus") == "Playing":
            self.server.bridge.pause_requested.emit()
        else:
            self.server.bridge.play_requested.emit()

    @method()
    def Stop(self) -> "":
        self.server.bridge.stop_requested.emit()

    @method()
    def Play(self) -> "":
        self.server.bridge.play_requested.emit()

    @method()
    def Seek(self, Offset: "x") -> "":
        self.server.bridge.seek_requested.emit(int(Offset // 1000))

    @method()
    def SetPosition(self, TrackId: "o", Position: "x") -> "":
        self.server.bridge.set_position_requested.emit(max(0, int(Position // 1000)))

    @method()
    def OpenUri(self, Uri: "s") -> "":
        self.server.bridge.open_uri_requested.emit(Uri)

    @signal()
    def Seeked(self, Position: "x") -> "x":
        return Position

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":
        return self.server.get("PlaybackStatus")

    @dbus_property(access=PropertyAccess.READWRITE)
    def LoopStatus(self) -> "s":
        return self.server.get("LoopStatus")

    @LoopStatus.setter
    def LoopStatus(self, value: "s") -> None:
        self.server.bridge.loop_status_requested.emit(value)

    @dbus_property(access=PropertyAccess.READWRITE)
    def Rate(self) -> "d":
        return 1.0

    @Rate.setter
    def Rate(self, value: "d") -> None:
        return None

    @dbus_property(access=PropertyAccess.READWRITE)
    def Shuffle(self) -> "b":
        return self.server.get("Shuffle")

    @Shuffle.setter
    def Shuffle(self, value: "b") -> None:
        self.server.bridge.shuffle_requested.emit(bool(value))

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        return self.server.get("Metadata")

    @dbus_property(access=PropertyAccess.READWRITE)
    def Volume(self) -> "d":
        return self.server.get("Volume")

    @Volume.setter
    def Volume(self, value: "d") -> None:
        self.server.bridge.volume_requested.emit(min(1.0, max(0.0, float(value))))

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":
        return self.server.get("Position")

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":
        return self.server.get("CanGoNext")

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":
        return self.server.get("CanGoPrevious")

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":
        return self.server.get("CanPlay")

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":
        return self.server.get("CanSeek")

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":
        return True


class MprisServer:
    PATH = "/org/mpris/MediaPlayer2"

    def __init__(self) -> None:
        self.service_name = "org.mpris.MediaPlayer2.msmp5"
        self.bridge = MprisCommandBridge()
        self.lock = threading.RLock()
        self.state = {
            "PlaybackStatus": "Stopped",
            "LoopStatus": "None",
            "Rate": 1.0,
            "Shuffle": False,
            "Metadata": self.empty_metadata(),
            "Volume": 0.8,
            "Position": 0,
            "MinimumRate": 1.0,
            "MaximumRate": 1.0,
            "CanGoNext": False,
            "CanGoPrevious": False,
            "CanPlay": False,
            "CanPause": True,
            "CanSeek": False,
            "CanControl": True,
        }
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.bus: Optional[MessageBus] = None
        self.root_interface: Optional[MprisRootInterface] = None
        self.player_interface: Optional[MprisPlayerInterface] = None
        self.thread: Optional[threading.Thread] = None

    @staticmethod
    def empty_metadata() -> dict[str, Variant]:
        return {
            "mpris:trackid": Variant("o", "/org/mpris/MediaPlayer2/Track/NoTrack"),
        }

    def start(self) -> None:
        if not sys.platform.startswith("linux") or self.thread is not None:
            return
        self.thread = threading.Thread(target=self.run_thread, name="MPRIS", daemon=True)
        self.thread.start()

    def run_thread(self) -> None:
        try:
            asyncio.run(self.run_async())
        except BaseException as exc:
            logging.warning("MPRIS disabled: %s", exc)

    async def run_async(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.bus = await MessageBus().connect()
        self.root_interface = MprisRootInterface(self)
        self.player_interface = MprisPlayerInterface(self)
        self.bus.export(self.PATH, self.root_interface)
        self.bus.export(self.PATH, self.player_interface)
        await self.bus.request_name(self.service_name)
        await asyncio.Event().wait()

    def stop(self) -> None:
        loop = self.loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self.stop_in_loop)
        self.loop = None

    def stop_in_loop(self) -> None:
        if self.bus is not None:
            self.bus.disconnect()
        loop = asyncio.get_running_loop()
        loop.stop()

    def get(self, key: str):
        with self.lock:
            return self.state[key]

    def update(self, changed: dict) -> None:
        with self.lock:
            self.state.update(changed)
        interface = self.player_interface
        loop = self.loop
        if interface is not None and loop is not None:
            loop.call_soon_threadsafe(interface.emit_properties_changed, changed, [])

    def seeked(self, position_ms: int) -> None:
        interface = self.player_interface
        loop = self.loop
        if interface is not None and loop is not None:
            loop.call_soon_threadsafe(interface.Seeked, int(position_ms * 1000))