"""GPU textures and the manager that owns them.

Textures made from image files go through the `ResourceManager`, so they are
cached, reference counted and freed with `collect()` like any other resource.
Textures made from surfaces or as render targets are owned by the
`TextureManager` and freed when released or at shutdown.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import moderngl as mgl
import pygame

from soragl.io.resource_manager import ResourceKind, ResourceManager

logger = logging.getLogger(__name__)

_MIN_FILTERS = {
    (True, "linear"): mgl.LINEAR_MIPMAP_LINEAR,
    (True, "nearest"): mgl.NEAREST_MIPMAP_NEAREST,
    (False, "linear"): mgl.LINEAR,
    (False, "nearest"): mgl.NEAREST,
}
_MAG_FILTERS = {"linear": mgl.LINEAR, "nearest": mgl.NEAREST}


# ============================================================================= #
# Settings
# ============================================================================= #


@dataclass(frozen=True)
class TextureSettings:
    """How a texture is uploaded and sampled. Part of a file texture's cache key."""

    mipmaps: bool = True
    filter: Literal["linear", "nearest"] = "linear"
    wrap: Literal["repeat", "clamp"] = "repeat"
    anisotropy: float = 1.0
    flip_x: bool = False
    flip_y: bool = False

    def __post_init__(self):
        if self.filter not in _MAG_FILTERS:
            raise ValueError(f"Unknown texture filter: {self.filter!r}")
        if self.wrap not in ("repeat", "clamp"):
            raise ValueError(f"Unknown texture wrap mode: {self.wrap!r}")


# ============================================================================= #
# Texture
# ============================================================================= #


class Texture:
    def __init__(
        self,
        gl_texture: mgl.Texture,
        width: int,
        height: int,
        components: int,
        settings: TextureSettings | None = None,
        path: str | Path | None = None,
    ):
        self.gl = gl_texture
        self.width = width
        self.height = height
        self.components = components
        self.settings = settings or TextureSettings()
        self.path = path
        self.released = False

    @property
    def nbytes(self) -> int:
        return self.width * self.height * self.components

    def use(self, location: int = 0):
        self.gl.use(location=location)

    def update_from_surface(self, surface: pygame.Surface):
        """Overwrite the pixels in place, so per-frame updates do not allocate."""
        if self.released:
            raise RuntimeError("Cannot update a released texture")
        if surface.get_size() != (self.width, self.height):
            raise ValueError(
                f"Surface is {surface.get_size()}, texture is "
                f"{(self.width, self.height)}"
            )
        self.gl.write(_surface_bytes(surface, self.settings))

    def release(self):
        """Free the GPU memory. Safe to call twice."""
        if not self.released:
            self.gl.release()
            self.released = True

    def __call__(self) -> mgl.Texture:
        return self.gl


def _surface_bytes(surface: pygame.Surface, settings: TextureSettings) -> bytes:
    flipped = pygame.transform.flip(surface, settings.flip_x, settings.flip_y)
    return pygame.image.tobytes(flipped, "RGBA", False)


def _apply_sampling(gl_texture: mgl.Texture, settings: TextureSettings):
    gl_texture.filter = (
        _MIN_FILTERS[(settings.mipmaps, settings.filter)],
        _MAG_FILTERS[settings.filter],
    )
    gl_texture.repeat_x = gl_texture.repeat_y = settings.wrap == "repeat"
    gl_texture.anisotropy = settings.anisotropy
    if settings.mipmaps:
        gl_texture.build_mipmaps()


# ============================================================================= #
# Manager
# ============================================================================= #


class TextureManager:
    def __init__(self, gl_context: mgl.Context, resources: ResourceManager):
        self._gl = gl_context
        self._resources = resources
        self._owned: set[Texture] = set()
        resources.register_kind(
            ResourceKind(
                "texture",
                (),
                self._load_file,
                unload=self._unload_file,
                size_of=lambda texture: texture.nbytes,
            )
        )

    # ------------------------------------------------------------------------ #
    # file textures
    # ------------------------------------------------------------------------ #

    def load(
        self, path: str | Path, settings: TextureSettings | None = None
    ) -> Texture:
        """Return the texture for an image file and add a reference to it.

        The same file with different settings (e.g. flipped) is a different texture.
        """
        return self._resources.load(
            path, kind="texture", settings=settings or TextureSettings()
        )

    def release(self, texture: Texture) -> None:
        """Give up one reference. Free file textures later with `collect()`."""
        if texture.path is None:
            self._owned.discard(texture)
            texture.release()
        else:
            self._resources.release(
                texture.path, kind="texture", settings=texture.settings
            )

    def collect(self) -> int:
        """Free file textures nobody references. Returns how many were freed."""
        return self._resources.collect()

    def _load_file(self, path: Path, settings: TextureSettings) -> Texture:
        surface = self._resources.load(path, kind="image")
        try:
            return self._upload(surface, settings, path=path)
        except Exception:
            self._resources.release(path, kind="image")
            raise

    def _unload_file(self, texture: Texture) -> None:
        texture.release()
        self._resources.release(texture.path, kind="image")

    # ------------------------------------------------------------------------ #
    # textures owned by the manager
    # ------------------------------------------------------------------------ #

    def from_surface(
        self, surface: pygame.Surface, settings: TextureSettings | None = None
    ) -> Texture:
        """Upload a surface. Release it with `release()` or let `shutdown()` do it."""
        return self._own(self._upload(surface, settings or TextureSettings()))

    def create_color_target(
        self, width: int, height: int, components: int = 4
    ) -> Texture:
        """An empty texture, usually a framebuffer color attachment."""
        if not 1 <= components <= 4:
            raise ValueError(f"Invalid channel count: {components}")
        gl_texture = self._gl.texture((width, height), components)
        return self._own(Texture(gl_texture, width, height, components))

    def create_depth_target(self, width: int, height: int) -> Texture:
        """An empty depth texture, usually a framebuffer depth attachment."""
        gl_texture = self._gl.depth_texture((width, height))
        return self._own(Texture(gl_texture, width, height, 1))

    def shutdown(self) -> None:
        """Free every texture the manager owns.

        File textures are freed by `ResourceManager.clear()`.
        """
        for texture in self._owned:
            texture.release()
        self._owned.clear()

    def stats(self) -> tuple[int, int]:
        """(count, bytes) of the textures owned by the manager."""
        return len(self._owned), sum(t.nbytes for t in self._owned)

    # ------------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------------ #

    def _own(self, texture: Texture) -> Texture:
        self._owned.add(texture)
        return texture

    def _upload(
        self,
        surface: pygame.Surface,
        settings: TextureSettings,
        path: Path | None = None,
    ) -> Texture:
        width, height = surface.get_size()
        gl_texture = self._gl.texture(
            (width, height), 4, data=_surface_bytes(surface, settings)
        )
        _apply_sampling(gl_texture, settings)
        return Texture(gl_texture, width, height, 4, settings, path)
