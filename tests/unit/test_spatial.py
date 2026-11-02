import math

import pytest
from pyglm import glm

from soragl.audio import spatial
from soragl.audio.spatial import Attenuation, DistanceModel, Listener


def _gains(source, listener=None, attenuation=None):
    return spatial.spatialize(
        listener or Listener(), source, attenuation or Attenuation()
    )


def test_source_on_the_right_is_louder_in_the_right_ear():
    gains = _gains((10, 0))

    assert gains.right > gains.left


def test_source_on_the_left_is_louder_in_the_left_ear():
    gains = _gains((-10, 0))

    assert gains.left > gains.right


def test_source_straight_ahead_is_balanced():
    gains = _gains((0, 0, -10))

    assert gains.left == pytest.approx(gains.right)


def test_source_far_to_the_side_is_nearly_one_ear_only():
    gains = _gains((1000, 0), attenuation=Attenuation(DistanceModel.NONE))

    assert gains.left == pytest.approx(0.0, abs=1e-6)
    assert gains.right == pytest.approx(1.0)


def test_turning_the_listener_moves_the_source_to_the_other_ear():
    # facing +x, the listener's right hand points along +z
    facing_x = Listener(forward=glm.vec3(1, 0, 0))

    assert _gains((0, 0, 10), facing_x).right > _gains((0, 0, 10), facing_x).left
    assert _gains((0, 0, -10), facing_x).left > _gains((0, 0, -10), facing_x).right


def test_panning_keeps_total_power_constant():
    attenuation = Attenuation(DistanceModel.NONE)

    for x in (-10, -3, 0, 2, 9):
        gains = _gains((x, 5), attenuation=attenuation)
        assert gains.left**2 + gains.right**2 == pytest.approx(1.0)


def test_closer_sounds_are_louder_and_the_sound_is_full_inside_min_distance():
    near = spatial.attenuation_gain(2, Attenuation())
    far = spatial.attenuation_gain(20, Attenuation())

    assert near > far
    assert spatial.attenuation_gain(0.5, Attenuation()) == 1.0


def test_linear_model_fades_to_silence_at_max_distance():
    linear = Attenuation(DistanceModel.LINEAR, min_distance=1, max_distance=11)

    assert spatial.attenuation_gain(6, linear) == pytest.approx(0.5)
    assert spatial.attenuation_gain(11, linear) == pytest.approx(0.0)
    assert spatial.attenuation_gain(500, linear) == pytest.approx(0.0)


def test_exponential_model_halves_volume_when_distance_doubles_at_rolloff_one():
    exponential = Attenuation(DistanceModel.EXPONENTIAL, min_distance=1)

    assert spatial.attenuation_gain(2, exponential) == pytest.approx(0.5)


def test_sound_on_top_of_the_listener_plays_in_the_center():
    gains = _gains((0, 0))

    assert gains.left == pytest.approx(gains.right)
    assert gains.left == pytest.approx(math.cos(math.pi / 4))


def test_2d_points_work_with_pygame_vectors():
    import pygame

    gains = _gains(pygame.Vector2(5, 3))

    assert gains.right > gains.left


@pytest.mark.parametrize(
    "kwargs", [{"min_distance": 0}, {"min_distance": 5, "max_distance": 1}]
)
def test_invalid_attenuation_ranges_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Attenuation(**kwargs)
