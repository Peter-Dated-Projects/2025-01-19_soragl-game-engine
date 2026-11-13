import logging
from typing import TYPE_CHECKING, Callable

import math
import pygame
import itertools

from soragl import state

from soragl.system import ecs

if TYPE_CHECKING:
    from soragl.system import world

logger = logging.getLogger(__name__)

# ======================================================================== #
# Interaction Field
# ======================================================================== #


class InteractionField:
    DETECTION_FUNCTIONS = {}
    RESOLUTION_FUNCTIONS = {}

    DETECTION_PREFIX = "_detect_"
    RESOLUTION_PREFIX = "_resolve_"

    @classmethod
    def get_detection_function(cls, shape_1: type, shape_2: type):
        target1 = min(shape_1, shape_2, key=lambda x: x.__name__)
        target2 = max(shape_1, shape_2, key=lambda x: x.__name__)
        key = cls.DETECTION_PREFIX + target1.__name__ + "_" + target2.__name__
        return cls.DETECTION_FUNCTIONS[key]

    @classmethod
    def get_resolution_function(cls, shape_1: type, shape_2: type):
        target1 = min(shape_1, shape_2, key=lambda x: x.__name__)
        target2 = max(shape_1, shape_2, key=lambda x: x.__name__)
        key = cls.RESOLUTION_PREFIX + target1.__name__ + "_" + target2.__name__
        return cls.RESOLUTION_FUNCTIONS[key]

    @classmethod
    def cache_detection_function(cls, shape_1: type, shape_2: type, function: Callable):
        # sort shape1 and shape2 by name
        target1 = min(shape_1, shape_2, key=lambda x: x.__name__)
        target2 = max(shape_1, shape_2, key=lambda x: x.__name__)
        key = cls.DETECTION_PREFIX + target1.__name__ + "_" + target2.__name__
        cls.DETECTION_FUNCTIONS[key] = function

    @classmethod
    def cache_resolution_function(
        cls, shape_1: type, shape_2: type, function: Callable
    ):
        target1 = min(shape_1, shape_2, key=lambda x: x.__name__)
        target2 = max(shape_1, shape_2, key=lambda x: x.__name__)
        key = cls.RESOLUTION_PREFIX + target1.__name__ + "_" + target2.__name__
        cls.RESOLUTION_FUNCTIONS[key] = function

    """
    Interaction Field

    A class that is found inside of a `World` class (2D or 3D).

    The goal?
    - resolve interactions between entities
    - collision detection
    - physics
    - etc.

    """

    def __init__(self, world: "world.World2D"):
        self._world = world

        logger.info("Physics only supports AABB objects for now")

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):

        # stage 0: move
        # TODO -- make this less hacky lol i guess
        interacts = self._world.get_components(InteractionFieldComponent)
        for interact in interacts.values():
            interact._entity._prev_position.xy = interact._entity._position.xy
            if interact._static:
                continue
            interact._entity._position += interact._velocity * state.delta_time

        # stage 1: detect
        collisions = []
        # TODO - optimize this later
        # TODO - use a quadtree or something or BVL

        for i1, i2 in itertools.combinations(interacts, 2):
            # TODO -- for SAT
            # iterate through each "line" of polygon
            # find normal
            # SAT along that "normal"
            # if collision -> find penetration
            # if no collision -> continue
            # all axis must "collide" for a collision to occur

            # print(interacts[i1]._shape, interacts[i2]._shape)
            manifold = self.detect_collision(interacts[i1], interacts[i2])
            if manifold is not None:
                collisions.append(manifold)

        # stage 2: resolve
        for manifold in collisions:
            self.resolve_collision(manifold)

    def detect_collision(
        self,
        interact1: "InteractionFieldComponent",
        interact2: "InteractionFieldComponent",
    ):
        if interact1._collision_mask & interact2._collision_mask == 0:
            return False

        # for some reason is reversed min?
        i2 = min(interact1, interact2, key=lambda x: x.__class__.__name__)
        i1 = interact2 if i2 == interact1 else interact1

        # print("detect", i1._shape, i2._shape)
        return self.get_detection_function(
            interact1._shape.__class__,
            interact2._shape.__class__,
        )(i1, i2)

    def resolve_collision(self, manifold: "CollisionManifold"):

        self.get_resolution_function(
            manifold._interact1._shape.__class__,
            manifold._interact2._shape.__class__,
        )(manifold)

    # ------------------------------------------------------------------------ #
    # helper functions
    # ------------------------------------------------------------------------ #


# ------------------------------------------------------------------------ #
# SAT
# ------------------------------------------------------------------------ #


def sat_test(
    self,
    interact1: "InteractionFieldComponent",
    interact2: "InteractionFieldComponent",
):
    # TODO - implement SAT
    pass


def single_axis_test(
    pts1: "list[pygame.Vector2]",
    pts2: "list[pygame.Vector2]",
    axis: pygame.Vector2,
) -> float:
    axis = axis.normalize()

    # print(f"{state.run_time:.5f} | AXIS: {axis}")

    # object 1
    dot = axis.dot(pts1[0])
    min1 = dot
    max1 = dot
    for i in range(1, len(pts1)):
        dot = axis.dot(pts1[i])
        # print(f"{state.run_time:.5f} | OBJ 1 | DOT: {dot}, POINT: {pts1[i]}")
        min1 = min(min1, dot)
        max1 = max(max1, dot)
    # print(f"{state.run_time:.5f} | OBJ 1 | LEFT: {min1}, RIGHT: {max1}")

    # object 2
    dot = axis.dot(pts2[0])
    min2 = dot
    max2 = dot
    for i in range(1, len(pts2)):
        dot = axis.dot(pts2[i])
        # print(f"{state.run_time:.5f} | OBJ 2 | DOT: {dot}, POINT: {pts2[i]}")
        min2 = min(min2, dot)
        max2 = max(max2, dot)

    # print(f"{state.run_time:.5f} | OBJ 2 | LEFT: {min2}, RIGHT: {max2}")

    # who is more left?
    # left = (min1, max1) if min1 < min2 else (min2, max2)
    # right = (min1, max1) if max1 > max2 else (min2, max2)

    # print("axis", axis)
    # print(min1 - max2, min2 - max1)

    # return penetration depth -- min makes more sense here
    return max([min1 - max2, min2 - max1], key=lambda x: abs(x))


# ======================================================================== #
# Collision Manifold
# ======================================================================== #


class CollisionManifold:
    def __init__(
        self,
        interact1: "InteractionFieldComponent",
        interact2: "InteractionFieldComponent",
        world: "world.World2D",
        extra: dict = {},
    ):
        self._interact1 = interact1
        self._interact2 = interact2

        self._restitution = min(
            self._interact1._restitution,
            self._interact2._restitution,
        )
        self._static_friction = math.sqrt(
            self._interact1._static_friction * self._interact2._static_friction
        )
        self._dynamic_friction = math.sqrt(
            self._interact1._dynamic_friction * self._interact2._dynamic_friction
        )

        self._extra = extra
        self._world = world

    # ------------------------------------------------------------------------ #
    def __str__(self):
        return f"{state.run_time:.5f} | Resolving: {self._interact1._shape.__class__.__name__} -> {self._interact2._shape.__class__.__name__}"


# ======================================================================== #
# Interaction Field Component
# ======================================================================== #


class InteractionFieldComponent(ecs.Component):
    def __init__(
        self,
        shape: "ShapeComponent" = None,
        collision_mask: int = 0b00000001,
        restitution: float = 0,
        static_friction: float = 0,
        dynamic_friction: float = 0,
        mass: float = 1,
        static: bool = False,
    ):
        super().__init__()
        self._shape = shape

        # information about interaction component
        self._collision_mask = collision_mask
        self._static = static

        self._restitution = restitution
        self._velocity = pygame.Vector2(0, 0)
        self._rotation = 0
        self._rotation_velocity = 0

        # physical properties
        self._static_friction = static_friction
        self._dynamic_friction = dynamic_friction
        self._mass = mass if not self._static else 1e9  # default mass = 1kg

    def __post_init__(self):
        if not self._shape:
            self._shape = self._entity.get_components(ShapeComponent)[0]

        # might still be None
        if self._shape is not None:
            self._shape._interact_component = self

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def set_collision_mask(self, mask: int):
        self._collision_mask = mask

    def toggle_collision_bit(self, bitnumber: int, value: bool):
        if value:
            self._collision_mask |= 1 << bitnumber
        else:
            self._collision_mask &= ~(1 << bitnumber)


# ======================================================================== #
# Shape Component
# ======================================================================== #


# all polygon based -- except for circles i guess lol
class ShapeComponent(ecs.Component):
    def __init__(self, relpoints: "list[pygame.Vector2]"):
        super().__init__()
        self._interact_component = None

        # sort points by rotation
        self._relpoints = sort_by_rotation(relpoints)
        self._relaxes = [
            (relpoints[i], relpoints[i - 1]) for i in range(len(relpoints))
        ]
        self._relnormals = [
            (relpoints[i] - relpoints[i - 1]).rotate(90).normalize()
            for i in range(len(relpoints))
        ]

    def __post_init__(self):
        pass

    # user needs to define shape of collider
    # and how to detect collisions with other "shapes"
    # and how to resolve collisions with other "shapes"

    # ------------------------------------------------------------------------ #
    # utils
    # ------------------------------------------------------------------------ #

    def get_abspoints(self):
        return [self._entity._position + point for point in self._relpoints]


def sort_by_rotation(points: "list[pygame.Vector2]") -> "list[pygame.Vector2]":
    # clockwise sorting
    return sorted(points, key=lambda p: math.atan2(p.y, p.x))
