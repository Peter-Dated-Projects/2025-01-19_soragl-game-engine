"""Distance attenuation and stereo panning for positioned sounds.

This is pure math with no audio device involved. Positions can be 2D (x, y) or
3D (x, y, z); 2D points are treated as lying on the z = 0 plane.

Panning is constant-power stereo. It places a sound left or right of the
listener but cannot tell front from back, and it applies no HRTF filtering.
"""

import math
from dataclasses import dataclass, field
from enum import Enum

from pyglm import glm


class DistanceModel(Enum):
    NONE = "none"
    INVERSE = "inverse"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


@dataclass(frozen=True)
class Attenuation:
    """How a sound gets quieter with distance, in world units.

    Distances are clamped to [min_distance, max_distance] before the model is
    applied, so the sound is at full volume inside `min_distance`.
    """

    model: DistanceModel = DistanceModel.INVERSE
    min_distance: float = 1.0
    max_distance: float = 50.0
    rolloff: float = 1.0

    def __post_init__(self):
        if self.min_distance <= 0:
            raise ValueError("min_distance must be positive")
        if self.max_distance < self.min_distance:
            raise ValueError("max_distance must not be below min_distance")


def to_vec3(point) -> glm.vec3:
    """Accept a 2D or 3D point from pygame, pyglm or a plain sequence."""
    values = tuple(point)
    if len(values) == 2:
        return glm.vec3(values[0], values[1], 0.0)
    if len(values) == 3:
        return glm.vec3(*values)
    raise ValueError(f"Expected a 2D or 3D point, got {values}")


@dataclass
class Listener:
    """Where the player's ears are. The defaults suit a 2D game: +x is right."""

    position: glm.vec3 = field(default_factory=lambda: glm.vec3(0, 0, 0))
    forward: glm.vec3 = field(default_factory=lambda: glm.vec3(0, 0, -1))
    up: glm.vec3 = field(default_factory=lambda: glm.vec3(0, 1, 0))

    def set_pose(self, position, forward=None, up=None) -> None:
        self.position = to_vec3(position)
        if forward is not None:
            self.forward = to_vec3(forward)
        if up is not None:
            self.up = to_vec3(up)

    @property
    def right(self) -> glm.vec3:
        right = glm.cross(self.forward, self.up)
        if glm.length(right) < 1e-8:
            return glm.vec3(1, 0, 0)
        return glm.normalize(right)


@dataclass(frozen=True)
class StereoGain:
    left: float
    right: float


def attenuation_gain(distance: float, attenuation: Attenuation) -> float:
    """Loudness from 0 to 1 at `distance`."""
    model = attenuation.model
    if model is DistanceModel.NONE:
        return 1.0

    near, far = attenuation.min_distance, attenuation.max_distance
    clamped = min(max(distance, near), far)
    rolloff = attenuation.rolloff

    if model is DistanceModel.INVERSE:
        gain = near / (near + rolloff * (clamped - near))
    elif model is DistanceModel.LINEAR:
        span = far - near
        gain = 1.0 - rolloff * (clamped - near) / span if span else 1.0
    else:
        gain = (clamped / near) ** -rolloff
    return min(max(gain, 0.0), 1.0)


def spatialize(
    listener: Listener, source_position, attenuation: Attenuation
) -> StereoGain:
    """The left and right gain that place a sound at `source_position`."""
    offset = to_vec3(source_position) - listener.position
    distance = glm.length(offset)
    gain = attenuation_gain(distance, attenuation)

    pan = 0.0
    if distance > 1e-6:
        pan = glm.dot(offset / distance, listener.right)
        # a sound inside min_distance is practically on top of the listener
        pan *= min(1.0, distance / attenuation.min_distance)

    angle = (pan + 1.0) * math.pi / 4.0
    return StereoGain(gain * math.cos(angle), gain * math.sin(angle))
