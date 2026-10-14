"""The smallest SoraGL program: one entity drawing one sprite."""

from pathlib import Path

import soragl
from soragl import state
from soragl.config import EngineConfig
from soragl.ecs import c_sprite
from soragl.physics import entity

ARROW = Path(__file__).parents[1] / "archer_demo/assets/entities/arrow/32xarrow.png"

soragl.init(EngineConfig(window_title="Hello sprite", background_color=(255, 224, 169)))

arrow = state.world.add_entity(entity.Entity(name="arrow"))
arrow._position.xy = (100, 100)
arrow.add_component(c_sprite.SpriteComponent(filepath=str(ARROW)))
arrow.add_component(c_sprite.SpriteRendererComponent())

soragl.run()
