"""UDP transport: a player's machine hosts and everyone connects to its IP and port.

Plain non-blocking UDP polled once per frame, plus a small reliability layer in the shape
of Gaffer on Games' "Reliability and Congestion Avoidance over UDP": every packet carries
a sequence number and acks for the last 33 packets it received; reliable messages are
resent on a timer until a packet carrying them is acked, and delivered in order. Messages
of any size are split into pieces (reliable: ordered pieces; unreliable: a group that is
dropped whole if a piece is lost).

Everything read from the socket is untrusted: malformed packets are ignored, and every
buffer a peer can grow is capped.
"""

import os
import random
import socket
import struct
import time

from soragl.net.transport import Event, Transport

MAGIC = b"SGL1"
CONNECT, ACCEPT, DATA, BYE = 1, 2, 3, 4
HEAD = struct.Struct("!4sBI")  # magic, packet type, connection id
SEQ = struct.Struct("!III")  # packet sequence, highest received, bits for the 32 before
MSG = struct.Struct("!BIH")  # flags, message id / group id, length
PART = struct.Struct("!HH")  # unreliable piece index, piece count

F_RELIABLE, F_MORE, F_PIECE = 1, 2, 4
MTU = 1200  # bytes per datagram: under the common 1280 IPv6 / tunnel minimum
PIECE = 1024  # payload bytes per message piece
WINDOW = 512  # reliable pieces in flight per peer
MAX_MESSAGE = 8 * 1024 * 1024  # largest message a peer may send us
MAX_GROUPS = 16  # unreliable groups being assembled per peer
KEEPALIVE = 0.1  # seconds: send an (ack-only) packet at least this often


class _Peer:
    def __init__(self, pid: int, addr, conn: int, now: float):
        self.id = pid
        self.addr = addr
        self.conn = conn
        self.connected = False
        self.last_recv = now
        self.last_send = -1.0
        self.next_seq = 1
        self.remote_seq = 0  # highest packet sequence received (0: none yet)
        self.remote_bits = 0
        self.sent: dict[
            int, tuple[float, list[int]]
        ] = {}  # seq -> (time, reliable ids)
        self.out: dict[
            int, list
        ] = {}  # reliable id -> [flags, data, last sent or None]
        self.next_out = 0
        self.unreliable: list[tuple[int, int, bytes]] = []
        self.next_group = 0
        self.next_in = 0
        self.inbox: dict[int, tuple[int, bytes]] = {}
        self.assembling: list[bytes] = []
        self.assembled = 0
        self.groups: dict[
            int, list
        ] = {}  # group id -> [first seen, count, {index: data}]
        self.rtt = 0.1
        self.need_ack = False


class UdpTransport(Transport):
    """`UdpTransport.host(port)` listens; `UdpTransport.connect("ip:port")` joins one.

    Test hooks (all default off): `loss` drops that share of outgoing datagrams,
    `duplicate` sends that share twice, `jitter` holds each one up to that many seconds
    (so datagrams overtake each other), all from `seed`.
    """

    def __init__(
        self,
        bind=("0.0.0.0", 0),
        *,
        is_host: bool,
        max_peers: int = 16,
        timeout: float = 5.0,
        loss: float = 0.0,
        duplicate: float = 0.0,
        jitter: float = 0.0,
        seed: int | None = None,
    ):
        self.is_host = is_host
        self.max_peers = max_peers
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        if is_host:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(bind)
        self.port = self.sock.getsockname()[1]
        self.peers: dict[int, _Peer] = {}
        self._by_addr: dict = {}
        self._next_pid = 1
        self._events: list[Event] = []
        self._chaos = (loss, duplicate, jitter)
        self._rng = random.Random(seed)
        self._held: list[tuple[float, bytes, tuple]] = []
        self._connecting: _Peer | None = None
        self._connect_started = 0.0
        self._last_hello = -1.0

    # ---- construction ----

    @classmethod
    def host(cls, port: int = 0, interface: str = "0.0.0.0", **kw) -> "UdpTransport":
        return cls((interface, port), is_host=True, **kw)

    @classmethod
    def connect(cls, address, **kw) -> "UdpTransport":
        """`address`: "ip:port" or (ip, port)."""
        if isinstance(address, str):
            ip, _, port = address.rpartition(":")
            address = (ip or "127.0.0.1", int(port))
        t = cls(is_host=False, **kw)
        addr = (socket.gethostbyname(address[0]), int(address[1]))
        now = time.monotonic()
        peer = _Peer(0, addr, struct.unpack("!I", os.urandom(4))[0] or 1, now)
        t.peers[0] = peer
        t._by_addr[addr] = peer
        t._connecting = peer
        t._connect_started = now
        return t

    # ---- Transport API ----

    def send(self, peer: int, data: bytes, reliable: bool = True) -> None:
        p = self.peers.get(peer)
        if p is None:
            return
        if len(data) > MAX_MESSAGE:
            raise ValueError(f"message of {len(data)} bytes is over {MAX_MESSAGE}")
        if reliable:
            pieces = [data[i : i + PIECE] for i in range(0, len(data), PIECE)] or [b""]
            for i, piece in enumerate(pieces):
                more = F_MORE if i < len(pieces) - 1 else 0
                p.out[p.next_out] = [F_RELIABLE | more, piece, None]
                p.next_out += 1
        elif len(data) <= PIECE:
            p.unreliable.append((0, 0, data))
        else:
            group = p.next_group = (p.next_group + 1) & 0xFFFFFFFF
            count = (len(data) + PIECE - 1) // PIECE
            if count > 0xFFFF:
                raise ValueError("unreliable message too large")
            for i in range(count):
                chunk = PART.pack(i, count) + data[i * PIECE : (i + 1) * PIECE]
                p.unreliable.append((F_PIECE, group, chunk))

    def poll(self) -> list[Event]:
        now = time.monotonic()
        self._receive(now)
        self._timeouts(now)
        for p in list(self.peers.values()):
            if p.connected:
                self._flush(p, now)
        self._release_held(now)
        out, self._events = self._events, []
        return out

    def disconnect(self, peer: int) -> None:
        p = self.peers.get(peer)
        if p is None:
            return
        for _ in range(3):  # best effort: BYE is not acked
            self._sendto(HEAD.pack(MAGIC, BYE, p.conn), p.addr)
        self._drop(p, "closed", notify=False)

    def close(self) -> None:
        for pid in list(self.peers):
            self.disconnect(pid)
        self._release_held(float("inf"))
        self.sock.close()

    def rtt(self, peer: int) -> float | None:
        p = self.peers.get(peer)
        return p.rtt if p and p.connected else None

    # ---- internals ----

    def _sendto(self, data: bytes, addr) -> None:
        loss, dup, jitter = self._chaos
        if loss or dup or jitter:
            if self._rng.random() < loss:
                return
            copies = 2 if self._rng.random() < dup else 1
            for _ in range(copies):
                due = time.monotonic() + self._rng.random() * jitter
                self._held.append((due, data, addr))
            return
        try:
            self.sock.sendto(data, addr)
        except OSError:
            pass  # unreachable / buffer full: UDP may lose it, the resend timer copes

    def _release_held(self, now: float) -> None:
        if not self._held:
            return
        due = [h for h in self._held if h[0] <= now]
        self._held = [h for h in self._held if h[0] > now]
        for _, data, addr in due:
            try:
                self.sock.sendto(data, addr)
            except OSError:
                pass

    def _receive(self, now: float) -> None:
        for _ in range(4096):  # bounded: a flood cannot stall the frame forever
            try:
                packet, addr = self.sock.recvfrom(65536)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                continue  # e.g. ICMP port unreachable surfacing on some platforms
            if len(packet) < HEAD.size:
                continue
            magic, kind, conn = HEAD.unpack_from(packet)
            if magic != MAGIC:
                continue
            try:
                self._handle(kind, conn, packet[HEAD.size :], addr, now)
            except (struct.error, ValueError, IndexError):
                continue  # malformed: ignore it

    def _handle(self, kind: int, conn: int, body: bytes, addr, now: float) -> None:
        p = self._by_addr.get(addr)
        if kind == CONNECT and self.is_host:
            if p is not None and p.conn == conn:
                self._sendto(
                    HEAD.pack(MAGIC, ACCEPT, conn), addr
                )  # our ACCEPT was lost
                return
            if p is not None:
                self._drop(p, "reconnected")
            if len(self.peers) >= self.max_peers:
                self._sendto(HEAD.pack(MAGIC, BYE, conn), addr)
                return
            p = _Peer(self._next_pid, addr, conn, now)
            self._next_pid += 1
            p.connected = True
            self.peers[p.id] = p
            self._by_addr[addr] = p
            self._sendto(HEAD.pack(MAGIC, ACCEPT, conn), addr)
            self._events.append(Event("connect", p.id))
            return
        if p is None or p.conn != conn:
            return
        p.last_recv = now
        if kind in (ACCEPT, DATA) and not self.is_host and not p.connected:
            # the host's data also proves we were accepted (its ACCEPT may be lost)
            p.connected = True
            self._connecting = None
            self._events.append(Event("connect", p.id))
        if kind == BYE:
            self._drop(p, "closed by peer" if p.connected else "refused (server full)")
        elif kind == DATA and p.connected:
            self._data(p, body, now)

    def _data(self, p: _Peer, body: bytes, now: float) -> None:
        seq, ack, bits = SEQ.unpack_from(body)
        if seq == 0:
            return
        # duplicate or too old to tell: drop it (reliable content is resent anyway)
        if seq == p.remote_seq:
            return
        if seq < p.remote_seq:
            d = p.remote_seq - seq - 1
            if d >= 32 or p.remote_bits >> d & 1:
                return
            p.remote_bits |= 1 << d
        else:
            shift = seq - p.remote_seq
            if p.remote_seq:
                p.remote_bits = (
                    (p.remote_bits << shift) | (1 << (shift - 1))
                ) & 0xFFFFFFFF
            p.remote_seq = seq
        p.need_ack = True
        self._acked(p, ack, now)
        for i in range(32):
            if bits >> i & 1:
                self._acked(p, ack - 1 - i, now)
        off = SEQ.size
        while off < len(body):
            flags, mid, n = MSG.unpack_from(body, off)
            off += MSG.size
            chunk = body[off : off + n]
            if len(chunk) != n:
                return
            off += n
            if flags & F_RELIABLE:
                self._reliable_in(p, flags, mid, chunk)
            elif flags & F_PIECE:
                self._piece_in(p, mid, chunk, now)
            else:
                self._events.append(Event("message", p.id, chunk, False))

    def _acked(self, p: _Peer, seq: int, now: float) -> None:
        entry = p.sent.pop(seq, None)
        if entry is None:
            return
        sent_at, ids = entry
        p.rtt += (max(0.0, now - sent_at) - p.rtt) * 0.1
        for mid in ids:
            p.out.pop(mid, None)

    def _reliable_in(self, p: _Peer, flags: int, mid: int, chunk: bytes) -> None:
        if mid < p.next_in or mid in p.inbox or mid - p.next_in >= WINDOW * 2:
            return
        p.inbox[mid] = (flags, chunk)
        while p.next_in in p.inbox:
            f, data = p.inbox.pop(p.next_in)
            p.next_in += 1
            p.assembling.append(data)
            p.assembled += len(data)
            if p.assembled > MAX_MESSAGE:
                self._drop(p, "message too large")
                return
            if not f & F_MORE:
                self._events.append(Event("message", p.id, b"".join(p.assembling)))
                p.assembling, p.assembled = [], 0

    def _piece_in(self, p: _Peer, group: int, chunk: bytes, now: float) -> None:
        index, count = PART.unpack_from(chunk)
        if count == 0 or index >= count or count * PIECE > MAX_MESSAGE:
            return
        g = p.groups.get(group)
        if g is None:
            for old in [k for k, v in p.groups.items() if now - v[0] > 1.0]:
                del p.groups[old]
            if len(p.groups) >= MAX_GROUPS:
                del p.groups[min(p.groups, key=lambda k: p.groups[k][0])]
            g = p.groups[group] = [now, count, {}]
        if g[1] != count:
            return
        g[2][index] = chunk[PART.size :]
        if len(g[2]) == count:
            del p.groups[group]
            data = b"".join(g[2][i] for i in range(count))
            self._events.append(Event("message", p.id, data, False))

    def _flush(self, p: _Peer, now: float) -> None:
        resend = max(0.05, p.rtt * 1.5)
        first = min(p.out) if p.out else p.next_out
        due = [
            (mid, e)
            for mid, e in p.out.items()
            if mid < first + WINDOW and (e[2] is None or now - e[2] >= resend)
        ]
        msgs = [(e[0], mid, e[1], mid) for mid, e in due]
        msgs += [(f, gid, data, None) for f, gid, data in p.unreliable]
        p.unreliable = []
        packets = 0
        i = 0
        while i < len(msgs) or (
            packets == 0 and (p.need_ack or now - p.last_send >= KEEPALIVE)
        ):
            body = [SEQ.pack(p.next_seq, p.remote_seq, p.remote_bits)]
            size = HEAD.size + SEQ.size
            ids = []
            while i < len(msgs):
                flags, mid, data, rid = msgs[i]
                if len(body) > 1 and size + MSG.size + len(data) > MTU:
                    break  # (one piece always fits: PIECE + headers < MTU)
                body.append(MSG.pack(flags, mid, len(data)))
                body.append(data)
                size += MSG.size + len(data)
                if rid is not None:
                    ids.append(rid)
                    p.out[rid][2] = now
                i += 1
            p.sent[p.next_seq] = (now, ids)
            if len(p.sent) > 1024:
                del p.sent[next(iter(p.sent))]  # oldest: sequences only grow
            self._sendto(HEAD.pack(MAGIC, DATA, p.conn) + b"".join(body), p.addr)
            p.next_seq += 1
            p.last_send = now
            p.need_ack = False
            packets += 1

    def _timeouts(self, now: float) -> None:
        c = self._connecting
        if c is not None:
            if now - self._connect_started > self.timeout:
                self._connecting = None
                self._drop(c, "could not reach the host")
            elif now - self._last_hello >= 0.2:
                self._last_hello = now
                self._sendto(HEAD.pack(MAGIC, CONNECT, c.conn), c.addr)
        for p in list(self.peers.values()):
            if p.connected and now - p.last_recv > self.timeout:
                self._drop(p, "timed out")

    def _drop(self, p: _Peer, reason: str, notify: bool = True) -> None:
        self.peers.pop(p.id, None)
        if self._by_addr.get(p.addr) is p:
            del self._by_addr[p.addr]
        if notify:
            self._events.append(Event("disconnect", p.id, reason=reason))
