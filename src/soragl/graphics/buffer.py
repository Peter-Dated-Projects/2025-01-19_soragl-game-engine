import logging
from typing import TYPE_CHECKING

import numpy as np

from soragl import state

if TYPE_CHECKING:
    from soragl.graphics import shader, texture

logger = logging.getLogger(__name__)


# ============================================================================= #
# Framebuffer
# ============================================================================= #


class FramebufferObject:
    FRAMEBUFFER_OBJECT_COUNT = 0
    FRAMEBUFFER_OBJECTS = {}

    @classmethod
    def generate_fbo_uuid(cls):
        cls.FRAMEBUFFER_OBJECT_COUNT += 1
        return cls.FRAMEBUFFER_OBJECT_COUNT

    @classmethod
    def clean_all(cls):
        logger.debug("---- CLEANING FRAMEBUFFER OBJECTS ----")
        for fbo in cls.FRAMEBUFFER_OBJECTS.values():
            logger.debug("%s", fbo._uuid)
            fbo.clean(clean_func=True)

    @classmethod
    def create_texture_attachment(cls, width: int, height: int, channels: int = 4):
        return state.texture_manager.create_color_target(width, height, channels)

    @classmethod
    def create_depth_attachment(cls, width: int, height: int):
        return state.texture_manager.create_depth_target(width, height)

    @classmethod
    def cache(cls, fbo):
        cls.FRAMEBUFFER_OBJECTS[fbo._uuid] = fbo

    @classmethod
    def remove_from_cache(cls, fbo):
        cls.FRAMEBUFFER_OBJECTS.pop(fbo._uuid)

    # ------------------------------------------------------------------------ #

    def __init__(
        self,
        width: int,
        height: int,
        color_attachments: list = [],
        depth_attachment: "texture.Texture" = None,
    ):
        self._uuid = self.generate_fbo_uuid()
        self.cache(self)

        self._width = width
        self._height = height

        self._color_attachments = color_attachments
        self._depth_attachment = depth_attachment

        # create framebuffer
        self._fbo = state.gl_context.framebuffer(
            color_attachments=[x.gl for x in self._color_attachments],
            depth_attachment=(
                self._depth_attachment.gl if self._depth_attachment else None
            ),
        )

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def use_framebuffer(self):
        self._fbo.use()

    def clean(self, clean_func: bool = False):
        self._fbo.release()
        if not clean_func:
            self.remove_from_cache(self)

    def get_color_attachments(self):
        return self._color_attachments

    def get_depth_attachment(self):
        return self._depth_attachment

    def get_stencil_attachment(self):
        return self._stencil_attachment

    # ------------------------------------------------------------------------ #
    # special functions
    # ------------------------------------------------------------------------ #

    def __call__(self):
        return self._fbo


# ============================================================================= #
# Rendering Manifold
# ============================================================================= #


class RenderingManifold:
    def __init__(
        self,
        vao: "VAOObject" = None,
        tex_count: int = 10,
        tex_uniform_name: str = "u_textures",
    ):
        self._vao = vao
        self._textures = [[i + 1, None] for i in range(tex_count)]

        self._tex_count = tex_count
        self._tex_uniform_name = tex_uniform_name

        if not self._vao:
            return
        # set default variables into shader program
        if tex_uniform_name:
            self.write_uniform(
                self._tex_uniform_name,
                np.array([i + 1 for i in range(tex_count)], dtype="int32"),
            )

    def __on_clean__(self):
        if not self._vao:
            return

        # clean if vao exists
        self._vao.clean()
        self._textures.clear()

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def handle(self):
        if not self._vao:
            return
        # stage 1: should have written required variables to shader
        # stage 2: use texture
        for i, tex in self._textures:
            if not tex:
                continue
            tex.use(location=i)

        # stage 3: render
        self._vao().render()

    def write_uniform(self, uniform_name: str, data):
        self._vao._shader_program[uniform_name].write(data)

    def set_uniform(self, uniform_name: str, data):
        self._vao._shader_program[uniform_name] = data

    def set_texture(self, key: int, texture: "texture.Texture"):
        self._textures[key][1] = texture

    def remove_texture(self, key: int):
        self._textures.pop(key)

    # ------------------------------------------------------------------------ #
    # special functions
    # ------------------------------------------------------------------------ #

    def get_texture_uniform_var(self, index: int):
        return f"texture{index}"


# ============================================================================= #
# VAO
# ============================================================================= #


class VAOObject:
    CACHE = {}
    VAO_COUNT = 0

    @classmethod
    def generate_vao_uuid(cls):
        cls.VAO_COUNT += 1
        return cls.VAO_COUNT

    @classmethod
    def __on_clean__(cls):
        logger.debug("---- CLEANING VAOs ----")
        for vao in cls.CACHE.values():
            logger.debug("%s", vao._uuid)
            vao.clean(clean_func=True)

    @classmethod
    def cache(cls, vao):
        cls.CACHE[vao._uuid] = vao

    @classmethod
    def remove_from_cache(cls, vao):
        if vao._uuid not in cls.CACHE:
            return
        cls.CACHE.pop(vao._uuid)
        # assume user has handled cleaning etc

    # ------------------------------------------------------------------------ #

    def __init__(
        self, shader_program: "shader.ShaderProgram", attributes: "list[tuple]"
    ):
        self._uuid = self.generate_vao_uuid()
        self.cache(self)

        self._shader_program = shader_program
        self._attributes = attributes

        # create vao
        self._vao = state.gl_context.vertex_array(
            self._shader_program(), self._attributes
        )

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def clean(self, clean_func: bool = False):
        self._vao.release()
        if not clean_func:
            self.remove_from_cache(self)

    # ------------------------------------------------------------------------ #
    # special functions
    # ------------------------------------------------------------------------ #

    def __call__(self):
        return self._vao


# ============================================================================= #
# GL Buffer Object
# ============================================================================= #


class GLBufferObject:
    CACHE = {}
    GLBUFFER_OBJECT_COUNT = 0

    @classmethod
    def generate_glbuffer_uuid(cls):
        cls.GLBUFFER_OBJECT_COUNT += 1
        return cls.GLBUFFER_OBJECT_COUNT

    @classmethod
    def __on_clean__(cls):
        logger.debug("---- CLEANING GLBUFFERs ----")
        for glbuffer in cls.CACHE.values():
            logger.debug("%s", glbuffer._uuid)
            glbuffer.clean(clean_func=True)

    @classmethod
    def cache(cls, buffer):
        cls.CACHE[buffer._uuid] = buffer

    @classmethod
    def remove_from_cache(cls, buffer):
        cls.CACHE.pop(buffer._uuid)
        # assume user has handled cleaning etc

    # ------------------------------------------------------------------------ #

    def __init__(self, buffer_data: list, reserve_size: int = 0, dynamic: bool = False):
        self._uuid = self.generate_glbuffer_uuid()
        self.cache(self)

        self._buffer_data = buffer_data
        self._reserver_size = reserve_size
        self._dynamic = dynamic

        # create buffer
        self._glbuffer = state.gl_context.buffer(
            self._buffer_data, reserve=self._reserver_size, dynamic=self._dynamic
        )

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def clean(self, clean_func: bool = False):
        self._glbuffer.release()
        if not clean_func:
            self.remove_from_cache(self)

    # ------------------------------------------------------------------------ #
    # special functions
    # ------------------------------------------------------------------------ #

    def __call__(self):
        return self._glbuffer
