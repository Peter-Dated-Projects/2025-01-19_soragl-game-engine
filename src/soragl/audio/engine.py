"""Mixing, voices, buses and music on top of pygame.mixer."""

import logging
from pathlib import Path

import pygame

from soragl.audio.spatial import Attenuation, Listener, spatialize, to_vec3
from soragl.io.resource_manager import ResourceManager

logger = logging.getLogger(__name__)

MASTER = "master"
DEFAULT_BUSES = ("sfx", "music", "ui")


class Voice:
    """One playing sound. Obtained from `AudioEngine.play`."""

    def __init__(
        self,
        engine: "AudioEngine",
        channel_index: int,
        bus: str,
        volume: float,
        priority: int,
        position,
        attenuation: Attenuation,
    ):
        self._engine = engine
        self._channel_index = channel_index
        self.bus = bus
        self.volume = volume
        self.priority = priority
        self.position = None if position is None else to_vec3(position)
        self.attenuation = attenuation
        self.gains = (0.0, 0.0)
        self._stopped = False

    @property
    def positional(self) -> bool:
        return self.position is not None

    @property
    def channel(self) -> pygame.mixer.Channel:
        return pygame.mixer.Channel(self._channel_index)

    @property
    def playing(self) -> bool:
        return not self._stopped and self.channel.get_busy()

    def set_position(self, position) -> None:
        self.position = to_vec3(position)

    def stop(self, fade_ms: int = 0) -> None:
        if self._stopped:
            return
        self._stopped = True
        if fade_ms > 0:
            self.channel.fadeout(fade_ms)
        else:
            self.channel.stop()

    def apply(self) -> None:
        """Recompute and set this voice's channel volume."""
        level = self.volume * self._engine.bus_volume(self.bus)
        if self.positional:
            stereo = spatialize(self._engine.listener, self.position, self.attenuation)
            self.gains = (stereo.left * level, stereo.right * level)
        else:
            self.gains = (level, level)
        self.channel.set_volume(*(min(g, 1.0) for g in self.gains))


class AudioEngine:
    """Plays sounds and music. Does nothing, quietly, when there is no audio device."""

    def __init__(
        self,
        resources: ResourceManager | None = None,
        voices: int = 32,
        frequency: int = 44100,
        buffer: int = 512,
        enabled: bool = True,
    ):
        self._resources = resources or ResourceManager()
        self._loaded: dict[Path, pygame.mixer.Sound] = {}
        self._voices: dict[int, Voice] = {}
        self._buses = {MASTER: 1.0, **{name: 1.0 for name in DEFAULT_BUSES}}
        self._music_volume = 1.0
        self.listener = Listener()
        self.available = False
        self._voice_count = 0

        if not enabled:
            return
        try:
            pygame.mixer.init(frequency=frequency, size=-16, channels=2, buffer=buffer)
            pygame.mixer.set_num_channels(voices)
        except pygame.error as error:
            logger.warning("Audio disabled: %s", error)
            return
        self.available = True
        self._voice_count = voices

    # ------------------------------------------------------------------------ #
    # volume
    # ------------------------------------------------------------------------ #

    def bus_volume(self, bus: str) -> float:
        """The effective volume of a bus: its own volume times master."""
        if bus not in self._buses:
            raise KeyError(f"Unknown audio bus: {bus!r}")
        return self._buses[bus] * (1.0 if bus == MASTER else self._buses[MASTER])

    def set_bus_volume(self, bus: str, volume: float) -> None:
        """Set a bus volume from 0 to 1. Unknown names create a new bus."""
        self._buses[bus] = min(max(volume, 0.0), 1.0)
        if self.available:
            self._apply_music_volume()

    # ------------------------------------------------------------------------ #
    # sounds
    # ------------------------------------------------------------------------ #

    def load(self, path: str | Path) -> pygame.mixer.Sound:
        """Load a sound once and keep it until `unload` or `shutdown`."""
        resolved = self._resources.resolve(path)
        if resolved not in self._loaded:
            self._loaded[resolved] = self._resources.load(resolved, kind="audio")
        return self._loaded[resolved]

    def unload(self, path: str | Path) -> None:
        resolved = self._resources.resolve(path)
        if self._loaded.pop(resolved, None) is not None:
            self._resources.release(resolved, kind="audio")

    def play(
        self,
        sound: str | Path | pygame.mixer.Sound,
        *,
        bus: str = "sfx",
        volume: float = 1.0,
        loop: bool = False,
        priority: int = 0,
        fade_ms: int = 0,
        position=None,
        attenuation: Attenuation | None = None,
    ) -> Voice | None:
        """Start a sound. Pass `position` (2D or 3D) to place it in the world.

        Returns None when audio is unavailable, or when every voice is busy with
        something of higher priority.
        """
        if not self.available:
            return None
        if bus not in self._buses:
            raise KeyError(f"Unknown audio bus: {bus!r}")
        if not isinstance(sound, pygame.mixer.Sound):
            sound = self.load(sound)

        index = self._claim_channel(priority)
        if index is None:
            return None

        voice = Voice(
            self, index, bus, volume, priority, position, attenuation or Attenuation()
        )
        self._voices[index] = voice
        voice.channel.play(sound, loops=-1 if loop else 0, fade_ms=fade_ms)
        # Channel.play resets the channel to full volume, so set gains afterwards
        voice.apply()
        return voice

    def stop_all(self, fade_ms: int = 0) -> None:
        for voice in list(self._voices.values()):
            voice.stop(fade_ms)

    @property
    def active_voices(self) -> int:
        return sum(1 for voice in self._voices.values() if voice.playing)

    def _claim_channel(self, priority: int) -> int | None:
        for index in range(self._voice_count):
            voice = self._voices.get(index)
            if voice is None or not voice.playing:
                return index

        quietest = min(self._voices.values(), key=lambda v: v.priority)
        if quietest.priority > priority:
            return None
        quietest.stop()
        return quietest._channel_index

    # ------------------------------------------------------------------------ #
    # music
    # ------------------------------------------------------------------------ #

    def play_music(
        self,
        path: str | Path,
        *,
        loop: bool = True,
        volume: float = 1.0,
        fade_ms: int = 0,
    ) -> None:
        """Stream a track on the "music" bus, replacing whatever is playing."""
        if not self.available:
            return
        pygame.mixer.music.load(str(self._resources.resolve(path)))
        self._music_volume = volume
        self._apply_music_volume()
        pygame.mixer.music.play(loops=-1 if loop else 0, fade_ms=fade_ms)

    def stop_music(self, fade_ms: int = 0) -> None:
        if not self.available:
            return
        if fade_ms > 0:
            pygame.mixer.music.fadeout(fade_ms)
        else:
            pygame.mixer.music.stop()

    def pause_music(self) -> None:
        if self.available:
            pygame.mixer.music.pause()

    def resume_music(self) -> None:
        if self.available:
            pygame.mixer.music.unpause()

    def _apply_music_volume(self) -> None:
        pygame.mixer.music.set_volume(self._music_volume * self.bus_volume("music"))

    # ------------------------------------------------------------------------ #
    # frame + shutdown
    # ------------------------------------------------------------------------ #

    def update(self) -> None:
        """Call once per frame, after positions have been updated."""
        if not self.available:
            return
        for index, voice in list(self._voices.items()):
            if not voice.playing:
                del self._voices[index]
            else:
                voice.apply()

    def shutdown(self) -> None:
        for path in list(self._loaded):
            self.unload(path)
        if self.available:
            self.stop_all()
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        self._voices.clear()
        self.available = False
