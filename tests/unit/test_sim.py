import numpy as np
import pytest

from soragl.sim import FixedStepClock, Modifiers, PhaseCycle, grid, noise

# ------------------------------------------------------------------ #
# clock
# ------------------------------------------------------------------ #


def test_clock_runs_whole_steps_and_keeps_the_remainder():
    clock = FixedStepClock(step=0.1)
    calls = []
    assert clock.advance(0.25, calls.append) == 2
    assert calls == [0.1, 0.1]
    assert clock.alpha == pytest.approx(0.5)
    assert clock.advance(0.05, calls.append) == 1


def test_clock_speed_scales_and_zero_pauses():
    clock = FixedStepClock(step=0.1, speed=4.0)
    assert clock.advance(0.1, lambda dt: None) == 4
    clock.speed = 0
    assert clock.paused
    assert clock.advance(10.0, lambda dt: None) == 0


def test_clock_caps_steps_and_drops_the_backlog():
    clock = FixedStepClock(step=0.1, max_steps=5)
    assert clock.advance(100.0, lambda dt: None) == 5
    assert clock.advance(0.0, lambda dt: None) == 0


def test_clock_step_function_can_stop_early():
    clock = FixedStepClock(step=0.1)
    assert clock.advance(1.0, lambda dt: True) == 1


# ------------------------------------------------------------------ #
# noise
# ------------------------------------------------------------------ #


def test_noise_is_deterministic_per_seed_and_normalised():
    a = noise.fbm(np.random.default_rng(7), 32, 24, 8)
    b = noise.fbm(np.random.default_rng(7), 32, 24, 8)
    c = noise.fbm(np.random.default_rng(8), 32, 24, 8)
    assert a.shape == (32, 24)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert a.min() == pytest.approx(0.0) and a.max() == pytest.approx(1.0)


def test_value_noise_is_smooth():
    n = noise.value_noise(np.random.default_rng(1), 64, 64, 16)
    assert np.abs(np.diff(n, axis=0)).max() < 0.2


# ------------------------------------------------------------------ #
# grid
# ------------------------------------------------------------------ #


def test_distance_field_routes_around_walls():
    passable = np.ones((5, 5), bool)
    passable[2, 0:4] = False  # wall with a gap at y=4
    field = grid.distance_field(passable, [(0, 0)])
    assert field[2, 1] == -1
    assert field[4, 0] > 4  # must walk around through the gap
    x, y = 4, 0
    for _ in range(20):
        if field[x, y] == 0:
            break
        x, y = grid.downhill(field, x, y)
    assert (x, y) == (0, 0)


def test_distance_field_marks_unreachable_tiles():
    passable = np.ones((4, 4), bool)
    passable[1, :] = False
    field = grid.distance_field(passable, [(0, 0)], diagonal=False)
    assert (field[2:, :] == -1).all()


def test_majority_smooth_removes_speckle():
    labels = np.zeros((9, 9), np.uint8)
    labels[4, 4] = 1
    assert grid.majority_smooth(labels)[4, 4] == 0


def test_neighbours_any_and_disc():
    mask = np.zeros((5, 5), bool)
    mask[2, 2] = True
    ring = grid.neighbours_any(mask)
    assert ring[1, 1] and ring[3, 3] and not ring[2, 2]
    assert set(grid.disc(0, 0, 1.0, (5, 5))) == {(0, 0), (1, 0), (0, 1)}


# ------------------------------------------------------------------ #
# modifiers
# ------------------------------------------------------------------ #


def test_modifiers_sum_multipliers_and_additions():
    mods = Modifiers().apply([("dps", 0.25), ("dps", 0.25), ("radius_add", 3)])
    assert mods.m("dps") == pytest.approx(1.5)
    assert mods.m("unknown") == 1.0
    assert mods.a("radius") == 3
    assert Modifiers().apply([("speed", -5)]).m("speed") == pytest.approx(0.05)


# ------------------------------------------------------------------ #
# cycle
# ------------------------------------------------------------------ #


def test_cycle_wraps_and_blends_into_the_next_phase():
    cycle = PhaseCycle([{"v": 0.0}, {"v": 10.0}], length=10.0, blend=0.2)
    assert cycle.value("v") == 0.0
    assert cycle.advance(9.0) is False
    assert 0.0 < cycle.value("v") < 10.0
    assert cycle.advance(1.0) is True
    assert cycle.index == 1
    cycle.advance(10.0)
    assert cycle.index == 0 and cycle.cycle == 2
    assert cycle.time_until(1) == pytest.approx(10.0)


def test_incremental_distance_field_matches_one_shot():
    rng = np.random.default_rng(4)
    passable = rng.random((60, 40)) > 0.2
    sources = [(30, 20), (5, 5)]
    expected = grid.distance_field(passable, sources)
    inc = grid.IncrementalDistanceField(passable, sources)
    steps = 0
    while not inc.advance(budget=97):
        steps += 1
        # partial fields never claim a tile that the finished one disagrees with
        reached = inc.field >= 0
        assert (inc.field[reached] == expected[reached]).all()
    assert steps > 5
    assert np.array_equal(inc.field, expected)


def test_incremental_distance_field_without_sources_is_done():
    inc = grid.IncrementalDistanceField(np.ones((4, 4), bool), [])
    assert inc.done and inc.advance() and (inc.field == -1).all()
