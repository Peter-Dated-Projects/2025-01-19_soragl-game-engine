"""Transports move bytes between peers; everything above them is transport-agnostic.

A transport is polled once per frame (no threads). `poll()` returns what happened since
the last poll as `Event`s; `send()` queues bytes for one peer, reliable (ordered, never
lost) or unreliable (latest-state traffic: may be dropped, never duplicated).
"""

from dataclasses import dataclass, field


@dataclass
class Event:
    kind: str  # "connect", "message", "disconnect"
    peer: int
    data: bytes = b""
    reliable: bool = True
    reason: str = ""


class Transport:
    """One endpoint. A host accepts many peers; a client connects to one host."""

    is_host: bool = False

    def send(self, peer: int, data: bytes, reliable: bool = True) -> None:
        raise NotImplementedError

    def poll(self) -> list[Event]:
        raise NotImplementedError

    def disconnect(self, peer: int) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def rtt(self, peer: int) -> float | None:
        """Round-trip time in seconds if the transport measures it."""
        return None


# ---------------------------------------------------------------------- #
# in-process loopback (tests, and single player through the online code path)
# ---------------------------------------------------------------------- #


@dataclass
class LoopbackNetwork:
    """A switchboard joining in-process transports. `drop_unreliable` (0..1) loses that
    share of unreliable messages, seeded, so tests can exercise latest-state traffic."""

    drop_unreliable: float = 0.0
    seed: int = 1
    _hosts: dict = field(default_factory=dict)
    _next_id: int = 1

    def __post_init__(self):
        import random

        self._rng = random.Random(self.seed)

    def host(self, address: str = "host") -> "LoopbackTransport":
        t = LoopbackTransport(self, is_host=True)
        self._hosts[address] = t
        return t

    def connect(self, address: str = "host") -> "LoopbackTransport":
        host = self._hosts.get(address)
        client = LoopbackTransport(self, is_host=False)
        if host is None or host.closed:
            client._inbox.append(
                Event("disconnect", 0, reason="no host at that address")
            )
            return client
        pid = self._next_id
        self._next_id += 1
        client._links[0] = (host, pid)
        host._links[pid] = (client, 0)
        client._inbox.append(Event("connect", 0))
        host._inbox.append(Event("connect", pid))
        return client


class LoopbackTransport(Transport):
    def __init__(self, net: LoopbackNetwork, is_host: bool):
        self.net = net
        self.is_host = is_host
        self.closed = False
        self._links: dict[
            int, tuple
        ] = {}  # my peer id -> (other transport, my id there)
        self._inbox: list[Event] = []

    def send(self, peer: int, data: bytes, reliable: bool = True) -> None:
        link = self._links.get(peer)
        if link is None:
            return
        if not reliable and self.net._rng.random() < self.net.drop_unreliable:
            return
        other, me = link
        other._inbox.append(Event("message", me, bytes(data), reliable))

    def poll(self) -> list[Event]:
        out, self._inbox = self._inbox, []
        return out

    def disconnect(self, peer: int) -> None:
        link = self._links.pop(peer, None)
        if link is not None:
            other, me = link
            other._links.pop(me, None)
            other._inbox.append(Event("disconnect", me, reason="closed by peer"))

    def close(self) -> None:
        for peer in list(self._links):
            self.disconnect(peer)
        self.closed = True
