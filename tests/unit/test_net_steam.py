"""The Steam transport against an in-process stand-in for py_steam_net's client.

The fake keeps lobbies and members, posts lobby callbacks on `run_callbacks()`, and
follows ISteamNetworkingMessages' session rule in its strictest form: a message is
dropped unless the receiver has already sent something to the sender.
"""

import os

import pytest

import soragl.net as net
from soragl.net import steam as st
from soragl.net.steam import SteamTransport

from test_net_models import GAME, Dots, agree, drive


class Cloud:
    def __init__(self):
        self.clients: dict[int, "FakeSteam"] = {}
        self.lobbies: dict[int, dict] = {}
        self.next_lobby = 9000
        self.dropped = 0


class FakeSteam:
    def __init__(self, cloud: Cloud, sid: int):
        self.cloud, self.sid = cloud, sid
        cloud.clients[sid] = self
        self.inbox = {0: [], 1: []}
        self.queued = []
        self.sent_to: set[int] = set()
        self.on_message = self.on_lobby = self.on_failed = None

    def own_steam_id(self):
        return self.sid

    def set_message_recv_callback(self, cb):
        self.on_message = cb

    def set_lobby_changed_callback(self, cb):
        self.on_lobby = cb

    def set_connection_failed_callback(self, cb):
        self.on_failed = cb

    def run_callbacks(self):
        queued, self.queued = self.queued, []
        for fn in queued:
            fn()

    def create_lobby(self, kind, max_members, cb):
        lid = self.cloud.next_lobby = self.cloud.next_lobby + 1
        self.cloud.lobbies[lid] = {"members": [self.sid], "max": max_members}
        self.queued.append(lambda: cb(lid))

    def join_lobby(self, lid, cb):
        lobby = self.cloud.lobbies.get(lid)
        if lobby is None or len(lobby["members"]) >= lobby["max"]:
            self.queued.append(lambda: cb(None, "No Lobby Found"))
            return
        for other in lobby["members"]:
            c = self.cloud.clients[other]
            c.queued.append(
                lambda c=c: c.on_lobby and c.on_lobby(lid, self.sid, self.sid, 1)
            )
        lobby["members"].append(self.sid)
        self.queued.append(lambda: cb(lid, None))

    def leave_lobby(self, lid):
        lobby = self.cloud.lobbies.get(lid)
        if lobby and self.sid in lobby["members"]:
            lobby["members"].remove(self.sid)
            for other in lobby["members"]:
                c = self.cloud.clients[other]
                c.queued.append(
                    lambda c=c: c.on_lobby and c.on_lobby(lid, self.sid, self.sid, 2)
                )

    def get_lobby_members(self, lid):
        lobby = self.cloud.lobbies.get(lid)
        if not lobby or not lobby["members"]:
            raise RuntimeError("Lobby not found or no members")
        return list(lobby["members"])

    def send_message_to(self, sid, flags, channel, data):
        assert len(data) <= st.STEAM_MAX
        self.sent_to.add(sid)
        target = self.cloud.clients.get(sid)
        if target is None:
            return
        if self.sid not in target.sent_to:  # the receiver never accepted this session
            self.cloud.dropped += 1
            return
        target.inbox[channel].append((self.sid, channel, bytes(data)))

    def receive_messages(self, channel, max_messages):
        msgs = self.inbox[channel][:max_messages]
        del self.inbox[channel][:max_messages]
        for m in msgs:
            self.on_message(*m)


def steam_game(cloud, players=3, model="lockstep"):
    games = [Dots(i) for i in range(players)]
    host_t = SteamTransport.host(max_players=8, steam=FakeSteam(cloud, 100))
    nets = [net.host(games[0], via="steam", model=model, transport=host_t, **GAME)]
    for i in range(1, players):
        t = SteamTransport.join(host_t.lobby_id, steam=FakeSteam(cloud, 100 + i))
        nets.append(
            net.join(
                games[i],
                via="steam",
                address=host_t.lobby_id,
                model=model,
                transport=t,
                **GAME,
            )
        )
    return games, nets


def test_lockstep_over_steam_lobbies_and_messages():
    cloud = Cloud()
    games, nets = steam_game(cloud)
    drive(nets, 10.0)
    assert nets[1].player and nets[2].player
    agree(games[0], games[1], 150)
    agree(games[0], games[2], 150)
    assert set(games[0].pos) == {"0", "1", "2"}
    assert cloud.dropped >= 1  # the session rule bit, and the handshake got through


def test_authority_over_steam():
    cloud = Cloud()
    games, nets = steam_game(cloud, players=2, model="authority")
    drive(nets, 3.0, dt=1 / 30)
    assert "1" in games[0].pos and nets[1].ready


def test_strangers_outside_the_lobby_are_ignored():
    cloud = Cloud()
    host_t = SteamTransport.host(steam=FakeSteam(cloud, 100))
    stranger = FakeSteam(cloud, 666)
    host_t.steam.sent_to.add(666)  # even with a session open, not a lobby member
    stranger.send_message_to(100, st.RELIABLE_FLAGS, 0, bytes([st.HELLO]))
    assert host_t.poll() == [] and host_t.peers == {}


def test_leaving_the_lobby_is_a_disconnect():
    cloud = Cloud()
    games, nets = steam_game(cloud)
    drive(nets, 1.0)
    nets[2].close()
    ev = {}
    drive(nets[:2], 2.0, events=ev)
    assert any(e.kind == "leave" and e.player == 2 for e in ev[id(nets[0])])
    assert games[0].tick > 30


def test_large_reliable_messages_are_split_under_steams_limit():
    cloud = Cloud()
    host_t = SteamTransport.host(steam=FakeSteam(cloud, 100))
    c = SteamTransport.join(host_t.lobby_id, steam=FakeSteam(cloud, 101))
    for _ in range(10):
        host_t.poll()
        c.poll()
    assert 0 in c.peers
    blob = os.urandom(1_300_000)
    c.send(0, blob)
    got = [e for _ in range(5) for e in host_t.poll() if e.kind == "message"]
    assert [e.data for e in got] == [blob]
    with pytest.raises(ValueError):
        c.send(0, b"x" * st.STEAM_MAX, reliable=False)


def test_joining_a_missing_lobby_says_why():
    cloud = Cloud()
    with pytest.raises(RuntimeError, match="could not join lobby 42"):
        SteamTransport.join(42, steam=FakeSteam(cloud, 101))


def test_a_clear_message_when_py_steam_net_is_missing(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_steam(name, *a, **kw):
        if name == "py_steam_net":
            raise ImportError("No module named 'py_steam_net'")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_steam)
    monkeypatch.setattr(st, "_client", None)
    with pytest.raises(RuntimeError, match="py_steam_net is not installed"):
        st.client()
