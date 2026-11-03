"""What a game implements to go online: four methods, all bytes in and out.

The game owns its encoding (struct, json, msgpack...). The engine never unpickles
anything from the network.
"""

import zlib
from typing import Protocol


class NetGame(Protocol):
    def net_input(self) -> bytes:
        """The local player's input for the next tick, encoded."""

    def net_step(self, dt: float, inputs: dict[int, bytes]) -> None:
        """Advance one tick. `inputs`: player id -> that player's encoded input (players
        with nothing for this tick are absent). Lockstep: must be deterministic."""

    def net_snapshot(self) -> bytes:
        """The whole game state (late joins, resyncs, authority snapshots)."""

    def net_restore(self, data: bytes) -> None:
        """Become the state `net_snapshot()` produced."""

    # Optional:
    #   net_checksum(self) -> int        lockstep desync check (default: crc32 of the
    #                                    snapshot; supply a cheaper digest if you can)
    #   net_interpolate(self, older: bytes, newer: bytes, t: float) -> None
    #                                    authority clients: show the state t (0..1) of
    #                                    the way from `older` to `newer` (default: show
    #                                    the newest snapshot as it arrives)


def checksum(game) -> int:
    fn = getattr(game, "net_checksum", None)
    value = fn() if fn is not None else zlib.crc32(game.net_snapshot())
    return int(value) & 0xFFFFFFFF
