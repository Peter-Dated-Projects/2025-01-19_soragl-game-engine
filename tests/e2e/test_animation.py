import json

import pygame

from soragl.ecs import c_sprite
from soragl.system import animation


def _sprite(duration, frame_number):
    sprite = c_sprite.SpriteComponent(image=pygame.Surface((4, 4)))
    sprite._extra["duration"] = duration
    sprite._extra["frame_number"] = frame_number
    return sprite


def test_animation_advances_after_frame_duration_and_wraps_to_start(engine):
    register = animation.Animation.from_array(
        [_sprite(0.1, 0), _sprite(0.1, 1)]
    ).get_register()

    engine.delta_time = 0.05
    register.update()
    assert register.get_current_frame_number() == 0

    engine.delta_time = 0.2
    register.update()
    assert register.get_current_frame_number() == 1

    register.update()
    assert register.get_current_frame_number() == 0


def test_animation_json_loads_frames_from_a_spritesheet(engine, tmp_path):
    image = tmp_path / "walk.png"
    pygame.image.save(pygame.Surface((200, 100)), str(image))
    (tmp_path / "walk.json").write_text(
        json.dumps(
            {
                "meta": {"source": str(image)},
                "sprites": [
                    {"area": {"x": 0, "y": 0, "w": 100, "h": 100}, "extra": {}},
                    {"area": {"x": 100, "y": 0, "w": 100, "h": 100}, "extra": {}},
                ],
            }
        ),
        encoding="utf-8",
    )
    animation_json = tmp_path / "walk_animation.json"
    animation_json.write_text(
        json.dumps(
            {
                "meta": {"resources": [{"file": "walk.json", "type": "spritesheet"}]},
                "frames": [
                    {
                        "source": "walk.json",
                        "area": None,
                        "duration": [0.1, 0.3],
                        "frame_number": [0, 1],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = animation.Animation.from_json(str(animation_json))

    register = loaded.get_register()
    assert register.get_current_sprite_duration() == 0.1
    assert len(loaded._sprites) == 2
