"""Multiplayer for SoraGL games: pick how players connect and how the game stays in sync.

    net = soragl.net.host(game, via="p2p", model="lockstep", game_id="my-game",
                          version="1.0", port=7777)
    net = soragl.net.join(game, via="p2p", address="203.0.113.5:7777", model="lockstep",
                          game_id="my-game", version="1.0")
    # every frame:
    for event in net.update(real_dt): ...   # join / leave / closed / desync ...

`via` (the player chooses; there is no default):
  "p2p"    a player's machine hosts and everyone connects to its IP and port (LAN, or
           the internet with that port forwarded on the host's router)
  "steam"  Steam carries the traffic: the host makes a Steam lobby, others join it by
           lobby id; Steam relays traffic, so nobody forwards ports (soragl.net.steam)

`model`:
  "lockstep"   only inputs travel; every machine runs the same deterministic simulation
  "authority"  the host simulates; clients send inputs and show the host's snapshots

The game implements `NetGame` (soragl.net.game): net_input, net_step, net_snapshot,
net_restore. A dedicated server is just a host whose own input is empty, run with
`run_headless`.
"""

import time

from soragl.net.authority import Authority
from soragl.net.game import NetGame
from soragl.net.lockstep import Lockstep
from soragl.net.session import ClientSession, HostSession, SessionEvent
from soragl.net.transport import Event, LoopbackNetwork, Transport
from soragl.net.udp import UdpTransport

DEFAULT_PORT = 7777
MODELS = {"lockstep": Lockstep, "authority": Authority}

__all__ = [
    "DEFAULT_PORT",
    "Authority",
    "ClientSession",
    "Event",
    "HostSession",
    "Lockstep",
    "LoopbackNetwork",
    "NetGame",
    "SessionEvent",
    "Transport",
    "UdpTransport",
    "host",
    "join",
    "run_headless",
]


def _sync(model: str, options: dict) -> str:
    if model not in MODELS:
        raise ValueError(f"model must be one of {sorted(MODELS)}, not {model!r}")
    return model + "".join(f";{k}={options[k]}" for k in sorted(options))


def host(
    game,
    *,
    via: str,
    model: str,
    game_id: str,
    version: str,
    name: str = "Host",
    max_players: int = 8,
    port: int = DEFAULT_PORT,
    lobby: str = "friends",
    transport: Transport | None = None,
    **options,
):
    """Start hosting. `options` go to the sync model (dt, input_delay, snapshot_every...)
    and must match on every player's side (the handshake checks)."""
    if transport is None:
        if via == "p2p":
            transport = UdpTransport.host(port, max_peers=max_players - 1)
        elif via == "steam":
            from soragl.net.steam import SteamTransport

            transport = SteamTransport.host(max_players=max_players, lobby=lobby)
        else:
            raise ValueError('via must be "p2p" or "steam"')
    session = HostSession(
        transport,
        game_id,
        version,
        name,
        max_players,
        info={"model": model},
        sync=_sync(model, options),
    )
    return MODELS[model](session, game, **options)


def join(
    game,
    *,
    via: str,
    address,
    model: str,
    game_id: str,
    version: str,
    name: str = "",
    transport: Transport | None = None,
    **options,
):
    """Join a host. `address`: "ip:port" for p2p, the lobby id for steam."""
    if transport is None:
        if via == "p2p":
            transport = UdpTransport.connect(address)
        elif via == "steam":
            from soragl.net.steam import SteamTransport

            transport = SteamTransport.join(int(address))
        else:
            raise ValueError('via must be "p2p" or "steam"')
    session = ClientSession(
        transport, game_id, version, name, sync=_sync(model, options)
    )
    return MODELS[model](session, game, **options)


def run_headless(net, *, seconds: float | None = None, on_event=None) -> None:
    """Drive a session without a window (a dedicated server, or a bot) until it closes
    or `seconds` pass. Sleeps between ticks rather than spinning."""
    start = last = time.monotonic()
    while not net.session.closed:
        now = time.monotonic()
        for ev in net.update(now - last):
            if on_event is not None:
                on_event(ev)
        last = now
        if seconds is not None and now - start >= seconds:
            return
        time.sleep(min(0.005, net.dt / 4))
