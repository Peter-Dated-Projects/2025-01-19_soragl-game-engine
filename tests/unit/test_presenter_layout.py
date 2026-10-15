import pytest

from soragl.graphics.presenter import fit_viewport


def test_matching_aspect_ratio_fills_the_window():
    assert fit_viewport((320, 180), (1280, 720)) == (0, 0, 1280, 720)


def test_wider_window_gets_bars_left_and_right():
    assert fit_viewport((320, 180), (1600, 720)) == (160, 0, 1280, 720)


def test_taller_window_gets_bars_top_and_bottom():
    assert fit_viewport((320, 180), (1280, 1000)) == (0, 140, 1280, 720)


def test_integer_scale_rounds_down_to_whole_pixels():
    # 900 / 320 = 2.8, so the scale drops to 2
    assert fit_viewport((320, 180), (900, 600), integer_scale=True) == (
        130,
        120,
        640,
        360,
    )


def test_integer_scale_still_shrinks_when_the_window_is_smaller_than_the_surface():
    x, y, w, h = fit_viewport((320, 180), (160, 90), integer_scale=True)

    assert (w, h) == (160, 90)


@pytest.mark.parametrize("window", [(1, 1), (7, 3000), (3000, 7)])
def test_viewport_is_never_empty(window):
    _, _, w, h = fit_viewport((320, 180), window)

    assert w >= 1 and h >= 1
