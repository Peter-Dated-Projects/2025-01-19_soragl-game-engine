"""Deterministic lockstep: players send only their inputs; every machine runs the same
simulation. For RTS-style games with many units and few players.

Star shape: clients send each input to the host, scheduled `input_delay` ticks ahead
(Age of Empires scheduled commands two turns ahead); the host gathers every player's
input for a tick into a turn and sends it to everyone; nobody runs tick T before turn T
has arrived. Every `checksum_every` ticks each client reports a checksum of its state; on
a mismatch the host sends that client a snapshot (a resync) instead of ending the game.
A late joiner gets the same snapshot plus the turns already sent but not yet run.
"""

import struct

from soragl.net.game import checksum
from soragl.net.session import SessionEvent

INPUT, TURN, STATE, CHECK = 1, 2, 3, 4
_TICK = struct.Struct("!I")
_ENTRY = struct.Struct("!HI")  # player, length
_CHECK = struct.Struct("!II")
_COUNT = struct.Struct("!H")
MAX_AHEAD = 1000  # ticks: inputs / turns further ahead than this are refused
RESYNC_GAP = 2.0  # seconds between resyncs of the same player


def encode_turn(turn: dict[int, bytes]) -> bytes:
    parts = [_COUNT.pack(len(turn))]
    for player in sorted(turn):
        parts.append(_ENTRY.pack(player, len(turn[player])))
        parts.append(turn[player])
    return b"".join(parts)


def decode_turn(data: bytes, off: int = 0) -> tuple[dict[int, bytes], int]:
    (count,) = _COUNT.unpack_from(data, off)
    off += _COUNT.size
    turn = {}
    for _ in range(count):
        player, n = _ENTRY.unpack_from(data, off)
        off += _ENTRY.size
        if off + n > len(data):
            raise ValueError("truncated turn")
        turn[player] = data[off : off + n]
        off += n
    return turn, off


class Lockstep:
    model = "lockstep"

    def __init__(
        self,
        session,
        game,
        *,
        dt: float = 0.05,
        input_delay: int = 3,
        checksum_every: int = 20,
        max_steps: int = 8,
    ):
        self.session = session
        self.game = game
        self.dt = dt
        self.delay = max(1, int(input_delay))
        self.check_every = max(1, int(checksum_every))
        self.max_steps = max_steps
        self.tick = 0  # the next tick to run
        self.turns: dict[int, dict[int, bytes]] = {}
        self.ready = session.is_host  # clients wait for the host's state
        self.waiting = False  # stalled for a turn (show "waiting for players")
        self.desyncs = 0
        self._acc = 0.0
        # host only
        self._pending: dict[int, dict[int, bytes]] = {}
        self._first: dict[int, int] = {
            0: self.delay
        }  # player -> first tick it must send
        self._next_turn = 0  # the next turn the host will complete
        self._crc: dict[int, int] = {}
        self._claims: dict[int, list[tuple[int, int]]] = {}
        self._resynced: dict[int, tuple[float, int]] = {}  # player -> (time, from tick)
        self._clock = 0.0
        self._notes: list[SessionEvent] = []  # events the model itself raises
        if session.is_host:
            self._finalize()

    @property
    def player(self) -> int:
        return self.session.player

    @property
    def players(self) -> dict[int, dict]:
        return self.session.players

    def update(self, real_dt: float) -> list[SessionEvent]:
        """Poll the network and run every tick that is due and whose turn is known.
        Returns session events for the game (join, leave, joined, closed, desync...)."""
        self._clock += real_dt
        out, self._notes = self._notes, []
        for ev in self.session.poll():
            if ev.kind == "message":
                try:
                    self._message(ev.player, ev.data)
                except (struct.error, ValueError):
                    if self.session.is_host:
                        self.session.kick(ev.player, "malformed game data")
                    else:
                        out.append(
                            SessionEvent("closed", reason="malformed data from host")
                        )
                        self.session.close()
                continue
            if self.session.is_host and ev.kind == "join":
                self._admit(ev.player)
            elif self.session.is_host and ev.kind == "leave":
                self._first.pop(ev.player, None)
            out.append(ev)
        if self.session.is_host:
            self._finalize()
        if not self.ready:
            return out
        self._acc += max(0.0, real_dt)
        steps = 0
        while self._acc >= self.dt and steps < self.max_steps:
            turn = self.turns.get(self.tick)
            if turn is None:
                break
            self._step(turn)
            self._acc -= self.dt
            steps += 1
        self.waiting = self._acc >= self.dt
        self._acc = min(self._acc, self.dt * self.max_steps)
        out += self._notes
        self._notes = []
        return out

    def close(self) -> None:
        self.session.close()

    # ---- both ends ----

    def _step(self, turn: dict[int, bytes]) -> None:
        t = self.tick
        del self.turns[t]
        self.game.net_step(self.dt, turn)
        self.tick = t + 1
        self._submit(t + self.delay, self.game.net_input())
        if self.session.is_host:
            self._finalize()
        if t % self.check_every == 0:
            crc = checksum(self.game)
            if self.session.is_host:
                self._crc[t] = crc
                for player, theirs in self._claims.pop(t, []):
                    self._compare(player, t, theirs)
                for old in [k for k in self._crc if k < t - 4096]:
                    del self._crc[old]
            else:
                self.session.send(0, bytes([CHECK]) + _CHECK.pack(t, crc))

    def _submit(self, tick: int, data: bytes) -> None:
        if self.session.is_host:
            self._input(0, tick, data)
        else:
            self.session.send(0, bytes([INPUT]) + _TICK.pack(tick) + data)

    def _message(self, player: int, data: bytes) -> None:
        kind, body = data[0], data[1:]
        host = self.session.is_host
        if host and kind == INPUT:
            (tick,) = _TICK.unpack_from(body)
            self._input(player, tick, body[_TICK.size :])
        elif host and kind == CHECK:
            tick, crc = _CHECK.unpack_from(body)
            if tick in self._crc:
                self._compare(player, tick, crc)
            elif self._next_turn - MAX_AHEAD <= tick <= self._next_turn:
                self._claims.setdefault(tick, []).append((player, crc))
        elif not host and kind == TURN:
            (tick,) = _TICK.unpack_from(body)
            turn, _ = decode_turn(body, _TICK.size)
            if self.tick <= tick < self.tick + MAX_AHEAD:
                self.turns[tick] = turn
        elif not host and kind == STATE:
            (tick,) = _TICK.unpack_from(body)
            off = _TICK.size
            (n,) = struct.unpack_from("!I", body, off)
            off += 4
            snapshot = body[off : off + n]
            off += n
            (count,) = _COUNT.unpack_from(body, off)
            off += _COUNT.size
            turns = {}
            for _ in range(count):
                (t,) = _TICK.unpack_from(body, off)
                turn, off = decode_turn(body, off + _TICK.size)
                turns[t] = turn
            self.game.net_restore(snapshot)
            resync = self.ready
            self.tick = tick
            self.turns = {t: v for t, v in self.turns.items() if t >= tick}
            self.turns.update(turns)
            self.ready = True
            self._acc = 0.0
            if resync:
                self._notes.append(SessionEvent("resync", self.session.player))

    # ---- host ----

    def _input(self, player: int, tick: int, data: bytes) -> None:
        if player not in self._first or not (
            self._next_turn <= tick < self._next_turn + MAX_AHEAD
        ):
            return  # too late (that turn is out) or absurdly early
        self._pending.setdefault(tick, {})[player] = data

    def _finalize(self) -> None:
        """Send out every turn whose inputs are all in."""
        while True:
            t = self._next_turn
            got = self._pending.get(t, {})
            if any(f <= t and p not in got for p, f in self._first.items()):
                return
            self._pending.pop(t, None)
            turn = {p: d for p, d in got.items() if p in self._first}
            self.turns[t] = turn
            self.session.send(None, bytes([TURN]) + _TICK.pack(t) + encode_turn(turn))
            self._next_turn = t + 1

    def _admit(self, player: int) -> None:
        """Bring `player` to the host's state: a snapshot, the turns sent but not yet run,
        and the first tick the host will wait for its input."""
        self._first[player] = max(self._next_turn, self.tick + self.delay)
        self._resynced[player] = (self._clock, self.tick)
        snapshot = self.game.net_snapshot()
        turns = [(t, self.turns[t]) for t in range(self.tick, self._next_turn)]
        parts = [
            bytes([STATE]),
            _TICK.pack(self.tick),
            struct.pack("!I", len(snapshot)),
            snapshot,
            _COUNT.pack(len(turns)),
        ]
        for t, turn in turns:
            parts.append(_TICK.pack(t) + encode_turn(turn))
        self.session.send(player, b"".join(parts))

    def _compare(self, player: int, tick: int, crc: int) -> None:
        if player not in self._first:
            return
        when, since = self._resynced.get(player, (-1e9, -1))
        if tick < since:
            return  # a check from before its last resync
        if crc != self._crc[tick] and self._clock - when >= RESYNC_GAP:
            self.desyncs += 1
            self._admit(player)
            self._notes.append(SessionEvent("desync", player, reason=f"tick {tick}"))
