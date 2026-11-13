import logging
import pygame

from soragl import state

from soragl.system import ecs

logger = logging.getLogger(__name__)

# ======================================================================== #
# Entity
# ======================================================================== #


class Entity:
    ENTITY_ID_COUNTER = 0

    @staticmethod
    def generate_entity_id():
        Entity.ENTITY_ID_COUNTER += 1
        return Entity.ENTITY_ID_COUNTER

    # ------------------------------------------------------------------------ #
    # init
    # ------------------------------------------------------------------------ #

    def __init__(self, name: str = None, zlayer: int = 0):
        self._entity_id = Entity.generate_entity_id()
        self._layer = None
        self._world = None
        self._name = name if name else f"GameObject-{self._entity_id}"

        # component handler
        self._components: dict[int, ecs.Component] = {}

        # basic information
        self._prev_position = pygame.Vector2()
        self._prev_chunk_pos = (0, 0)
        self._prev_zlayer = 0
        self._position = pygame.Vector2()
        self._chunk_pos = (0, 0)
        self._zlayer = zlayer
        self._alive = True

        self._rect = pygame.FRect()

    def __post_init__(self):
        # override in subclasses
        pass

    # ------------------------------------------------------------------------ #
    # component logic
    # ------------------------------------------------------------------------ #

    def add_component(self, component, priority: int = 0):
        # add to ecs -- if component not in ecs
        component._priority = priority
        result = self._world._gamestate._ecs.add_component(component, self)
        for i in self._components.values():
            i.__post_init__()
        return result

    def remove_component(self, component, _reload=True):
        self._components.pop(component._uuid)
        if not _reload:
            return
        # run post init again to update all components
        for i in self._components.values():
            i.__post_init__()

    def get_component(self, component_class: type):
        """Get the first component of the specified type, or None if not found."""
        for component in self._components.values():
            if isinstance(component, component_class):
                return component
        return None

    def get_components(self, component_class: type):
        return [
            component
            for component in self._components.values()
            if isinstance(component, component_class)
        ]

    def get_component_by_id(self, component_id: int):
        return (
            self._components[component_id] if component_id in self._components else None
        )

    def iterate_components(self, component_class: type):
        for component in self._components.values():
            if isinstance(component, component_class):
                yield component

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        # print(f"{state.run_time:.5f} | UPDATING ENTITY", self, self._zlayer)
        pass

    def handle_components(self):
        for component in self._components.values():
            component.update()

    def debug(self):
        for component in self._components.values():
            component.debug()

    def clean(self):
        # kill all components
        for component in list(self._components.values()):
            self._world._gamestate._ecs.remove_component(component)
            # print(f"{state.run_time:.5f} | REMAINING COMPS:", self._components)

    # ------------------------------------------------------------------------ #
    # special properties
    # ------------------------------------------------------------------------ #

    def __eq__(self, other):
        return self._entity_id == other._entity_id

    def __hash__(self):
        return self._entity_id

    def __str__(self):
        return f"{self._name}, {self._entity_id}"

    @property
    def zlayer(self):
        return self._zlayer

    @zlayer.setter
    def zlayer(self, value):
        self._prev_zlayer = self._zlayer
        self._zlayer = value

    @property
    def alive(self):
        return self._alive

    @alive.setter
    def alive(self, value):
        if not self._alive:
            logger.debug("already dead")
            return
        self._alive = value
        if not value:
            state.signal_handler.emit_signal(f"SORA_ENTITY_DEATH-{self._zlayer}", self)
