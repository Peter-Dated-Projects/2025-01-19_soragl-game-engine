from pathlib import Path

from soragl import state
from soragl.audio import engine
from soragl.audio.spatial import Attenuation
from soragl.system import ecs

# ======================================================================== #
# Audio Source
# ======================================================================== #


class AudioSourceComponent(ecs.Component):
    """A sound that follows its entity around the world."""

    def __init__(
        self,
        sound: str | Path,
        *,
        bus: str = "sfx",
        volume: float = 1.0,
        loop: bool = False,
        autoplay: bool = True,
        spatial: bool = True,
        priority: int = 0,
        attenuation: Attenuation | None = None,
    ):
        super().__init__()
        self._sound = sound
        self._play_options = {
            "bus": bus,
            "volume": volume,
            "loop": loop,
            "priority": priority,
            "attenuation": attenuation,
        }
        self._spatial = spatial
        self._autoplay = autoplay
        self.voice: engine.Voice | None = None

    def __post_init__(self):
        # runs again whenever another component joins the entity
        if self._autoplay:
            self._autoplay = False
            self.play()

    def play(self) -> None:
        """Start the sound from the beginning, replacing any earlier playback."""
        self.stop()
        position = self._entity._position if self._spatial else None
        self.voice = state.audio.play(
            self._sound, position=position, **self._play_options
        )

    def stop(self, fade_ms: int = 0) -> None:
        if self.voice is not None:
            self.voice.stop(fade_ms)
            self.voice = None

    @property
    def playing(self) -> bool:
        return self.voice is not None and self.voice.playing

    def update(self):
        if self.voice is not None and self._spatial:
            self.voice.set_position(self._entity._position)

    def debug(self):
        pass

    def __on_remove__(self):
        self.stop()

    def __on_clean__(self):
        self.stop()
