import moderngl
import pygame
import pytest

from soragl.graphics.texture import TextureSettings


def _save(path, colors):
    surface = pygame.Surface((len(colors), 1))
    for x, color in enumerate(colors):
        surface.set_at((x, 0), color)
    pygame.image.save(surface, str(path))
    return str(path)


def _pixels(texture):
    data = texture.gl.read()
    return [tuple(data[i : i + 4]) for i in range(0, len(data), 4)]


RED, BLUE = (255, 0, 0), (0, 0, 255)


def test_loading_the_same_file_twice_shares_one_gpu_texture(textures, tmp_path):
    path = _save(tmp_path / "a.png", [RED, BLUE])

    first = textures.load(path)
    second = textures.load(path)

    assert first is second
    assert (
        textures.resources.ref_count(
            first.path, kind="texture", settings=first.settings
        )
        == 2
    )


def test_flipped_variant_is_a_separate_texture_with_mirrored_pixels(textures, tmp_path):
    path = _save(tmp_path / "a.png", [RED, BLUE])

    plain = textures.load(path)
    mirrored = textures.load(path, TextureSettings(flip_x=True, mipmaps=False))

    assert plain is not mirrored
    assert _pixels(plain)[0][:3] == RED
    assert _pixels(mirrored)[0][:3] == BLUE


def test_unreferenced_texture_is_freed_with_its_image_on_collect(textures, tmp_path):
    path = _save(tmp_path / "a.png", [RED])
    texture = textures.load(path)

    textures.release(texture)
    assert not texture.released
    assert textures.collect() == 2  # the texture and the image it came from

    assert texture.released
    assert not textures.resources.is_loaded(path, kind="image")


def test_sampling_settings_reach_the_gpu_texture(textures, tmp_path):
    path = _save(tmp_path / "a.png", [RED])

    crisp = textures.load(
        path, TextureSettings(filter="nearest", mipmaps=False, wrap="clamp")
    )

    assert crisp.gl.filter == (moderngl.NEAREST, moderngl.NEAREST)
    assert not crisp.gl.repeat_x and not crisp.gl.repeat_y


def test_surface_texture_is_updated_in_place(textures):
    surface = pygame.Surface((2, 1))
    surface.fill(RED)
    texture = textures.from_surface(surface, TextureSettings(mipmaps=False))

    surface.fill(BLUE)
    texture.update_from_surface(surface)

    assert _pixels(texture)[0][:3] == BLUE


def test_updating_with_a_differently_sized_surface_is_rejected(textures):
    texture = textures.from_surface(pygame.Surface((2, 2)))

    with pytest.raises(ValueError, match="texture is"):
        texture.update_from_surface(pygame.Surface((3, 3)))


def test_render_targets_and_surface_textures_are_freed_at_shutdown(textures):
    color = textures.create_color_target(8, 8)
    depth = textures.create_depth_target(8, 8)
    uploaded = textures.from_surface(pygame.Surface((2, 2)))
    assert textures.stats() == (3, 8 * 8 * 4 + 8 * 8 + 2 * 2 * 4)

    textures.shutdown()

    assert all(t.released for t in (color, depth, uploaded))
    assert textures.stats() == (0, 0)


def test_releasing_a_surface_texture_frees_it_immediately(textures):
    texture = textures.from_surface(pygame.Surface((2, 2)))

    textures.release(texture)

    assert texture.released
    assert textures.stats() == (0, 0)


def test_clearing_the_resource_manager_frees_file_textures(textures, tmp_path):
    texture = textures.load(_save(tmp_path / "a.png", [RED]))

    textures.resources.clear()

    assert texture.released


def test_invalid_sampling_settings_are_rejected():
    with pytest.raises(ValueError, match="filter"):
        TextureSettings(filter="cubic")
    with pytest.raises(ValueError, match="wrap"):
        TextureSettings(wrap="mirror")
