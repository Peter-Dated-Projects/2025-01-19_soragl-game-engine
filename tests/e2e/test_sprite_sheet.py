import json

import pygame

from soragl.graphics import sprite_sheet


def _make_sheet_image(directory):
    path = directory / "idle.png"
    pygame.image.save(pygame.Surface((300, 100)), str(path))
    return str(path)


def test_uniform_sheet_is_sliced_and_cached_as_json_next_to_the_image(engine, tmp_path):
    image = _make_sheet_image(tmp_path)
    meta = sprite_sheet.SpriteSheet.create_meta(
        source=image, uniform=True, uwidth=100, uheight=100
    )

    sheet = sprite_sheet.SpriteSheet.from_image(image, meta)

    assert len(sheet._sprites) == 3
    saved = json.loads((tmp_path / "idle.json").read_text(encoding="utf-8"))
    assert [s["area"]["x"] for s in saved["sprites"]] == [0, 100, 200]


def test_sheet_saved_in_a_directory_with_dots_is_found_again(engine, tmp_path):
    dotted = tmp_path / "my.game" / "art.v2"
    dotted.mkdir(parents=True)
    image = _make_sheet_image(dotted)
    meta = sprite_sheet.SpriteSheet.create_meta(
        source=image, uniform=True, uwidth=100, uheight=100
    )
    sprite_sheet.SpriteSheet.from_image(image, meta)
    sprite_sheet.SpriteSheet.SPRITESHEET_CACHE.clear()

    reloaded = sprite_sheet.SpriteSheet.from_image(image, meta)

    assert (dotted / "idle.json").exists()
    assert len(reloaded._sprites) == 3
