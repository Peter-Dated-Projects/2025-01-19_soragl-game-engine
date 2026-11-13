"""Puts a CPU-drawn pygame surface on screen, for 2D games drawn with pygame."""

from typing import Literal

import moderngl as mgl
import numpy as np
import pygame

from soragl.graphics.shader import Shader
from soragl.graphics.texture import TextureManager, TextureSettings

Scaling = Literal["sharp", "nearest", "linear"]

_QUAD = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4")


def fit_viewport(
    surface_size: tuple[int, int],
    window_size: tuple[int, int],
    integer_scale: bool = False,
) -> tuple[int, int, int, int]:
    """The largest (x, y, w, h) with the surface's aspect ratio, centred in the window.

    `y` counts from the bottom, as OpenGL viewports do.
    """
    sw, sh = surface_size
    ww, wh = window_size
    scale = min(ww / sw, wh / sh)
    if integer_scale and scale >= 1:
        scale = int(scale)
    w, h = max(1, round(sw * scale)), max(1, round(sh * scale))
    return (ww - w) // 2, (wh - h) // 2, w, h


class SurfacePresenter:
    """Uploads a surface each frame and draws it letterboxed to fill the window."""

    def __init__(
        self,
        gl_context: mgl.Context,
        textures: TextureManager,
        surface_size: tuple[int, int],
        scaling: Scaling = "sharp",
        integer_scale: bool = False,
        border_color: tuple[int, int, int] = (0, 0, 0),
    ):
        if scaling not in ("sharp", "nearest", "linear"):
            raise ValueError(f"Unknown scaling mode: {scaling!r}")
        self._gl = gl_context
        self._textures = textures
        self._scaling = scaling
        self.integer_scale = integer_scale
        self.border_color = tuple(c / 255 for c in border_color)
        self.surface_size = tuple(surface_size)

        filter_ = "nearest" if scaling == "nearest" else "linear"
        self._texture = textures.from_surface(
            pygame.Surface(self.surface_size, pygame.SRCALPHA),
            TextureSettings(mipmaps=False, filter=filter_, wrap="clamp"),
        )
        self._program = gl_context.program(
            vertex_shader=Shader.builtin("present_vertex").get_shader_code(),
            fragment_shader=Shader.builtin("present_fragment").get_shader_code(),
        )
        self._program["u_surface"] = 0
        self._program["u_surface_size"] = self.surface_size
        self._vbo = gl_context.buffer(_QUAD.tobytes())
        self._vao = gl_context.vertex_array(
            self._program, [(self._vbo, "2f", "in_position")]
        )

    def viewport(self, window_size: tuple[int, int]) -> tuple[int, int, int, int]:
        return fit_viewport(self.surface_size, window_size, self.integer_scale)

    def window_to_surface(
        self, position: tuple[float, float], window_size: tuple[int, int]
    ) -> tuple[float, float] | None:
        """Map a window position (e.g. the mouse) to surface pixels, or None outside it."""
        x, y, w, h = self.viewport(window_size)
        top = window_size[1] - y - h
        sx = (position[0] - x) / w * self.surface_size[0]
        sy = (position[1] - top) / h * self.surface_size[1]
        if 0 <= sx < self.surface_size[0] and 0 <= sy < self.surface_size[1]:
            return sx, sy
        return None

    def present(
        self,
        surface: pygame.Surface,
        window_size: tuple[int, int],
        target: mgl.Framebuffer | None = None,
    ) -> None:
        """Draw `surface` into `target` (default: the window)."""
        if surface.get_size() != self.surface_size:
            raise ValueError(
                f"Surface is {surface.get_size()}, presenter expects {self.surface_size}"
            )
        self._texture.update_from_surface(surface)

        (target or self._gl.screen).use()
        self._gl.viewport = (0, 0, *window_size)
        self._gl.disable(mgl.DEPTH_TEST | mgl.BLEND)
        self._gl.clear(*self.border_color)

        viewport = self.viewport(window_size)
        self._gl.viewport = viewport
        if self._scaling == "sharp":
            self._program["u_scale"] = (
                viewport[2] / self.surface_size[0],
                viewport[3] / self.surface_size[1],
            )
        else:
            self._program["u_scale"] = (0.0, 0.0)
        self._texture.use(0)
        self._vao.render(mgl.TRIANGLE_STRIP)

    def release(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._program.release()
        self._textures.release(self._texture)
