"""Steam transport: Steam carries the traffic, so nobody forwards ports.

Built on `py_steam_net` (Rust bindings over steamworks-rs: lobbies plus
ISteamNetworkingMessages). The host creates a Steam lobby; players join it by lobby id;
messages go peer to peer by Steam ID through Steam's relay network (SDR), which also
hides everyone's IP address.

ISteamNetworkingMessages only delivers from a peer once we have sent to that peer, so
the host messages every player who enters its lobby, and a joining player keeps saying
hello to the lobby's members until the host answers. The host only talks to members of
its own lobby.

Setup (once per machine): the wheel from the py_steam_net GitHub releases, and Valve's
redistributable `libsteam_api` (Steamworks SDK, redistributable_bin/) copied next to it:
`python -m soragl.net.steam install /path/to/libsteam_api.dylib`. Steam must be running
and signed in. App id 480 (Valve's Spacewar test app) works until the game has its own.
"""

import shutil
import sys
import time
from pathlib import Path

from soragl.net.transport import Event, Transport

DEV_APP_ID = 480
HELLO, WELCOME, DATA, MORE, BYE, PROBE = range(1, 7)
RELIABLE_FLAGS = 8 | 32  # k_nSteamNetworkingSend_Reliable | AutoRestartBrokenSession
UNRELIABLE_FLAGS = 1  # k_nSteamNetworkingSend_UnreliableNoNagle
CH_RELIABLE, CH_UNRELIABLE = 0, 1
STEAM_MAX = 512 * 1024  # Steam's largest message
PIECE = STEAM_MAX - 1024
MAX_MESSAGE = 8 * 1024 * 1024
LOBBY_TYPES = {"private": 0, "friends": 1, "public": 2, "invisible": 3}
ENTERED = 1  # EChatMemberStateChange: anything else means the member left
HELLO_EVERY = 0.5
CONNECT_TIMEOUT = 15.0
SILENCE_TIMEOUT = 10.0  # the session layer pings every second

_client = None


def library_name() -> str:
    if sys.platform == "win32":
        return "steam_api64.dll"
    return "libsteam_api.dylib" if sys.platform == "darwin" else "libsteam_api.so"


def install(lib: str | Path) -> Path:
    """Copy Valve's redistributable Steam API library next to py_steam_net's module,
    where it looks for it (`@loader_path` on macOS; the DLL search path on Windows)."""
    import importlib.util

    spec = importlib.util.find_spec("py_steam_net")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("py_steam_net is not installed (see soragl.net.steam)")
    dest = Path(next(iter(spec.submodule_search_locations))) / library_name()
    shutil.copy2(lib, dest)
    return dest


def client(app_id: int = DEV_APP_ID):
    """The process-wide Steam client (Steam allows one per process), started once."""
    global _client
    if _client is not None:
        return _client
    try:
        import py_steam_net
    except ImportError as e:
        if library_name().split(".")[0] in str(e):
            raise RuntimeError(
                f"py_steam_net cannot find {library_name()}: run "
                "`python -m soragl.net.steam install <path to it>`"
            ) from e
        raise RuntimeError(
            "py_steam_net is not installed: get the wheel for this Python and platform "
            "from https://github.com/HeatXD/py_steam_net/releases"
        ) from e
    c = py_steam_net.PySteamClient()
    try:
        c.init(int(app_id))
    except RuntimeError as e:
        raise RuntimeError(
            f"Steam did not start ({e}): is Steam running and signed in?"
        ) from e
    _client = c
    return c


def _wait(c, done, seconds: float, what: str):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        c.run_callbacks()
        if done():
            return
        time.sleep(0.02)
    raise RuntimeError(f"Steam: timed out {what}")


class SteamTransport(Transport):
    """`SteamTransport.host()` makes a lobby (its id: `.lobby_id`, for invites);
    `SteamTransport.join(lobby_id)` joins one. Both wait (a few seconds at most) for
    Steam, and raise RuntimeError with a reason if it fails."""

    def __init__(self, steam, is_host: bool, lobby_id: int):
        self.steam = steam
        self.is_host = is_host
        self.lobby_id = lobby_id
        self.me = steam.own_steam_id()
        self.peers: dict[int, int] = {}  # peer id -> steam id
        self._pid_of: dict[int, int] = {}  # steam id -> peer id
        self._next_pid = 1
        self._heard: dict[int, float] = {}
        self._parts: dict[int, list[bytes]] = {}
        self._inbox: list[tuple[int, int, bytes]] = []
        self._events: list[Event] = []
        self._members: set[int] = set()
        self._host_id: int | None = None
        self._started = time.monotonic()
        self._last_hello = 0.0
        self.closed = False
        steam.set_message_recv_callback(
            lambda sid, ch, data: self._inbox.append((sid, ch, data))
        )
        steam.set_lobby_changed_callback(self._lobby_changed)
        steam.set_connection_failed_callback(self._failed)
        self._refresh_members()

    @classmethod
    def host(
        cls,
        max_players: int = 8,
        lobby: str = "friends",
        app_id: int = DEV_APP_ID,
        steam=None,
    ):
        c = steam or client(app_id)
        made: list = []
        c.create_lobby(
            LOBBY_TYPES[lobby],
            max_players,
            lambda lid, err=None: made.append((lid, err)),
        )
        _wait(c, lambda: made, 10.0, "creating a lobby")
        lobby_id, err = made[0]
        if lobby_id is None:
            raise RuntimeError(f"Steam: could not create a lobby ({err})")
        return cls(c, True, int(lobby_id))

    @classmethod
    def join(cls, lobby_id: int, app_id: int = DEV_APP_ID, steam=None):
        c = steam or client(app_id)
        got: list = []
        c.join_lobby(int(lobby_id), lambda lid, err=None: got.append((lid, err)))
        _wait(c, lambda: got, 10.0, "joining the lobby")
        lid, err = got[0]
        if lid is None:
            raise RuntimeError(f"Steam: could not join lobby {lobby_id} ({err})")
        return cls(c, False, int(lid))

    # ---- Transport API ----

    def send(self, peer: int, data: bytes, reliable: bool = True) -> None:
        sid = self.peers.get(peer)
        if sid is None or self.closed:
            return
        if len(data) > MAX_MESSAGE:
            raise ValueError(f"message of {len(data)} bytes is over {MAX_MESSAGE}")
        if not reliable:
            if len(data) >= STEAM_MAX:
                raise ValueError("unreliable Steam messages must be under 512 KB")
            self._raw(sid, bytes([DATA]) + data, CH_UNRELIABLE)
            return
        for i in range(0, max(1, len(data)), PIECE):
            last = i + PIECE >= len(data)
            self._raw(
                sid, bytes([DATA if last else MORE]) + data[i : i + PIECE], CH_RELIABLE
            )

    def poll(self) -> list[Event]:
        if self.closed:
            return []
        now = time.monotonic()
        self.steam.run_callbacks()
        self.steam.receive_messages(CH_RELIABLE, 256)
        self.steam.receive_messages(CH_UNRELIABLE, 256)
        inbox, self._inbox = self._inbox, []
        for sid, channel, data in inbox:
            if data:
                self._handle(sid, channel, bytes(data), now)
        if not self.is_host and self._host_id is None:
            if now - self._started > CONNECT_TIMEOUT:
                self._events.append(
                    Event("disconnect", 0, reason="could not reach the host")
                )
                self.closed = True
            elif now - self._last_hello >= HELLO_EVERY:
                self._last_hello = now
                self._refresh_members()
                for sid in self._members - {self.me}:
                    self._raw(sid, bytes([HELLO]), CH_RELIABLE)
        for pid, sid in list(self.peers.items()):
            if now - self._heard.get(sid, now) > SILENCE_TIMEOUT:
                self._lost(sid, "timed out")
        out, self._events = self._events, []
        return out

    def disconnect(self, peer: int) -> None:
        sid = self.peers.get(peer)
        if sid is not None:
            self._raw(sid, bytes([BYE]), CH_RELIABLE)
            self._forget(sid)

    def close(self) -> None:
        if self.closed:
            return
        for pid in list(self.peers):
            self.disconnect(pid)
        self.steam.leave_lobby(self.lobby_id)
        self.closed = True

    # ---- internals ----

    def _raw(self, sid: int, data: bytes, channel: int) -> None:
        flags = RELIABLE_FLAGS if channel == CH_RELIABLE else UNRELIABLE_FLAGS
        self.steam.send_message_to(sid, flags, channel, data)

    def _refresh_members(self) -> None:
        try:
            self._members = set(self.steam.get_lobby_members(self.lobby_id))
        except RuntimeError:
            self._members = set()

    def _handle(self, sid: int, channel: int, data: bytes, now: float) -> None:
        kind, body = data[0], data[1:]
        if self.is_host:
            if sid not in self._pid_of:
                if kind != HELLO:
                    return
                self._refresh_members()
                if sid not in self._members:
                    return  # only members of our lobby
                pid = self._next_pid
                self._next_pid += 1
                self.peers[pid] = sid
                self._pid_of[sid] = pid
                self._heard[sid] = now
                self._raw(sid, bytes([WELCOME]), CH_RELIABLE)
                self._events.append(Event("connect", pid))
                return
            if kind == HELLO:  # our WELCOME was not seen yet
                self._raw(sid, bytes([WELCOME]), CH_RELIABLE)
        elif kind == WELCOME and self._host_id is None:
            self._host_id = sid
            self.peers[0] = sid
            self._pid_of[sid] = 0
            self._events.append(Event("connect", 0))
        if sid not in self._pid_of:
            return
        self._heard[sid] = now
        pid = self._pid_of[sid]
        if kind == BYE:
            self._lost(sid, "closed by peer")
        elif kind == MORE and channel == CH_RELIABLE:
            parts = self._parts.setdefault(sid, [])
            parts.append(body)
            if sum(map(len, parts)) > MAX_MESSAGE:
                self._lost(sid, "message too large")
        elif kind == DATA:
            if channel == CH_RELIABLE:
                body = b"".join(self._parts.pop(sid, [])) + body
            self._events.append(Event("message", pid, body, channel == CH_RELIABLE))

    def _lobby_changed(self, lobby_id, user, making_change, state) -> None:
        if lobby_id != self.lobby_id:
            return
        if state == ENTERED:
            self._members.add(user)
            if self.is_host:
                self._raw(
                    user, bytes([PROBE]), CH_RELIABLE
                )  # lets their hello reach us
        else:
            self._members.discard(user)
            self._lost(user, "left the lobby")

    def _failed(self, sid, *reason) -> None:
        self._lost(sid, "connection failed")

    def _lost(self, sid: int, reason: str) -> None:
        pid = self._pid_of.get(sid)
        if pid is None:
            return
        self._forget(sid)
        self._events.append(Event("disconnect", pid, reason=reason))
        if not self.is_host:
            self.closed = True

    def _forget(self, sid: int) -> None:
        pid = self._pid_of.pop(sid, None)
        self.peers.pop(pid, None)
        self._heard.pop(sid, None)
        self._parts.pop(sid, None)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "install":
        print("installed", install(sys.argv[2]))
    else:
        print("usage: python -m soragl.net.steam install <path to libsteam_api>")
