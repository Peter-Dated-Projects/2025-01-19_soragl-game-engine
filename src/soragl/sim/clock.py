"""A fixed-timestep clock, so simulation runs at the same rate whatever the frame rate."""

import time
from collections.abc import Callable


class FixedStepClock:
    """Turns variable frame time into a whole number of fixed simulation steps.

    `speed` scales game time against real time (0 pauses). `max_steps` caps the steps run
    for one frame, so a long stall does not freeze the game catching up; the backlog
    beyond the cap is dropped.
    """

    def __init__(self, step: float = 0.1, max_steps: int = 40, speed: float = 1.0):
        if step <= 0:
            raise ValueError("step must be positive")
        self.step = float(step)
        self.max_steps = int(max_steps)
        self.speed = float(speed)
        self.time = 0.0
        self.ticks = 0
        self._acc = 0.0
        # milliseconds per step: smoothed average and decaying peak
        self.step_ms = 0.0
        self.step_ms_max = 0.0

    @property
    def paused(self) -> bool:
        return self.speed <= 0

    @property
    def alpha(self) -> float:
        """How far between the last step and the next one we are, for interpolation."""
        return max(0.0, self._acc) / self.step

    def advance(self, real_dt: float, step_fn: Callable[[float], bool | None]) -> int:
        """Run `step_fn(step)` once per whole step owed. Returns how many ran.

        `step_fn` may return True to stop early (e.g. game over); the backlog is kept.
        """
        self._acc += max(0.0, real_dt) * max(0.0, self.speed)
        steps = 0
        # the epsilon keeps float drift (0.25 - 0.2 + 0.05 < 0.1) from losing a step
        while self._acc >= self.step - 1e-9 and steps < self.max_steps:
            start = time.perf_counter()
            self.time += self.step
            self.ticks += 1
            self._acc -= self.step
            steps += 1
            stop = step_fn(self.step)
            ms = (time.perf_counter() - start) * 1000.0
            self.step_ms = self.step_ms * 0.95 + ms * 0.05
            self.step_ms_max = max(self.step_ms_max * 0.999, ms)
            if stop:
                break
        if steps >= self.max_steps:
            self._acc = 0.0
        return steps

    def to_dict(self) -> dict:
        return {"time": self.time, "ticks": self.ticks, "step": self.step}

    def load(self, data: dict):
        self.time = float(data["time"])
        self.ticks = int(data["ticks"])
        self.step = float(data.get("step", self.step))
        self._acc = 0.0
