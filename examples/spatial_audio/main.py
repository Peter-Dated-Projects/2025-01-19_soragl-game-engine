"""Put on headphones: a beeping sound circles the listener in 2D.

Close the window to quit.
"""

import math
import tempfile
import wave
from pathlib import Path

import numpy as np

import soragl
from soragl import state
from soragl.audio import Attenuation, DistanceModel
from soragl.audio.ecs import c_audio_listener, c_audio_source
from soragl.config import EngineConfig
from soragl.ecs import c_task
from soragl.physics import entity
from soragl.system import log

ORBIT_SECONDS = 6.0


def write_beep(path: Path, rate: int = 22050) -> None:
    """A 440 Hz tone that pulses four times a second, so panning is easy to hear."""
    t = np.arange(rate) / rate
    pulse = (np.sin(2 * math.pi * 4 * t) > 0).astype(np.float64)
    samples = (np.sin(2 * math.pi * 440 * t) * pulse * 12000).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())


log.configure()

soragl.init(
    EngineConfig(
        window_title="Spatial audio: listen", window_width=480, window_height=240
    )
)

beep = Path(tempfile.mkdtemp()) / "beep.wav"
write_beep(beep)

listener = state.world.add_entity(entity.Entity(name="listener"))
listener.add_component(c_audio_listener.AudioListenerComponent())

emitter = state.world.add_entity(entity.Entity(name="emitter"))
emitter.add_component(
    c_audio_source.AudioSourceComponent(
        beep,
        loop=True,
        attenuation=Attenuation(
            DistanceModel.INVERSE, min_distance=50, max_distance=800
        ),
    )
)

radius = 300.0


def orbit():
    angle = 2 * math.pi * state.run_time / ORBIT_SECONDS
    emitter._position.xy = (math.cos(angle) * radius, math.sin(angle) * radius)


emitter.add_component(c_task.TaskComponent("orbit", orbit))

soragl.run()
