"""Sessions: who is in the game. One host (player 0) and clients that connect to it.

The handshake checks the game id, the game's version and the protocol before anyone is
let in, so mismatched builds are refused with a reason instead of desyncing later. The
host numbers players (1, 2, ...), keeps the roster and tells everyone when it changes.
Clients talk only to the host; the host can talk to one player or to all.

Control messages are JSON (never pickle: the bytes come from other machines); game
traffic is opaque bytes for the sync model above.
"""

import json
import struct
import time
from dataclasses import dataclass

from soragl.net.transport import Transport

PROTOCOL = 1
HELLO, WELCOME, REJECT, ROSTER, PING, PONG, GAME, BYE = range(1, 9)
_TIME = struct.Struct("!d")
HELLO_TIMEOUT = 5.0  # seconds a connected peer has to introduce itself
PING_EVERY = 1.0


@dataclass
class SessionEvent:
    kind: str  # "joined", "rejected", "join", "leave", "message", "closed"
    player: int = 0
    data: bytes = b""
    reliable: bool = True
    reason: str = ""


def _json(kind: int, obj) -> bytes:
    return bytes([kind]) + json.dumps(obj, separators=(",", ":")).encode()


def _read_json(body: bytes):
    if len(body) > 65536:
        raise ValueError("control message too large")
    obj = json.loads(body.decode())
    if not isinstance(obj, dict):
        raise ValueError("expected an object")
    return obj


class Session:
    """Common to both ends. `players`: id -> {"name": ...}; `player`: our own id."""

    is_host = False

    def __init__(
        self,
        transport: Transport,
        game_id: str,
        version: str,
        name: str,
        sync: str = "",
    ):
        self.transport = transport
        self.sync = sync  # the sync model and its settings: both ends must match
        self.game_id = game_id
        self.version = version
        self.name = name
        self.player = 0
        self.players: dict[int, dict] = {}
        self.rtt: dict[int, float] = {}
        self.info: dict = {}  # the host's session info (sync model, settings), from WELCOME
        self.closed = False
        self._last_ping = 0.0
        self._stash: list = []  # transport events read while flushing, for the next poll

    def _flush(self) -> None:
        """Let the transport send what is queued (UDP sends while polling); whatever it
        reads meanwhile is kept for the next `poll()`."""
        self._stash += self.transport.poll()

    def _events(self) -> list:
        out, self._stash = self._stash + self.transport.poll(), []
        return out

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.transport.close()

    def _ping(self, peers) -> None:
        now = time.monotonic()
        if now - self._last_ping >= PING_EVERY:
            self._last_ping = now
            for peer in peers:
                self.transport.send(
                    peer, bytes([PING]) + _TIME.pack(now), reliable=False
                )


class HostSession(Session):
    is_host = True

    def __init__(
        self,
        transport: Transport,
        game_id: str,
        version: str,
        name: str = "Host",
        max_players: int = 8,
        info: dict | None = None,
        sync: str = "",
    ):
        super().__init__(transport, game_id, version, name, sync)
        self.max_players = max_players
        self.info = dict(info or {})
        self.players = {0: {"name": name}}
        self._peer_of: dict[int, int] = {}  # player -> transport peer
        self._player_of: dict[int, int] = {}  # transport peer -> player
        self._waiting: dict[int, float] = {}  # peers connected but not introduced
        self._next_player = 1
        self._kicked: list[SessionEvent] = []  # leave events raised outside poll()

    def send(self, player: int | None, data: bytes, reliable: bool = True) -> None:
        """To one player, or to every client with `player=None`."""
        msg = bytes([GAME]) + data
        targets = (
            self._peer_of.values() if player is None else [self._peer_of.get(player)]
        )
        for peer in targets:
            if peer is not None:
                self.transport.send(peer, msg, reliable)

    def kick(self, player: int, reason: str = "removed by the host") -> None:
        peer = self._peer_of.get(player)
        if peer is not None:
            self.transport.send(peer, _json(BYE, {"reason": reason}))
            self._flush()  # send it before the link goes
            self.transport.disconnect(peer)
            self._left(peer, self._kicked, reason)

    def poll(self) -> list[SessionEvent]:
        out, self._kicked = self._kicked, []
        now = time.monotonic()
        for ev in self._events():
            if ev.kind == "connect":
                self._waiting[ev.peer] = now
            elif ev.kind == "disconnect":
                self._waiting.pop(ev.peer, None)
                self._left(ev.peer, out, ev.reason)
            elif ev.data:
                try:
                    self._message(ev.peer, ev.data, ev.reliable, out)
                except (
                    ValueError,
                    UnicodeDecodeError,
                    KeyError,
                    TypeError,
                    struct.error,
                ):
                    self._refuse(ev.peer, "malformed message")
                    self._left(ev.peer, out, "malformed message")
        for peer, since in list(self._waiting.items()):
            if now - since > HELLO_TIMEOUT:
                self._refuse(peer, "no hello")
        self._ping(self._peer_of.values())
        return out

    def close(self) -> None:
        for peer in list(self._peer_of.values()):
            self.transport.send(peer, _json(BYE, {"reason": "the host left"}))
        self._flush()
        super().close()

    def _message(self, peer: int, data: bytes, reliable: bool, out) -> None:
        kind, body = data[0], data[1:]
        player = self._player_of.get(peer)
        if kind == HELLO and peer in self._waiting:
            hello = _read_json(body)
            reason = self._check(hello)
            if reason:
                self._refuse(peer, reason)
                return
            del self._waiting[peer]
            player = self._next_player
            self._next_player += 1
            self._peer_of[player] = peer
            self._player_of[peer] = player
            name = str(hello.get("name", ""))[:32] or f"Player {player}"
            self.players[player] = {"name": name}
            self.transport.send(
                peer,
                _json(
                    WELCOME,
                    {"player": player, "players": self.players, "info": self.info},
                ),
            )
            self._roster()
            out.append(SessionEvent("join", player))
        elif player is None:
            return  # nothing but HELLO from strangers
        elif kind == GAME:
            out.append(SessionEvent("message", player, body, reliable))
        elif kind == PING:
            self.transport.send(
                peer, bytes([PONG]) + body[: _TIME.size], reliable=False
            )
        elif kind == PONG:
            (sent,) = _TIME.unpack_from(body)
            self.rtt[player] = max(0.0, time.monotonic() - sent)
        elif kind == BYE:
            self.transport.disconnect(peer)
            self._left(peer, out, "left")

    def _check(self, hello: dict) -> str:
        if hello.get("protocol") != PROTOCOL:
            return "different network protocol (update the game)"
        if hello.get("game") != self.game_id:
            return "a different game"
        if hello.get("version") != self.version:
            return f"different version (host has {self.version})"
        if hello.get("sync") != self.sync:
            return f"different network settings (host uses {self.sync})"
        if len(self.players) >= self.max_players:
            return "the game is full"
        return ""

    def _refuse(self, peer: int, reason: str) -> None:
        self._waiting.pop(peer, None)
        self.transport.send(peer, _json(REJECT, {"reason": reason}))
        self._flush()  # send it before the link goes
        self.transport.disconnect(peer)

    def _left(self, peer: int, out, reason: str) -> None:
        player = self._player_of.pop(peer, None)
        if player is None:
            return
        self._peer_of.pop(player, None)
        self.players.pop(player, None)
        self.rtt.pop(player, None)
        self._roster()
        out.append(SessionEvent("leave", player, reason=reason))

    def _roster(self) -> None:
        msg = _json(ROSTER, {"players": self.players})
        for peer in self._peer_of.values():
            self.transport.send(peer, msg)


class ClientSession(Session):
    def __init__(
        self,
        transport: Transport,
        game_id: str,
        version: str,
        name: str = "",
        sync: str = "",
    ):
        super().__init__(transport, game_id, version, name, sync)
        self.joined = False

    def send(self, player: int | None, data: bytes, reliable: bool = True) -> None:
        """Clients only reach the host (`player` is ignored)."""
        if self.joined:
            self.transport.send(0, bytes([GAME]) + data, reliable)

    def poll(self) -> list[SessionEvent]:
        out: list[SessionEvent] = []
        if self.closed:
            return out
        for ev in self._events():
            if ev.kind == "connect":
                hello = {
                    "protocol": PROTOCOL,
                    "game": self.game_id,
                    "version": self.version,
                    "name": self.name,
                    "sync": self.sync,
                }
                self.transport.send(0, _json(HELLO, hello))
            elif ev.kind == "disconnect":
                if not self.closed:
                    out.append(SessionEvent("closed", reason=ev.reason))
                    self.closed = True
            elif ev.data:
                try:
                    self._message(ev.data, ev.reliable, out)
                except (
                    ValueError,
                    UnicodeDecodeError,
                    KeyError,
                    TypeError,
                    struct.error,
                ):
                    out.append(
                        SessionEvent("closed", reason="malformed message from host")
                    )
                    self.close()
        if self.joined and not self.closed:
            self._ping([0])
        return out

    def close(self) -> None:
        if not self.closed and self.joined:
            self.transport.send(0, _json(BYE, {}))
            self._flush()
        super().close()

    def _message(self, data: bytes, reliable: bool, out) -> None:
        kind, body = data[0], data[1:]
        if kind == WELCOME:
            w = _read_json(body)
            self.player = int(w["player"])
            self.players = {int(k): v for k, v in w["players"].items()}
            self.info = dict(w.get("info", {}))
            self.joined = True
            out.append(SessionEvent("joined", self.player))
        elif kind == REJECT:
            out.append(SessionEvent("rejected", reason=str(_read_json(body)["reason"])))
            self.closed = True
            self.transport.close()
        elif kind == ROSTER:
            self.players = {int(k): v for k, v in _read_json(body)["players"].items()}
        elif kind == GAME:
            out.append(SessionEvent("message", 0, body, reliable))
        elif kind == PING:
            self.transport.send(0, bytes([PONG]) + body[: _TIME.size], reliable=False)
        elif kind == PONG:
            (sent,) = _TIME.unpack_from(body)
            self.rtt[0] = max(0.0, time.monotonic() - sent)
        elif kind == BYE:
            out.append(
                SessionEvent("closed", reason=str(_read_json(body).get("reason", "")))
            )
            self.closed = True
            self.transport.close()
