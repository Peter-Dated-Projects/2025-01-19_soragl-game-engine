"""A repeating cycle of phases (seasons, day/night) whose properties blend at the seams."""


def smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


class PhaseCycle:
    """`phases` is a list of dicts with the same keys; each phase lasts `length` seconds.

    `value(key)` returns the current phase's number, blended toward the next phase over
    the last `blend` fraction of the phase, so properties change smoothly. Lookups are
    cached for the current time, so calling `value` many times per step is cheap.
    """

    def __init__(self, phases: list[dict], length: float, blend: float = 0.2):
        if not phases:
            raise ValueError("a cycle needs at least one phase")
        if length <= 0:
            raise ValueError("length must be positive")
        self.phases = phases
        self.length = float(length)
        self.blend = float(blend)
        self.time = 0.0
        self._cache_time = -1.0
        self._cache: dict = {}

    # ------------------------------------------------------------------ #
    # clock
    # ------------------------------------------------------------------ #

    def advance(self, dt: float) -> bool:
        """Move time on by `dt`; True when a new phase started."""
        before = self.index
        self.time += dt
        return self.index != before

    @property
    def index(self) -> int:
        return int(self.time // self.length) % len(self.phases)

    @property
    def cycle(self) -> int:
        """1-based count of full cycles (years, days)."""
        return int(self.time // (self.length * len(self.phases))) + 1

    @property
    def progress(self) -> float:
        return (self.time % self.length) / self.length

    @property
    def time_left(self) -> float:
        return self.length - (self.time % self.length)

    @property
    def current(self) -> dict:
        return self.phases[self.index]

    @property
    def next(self) -> dict:
        return self.phases[(self.index + 1) % len(self.phases)]

    def time_until(self, index: int) -> float:
        """Seconds until phase `index` next starts (0 if it is the current phase)."""
        if index == self.index:
            return 0.0
        steps = (index - self.index) % len(self.phases)
        return self.time_left + (steps - 1) * self.length

    # ------------------------------------------------------------------ #
    # blended properties
    # ------------------------------------------------------------------ #

    def blend_weight(self) -> float:
        """0 for most of a phase, rising to 1 as the next phase begins."""
        if self.blend <= 0:
            return 0.0
        return self.cached(
            "_w", lambda: smoothstep((self.progress - (1.0 - self.blend)) / self.blend)
        )

    def value(self, key: str) -> float:
        def compute():
            w = self.blend_weight()
            return self.current[key] * (1.0 - w) + self.next[key] * w

        return self.cached(key, compute)

    def colour(self, key: str) -> tuple[float, ...]:
        """Blend a tuple-valued property (a colour, a vector) component-wise."""
        w = self.blend_weight()
        a, b = self.current[key], self.next[key]
        return tuple(a[i] * (1.0 - w) + b[i] * w for i in range(len(a)))

    def cached(self, key, compute):
        """Memoise `compute()` under `key` until time moves."""
        if self._cache_time != self.time:
            self._cache_time = self.time
            self._cache = {}
        if key not in self._cache:
            self._cache[key] = compute()
        return self._cache[key]
