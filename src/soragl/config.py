from dataclasses import dataclass, field
from typing import Literal

import pygame

# ======================================================================== #
# engine configuration
# ======================================================================== #


@dataclass
class EngineConfig:
    """Settings fixed before `soragl.init()` is called.

    `window_width` / `window_height` track the live window size once the
    engine is running, so they change on resize.
    """

    debug_mode: bool = False

    window_width: int = 1280
    window_height: int = 720
    window_title: str = "SoraGL"
    window_fps: int = 60
    window_bit_depth: int = 32
    window_flags: int = (
        pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.RESIZABLE | pygame.OPENGL
    )
    window_icon: str | None = None
    # None leaves the driver's default swap interval; 1 = vsync on, 0 = off
    window_vsync: int | None = None

    framebuffer_width: int = 1280
    framebuffer_height: int = 720
    framebuffer_flags: int = pygame.SRCALPHA
    framebuffer_bit_depth: int = 32

    # "3d": the game renders with OpenGL. "2d": the game draws `framebuffer_surface`
    # with pygame and the engine scales it to the window.
    render_mode: Literal["3d", "2d"] = "3d"
    present_scaling: Literal["sharp", "nearest", "linear"] = "sharp"
    present_integer_scale: bool = False

    # longest frame the simulation will see, so a stalled window does not
    # teleport everything on the next frame
    max_delta_time: float = 0.1

    background_color: tuple[int, int, int] = (255, 0, 0)

    audio_enabled: bool = True
    audio_voices: int = 32
    audio_frequency: int = 44100
    audio_buffer: int = 512

    default_chunk_pixel_width: int = 4096
    default_chunk_pixel_height: int = 4096

    default_physics_gravity: pygame.Vector2 = field(
        default_factory=lambda: pygame.Vector2(0, -9.8)
    )
    default_physics_pos_steps: int = 2
    default_physics_vel_steps: int = 4
