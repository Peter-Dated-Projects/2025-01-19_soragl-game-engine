"""Cinematic camera moves for recorded scenes: keyframed pan, track, zoom, cuts, shake.

Everything is a pure function of time, so a shot renders the same every time.
"""

import math
from dataclasses import dataclass
from typing import Callable, Literal

from pyglm import glm

from soragl.graphics.camera import Camera3D

Vec3 = tuple[float, float, float]


@dataclass
class Key:
    """Where the camera looks at time `t`.

    `target` is a point, or a function of time (to track a moving character).
    `yaw` and `pitch` are degrees around and above the target, `height` is the
    orthographic view height in world units (smaller = zoomed in). `ease` shapes the
    move *into* this key: "smooth", "linear", or "cut" (jump when `t` is reached).
    """

    t: float
    target: Vec3 | Callable[[float], Vec3]
    yaw: float = 45.0
    pitch: float = 35.0
    height: float = 12.0
    ease: Literal["smooth", "linear", "cut"] = "smooth"


@dataclass
class Shake:
    start: float
    duration: float = 0.4
    amplitude: float = 0.3  # world units
    frequency: float = 25.0


class Shot:
    def __init__(
        self, keys: list[Key], shakes: list[Shake] | None = None, seed: int = 0
    ):
        if not keys:
            raise ValueError("A shot needs at least one key")
        self.keys = sorted(keys, key=lambda k: k.t)
        self.shakes = shakes or []
        self._phase = [(seed * 7.13 + i * 1.7) % (2 * math.pi) for i in range(4)]

    def pose(self, t: float) -> tuple[glm.vec3, float, float, float]:
        """(target, yaw, pitch, height) at time `t`."""
        keys = self.keys
        before = keys[0]
        after = keys[0]
        for key in keys:
            if key.t <= t:
                before = after = key
            else:
                after = key
                break
        if after is before or after.ease == "cut":
            k = 0.0
        else:
            k = (t - before.t) / (after.t - before.t)
            if after.ease == "smooth":
                k = k * k * (3 - 2 * k)
        a, b = _target(before, t), _target(after, t)
        return (
            glm.mix(a, b, k),
            before.yaw + (after.yaw - before.yaw) * k,
            before.pitch + (after.pitch - before.pitch) * k,
            before.height + (after.height - before.height) * k,
        )

    def shake_offset(self, t: float) -> glm.vec3:
        offset = glm.vec3(0)
        p = self._phase
        for s in self.shakes:
            age = t - s.start
            if 0 <= age < s.duration:
                strength = s.amplitude * (1 - age / s.duration) ** 2
                w = 2 * math.pi * s.frequency * age
                offset += strength * glm.vec3(
                    math.sin(w + p[0]) * 0.7 + math.sin(1.9 * w + p[1]) * 0.3,
                    math.sin(1.3 * w + p[2]) * 0.7 + math.sin(2.3 * w + p[3]) * 0.3,
                    0,
                )
        return offset

    def apply(self, camera: Camera3D, t: float, distance: float = 60.0) -> None:
        """Point an orthographic `camera` for time `t`."""
        target, yaw, pitch, height = self.pose(t)
        y, p = math.radians(yaw), math.radians(pitch)
        forward = glm.vec3(
            -math.sin(y) * math.cos(p), -math.sin(p), -math.cos(y) * math.cos(p)
        )
        right = glm.normalize(glm.cross(forward, glm.vec3(0, 1, 0)))
        up = glm.cross(right, forward)
        shake = self.shake_offset(t)
        target = target + right * shake.x + up * shake.y
        camera.ortho_height = height
        camera.forward = forward
        camera.position = target - forward * distance


def _target(key: Key, t: float) -> glm.vec3:
    return glm.vec3(key.target(t) if callable(key.target) else key.target)
