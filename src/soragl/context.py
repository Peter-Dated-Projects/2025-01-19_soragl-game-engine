import logging
import time
import pygame
import numpy as np

import moderngl as mgl


from soragl.system import signal
from soragl.system import game_state

from soragl.graphics import buffer
from soragl.graphics import shader
from soragl.graphics import texture

from soragl.audio import engine as audio_engine

from soragl.physics import entity

from soragl.io import resource_manager
from soragl.io import input_handler

from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_LEQUAL,
    GL_SHADING_LANGUAGE_VERSION,
    GL_VERSION,
    glClear,
    glDepthFunc,
    glGetString,
)

from soragl import state
from soragl.config import EngineConfig
import soragl.graphics.constants as gfx_consts

logger = logging.getLogger(__name__)


# ======================================================================== #
# init
# ======================================================================== #


def init(config: EngineConfig | None = None):
    """Create the window, OpenGL context and engine objects described by `config`."""
    state.config = config if config is not None else EngineConfig()
    pygame.init()

    # ------------------------------------------------------------------------ #
    # opengl setup
    # ------------------------------------------------------------------------ #
    logger.info("Initializing OpenGL Context...")

    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
    )
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, 1)

    # ------------------------------------------------------------------------ #
    # pygame window
    # ------------------------------------------------------------------------ #

    logger.info("Initializing pygame window Context...")

    state.window_surface = pygame.display.set_mode(
        (state.config.window_width, state.config.window_height),
        state.config.window_flags,
        state.config.window_bit_depth,
    )
    state.gl_context = mgl.create_context()
    state.clock = pygame.time.Clock()
    state.framebuffer_surface = pygame.Surface(
        (state.config.framebuffer_width, state.config.framebuffer_height),
        state.config.framebuffer_flags,
        state.config.framebuffer_bit_depth,
    ).convert_alpha()
    # set pygame window specs
    pygame.display.set_caption(state.config.window_title)
    if state.config.window_icon:
        pygame.display.set_icon(pygame.image.load(state.config.window_icon))

    # create objects
    state.input_handler = input_handler.InputHandler()
    state.signal_handler = signal.SignalHandler()
    state.resource_manager = resource_manager.ResourceManager()
    state.texture_manager = texture.TextureManager(
        state.gl_context, state.resource_manager
    )
    state.audio = audio_engine.AudioEngine(
        resources=state.resource_manager,
        voices=state.config.audio_voices,
        frequency=state.config.audio_frequency,
        buffer=state.config.audio_buffer,
        enabled=state.config.audio_enabled,
    )

    state.game_state_manager = game_state.GameStateManager()
    # update ecs handler
    state.ecs_handler = state.game_state_manager.get_current_ecs()

    # ------------------------------------------------------------------------ #
    # post initialization script
    # ------------------------------------------------------------------------ #

    state.signal_handler.register_signal("SORA_ENTITY_DEATH", [entity.Entity])

    state.gl_framebuffer_vbo = buffer.GLBufferObject(
        np.hstack(
            [
                gfx_consts.Plane.get_plane_vert(),
                gfx_consts.Plane.get_plane_tex(),
            ]
        )
    )
    state.gl_framebuffer_shader = shader.ShaderProgram(
        vertex_shader=shader.Shader.builtin("default_post_vertex"),
        fragment_shader=shader.Shader.builtin("default_post_fragment"),
    )
    # Set depth visualization uniforms (near and far plane)
    state.gl_framebuffer_shader["u_near"] = 0.1
    state.gl_framebuffer_shader["u_far"] = 50.0

    state.gl_framebuffer_vao = buffer.VAOObject(
        state.gl_framebuffer_shader,
        [(state.gl_framebuffer_vbo(), "3f 2f", "in_position", "in_texcoords")],
    )
    state.gl_framebuffer_rendering_manifold = buffer.RenderingManifold(
        vao=state.gl_framebuffer_vao
    )
    state.gl_framebuffer = buffer.FramebufferObject(
        state.config.framebuffer_width,
        state.config.framebuffer_height,
        color_attachments=[
            buffer.FramebufferObject.create_texture_attachment(
                state.config.framebuffer_width, state.config.framebuffer_height, 4
            )
        ],
        depth_attachment=buffer.FramebufferObject.create_depth_attachment(
            state.config.framebuffer_width, state.config.framebuffer_height
        ),
    )

    # ------------------------------------------------------------------------ #


def run():
    # run game
    state.running = True

    # begin the game loop
    state.start_time = time.time()
    state.end_time = state.start_time
    state.run_time = 0

    # ------------------------------------------------------------------------ #
    # testing

    # get opengl data
    logger.info("OpenGL version: %s", glGetString(GL_VERSION).decode())
    logger.info("GLSL version: %s", glGetString(GL_SHADING_LANGUAGE_VERSION).decode())

    state.gl_context.enable(flags=mgl.DEPTH_TEST)
    glDepthFunc(GL_LEQUAL)
    # glEnable(GL_BLEND)
    # glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # ------------------------------------------------------------------------ #

    while state.running:
        # stop()
        # ------------------------------------------------------------------------ #
        # time
        # ------------------------------------------------------------------------ #
        logger.debug(
            "===================== START NEW LOOP ================================"
        )
        # calculate delta time
        state.start_time = time.time()
        state.delta_time = state.start_time - state.end_time
        state.end_time = state.start_time
        state.run_time += state.delta_time

        # ------------------------------------------------------------------------ #
        # events
        # ------------------------------------------------------------------------ #

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                state.running = False

            # window resize events
            if event.type == pygame.VIDEORESIZE:
                state.config.window_width = event.w
                state.config.window_height = event.h

        # ------------------------------------------------------------------------ #
        # reset + clearing
        # ------------------------------------------------------------------------ #

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        state.gl_framebuffer().clear(*state.config.background_color, depth=1.0)
        state.framebuffer_surface.fill(state.config.background_color)

        # ------------------------------------------------------------------------ #
        # updating + drawing
        # ------------------------------------------------------------------------ #

        state.input_handler.update()

        if state.input_handler.get_keyboard_pressed(pygame.K_e):
            # stage 1: render pass #1
            state.gl_framebuffer.use_framebuffer()

            # update game state
            state.game_state_manager.update()
            state.signal_handler.handle()

            # stage 2: render pass #2
            state.gl_context.screen.use()
            state.gl_framebuffer.get_color_attachments()[0].use(location=1)
            state.gl_framebuffer.get_depth_attachment().use(location=2)
            state.gl_framebuffer_rendering_manifold.handle()
        else:
            # render to screen directly
            state.gl_context.screen.use()

            state.game_state_manager.update()
            state.signal_handler.handle()

        state.audio.update()

        # update window
        pygame.display.flip()
        state.clock.tick(state.config.window_fps)

    # ------------------------------------------------------------------------ #
    # final cleaning
    # ------------------------------------------------------------------------ #
    logger.info("===================== STOPPING GAME ================================")

    # clear up all game states
    state.game_state_manager.__on_clean__()
    # clean up textures + shaders + buffers + vaos + framebuffers
    state.audio.shutdown()
    state.texture_manager.shutdown()
    state.resource_manager.clear()
    shader.ShaderProgram.__on_clean__()
    buffer.GLBufferObject.__on_clean__()
    buffer.VAOObject.__on_clean__()
    buffer.FramebufferObject.clean_all()

    pygame.quit()
    state.reset()

    logger.info("Game Stopped + Caches + Memory Cleaned")


def stop():
    # stop game
    state.running = False
