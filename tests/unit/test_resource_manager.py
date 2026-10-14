import pygame
import pytest

from soragl.io import resource_manager


@pytest.fixture
def manager(window):
    return resource_manager.ResourceManager()


def _write_png(path):
    pygame.image.save(pygame.Surface((4, 4)), str(path))
    return str(path)


def test_loading_the_same_image_twice_returns_the_cached_surface(manager, tmp_path):
    path = _write_png(tmp_path / "hero.png")

    assert manager.load(path) is manager.load(path)


def test_uppercase_extension_is_accepted(manager, tmp_path):
    png = _write_png(tmp_path / "hero.png")
    upper = tmp_path / "HERO.PNG"
    (tmp_path / "hero.png").rename(upper)

    assert manager.load(str(upper)).get_size() == (4, 4)
    assert png != str(upper)


def test_missing_file_raises_file_not_found(manager, tmp_path):
    with pytest.raises(FileNotFoundError):
        manager.load(str(tmp_path / "ghost.png"))


def test_unsupported_extension_raises_value_error(manager, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hi")

    with pytest.raises(ValueError, match="Unsupported resource type"):
        manager.load(str(notes))
