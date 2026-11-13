"""Stat modifiers: combine upgrade/research/buff effects into multipliers and additions."""

from collections import defaultdict
from collections.abc import Iterable


class Modifiers:
    """Effects are `(stat, amount)` pairs.

    A stat ending in `_add` is a flat addition read with `a("stat")`. Any other stat is a
    multiplier read with `m("stat")` that starts at 1.0 and sums its amounts, so two +25%
    effects give 1.5 rather than compounding to 1.5625. `unlocks` collects named flags.
    """

    def __init__(self, floor: float = 0.05):
        self.mult: dict[str, float] = defaultdict(float)
        self.add: dict[str, float] = defaultdict(float)
        self.unlocks: set[str] = set()
        self._floor = floor

    def apply(self, effects: Iterable[tuple[str, float]]) -> "Modifiers":
        for stat, amount in effects:
            if stat.endswith("_add"):
                self.add[stat[:-4]] += amount
            else:
                self.mult[stat] += amount
        return self

    def unlock(self, *flags: str) -> "Modifiers":
        self.unlocks.update(flags)
        return self

    def m(self, stat: str) -> float:
        """Multiplier for `stat`, never below the floor."""
        return max(self._floor, 1.0 + self.mult.get(stat, 0.0))

    def a(self, stat: str) -> float:
        """Flat addition for `stat`."""
        return self.add.get(stat, 0.0)
