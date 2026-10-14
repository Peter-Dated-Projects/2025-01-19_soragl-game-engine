import pygame

from soragl import state
from soragl.physics import entity, interact
from soragl.physics.ecs import c_aabb, c_sora_box2d
from soragl.system import ecs


class _Recorder(ecs.Component):
    def __init__(self, label, log):
        super().__init__()
        self.label = label
        self.log = log

    def update(self):
        self.log.append(self.label)

    def debug(self):
        pass


def _collider(world, position, shape, **kwargs):
    thing = world.add_entity(entity.Entity())
    thing._position = pygame.Vector2(position)
    thing.add_component(shape)
    thing.add_component(interact.InteractionFieldComponent(**kwargs))
    return thing


def test_components_with_higher_priority_update_first(engine):
    log = []
    thing = state.world.add_entity(entity.Entity())
    thing.add_component(_Recorder("low", log), priority=0)
    thing.add_component(_Recorder("high", log), priority=5)

    thing.handle_components()

    assert log == ["high", "low"]


def test_overlapping_boxes_are_detected_as_colliding(engine):
    field = state.world._interaction_field
    wall = _collider(
        state.world, (0, 0), c_aabb.AABBColliderComponent(20, 20), static=True
    )
    mover = _collider(
        state.world, (10, 0), c_sora_box2d.SoraBox2DColliderComponent(20, 20)
    )

    manifold = field.detect_collision(
        wall.get_component(interact.InteractionFieldComponent),
        mover.get_component(interact.InteractionFieldComponent),
    )

    assert manifold


def test_separated_boxes_are_not_colliding(engine):
    field = state.world._interaction_field
    wall = _collider(
        state.world, (0, 0), c_aabb.AABBColliderComponent(20, 20), static=True
    )
    mover = _collider(
        state.world, (500, 0), c_sora_box2d.SoraBox2DColliderComponent(20, 20)
    )

    manifold = field.detect_collision(
        wall.get_component(interact.InteractionFieldComponent),
        mover.get_component(interact.InteractionFieldComponent),
    )

    assert not manifold


def test_removed_entity_leaves_the_world_after_the_next_update(engine):
    thing = state.world.add_entity(entity.Entity())

    state.world.remove_entity(thing)
    assert thing._entity_id in state.world._entities

    state.world.update()

    assert thing._entity_id not in state.world._entities


def test_updating_a_world_without_physics_entities_does_not_crash(engine):
    state.world.update()
