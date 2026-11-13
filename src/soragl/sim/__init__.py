"""Headless simulation helpers: fixed-step clock, seeded noise, grid fields, modifiers, cycles.

Nothing here imports OpenGL, pygame or the rest of the engine, so game rules built on it
run in tests and dedicated servers without a window.
"""

from soragl.sim import grid, noise
from soragl.sim.clock import FixedStepClock
from soragl.sim.cycle import PhaseCycle, smoothstep
from soragl.sim.modifiers import Modifiers

__all__ = [
    "FixedStepClock",
    "Modifiers",
    "PhaseCycle",
    "grid",
    "noise",
    "smoothstep",
]
