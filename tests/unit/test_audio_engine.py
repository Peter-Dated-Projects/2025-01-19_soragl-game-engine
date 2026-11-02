import pygame
import pytest

from soragl.audio import AudioEngine, Attenuation, DistanceModel


def test_playing_a_sound_gives_a_playing_voice(audio, make_wav):
    voice = audio.play(make_wav())

    assert voice.playing
    assert audio.active_voices == 1


def test_stopping_a_voice_frees_its_slot(audio, make_wav):
    voice = audio.play(make_wav())

    voice.stop()
    audio.update()

    assert not voice.playing
    assert audio.active_voices == 0


def test_bus_and_master_volume_scale_the_voice(audio, make_wav):
    voice = audio.play(make_wav(), bus="sfx", volume=0.8)

    audio.set_bus_volume("sfx", 0.5)
    audio.set_bus_volume("master", 0.5)
    audio.update()

    assert voice.gains == pytest.approx((0.2, 0.2))


def test_unknown_bus_is_an_error(audio, make_wav):
    with pytest.raises(KeyError, match="reverb"):
        audio.play(make_wav(), bus="reverb")


def test_positioned_voice_follows_the_listener_and_source(audio, make_wav):
    voice = audio.play(
        make_wav(), position=(10, 0), attenuation=Attenuation(DistanceModel.NONE)
    )
    audio.update()
    assert voice.gains[1] > voice.gains[0]

    voice.set_position((-10, 0))
    audio.update()
    assert voice.gains[0] > voice.gains[1]

    audio.listener.set_pose((-20, 0))
    audio.update()
    assert voice.gains[1] > voice.gains[0]


def test_unpositioned_voice_ignores_the_listener(audio, make_wav):
    voice = audio.play(make_wav(), volume=0.6)

    audio.listener.set_pose((500, 500))
    audio.update()

    assert voice.gains == pytest.approx((0.6, 0.6))


def test_higher_priority_sound_takes_over_the_quietest_voice_when_all_are_busy(
    audio, make_wav
):
    wav = make_wav()
    voices = [audio.play(wav, priority=p) for p in (5, 1, 3, 4)]

    newcomer = audio.play(wav, priority=2)

    assert newcomer is not None and newcomer.playing
    assert not voices[1].playing
    assert all(v.playing for i, v in enumerate(voices) if i != 1)


def test_low_priority_sound_is_dropped_when_all_voices_are_more_important(
    audio, make_wav
):
    wav = make_wav()
    for _ in range(4):
        audio.play(wav, priority=5)

    assert audio.play(wav, priority=1) is None


def test_sounds_are_loaded_once_and_unloading_releases_them(audio, make_wav):
    wav = make_wav()

    assert audio.load(wav) is audio.load(wav)
    assert audio._resources.ref_count(wav) == 1

    audio.unload(wav)

    assert audio._resources.ref_count(wav) == 0


def test_music_streams_on_the_music_bus(audio, make_wav):
    audio.set_bus_volume("music", 0.5)

    audio.play_music(make_wav("theme.wav"), volume=0.5)

    assert pygame.mixer.music.get_busy()
    assert pygame.mixer.music.get_volume() == pytest.approx(0.25, abs=0.01)

    audio.stop_music()
    assert not pygame.mixer.music.get_busy()


def test_engine_without_an_audio_device_stays_silent_instead_of_failing(
    make_wav, monkeypatch
):
    def no_device(*args, **kwargs):
        raise pygame.error("No audio device")

    monkeypatch.setattr(pygame.mixer, "init", no_device)
    silent = AudioEngine()

    assert not silent.available
    assert silent.play(make_wav()) is None
    silent.update()
    silent.play_music(make_wav())
    silent.shutdown()


def test_disabled_engine_never_touches_the_mixer(make_wav):
    pygame.mixer.quit()

    silent = AudioEngine(enabled=False)

    assert silent.play(make_wav()) is None
    assert pygame.mixer.get_init() is None


def test_shutdown_closes_the_mixer(audio):
    audio.shutdown()

    assert pygame.mixer.get_init() is None
