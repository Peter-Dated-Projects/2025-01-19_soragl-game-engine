import moderngl
import pygame
import pytest

from soragl.graphics.presenter import SurfacePresenter


@pytest.fixture
def presenter(textures, gl_context):
    presenter = SurfacePresenter(gl_context, textures, (4, 2), scaling="nearest")
    yield presenter
    presenter.release()


def _render(gl_context, presenter, surface, window_size):
    target = gl_context.framebuffer(
        color_attachments=[gl_context.texture(window_size, 3)]
    )
    presenter.present(surface, window_size, target=target)
    data = target.read(components=3)
    image = pygame.image.frombytes(data, window_size, "RGB", True)
    target.release()
    return image


def test_surface_is_scaled_up_and_kept_upright(gl_context, presenter):
    surface = pygame.Surface((4, 2))
    surface.fill((0, 0, 255))
    surface.set_at((0, 0), (255, 0, 0))

    image = _render(gl_context, presenter, surface, (8, 4))

    assert image.get_at((0, 0))[:3] == (255, 0, 0)
    assert image.get_at((1, 1))[:3] == (255, 0, 0)
    assert image.get_at((2, 0))[:3] == (0, 0, 255)
    assert image.get_at((7, 3))[:3] == (0, 0, 255)


def test_extra_window_space_becomes_border(gl_context, presenter):
    presenter.border_color = (0.0, 1.0, 0.0)
    surface = pygame.Surface((4, 2))
    surface.fill((255, 255, 255))

    image = _render(gl_context, presenter, surface, (8, 8))

    assert image.get_at((4, 0))[:3] == (0, 255, 0)
    assert image.get_at((4, 4))[:3] == (255, 255, 255)
    assert image.get_at((4, 7))[:3] == (0, 255, 0)


def test_window_positions_map_back_to_surface_pixels(presenter):
    # an 8x8 window shows the 4x2 surface as an 8x4 band in the middle
    assert presenter.window_to_surface((0, 2), (8, 8)) == (0, 0)
    assert presenter.window_to_surface((7.9, 5.9), (8, 8)) == pytest.approx(
        (3.95, 1.95)
    )
    assert presenter.window_to_surface((4, 0), (8, 8)) is None


def test_surface_of_the_wrong_size_is_rejected(gl_context, presenter):
    with pytest.raises(ValueError, match="presenter expects"):
        _render(gl_context, presenter, pygame.Surface((5, 5)), (8, 8))


def test_unknown_scaling_mode_is_rejected(textures, gl_context):
    with pytest.raises(ValueError, match="scaling"):
        SurfacePresenter(gl_context, textures, (4, 2), scaling="bicubic")


def test_sharp_scaling_keeps_pixel_centres_exact(textures, gl_context):
    sharp = SurfacePresenter(gl_context, textures, (4, 2), scaling="sharp")
    surface = pygame.Surface((4, 2))
    surface.fill((0, 0, 0))
    surface.set_at((1, 0), (255, 255, 255))

    image = _render(gl_context, sharp, surface, (12, 6))
    sharp.release()

    assert image.get_at((4, 1))[:3] == (255, 255, 255)
    assert image.get_at((10, 1))[:3] == (0, 0, 0)
    assert isinstance(gl_context, moderngl.Context)
