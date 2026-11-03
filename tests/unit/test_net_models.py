"""Sessions and the two sync models, over loopback and over real UDP with packet loss."""

import json
import time
import zlib

import pytest

import soragl.net as net
from soragl.net.transport import LoopbackNetwork
from soragl.net.udp import UdpTransport

GAME = {"game_id": "toy", "version": "1"}


class Dots:
    """A deterministic toy: each player moves a dot; `mix` folds every input into a hash,
    so any divergence shows at once. `history`: tick -> state digest after that tick."""

    def __init__(self, seed: int):
        self.seed = seed
        self.pos: dict[str, list[int]] = {}
        self.mix = 7
        self.tick = 0
        self.history: dict[int, int] = {}
        self.sampled = 0

    def net_input(self) -> bytes:
        self.sampled += 1
        return bytes([(self.seed * 7 + self.sampled * 13) % 5])

    def net_step(self, dt, inputs):
        for pid in sorted(inputs):
            d = inputs[pid][0] if inputs[pid] else 0
            x, y = self.pos.setdefault(str(pid), [0, 0])
            dx, dy = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)][d]
            self.pos[str(pid)] = [x + dx, y + dy]
            self.mix = (self.mix * 31 + pid * 17 + d + 1) % 2_147_483_647
        self.tick += 1
        self.history[self.tick] = self.digest()

    def digest(self) -> int:
        return zlib.crc32(self.net_snapshot())

    def net_snapshot(self) -> bytes:
        return json.dumps(
            {"pos": self.pos, "mix": self.mix, "tick": self.tick}, sort_keys=True
        ).encode()

    def net_restore(self, data: bytes) -> None:
        s = json.loads(data)
        self.pos, self.mix, self.tick = s["pos"], s["mix"], s["tick"]


def drive(nets, seconds, dt=0.05, real=False, events=None):
    """Advance every session by `seconds`: simulated time over loopback, real elapsed
    time over sockets (lockstep cannot outrun the packets carrying its turns)."""
    if real:
        start = last = time.monotonic()
        while (now := time.monotonic()) - start < seconds:
            for n in nets:
                evs = n.update(now - last)
                if events is not None:
                    events.setdefault(id(n), []).extend(evs)
            last = now
            time.sleep(0.003)
        return
    for _ in range(int(seconds / dt)):
        for n in nets:
            evs = n.update(dt)
            if events is not None:
                events.setdefault(id(n), []).extend(evs)


def agree(a: Dots, b: Dots, at_least=50):
    common = set(a.history) & set(b.history)
    assert len(common) >= at_least, (len(common), a.tick, b.tick)
    bad = [t for t in sorted(common) if a.history[t] != b.history[t]]
    assert not bad, f"diverged at ticks {bad[:5]}"


def loop_host(lan, game, model="lockstep", **kw):
    return net.host(game, via="p2p", model=model, transport=lan.host(), **GAME, **kw)


def loop_join(lan, game, model="lockstep", name="", **kw):
    t = lan.connect()
    return net.join(
        game, via="p2p", address="", model=model, transport=t, name=name, **GAME, **kw
    )


# ---------------------------------------------------------------------- #
# sessions
# ---------------------------------------------------------------------- #


def test_players_get_ids_names_and_a_roster():
    lan = LoopbackNetwork()
    h = loop_host(lan, Dots(0))
    a = loop_join(lan, Dots(1), name="Ann")
    b = loop_join(lan, Dots(2), name="Bo")
    ev = {}
    drive([h, a, b], 0.2, events=ev)
    assert (a.player, b.player) == (1, 2)
    assert h.players == {0: {"name": "Host"}, 1: {"name": "Ann"}, 2: {"name": "Bo"}}
    assert a.players == h.players == b.players
    assert [e.kind for e in ev[id(h)]].count("join") == 2
    assert [e.kind for e in ev[id(a)]] == ["joined"]


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"version": "2"}, "different version"),
        ({"game_id": "other"}, "a different game"),
        ({"input_delay": 5}, "different network settings"),
    ],
)
def test_mismatched_clients_are_refused_with_a_reason(change, reason):
    lan = LoopbackNetwork()
    h = loop_host(lan, Dots(0))
    kw = {**GAME, "model": "lockstep", **change}
    c = net.join(Dots(1), via="p2p", address="", transport=lan.connect(), **kw)
    ev = {}
    drive([h, c], 0.2, events=ev)
    rejected = [e for e in ev[id(c)] if e.kind == "rejected"]
    assert rejected and reason in rejected[0].reason
    assert c.session.closed and len(h.players) == 1


def test_a_full_game_refuses_more_players():
    lan = LoopbackNetwork()
    h = loop_host(lan, Dots(0), max_players=2)
    a = loop_join(lan, Dots(1))
    b = loop_join(lan, Dots(2))
    ev = {}
    drive([h, a, b], 0.2, events=ev)
    assert a.session.joined
    assert any(e.kind == "rejected" and "full" in e.reason for e in ev[id(b)])


# ---------------------------------------------------------------------- #
# lockstep
# ---------------------------------------------------------------------- #


def test_lockstep_peers_run_identical_simulations():
    lan = LoopbackNetwork()
    games = [Dots(0), Dots(1), Dots(2)]
    h = loop_host(lan, games[0])
    peers = [h, loop_join(lan, games[1]), loop_join(lan, games[2])]
    drive(peers, 15.0)
    assert games[0].tick > 250
    agree(games[0], games[1], 250)
    agree(games[0], games[2], 250)
    assert set(games[0].pos) == {"0", "1", "2"}  # every player's input was used
    assert h.desyncs == 0


def test_lockstep_over_udp_with_packet_loss():
    games = [Dots(0), Dots(1), Dots(2)]
    chaos = {"loss": 0.2, "duplicate": 0.1, "jitter": 0.02}
    h = net.host(
        games[0],
        via="p2p",
        model="lockstep",
        port=0,
        transport=UdpTransport.host(0, interface="127.0.0.1", seed=3, **chaos),
        **GAME,
    )
    port = h.session.transport.port
    clients = [
        net.join(
            g,
            via="p2p",
            address="",
            model="lockstep",
            **GAME,
            transport=UdpTransport.connect(f"127.0.0.1:{port}", seed=10 + i, **chaos),
        )
        for i, g in enumerate(games[1:])
    ]
    drive([h, *clients], 5.0, real=True)
    assert games[0].tick > 60  # ~100 ticks in 5 s at 20 Hz, less the stalls
    agree(games[0], games[1], 50)
    agree(games[0], games[2], 50)
    assert set(games[0].pos) == {"0", "1", "2"}
    for n in [h, *clients]:
        n.close()


def test_a_late_joiner_gets_the_state_and_keeps_up():
    lan = LoopbackNetwork()
    host_game, late = Dots(0), Dots(9)
    h = loop_host(lan, host_game)
    a = loop_join(lan, Dots(1))
    drive([h, a], 5.0)
    started = host_game.tick
    b = loop_join(lan, late)
    drive([h, a, b], 5.0)
    assert min(late.history) > started  # it never ran the early ticks
    agree(host_game, late, 80)
    assert str(b.player) in host_game.pos  # its inputs are in the game


def test_a_desync_is_detected_and_repaired():
    lan = LoopbackNetwork()
    g0, g1 = Dots(0), Dots(1)
    h = loop_host(lan, g0, checksum_every=10)
    c = loop_join(lan, g1, checksum_every=10)
    ev = {}
    drive([h, c], 3.0, events=ev)
    g1.mix += 1  # a bug: the client's simulation drifts
    drive([h, c], 3.0, events=ev)
    assert h.desyncs == 1
    assert any(e.kind == "desync" for e in ev[id(h)])
    assert any(e.kind == "resync" for e in ev[id(c)])
    after = max(g1.history) - 40
    common = [t for t in set(g0.history) & set(g1.history) if t > after]
    assert common and all(g0.history[t] == g1.history[t] for t in common)


def test_others_play_on_when_a_client_leaves():
    lan = LoopbackNetwork()
    g0, g1, g2 = Dots(0), Dots(1), Dots(2)
    h = loop_host(lan, g0)
    a, b = loop_join(lan, g1), loop_join(lan, g2)
    drive([h, a, b], 2.0)
    b.close()
    before = g0.tick
    ev = {}
    drive([h, a], 3.0, events=ev)
    assert g0.tick > before + 40  # nobody waits for the leaver
    assert any(e.kind == "leave" and e.player == 2 for e in ev[id(h)])
    agree(g0, g1, 80)


def test_a_kicked_client_is_not_waited_for():
    lan = LoopbackNetwork()
    g0 = Dots(0)
    h = loop_host(lan, g0)
    c = loop_join(lan, Dots(1))
    drive([h, c], 1.0)
    h.session.kick(c.player)
    before = g0.tick
    ev = {}
    drive([h], 2.0, events=ev)
    assert any(e.kind == "leave" and e.player == 1 for e in ev[id(h)])
    assert g0.tick > before + 30


def test_lockstep_stalls_rather_than_guesses_when_a_client_goes_quiet():
    lan = LoopbackNetwork()
    g0 = Dots(0)
    h = loop_host(lan, g0)
    c = loop_join(lan, Dots(1))
    drive([h, c], 1.0)
    before = g0.tick
    drive([h], 1.0)  # the client stops sending (but has not left)
    assert g0.tick <= before + 3 + 1  # at most the input delay runs ahead
    assert h.waiting


# ---------------------------------------------------------------------- #
# authority
# ---------------------------------------------------------------------- #


def test_authority_clients_drive_their_dot_on_the_host_and_see_the_host_state():
    lan = LoopbackNetwork(drop_unreliable=0.3)
    g0, g1 = Dots(0), Dots(1)
    h = loop_host(lan, g0, model="authority")
    c = loop_join(lan, g1, model="authority")
    drive([h, c], 4.0, dt=1 / 30)
    assert "1" in g0.pos  # the client's inputs move its dot on the host
    assert c.ready
    # the client shows a recent host state (it does not simulate on its own)
    assert g1.tick in g0.history and g1.digest() == g0.history[g1.tick]
    assert g0.tick - g1.tick <= 12


def test_authority_interpolates_between_snapshots_when_the_game_can():
    class Smooth(Dots):
        def __init__(self, seed):
            super().__init__(seed)
            self.blends = []

        def net_interpolate(self, older, newer, t):
            self.blends.append(t)
            self.net_restore(newer if t >= 0.5 else older)

    lan = LoopbackNetwork()
    g0, g1 = Dots(0), Smooth(1)
    h = loop_host(lan, g0, model="authority", snapshot_every=3)
    c = loop_join(lan, g1, model="authority", snapshot_every=3)
    drive([h, c], 3.0, dt=1 / 60)
    inner = [t for t in g1.blends if 0.0 < t < 1.0]
    assert len(inner) > 20  # shown between snapshots, not only on them
