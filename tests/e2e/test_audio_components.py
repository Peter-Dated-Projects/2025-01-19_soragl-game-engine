from soragl import state
from soragl.audio import Attenuation, DistanceModel
from soragl.audio.ecs import c_audio_listener, c_audio_source
from soragl.physics import entity

NO_FALLOFF = Attenuation(DistanceModel.NONE)


def _spawn(position, *components):
    thing = state.world.add_entity(entity.Entity())
    thing._position.xy = position
    for component in components:
        thing.add_component(component)
    return thing


def _frame():
    state.world.update()
    state.audio.update()


def test_sound_moves_between_ears_as_its_entity_crosses_the_listener(engine, make_wav):
    _spawn((0, 0), c_audio_listener.AudioListenerComponent())
    source = c_audio_source.AudioSourceComponent(
        make_wav(), loop=True, attenuation=NO_FALLOFF
    )
    thing = _spawn((100, 0), source)

    _frame()
    left, right = source.voice.gains
    assert right > left

    thing._position.x = -100
    _frame()
    left, right = source.voice.gains
    assert left > right


def test_listener_entity_orientation_is_used_when_it_has_one(engine, make_wav):
    from pyglm import glm

    camera = _spawn((0, 0), c_audio_listener.AudioListenerComponent())
    camera._forward = glm.vec3(1, 0, 0)
    camera._up = glm.vec3(0, 1, 0)
    source = c_audio_source.AudioSourceComponent(
        make_wav(), loop=True, attenuation=NO_FALLOFF
    )
    behind_the_camera_left = _spawn((0, 0), source)
    behind_the_camera_left._position = glm.vec3(0, 0, 10)

    _frame()

    left, right = source.voice.gains
    assert right > left


def test_sound_stops_when_its_entity_dies(engine, make_wav):
    source = c_audio_source.AudioSourceComponent(make_wav(), loop=True)
    thing = _spawn((0, 0), source)
    voice = source.voice
    assert voice.playing

    thing.alive = False
    state.signal_handler.handle()
    _frame()

    assert not voice.playing


def test_source_without_autoplay_waits_until_play_is_called(engine, make_wav):
    source = c_audio_source.AudioSourceComponent(make_wav(), autoplay=False)
    _spawn((0, 0), source)
    assert not source.playing

    source.play()

    assert source.playing


def test_non_spatial_source_ignores_where_the_entity_is(engine, make_wav):
    source = c_audio_source.AudioSourceComponent(
        make_wav(), loop=True, spatial=False, volume=0.7
    )
    _spawn((9000, 9000), source)

    _frame()

    assert source.voice.gains == (0.7, 0.7)
