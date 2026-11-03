"""The UDP transport over real localhost sockets, with loss, duplication and reordering."""

import os
import random
import socket
import time

import pytest

from soragl.net.udp import MAGIC, UdpTransport


def pump(*ts, until, seconds=10.0):
    """Poll every transport until `until(events)` holds; returns events per transport."""
    seen = [[] for _ in ts]
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for i, t in enumerate(ts):
            seen[i] += t.poll()
        if until(seen):
            return seen
        time.sleep(0.002)
    raise AssertionError(f"timed out; saw {[[e.kind for e in s][:20] for s in seen]}")


def connected_pair(**chaos):
    host = UdpTransport.host(0, interface="127.0.0.1", seed=1, **chaos)
    client = UdpTransport.connect(f"127.0.0.1:{host.port}", seed=2, **chaos)
    pump(
        host,
        client,
        until=lambda s: (
            any(e.kind == "connect" for e in s[0])
            and any(e.kind == "connect" for e in s[1])
        ),
    )
    return host, client


def messages(events, reliable=True):
    return [e.data for e in events if e.kind == "message" and e.reliable == reliable]


def test_reliable_messages_arrive_once_and_in_order_through_loss_and_reordering():
    host, client = connected_pair(loss=0.3, duplicate=0.2, jitter=0.03)
    sent = [f"msg {i}".encode() for i in range(2000)]
    for i, m in enumerate(sent):
        client.send(0, m)
        if i % 100 == 0:  # spread over several frames, as a game would
            client.poll()
            host.poll()
    seen = pump(
        host, client, until=lambda s: len(messages(s[0])) >= len(sent), seconds=30
    )
    assert messages(seen[0]) == sent
    host.close()
    client.close()


def test_a_large_message_is_split_and_rebuilt_under_loss():
    host, client = connected_pair(loss=0.25, jitter=0.02)
    blob = os.urandom(300_000)
    host.send(1, blob)
    host.send(1, b"after")
    seen = pump(host, client, until=lambda s: len(messages(s[1])) >= 2, seconds=30)
    assert messages(seen[1]) == [blob, b"after"]
    host.close()
    client.close()


def test_unreliable_messages_large_and_small_arrive_without_loss_injected():
    host, client = connected_pair()
    big = os.urandom(20_000)
    client.send(0, b"tiny", reliable=False)
    client.send(0, big, reliable=False)
    seen = pump(host, client, until=lambda s: len(messages(s[0], False)) >= 2)
    assert sorted(messages(seen[0], False), key=len) == [b"tiny", big]
    host.close()
    client.close()


def test_rtt_is_measured():
    host, client = connected_pair()
    for _ in range(20):
        client.send(0, b"x")
        pump(host, client, until=lambda s: True)
        time.sleep(0.01)
    assert 0.0 <= client.rtt(0) < 0.1


def test_connecting_to_nobody_times_out():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()  # nothing listens there now
    client = UdpTransport.connect(f"127.0.0.1:{port}", timeout=0.5)
    seen = pump(client, until=lambda s: any(e.kind == "disconnect" for e in s[0]))
    assert seen[0][-1].reason == "could not reach the host"
    client.close()


def test_a_full_host_refuses_and_a_closed_peer_is_reported():
    host = UdpTransport.host(0, interface="127.0.0.1", max_peers=1)
    a = UdpTransport.connect(f"127.0.0.1:{host.port}")
    pump(host, a, until=lambda s: any(e.kind == "connect" for e in s[1]))
    b = UdpTransport.connect(f"127.0.0.1:{host.port}")
    seen = pump(host, b, until=lambda s: any(e.kind == "disconnect" for e in s[1]))
    assert "full" in seen[1][-1].reason
    a.close()
    seen = pump(host, until=lambda s: any(e.kind == "disconnect" for e in s[0]))
    assert seen[0][-1].reason == "closed by peer"
    host.close()
    b.close()


def test_a_silent_peer_times_out():
    host = UdpTransport.host(0, interface="127.0.0.1", timeout=0.4)
    client = UdpTransport.connect(f"127.0.0.1:{host.port}")
    pump(host, client, until=lambda s: any(e.kind == "connect" for e in s[0]))
    client.sock.close()  # vanishes without a word
    seen = pump(host, until=lambda s: any(e.kind == "disconnect" for e in s[0]))
    assert seen[0][-1].reason == "timed out"
    host.close()


def test_junk_packets_are_ignored():
    host, client = connected_pair()
    rng = random.Random(5)
    junk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(2000):
        n = rng.randrange(0, 200)
        data = bytes(rng.randrange(256) for _ in range(n))
        if i % 2:
            data = MAGIC + data  # past the magic check, into the parsers
        junk.sendto(data, ("127.0.0.1", host.port))
    client.send(0, b"still fine")
    seen = pump(host, client, until=lambda s: b"still fine" in messages(s[0]))
    # junk that happens to parse as CONNECT becomes (and stops being) a peer of its
    # own; the real client (peer 1) is never dropped
    assert all(e.peer != 1 for e in seen[0] if e.kind == "disconnect")
    assert 1 in host.peers
    junk.close()
    host.close()
    client.close()


def test_oversized_messages_are_refused_up_front():
    host, client = connected_pair()
    with pytest.raises(ValueError):
        client.send(0, b"x" * (8 * 1024 * 1024 + 1))
    host.close()
    client.close()
