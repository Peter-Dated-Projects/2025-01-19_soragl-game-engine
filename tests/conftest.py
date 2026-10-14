import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
import pytest  # noqa: E402

from soragl import state  # noqa: E402
from soragl.graphics import sprite_sheet  # noqa: E402
from soragl.io import resource_manager  # noqa: E402
from soragl.system import animation, game_state, signal  # noqa: E402


@pytest.fixture
def window():
    """A hidden pygame display, enough for loading and converting images."""
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


@pytest.fixture
def engine(window):
    """The engine objects `soragl.init()` creates, minus the OpenGL parts."""
    state.reset()
    sprite_sheet.SpriteSheet.SPRITESHEET_CACHE.clear()
    animation.Animation.ANIMATION_CACHE.clear()

    state.framebuffer_surface = pygame.Surface((64, 64))
    state.signal_handler = signal.SignalHandler()
    state.resource_manager = resource_manager.ResourceManager()
    state.game_state_manager = game_state.GameStateManager()
    yield state
    state.reset()
