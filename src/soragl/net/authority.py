"""Authority: the host runs the game; clients send inputs and show the host's snapshots.
For physics and action games, which need not be deterministic.

Clients send their newest few inputs every tick, unreliably (a lost packet is covered by
the next one). The host keeps a short queue per player and uses one input per tick,
repeating the last when the queue runs dry. Every `snapshot_every` ticks the host sends
everyone a snapshot (unreliably: a newer one replaces a lost one). Clients show the state
`delay` seconds behind the newest snapshot, interpolated between the two around it
(Gaffer on Games, "Snapshot Interpolation").

shortcut: no client-side prediction; add it if a game needs instant local response.
"""

import struct
from collections import deque

from soragl.net.session import SessionEvent

INPUTS, SNAP = 1, 2
_TICK = struct.Struct("!I")
_INPUT = struct.Struct("!IH")  # sequence, length
QUEUE_MAX = 6  # inputs a player may have waiting; beyond this the host catches up


class Authority:
    model = "authority"

    def __init__(
        self,
        session,
        game,
        *,
        dt: float = 1 / 30,
        snapshot_every: int = 2,
        delay: float = 0.1,
        max_steps: int = 8,
    ):
        self.session = session
        self.game = game
        self.dt = dt
        self.snapshot_every = max(1, int(snapshot_every))
        self.delay = delay
        self.max_steps = max_steps
        self.tick = 0
        self.ready = session.is_host  # clients: a snapshot has arrived
        self._acc = 0.0
        # host
        self._queues: dict[int, deque] = {}
        self._last: dict[int, bytes] = {}
        self._seen: dict[int, int] = {}
        # client
        self._seq = 0
        self._recent: list[tuple[int, bytes]] = []
        self._snaps: list[tuple[int, bytes]] = []
        self._view = 0.0  # the host tick being shown (fractional)
        self._shown: int | None = None  # tick restored last (when not interpolating)

    @property
    def player(self) -> int:
        return self.session.player

    @property
    def players(self) -> dict[int, dict]:
        return self.session.players

    def update(self, real_dt: float) -> list[SessionEvent]:
        out = []
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
            if ev.kind == "leave":
                self._queues.pop(ev.player, None)
                self._last.pop(ev.player, None)
                self._seen.pop(ev.player, None)
            out.append(ev)
        self._acc += max(0.0, real_dt)
        steps = 0
        while self._acc >= self.dt and steps < self.max_steps:
            self._acc -= self.dt
            steps += 1
            if self.session.is_host:
                self._host_tick()
            else:
                self._client_tick()
        self._acc = min(self._acc, self.dt * self.max_steps)
        if not self.session.is_host:
            self._show(real_dt)
        return out

    def close(self) -> None:
        self.session.close()

    # ---- host ----

    def _host_tick(self) -> None:
        inputs = {0: self.game.net_input()}
        for player, q in self._queues.items():
            if q:
                self._last[player] = q.popleft()
            if player in self._last:
                inputs[player] = self._last[player]
        self.game.net_step(self.dt, inputs)
        self.tick += 1
        if self.tick % self.snapshot_every == 0:
            snap = bytes([SNAP]) + _TICK.pack(self.tick) + self.game.net_snapshot()
            self.session.send(None, snap, reliable=False)

    def _message(self, player: int, data: bytes) -> None:
        kind, body = data[0], data[1:]
        if self.session.is_host and kind == INPUTS:
            (count,) = struct.unpack_from("!B", body)
            off, fresh = 1, []
            for _ in range(min(count, 8)):
                seq, n = _INPUT.unpack_from(body, off)
                off += _INPUT.size
                if off + n > len(body):
                    raise ValueError("truncated input")
                fresh.append((seq, body[off : off + n]))
                off += n
            q = self._queues.setdefault(player, deque())
            for seq, inp in sorted(fresh):
                if seq > self._seen.get(player, 0):
                    self._seen[player] = seq
                    q.append(inp)
            while len(q) > QUEUE_MAX:
                q.popleft()
        elif not self.session.is_host and kind == SNAP:
            (tick,) = _TICK.unpack_from(body)
            if not self._snaps or tick > self._snaps[-1][0]:
                self._snaps.append((tick, body[_TICK.size :]))
                self._snaps = self._snaps[-8:]
                if not self.ready:
                    self.ready = True
                    self._view = float(tick)

    # ---- client ----

    def _client_tick(self) -> None:
        self._seq += 1
        self._recent = (self._recent + [(self._seq, self.game.net_input())])[-3:]
        parts = [bytes([INPUTS]), struct.pack("!B", len(self._recent))]
        for seq, inp in self._recent:
            parts.append(_INPUT.pack(seq, len(inp)) + inp)
        self.session.send(0, b"".join(parts), reliable=False)

    def _show(self, real_dt: float) -> None:
        if not self._snaps:
            return
        newest = self._snaps[-1][0]
        behind = self.delay / self.dt
        self._view += real_dt / self.dt
        # drifted (a stall, a burst, or the delay changed): jump back on track
        if self._view > newest or self._view < newest - behind * 3:
            self._view = newest - behind
        older = newer = None
        for snap in self._snaps:
            if snap[0] <= self._view:
                older = snap
            elif newer is None:
                newer = snap
        lerp = getattr(self.game, "net_interpolate", None)
        if lerp is None:
            target = self._snaps[-1]  # no interpolation: show the newest as it comes
            if target[0] != self._shown:
                self.game.net_restore(target[1])
                self._shown = target[0]
            return
        if older is None:
            self.game.net_restore(self._snaps[0][1])
        elif newer is None:
            self.game.net_restore(older[1])
        else:
            t = (self._view - older[0]) / (newer[0] - older[0])
            lerp(older[1], newer[1], min(1.0, max(0.0, t)))
