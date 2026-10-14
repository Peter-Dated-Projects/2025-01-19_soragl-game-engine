"""Runtime state shared across the engine.

Everything here is populated by `soragl.init()` and cleared by `reset()`.
Read it as `state.<name>` (never `from soragl.state import <name>`), so that
later assignments are visible to every module.
"""

from soragl.config import EngineConfig

# ======================================================================== #
# state
# ======================================================================== #

config: EngineConfig = EngineConfig()

running = False

# time
delta_time = 0
start_time = 0
end_time = 0
run_time = 0

# opengl / moderngl objects
gl_context = None
gl_framebuffer = None
gl_framebuffer_vao = None
gl_framebuffer_vbo = None
gl_framebuffer_shader = None
gl_framebuffer_rendering_manifold = None

# pygame objects
window_surface = None
framebuffer_surface = None
clock = None

# engine objects
ecs_handler = None
input_handler = None
signal_handler = None
resource_manager = None
texture_manager = None
audio = None
game_state_manager = None
world = None


def reset():
    """Restore every value to its import-time default."""
    global config, running, delta_time, start_time, end_time, run_time
    global gl_context, gl_framebuffer, gl_framebuffer_vao, gl_framebuffer_vbo
    global gl_framebuffer_shader, gl_framebuffer_rendering_manifold
    global window_surface, framebuffer_surface, clock
    global ecs_handler, input_handler, signal_handler, resource_manager
    global texture_manager, audio
    global game_state_manager, world

    config = EngineConfig()
    running = False
    delta_time = start_time = end_time = run_time = 0
    gl_context = gl_framebuffer = gl_framebuffer_vao = gl_framebuffer_vbo = None
    gl_framebuffer_shader = gl_framebuffer_rendering_manifold = None
    window_surface = framebuffer_surface = clock = None
    ecs_handler = input_handler = signal_handler = resource_manager = None
    texture_manager = audio = None
    game_state_manager = world = None
