import pygame

from soragl import constants
from soragl import state

from soragl.physics import interact
from soragl.physics.ecs import c_aabb
from soragl.physics.ecs import c_sora_box2d

# ------------------------------------------------------------------------ #
# detect aabb aabb
# ------------------------------------------------------------------------ #


def _detect_aabb_aabb(
    interact1: interact.InteractionFieldComponent,
    interact2: interact.InteractionFieldComponent,
):
    # check if the two colliders are intersecting
    shape1 = interact1._shape
    shape2 = interact2._shape

    shape1._rect.center = interact1._entity._position
    shape2._rect.center = interact2._entity._position

    if not shape1._rect.colliderect(shape2._rect):
        return None

    # return the manifold + calculate everything with custom information
    ab1 = shape1.get_abspoints()
    ab2 = shape2.get_abspoints()

    # print(f"{state.run_time:.5f} | AB1: {ab1}, ENTITY_POS: {interact1._entity._position}")
    # print(f"{state.run_time:.5f} | AB2: {ab2}, ENTITY_POS: {interact2._entity._position}")

    result = interact.CollisionManifold(
        interact1,
        interact2,
        state.world,
        extra={
            "penetration": pygame.Vector2(
                interact.single_axis_test(
                    ab1,
                    ab2,
                    constants.Constants.RIGHT,
                )
                / 2,
                interact.single_axis_test(
                    ab1,
                    ab2,
                    constants.Constants.UP,
                )
                / 2,
            )
        },
    )

    return result


interact.InteractionField.cache_detection_function(
    c_aabb.AABBColliderComponent, c_aabb.AABBColliderComponent, _detect_aabb_aabb
)

# ------------------------------------------------------------------------ #
# detect box2d aabb
# ------------------------------------------------------------------------ #


def _detect_aabb_sorabox2d(
    interact1: interact.InteractionFieldComponent,
    interact2: interact.InteractionFieldComponent,
):
    # check if the two colliders are intersecting
    shape1 = interact1._shape
    shape2 = interact2._shape

    shape1._rect.center = interact1._entity._position
    shape2._rect.center = interact2._entity._position

    if not shape1._rect.colliderect(shape2._rect):
        return None

    # return the manifold + calculate everything
    # we only care if they hit or not
    result = interact.CollisionManifold(interact1, interact2, state.world)

    return result


interact.InteractionField.cache_detection_function(
    c_aabb.AABBColliderComponent,
    c_sora_box2d.SoraBox2DColliderComponent,
    _detect_aabb_sorabox2d,
)

# ------------------------------------------------------------------------ #
# detect sorabox2d sorabox2d
# ------------------------------------------------------------------------ #


def _detect_sorabox2d_sorabox2d(
    interact1: interact.InteractionFieldComponent,
    interact2: interact.InteractionFieldComponent,
):
    # check if the two colliders are intersecting
    shape1 = interact1._shape
    shape2 = interact2._shape

    shape1._rect.center = interact1._entity._position
    shape2._rect.center = interact2._entity._position

    if not shape1._rect.colliderect(shape2._rect):
        return None

    # return the manifold + calculate everything
    # we only care if they hit or not
    result = interact.CollisionManifold(interact1, interact2, state.world)

    return result


interact.InteractionField.cache_detection_function(
    c_sora_box2d.SoraBox2DColliderComponent,
    c_sora_box2d.SoraBox2DColliderComponent,
    _detect_sorabox2d_sorabox2d,
)
