"""Operations on 2D tile grids held as numpy arrays indexed `[x, y]`."""

from collections import deque
from collections.abc import Iterable, Iterator

import numpy as np

_STRAIGHT = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def distance_field(
    passable: np.ndarray,
    sources: Iterable[tuple[int, int]],
    diagonal: bool = True,
) -> np.ndarray:
    """Breadth-first step distance from `sources` over `passable` tiles.

    Unreachable tiles are -1. Walkers reach a source by repeatedly stepping to a
    neighbour with a smaller distance (a flow field, see `downhill`), so one field serves
    any number of walkers heading to the same place. Diagonal steps need both orthogonal
    neighbours passable, so walkers never clip a corner.
    """
    w, h = passable.shape
    dist = np.full((w, h), -1, np.int32)
    queue = deque()
    for x, y in sources:
        if 0 <= x < w and 0 <= y < h:
            dist[x, y] = 0
            queue.append((x, y))
    steps = _STRAIGHT + _DIAGONAL if diagonal else _STRAIGHT
    while queue:
        x, y = queue.popleft()
        d = dist[x, y] + 1
        for dx, dy in steps:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and dist[nx, ny] < 0 and passable[nx, ny]:
                if dx and dy and not (passable[x + dx, y] and passable[x, y + dy]):
                    continue
                dist[nx, ny] = d
                queue.append((nx, ny))
    return dist


class IncrementalDistanceField:
    """`distance_field`, computed a slice at a time so no single frame pays for it.

    Call `advance(budget)` once per tick with how many tiles it may expand; it returns
    True once the field is complete. Until then `field` holds a partial result (tiles not
    yet reached are -1), so callers can fall back to straight-line steering meanwhile.
    The finished field is identical to `distance_field` on the same inputs.
    """

    def __init__(
        self,
        passable: np.ndarray,
        sources: Iterable[tuple[int, int]],
        diagonal: bool = True,
    ):
        self.passable = passable
        w, h = passable.shape
        self.field = np.full((w, h), -1, np.int32)
        self._queue = deque()
        for x, y in sources:
            if 0 <= x < w and 0 <= y < h:
                self.field[x, y] = 0
                self._queue.append((x, y))
        self._steps = _STRAIGHT + _DIAGONAL if diagonal else _STRAIGHT
        self.done = not self._queue
        self.expanded = 0  # tiles processed so far (replaying this many recreates the state)

    def advance(self, budget: int = 5000) -> bool:
        if self.done:
            return True
        dist, passable, queue = self.field, self.passable, self._queue
        w, h = passable.shape
        steps = self._steps
        while queue and budget > 0:
            budget -= 1
            self.expanded += 1
            x, y = queue.popleft()
            d = dist[x, y] + 1
            for dx, dy in steps:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and dist[nx, ny] < 0 and passable[nx, ny]:
                    if dx and dy and not (passable[x + dx, y] and passable[x, y + dy]):
                        continue
                    dist[nx, ny] = d
                    queue.append((nx, ny))
        self.done = not queue
        return self.done


def downhill(field: np.ndarray, x: int, y: int) -> tuple[int, int]:
    """The neighbour of (x, y) with the smallest non-negative field value (or (x, y))."""
    w, h = field.shape
    best, bd = (x, y), field[x, y]
    for dx, dy in _STRAIGHT + _DIAGONAL:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and 0 <= field[nx, ny] < bd:
            if dx and dy and (field[x + dx, y] < 0 or field[x, y + dy] < 0):
                continue
            best, bd = (nx, ny), field[nx, ny]
    return best


def neighbours_any(mask: np.ndarray) -> np.ndarray:
    """True where any of the 8 neighbours is True (the grid wraps at the edges)."""
    out = np.zeros_like(mask)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                out |= np.roll(np.roll(mask, dx, 0), dy, 1)
    return out


def majority_smooth(
    labels: np.ndarray, passes: int = 1, threshold: int = 5
) -> np.ndarray:
    """Replace each label with its 3x3 majority when at least `threshold` of 9 agree.

    Turns speckled per-tile classifications into natural-looking clusters.
    """
    labels = labels.copy()
    count = int(labels.max()) + 1
    for _ in range(passes):
        votes = np.zeros((count,) + labels.shape, np.int8)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                shifted = np.roll(np.roll(labels, dx, 0), dy, 1)
                for value in range(count):
                    votes[value] += shifted == value
        best = votes.argmax(axis=0).astype(labels.dtype)
        labels = np.where(votes.max(axis=0) >= threshold, best, labels).astype(
            labels.dtype
        )
    return labels


def disc(
    cx: float, cy: float, radius: float, shape: tuple[int, int]
) -> Iterator[tuple[int, int]]:
    """Tiles whose index lies within `radius` of (cx, cy), clipped to `shape`."""
    r = int(np.ceil(radius))
    for x in range(int(cx) - r, int(cx) + r + 1):
        for y in range(int(cy) - r, int(cy) + r + 1):
            if (
                0 <= x < shape[0]
                and 0 <= y < shape[1]
                and (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius
            ):
                yield x, y
