"""Plain data describing a 2.5D frame: 3D meshes, flat sprites, particles and a light.

Nothing here touches OpenGL, so world simulation code can build a `Scene` from a
snapshot without a window. `soragl.graphics.renderer3d.Renderer` draws it.
"""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from pyglm import glm

from soragl.io.model import FLOATS_PER_VERTEX, ModelData

Vec3 = tuple[float, float, float]
Color = tuple[float, float, float, float]


# ============================================================================= #
# meshes
# ============================================================================= #


@dataclass(eq=False)
class Mesh:
    """Unindexed float32 vertices, (n, 8): position, uv, normal (the OBJ loader's format)."""

    vertices: np.ndarray

    @classmethod
    def from_model(cls, model: ModelData) -> "Mesh":
        return cls(np.ascontiguousarray(model.vertices, dtype="f4"))

    @classmethod
    def box(cls, size: Vec3 = (1, 1, 1), origin: Vec3 = (0, 0, 0)) -> "Mesh":
        """An axis-aligned box whose bottom face is centred on `origin`."""
        hx, hy, hz = size[0] / 2, size[1], size[2] / 2
        ox, oy, oz = origin
        faces = []
        # (normal, u axis, v axis) per face; the face sits at normal * half extent
        for normal, u_axis, v_axis in (
            ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
            ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
            ((0, 1, 0), (1, 0, 0), (0, 0, -1)),
            ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
            ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
            ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
        ):
            n, u, v = np.array(normal), np.array(u_axis), np.array(v_axis)
            half = np.array([hx, hy / 2, hz])
            centre = np.array([ox, oy + hy / 2, oz]) + n * half
            corners = []
            for cu, cv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = centre + (u * cu + v * cv) * half
                corners.append([*p, (cu + 1) / 2, (1 - cv) / 2, *n])
            a, b, c, d = corners
            faces += [a, b, c, a, c, d]
        return cls(np.array(faces, dtype="f4"))

    @classmethod
    def plane(
        cls, width: float, depth: float, origin: Vec3 = (0, 0, 0), uv_repeat: float = 1
    ) -> "Mesh":
        """A ground plane facing +y. `uv_repeat` tiles the texture that many times."""
        hx, hz = width / 2, depth / 2
        ox, oy, oz = origin
        r = uv_repeat
        a = [ox - hx, oy, oz + hz, 0, r, 0, 1, 0]
        b = [ox + hx, oy, oz + hz, r, r, 0, 1, 0]
        c = [ox + hx, oy, oz - hz, r, 0, 0, 1, 0]
        d = [ox - hx, oy, oz - hz, 0, 0, 0, 1, 0]
        return cls(np.array([a, b, c, a, c, d], dtype="f4"))

    def __post_init__(self):
        if self.vertices.ndim != 2 or self.vertices.shape[1] != FLOATS_PER_VERTEX:
            raise ValueError(f"Mesh vertices must be (n, 8), got {self.vertices.shape}")


@dataclass
class Material:
    color: Color = (1.0, 1.0, 1.0, 1.0)
    texture: object = None  # moderngl.Texture or soragl Texture; None = plain colour
    unlit: bool = False


@dataclass
class MeshInstance:
    mesh: Mesh
    material: Material = field(default_factory=Material)
    model: glm.mat4 = field(default_factory=lambda: glm.mat4(1.0))
    cast_shadow: bool = True


# ============================================================================= #
# sprites
# ============================================================================= #


@dataclass
class Sprite3D:
    """A flat textured quad standing in the 3D world, anchored at its feet.

    billboard "y" turns to face the camera around the vertical axis (Paper Mario),
    "full" faces the camera completely, "none" uses `yaw` (degrees) and stays put.
    `uv` is (u0, v0, u1, v1) with v0 the top row of the image.
    """

    texture: object
    position: Vec3
    size: tuple[float, float] = (1.0, 1.0)
    uv: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    billboard: Literal["y", "full", "none"] = "y"
    yaw: float = 0.0
    flip_x: bool = False
    color: Color = (1.0, 1.0, 1.0, 1.0)
    alpha_cutoff: float = 0.5
    cast_shadow: bool = True
    unlit: bool = False


def strip_uvs(columns: int, rows: int = 1, count: int | None = None) -> list[tuple]:
    """UV rects of a sprite sheet's frames, left to right then top to bottom."""
    frames = [
        (c / columns, r / rows, (c + 1) / columns, (r + 1) / rows)
        for r in range(rows)
        for c in range(columns)
    ]
    return frames[:count] if count is not None else frames


# ============================================================================= #
# particles
# ============================================================================= #


@dataclass
class ParticleEmitter:
    """CPU particles drawn as camera-facing quads. Seeded, so replays match exactly.

    Advance it with `update(dt)` from a fixed time step; `burst(n)` spawns at once,
    `rate` spawns continuously (particles per second).
    """

    position: Vec3 = (0.0, 0.0, 0.0)
    seed: int = 0
    rate: float = 0.0
    lifetime: tuple[float, float] = (0.5, 1.0)
    speed: tuple[float, float] = (1.0, 2.0)
    direction: Vec3 = (0.0, 1.0, 0.0)
    spread: float = 1.0  # 0 = straight along `direction`, 1 = any direction
    gravity: Vec3 = (0.0, -2.0, 0.0)
    drag: float = 0.0
    size: tuple[float, float] = (0.15, 0.0)  # at birth, at death
    color_start: Color = (1.0, 1.0, 1.0, 1.0)
    color_end: Color = (1.0, 1.0, 1.0, 0.0)
    additive: bool = True
    round: bool = False
    max_particles: int = 2000

    def __post_init__(self):
        self._rng = np.random.default_rng(self.seed)
        self._pos = np.zeros((0, 3), "f4")
        self._vel = np.zeros((0, 3), "f4")
        self._age = np.zeros(0, "f4")
        self._life = np.zeros(0, "f4")
        self._owed = 0.0

    @property
    def count(self) -> int:
        return len(self._age)

    def burst(self, n: int) -> None:
        n = min(n, self.max_particles - self.count)
        if n <= 0:
            return
        rng = self._rng
        random_dir = rng.normal(size=(n, 3))
        random_dir /= np.linalg.norm(random_dir, axis=1, keepdims=True) + 1e-9
        base = np.array(self.direction, "f4")
        base /= np.linalg.norm(base) + 1e-9
        dirs = base + random_dir * self.spread
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-9
        speeds = rng.uniform(*self.speed, size=(n, 1))
        self._pos = np.vstack([self._pos, np.tile(self.position, (n, 1))]).astype("f4")
        self._vel = np.vstack([self._vel, dirs * speeds]).astype("f4")
        self._age = np.concatenate([self._age, np.zeros(n, "f4")])
        self._life = np.concatenate([self._life, rng.uniform(*self.lifetime, size=n)])

    def update(self, dt: float) -> None:
        self._owed += self.rate * dt
        if self._owed >= 1:
            self.burst(int(self._owed))
            self._owed -= int(self._owed)
        self._vel += np.array(self.gravity, "f4") * dt
        self._vel *= max(0.0, 1.0 - self.drag * dt)
        self._pos += self._vel * dt
        self._age += dt
        alive = self._age < self._life
        self._pos, self._vel = self._pos[alive], self._vel[alive]
        self._age, self._life = self._age[alive], self._life[alive]

    def instance_data(self) -> np.ndarray:
        """(n, 8) float32 per particle: centre xyz, size, rgba."""
        t = (self._age / np.maximum(self._life, 1e-6))[:, None]
        size = self.size[0] + (self.size[1] - self.size[0]) * t
        start, end = np.array(self.color_start, "f4"), np.array(self.color_end, "f4")
        color = start + (end - start) * t
        return np.hstack([self._pos, size, color]).astype("f4")


# ============================================================================= #
# light and scene
# ============================================================================= #


@dataclass
class DirectionalLight:
    direction: Vec3 = (-0.5, -1.0, -0.4)  # the way the light travels
    color: Vec3 = (1.0, 0.95, 0.85)
    ambient: Vec3 = (0.35, 0.38, 0.5)
    shadow_extent: float = 20.0  # half-width, in world units, of the shadowed area
    shadow_map_size: int = 2048


@dataclass
class Scene:
    meshes: list[MeshInstance] = field(default_factory=list)
    sprites: list[Sprite3D] = field(default_factory=list)
    emitters: list[ParticleEmitter] = field(default_factory=list)
    light: DirectionalLight = field(default_factory=DirectionalLight)
    background: tuple[float, float, float] = (0.55, 0.75, 0.95)
    toon_bands: int = 3  # 0 = smooth lighting
    shadow_center: Vec3 | None = None  # None = the camera's target
