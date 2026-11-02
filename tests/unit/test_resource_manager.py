import json

import pygame
import pytest

from soragl.io import resource_manager
from soragl.io.resource_manager import ResourceKind


@pytest.fixture
def manager(window):
    return resource_manager.ResourceManager()


def _write_png(path, size=(4, 4)):
    pygame.image.save(pygame.Surface(size), str(path))
    return str(path)


def test_loading_the_same_image_twice_returns_the_cached_surface(manager, tmp_path):
    path = _write_png(tmp_path / "hero.png")

    assert manager.load(path) is manager.load(path)


def test_two_spellings_of_one_path_share_a_resource(manager, tmp_path):
    path = _write_png(tmp_path / "hero.png")
    (tmp_path / "sub").mkdir()

    assert manager.load(path) is manager.load(str(tmp_path / "sub" / ".." / "hero.png"))
    assert manager.stats().count == 1


def test_uppercase_extension_is_accepted(manager, tmp_path):
    _write_png(tmp_path / "hero.png")
    upper = tmp_path / "HERO.PNG"
    (tmp_path / "hero.png").rename(upper)

    assert manager.load(str(upper)).get_size() == (4, 4)


def test_missing_file_raises_file_not_found(manager, tmp_path):
    with pytest.raises(FileNotFoundError):
        manager.load(str(tmp_path / "ghost.png"))


def test_unsupported_extension_raises_value_error(manager, tmp_path):
    odd = tmp_path / "notes.xyz"
    odd.write_text("hi")

    with pytest.raises(ValueError, match="Unsupported resource type"):
        manager.load(str(odd))


def test_files_load_as_text_json_and_bytes(manager, tmp_path):
    (tmp_path / "level.json").write_text(json.dumps({"name": "cave"}))
    (tmp_path / "frag.glsl").write_text("void main() {}")
    (tmp_path / "save.dat").write_bytes(b"\x00\x01")

    assert manager.load(tmp_path / "level.json") == {"name": "cave"}
    assert manager.load(tmp_path / "frag.glsl") == "void main() {}"
    assert manager.load(tmp_path / "save.dat", kind="bytes") == b"\x00\x01"


def test_models_load_as_vertex_data(manager, tmp_path):
    (tmp_path / "tri.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")

    assert manager.load(tmp_path / "tri.obj").vertex_count == 3


def test_search_paths_resolve_relative_names(manager, tmp_path):
    (tmp_path / "art").mkdir()
    _write_png(tmp_path / "art" / "hero.png")
    manager.add_search_path(tmp_path / "art")

    assert manager.load("hero.png").get_size() == (4, 4)


def test_release_keeps_the_resource_until_collect_frees_it(manager, tmp_path):
    path = _write_png(tmp_path / "hero.png")
    manager.load(path)
    manager.load(path)

    manager.release(path)
    assert manager.collect() == 0
    manager.release(path)

    assert manager.is_loaded(path)
    assert manager.collect() == 1
    assert not manager.is_loaded(path)


def test_releasing_more_often_than_loading_raises(manager, tmp_path):
    path = _write_png(tmp_path / "hero.png")
    manager.load(path)
    manager.release(path)

    with pytest.raises(ValueError, match="released more often"):
        manager.release(path)


def test_scope_drops_what_it_loaded_but_keeps_what_others_hold(manager, tmp_path):
    shared = _write_png(tmp_path / "shared.png")
    level_only = _write_png(tmp_path / "level.png")
    manager.load(shared)

    with manager.scope() as scope:
        scope.load(shared)
        scope.load(level_only)

    assert manager.is_loaded(shared)
    assert not manager.is_loaded(level_only)


def test_custom_kinds_load_options_and_unload_when_collected(manager, tmp_path):
    freed = []
    (tmp_path / "pal.pal").write_text("ff0000")
    manager.register_kind(
        ResourceKind(
            "palette",
            (".pal",),
            lambda path, shade=1: (path.read_text(), shade),
            unload=freed.append,
        )
    )

    dark = manager.load(tmp_path / "pal.pal", shade=0.5)
    light = manager.load(tmp_path / "pal.pal", shade=1)
    manager.release(tmp_path / "pal.pal", shade=0.5)
    manager.collect()

    assert dark != light
    assert freed == [dark]


def test_stats_report_bytes_per_kind(manager, tmp_path):
    manager.load(_write_png(tmp_path / "a.png", (10, 10)))
    (tmp_path / "t.txt").write_text("hello")
    manager.load(tmp_path / "t.txt")

    stats = manager.stats()

    assert stats.count == 2
    assert stats.by_kind["image"] == (1, 10 * 10 * 4)
    assert stats.by_kind["text"] == (1, 5)


def test_clear_unloads_everything_even_when_still_referenced(manager, tmp_path):
    path = _write_png(tmp_path / "a.png")
    manager.load(path)

    manager.clear()

    assert manager.stats().count == 0


def test_clear_copes_with_resources_that_release_their_dependencies(manager, tmp_path):
    image = _write_png(tmp_path / "a.png")
    (tmp_path / "a.derived").write_text("x")

    def load_derived(path):
        manager.load(image)  # depends on the image staying loaded
        return object()

    manager.register_kind(
        ResourceKind(
            "derived",
            (".derived",),
            load_derived,
            unload=lambda value: manager.release(image),
        )
    )
    manager.load(tmp_path / "a.derived")

    manager.clear()

    assert manager.stats().count == 0
