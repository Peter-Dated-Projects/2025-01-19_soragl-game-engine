import math
import os
import struct
import wave

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import moderngl  # noqa: E402
import pygame  # noqa: E402
import pytest  # noqa: E402

from soragl import state  # noqa: E402
from soragl.audio import engine as audio_engine  # noqa: E402
from soragl.graphics import sprite_sheet, texture  # noqa: E402
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
    state.audio = audio_engine.AudioEngine(resources=state.resource_manager, voices=8)
    state.game_state_manager = game_state.GameStateManager()
    yield state
    state.audio.shutdown()
    state.reset()


@pytest.fixture
def gl_context():
    """A real OpenGL context without a window. Skips where the machine has none."""
    try:
        context = moderngl.create_standalone_context(require=330)
    except Exception as error:
        pytest.skip(f"no OpenGL context available: {error}")
    yield context
    context.release()


@pytest.fixture
def textures(window, gl_context):
    resources = resource_manager.ResourceManager()
    manager = texture.TextureManager(gl_context, resources)
    manager.resources = resources
    yield manager
    manager.shutdown()
    resources.clear()


@pytest.fixture
def audio():
    """An audio engine on SDL's dummy device, with four voices."""
    pygame.mixer.quit()
    engine_ = audio_engine.AudioEngine(voices=4)
    assert engine_.available
    yield engine_
    engine_.shutdown()


@pytest.fixture
def make_wav(tmp_path):
    """Write a short mono sine wave and return its path."""

    def make(name="beep.wav", seconds=1.0):
        path = tmp_path / name
        rate = 22050
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            frames = (
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(int(rate * seconds))
            )
            out.writeframes(b"".join(frames))
        return path

    return make
