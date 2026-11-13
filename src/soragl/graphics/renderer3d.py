"""Forward renderer for 2.5D scenes: lit 3D meshes, flat sprites, particles, shadows.

Takes the moderngl context it should draw with, so it runs in the game window
(`state.gl_context`) or headless (`moderngl.create_standalone_context()`) for
recording. Passes: shadow map -> opaque meshes -> alpha-cut sprites -> blended
particles, all at a low internal resolution, then a sharp integer upscale to the
output size so pixel art stays crisp.
"""

import re
from importlib import resources

import moderngl as mgl
import numpy as np
from pyglm import glm

from soragl.graphics.camera import Camera3D
from soragl.graphics.scene3d import Scene, Sprite3D

_INCLUDE = re.compile(r"^#include (\w+)$", re.MULTILINE)


def _source(name: str) -> str:
    text = (resources.files("soragl") / "data" / "shaders" / f"{name}.glsl").read_text(
        encoding="utf-8"
    )
    return _INCLUDE.sub(lambda m: _source(m.group(1)), text)


def _program(ctx: mgl.Context, name: str, fragment: str | None = None) -> mgl.Program:
    return ctx.program(
        vertex_shader=_source(f"{name}_vertex"),
        fragment_shader=_source(fragment or f"{name}_fragment"),
    )


def _set(program: mgl.Program, **uniforms) -> None:
    """Write uniforms the program actually uses; the compiler drops unused ones."""
    for name, value in uniforms.items():
        if name in program:
            if isinstance(value, (glm.mat4, glm.vec3, glm.vec4)):
                program[name].write(value)
            else:
                program[name].value = value


def _gl_texture(texture) -> mgl.Texture:
    return getattr(texture, "gl", texture)


class Renderer:
    def __init__(
        self,
        ctx: mgl.Context,
        output_size: tuple[int, int] = (1440, 2560),
        pixel_scale: int = 4,
    ):
        """`pixel_scale` > 1 renders the scene that many times smaller, then scales up
        with sharp nearest sampling: the 8-bit look, and cheaper shading."""
        if output_size[0] % pixel_scale or output_size[1] % pixel_scale:
            raise ValueError(
                f"{output_size} is not divisible by pixel_scale {pixel_scale}"
            )
        self.ctx = ctx
        self.output_size = output_size
        self.pixel_scale = pixel_scale
        self.render_size = (
            output_size[0] // pixel_scale,
            output_size[1] // pixel_scale,
        )

        self._mesh_prog = _program(ctx, "mesh3d")
        self._sprite_prog = _program(ctx, "sprite3d")
        self._shadow_prog = _program(ctx, "shadow3d")
        self._particle_prog = _program(ctx, "particle3d")
        self._blit_prog = ctx.program(
            vertex_shader=_source("blit_vertex"),
            fragment_shader=_source("present_fragment"),
        )

        self._white = ctx.texture((1, 1), 4, b"\xff\xff\xff\xff")
        quad = np.array(
            [-0.5, 0, 0, 0.5, 0, 0, 0.5, 1, 0, -0.5, 0, 0, 0.5, 1, 0, -0.5, 1, 0], "f4"
        )
        self._quad = ctx.buffer(quad)
        self._sprite_vao = ctx.vertex_array(
            self._sprite_prog, [(self._quad, "3f", "in_corner")]
        )
        self._shadow_sprite_vao = ctx.vertex_array(
            self._shadow_prog, [(self._quad, "3f", "in_position")]
        )
        centered = np.array([-0.5, -0.5, 0.5, -0.5, 0.5, 0.5, -0.5, 0.5], "f4")
        self._corners = ctx.buffer(centered)
        self._instances = ctx.buffer(reserve=8 * 4 * 256, dynamic=True)
        self._indices = ctx.buffer(np.array([0, 1, 2, 0, 2, 3], "i4"))
        self._screen_quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], "f4"))
        self._particle_vao = ctx.vertex_array(
            self._particle_prog,
            [
                (self._corners, "2f", "in_corner"),
                (self._instances, "3f 1f 4f/i", "in_center", "in_size", "in_color"),
            ],
            index_buffer=self._indices,
        )
        self._blit_vao = ctx.vertex_array(
            self._blit_prog,
            [(self._screen_quad, "2f", "in_position")],
        )

        self._scene_color = ctx.texture(self.render_size, 4)
        self._scene_color.filter = (mgl.NEAREST, mgl.NEAREST)
        self._scene_depth = ctx.depth_renderbuffer(self.render_size)
        self._scene_fbo = ctx.framebuffer([self._scene_color], self._scene_depth)
        # released in this order by release(): users before what they use
        self._owned = [
            self._scene_fbo, self._scene_depth, self._scene_color,
            self._sprite_vao, self._shadow_sprite_vao, self._particle_vao, self._blit_vao,
            self._quad, self._corners, self._instances, self._indices, self._screen_quad,
            self._mesh_prog, self._sprite_prog, self._shadow_prog, self._particle_prog,
            self._blit_prog, self._white,
        ]  # fmt: skip
        self._shadow_size = 0
        self._mesh_vaos: dict[tuple, tuple[mgl.VertexArray, mgl.Buffer]] = {}

    # ------------------------------------------------------------------------ #
    # public
    # ------------------------------------------------------------------------ #

    def render(
        self, scene: Scene, camera: Camera3D, target: mgl.Framebuffer | None = None
    ):
        """Draw one frame. `read_pixels` reads it afterwards; pass a `target`
        framebuffer (e.g. `ctx.screen` in a game window) to also show it upscaled."""
        light_matrix = self._shadow_pass(scene, camera)

        self._scene_fbo.use()
        self._scene_fbo.clear(*scene.background, 1.0, depth=1.0)
        lighting = dict(
            m_proj=camera.projection,
            m_view=camera.view,
            m_light=light_matrix,
            u_light_dir=glm.normalize(glm.vec3(scene.light.direction)),
            u_light_color=glm.vec3(scene.light.color),
            u_ambient=glm.vec3(scene.light.ambient),
            u_toon_bands=scene.toon_bands,
            u_shadow_map=1,
        )
        self._shadow_tex.use(location=1)

        self.ctx.enable_only(mgl.DEPTH_TEST | mgl.CULL_FACE)
        _set(self._mesh_prog, u_texture=0, **lighting)
        for item in scene.meshes:
            _gl_texture(item.material.texture or self._white).use(location=0)
            _set(
                self._mesh_prog,
                m_model=item.model,
                u_color=item.material.color,
                u_unlit=item.material.unlit,
            )
            self._vao(self._mesh_prog, item.mesh).render()

        self.ctx.enable_only(mgl.DEPTH_TEST)
        _set(self._sprite_prog, u_texture=0, **lighting)
        for sprite in scene.sprites:
            right, up = self._sprite_axes(sprite, camera.forward)
            _gl_texture(sprite.texture).use(location=0)
            _set(
                self._sprite_prog,
                u_anchor=glm.vec3(sprite.position),
                u_right=right,
                u_up=up,
                u_uv_rect=_uv(sprite),
                u_color=sprite.color,
                u_alpha_cutoff=sprite.alpha_cutoff,
                u_unlit=sprite.unlit,
            )
            self._sprite_vao.render()

        self._draw_particles(scene, camera)
        if target is not None:
            self._present(target)
        self.ctx.enable_only(mgl.DEPTH_TEST)  # what the engine's 3D loop expects

    def read_pixels(self, native: bool = False) -> np.ndarray:
        """The last rendered frame, (height, width, 3) uint8, top row first.

        Valid whatever `target` was. `native=True` returns it at `render_size` (one
        pixel per art pixel), which is `pixel_scale`² less data to read back; give
        `FrameRecorder` `upscale=pixel_scale` to get the same output-size video.
        """
        w, h = self.render_size
        data = np.frombuffer(self._scene_fbo.read(components=3), np.uint8)
        frame = np.flipud(data.reshape(h, w, 3))
        if native or self.pixel_scale == 1:
            return frame
        # the present shader's sharp filter equals nearest at integer scales
        s = self.pixel_scale
        return frame.repeat(s, axis=0).repeat(s, axis=1)

    def release(self) -> None:
        """Free every GL object the renderer made. Textures passed in stay the caller's."""
        for vao, buffer in self._mesh_vaos.values():
            vao.release()
            buffer.release()
        self._mesh_vaos.clear()
        for obj in self._owned:
            obj.release()
        self._owned.clear()
        if self._shadow_size:
            self._shadow_fbo.release()
            self._shadow_tex.release()
            self._shadow_size = 0

    # ------------------------------------------------------------------------ #
    # passes
    # ------------------------------------------------------------------------ #

    def _shadow_pass(self, scene: Scene, camera: Camera3D) -> glm.mat4:
        light = scene.light
        if self._shadow_size != light.shadow_map_size:
            if self._shadow_size:
                self._shadow_fbo.release()
                self._shadow_tex.release()
            size = (light.shadow_map_size,) * 2
            self._shadow_tex = self.ctx.depth_texture(size)
            self._shadow_tex.compare_func = ""  # sampled as a plain float
            self._shadow_tex.filter = (mgl.NEAREST, mgl.NEAREST)
            self._shadow_tex.repeat_x = self._shadow_tex.repeat_y = False
            self._shadow_fbo = self.ctx.framebuffer(depth_attachment=self._shadow_tex)
            self._shadow_size = light.shadow_map_size

        if scene.shadow_center is not None:
            centre = glm.vec3(scene.shadow_center)
        elif camera.forward.y < -1e-3:  # where the view ray meets the ground (y = 0)
            centre = camera.position - camera.forward * (
                camera.position.y / camera.forward.y
            )
        else:
            centre = camera.position
        direction = glm.normalize(glm.vec3(light.direction))
        up = glm.vec3(0, 0, 1) if abs(direction.y) > 0.99 else glm.vec3(0, 1, 0)
        e = light.shadow_extent
        light_matrix = glm.ortho(-e, e, -e, e, 0.1, 4 * e) * glm.lookAt(
            centre - direction * 2 * e, centre, up
        )

        self._shadow_fbo.use()
        self._shadow_fbo.clear(depth=1.0)
        self.ctx.enable_only(mgl.DEPTH_TEST)
        self._white.use(location=0)  # meshes don't sample it, but GL wants it valid
        _set(self._shadow_prog, m_light=light_matrix, u_texture=0)
        _set(self._shadow_prog, u_sprite=False)
        for item in scene.meshes:
            if item.cast_shadow:
                _set(self._shadow_prog, m_model=item.model)
                self._vao(self._shadow_prog, item.mesh).render()
        _set(self._shadow_prog, u_sprite=True)
        for sprite in scene.sprites:
            if not sprite.cast_shadow:
                continue
            # face the light, so the shadow is the sprite's full silhouette
            right, up_axis = self._sprite_axes(sprite, direction)
            _gl_texture(sprite.texture).use(location=0)
            _set(
                self._shadow_prog,
                u_anchor=glm.vec3(sprite.position),
                u_right=right,
                u_up=up_axis,
                u_uv_rect=_uv(sprite),
                u_alpha_cutoff=sprite.alpha_cutoff,
            )
            self._shadow_sprite_vao.render()
        return light_matrix

    def _draw_particles(self, scene: Scene, camera: Camera3D) -> None:
        view = camera.view
        cam_right = glm.vec3(view[0][0], view[1][0], view[2][0])
        cam_up = glm.vec3(view[0][1], view[1][1], view[2][1])
        _set(
            self._particle_prog,
            m_proj=camera.projection,
            m_view=view,
            u_cam_right=cam_right,
            u_cam_up=cam_up,
        )
        self.ctx.enable_only(mgl.DEPTH_TEST | mgl.BLEND)
        self.ctx.depth_mask = False
        for emitter in scene.emitters:
            data = emitter.instance_data()
            if not len(data):
                continue
            if data.nbytes > self._instances.size:
                self._instances.orphan(data.nbytes * 2)
            self._instances.write(data.tobytes())
            self.ctx.blend_func = (
                (mgl.SRC_ALPHA, mgl.ONE) if emitter.additive else mgl.DEFAULT_BLENDING
            )
            _set(self._particle_prog, u_round=emitter.round)
            self._particle_vao.render(instances=len(data))
        self.ctx.depth_mask = True
        self.ctx.blend_func = mgl.DEFAULT_BLENDING

    def _present(self, target: mgl.Framebuffer) -> None:
        target.use()
        self.ctx.enable_only(mgl.NOTHING)
        w, h = self.render_size
        self._scene_color.use(location=0)
        _set(
            self._blit_prog,
            u_surface=0,
            u_surface_size=(float(w), float(h)),
            u_scale=(
                target.viewport[2] / w,
                target.viewport[3] / h,
            ),
        )
        self._blit_vao.render(mgl.TRIANGLE_STRIP)

    # ------------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------------ #

    def _vao(self, program: mgl.Program, mesh) -> mgl.VertexArray:
        # shortcut: keyed on identity and uploaded once; meshes are treated as immutable,
        # and a long-lived renderer with churning meshes should add eviction
        key = (id(program), id(mesh))
        cached = self._mesh_vaos.get(key)
        if cached is None:
            buffer = self.ctx.buffer(mesh.vertices.tobytes())
            if program is self._shadow_prog:
                layout = (buffer, "3f 20x", "in_position")
            else:
                layout = (buffer, "3f 2f 3f", "in_position", "in_uv", "in_normal")
            cached = self._mesh_vaos[key] = (
                self.ctx.vertex_array(program, [layout]),
                buffer,
            )
        return cached[0]

    @staticmethod
    def _sprite_axes(sprite: Sprite3D, facing: glm.vec3) -> tuple[glm.vec3, glm.vec3]:
        """Scaled (right, up) of the sprite's quad when it faces against `facing`."""
        width, height = sprite.size
        up = glm.vec3(0, 1, 0)
        if sprite.billboard == "none":
            yaw = glm.radians(sprite.yaw)
            right = glm.vec3(glm.cos(yaw), 0, -glm.sin(yaw))
        else:
            flat = glm.vec3(facing.x, 0, facing.z)
            if glm.length(flat) < 1e-6:
                flat = glm.vec3(0, 0, -1)
            right = glm.normalize(glm.cross(glm.normalize(flat), up))
            if sprite.billboard == "full":
                up = glm.normalize(glm.cross(right, glm.normalize(facing)))
        if sprite.flip_x:
            right = -right
        return right * width, up * height


def _uv(sprite: Sprite3D) -> glm.vec4:
    return glm.vec4(*sprite.uv)
