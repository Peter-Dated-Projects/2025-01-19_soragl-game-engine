import logging
import pygame

from Box2D import b2

from soragl import constants
from soragl import state

from soragl.ecs import c_task

from soragl.graphics import camera

from soragl.physics import entity
from soragl.physics import interact

logger = logging.getLogger(__name__)

# ======================================================================== #
# World
# ======================================================================== #


class World2D(entity.Entity):
    def __init__(
        self,
        name: str,
        gravity: tuple = state.config.default_physics_gravity.xy,
        _physics_pos_steps: int = state.config.default_physics_pos_steps,
        _physics_vel_steps: int = state.config.default_physics_vel_steps,
    ):
        super().__init__()
        self._name = name

        # management information
        self._layers = {}
        self._layers_order = []
        self._delta_layers = []
        self._physics_world = b2.world(gravity=gravity, doSleep=True)

        # rendering information
        self._render_chunk_cache = set()
        self._camera = camera.Camera2D(render_distance=4)
        self._physics_pos_steps = _physics_pos_steps
        self._physics_vel_steps = _physics_vel_steps

        # entity management - entities are just "container" objects
        self._entities = {}
        self._delta_entities = []

        # gamestate + interaction field parents
        self._interaction_field = interact.InteractionField(self)
        self._gamestate = None

    def __post_init__(self):
        # default task for the aspect handler
        self._entity_chunk_change_task = c_task.TaskComponent(
            f"_{constants.ENGINE_NAME}_entity_chunk_change_task",
            self._entity_chunk_change_task,
        )
        state.ecs_handler.add_component(self._entity_chunk_change_task, self)

    def __on_clean__(self):
        pass

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):

        # TODO - check if camera moved chunks
        self._render_chunk_cache = set(self._camera.generate_visible_chunks())

        # update all layers
        for layer_index in self._layers_order:
            self._layers[layer_index].update()

        # physics
        self._interaction_field.update()
        self._physics_world.Step(
            state.delta_time, self._physics_vel_steps, self._physics_pos_steps
        )
        self._physics_world.ClearForces()

        # ------------------------------------------------ #
        # finish up by updating layers
        for layer in self._delta_layers:
            self._layers.pop(layer)
        self._delta_layers.clear()

        # finish up by updating entities
        for deleted in self._delta_entities:
            self._entities.pop(deleted._entity_id)
        self._delta_entities.clear()

    def _entity_chunk_change_task(self):
        for ent in self._entities.values():
            # calculate new chunk
            ent._chunk_pos = (
                int(ent._position.x // state.config.default_chunk_pixel_width),
                int(ent._position.y // state.config.default_chunk_pixel_height),
            )

            # check if ent moved chunks
            if ent._chunk_pos != ent._prev_chunk_pos:
                # remove ent from old chunk
                self.get_chunk(ent._prev_chunk_pos, ent._prev_zlayer).remove_not_clean(
                    ent
                )
                # add ent to new chunk
                self.get_chunk(ent._chunk_pos, ent._zlayer).add_entity(ent)
                # update previous chunk position
                ent._prev_chunk_pos = ent._chunk_pos
                ent._prev_zlayer = ent._zlayer

                logger.debug("%s %s", "ENTITY MOVED CHUNKS", ent)

    # ------------------------------------------------------------------------ #
    # layer logic
    # ------------------------------------------------------------------------ #

    def add_layer(self, layer: "Layer"):
        self._layers[layer._zlevel] = layer
        self._layers_order.append(layer._zlevel)
        layer._world = self
        layer.__post_init__()
        # sort layers
        self._layers_order.sort()

    def remove_layer(self, zlevel: int):
        self._delta_layers.append(zlevel)

    def get_layer(self, zlevel: int):
        if zlevel not in self._layers:
            self.add_layer(Layer(zlevel))
        return self._layers[zlevel]

    # ------------------------------------------------------------------------ #
    # chunk logic
    # ------------------------------------------------------------------------ #

    def add_chunk(self, chunk: "Chunk", zlayer: int):
        self.get_layer(zlayer).add_chunk(chunk)

    def remove_chunk(self, chunk: "Chunk", zlayer: int):
        self.get_layer(zlayer).remove_chunk(chunk)

    def get_chunk(self, chunk_position: tuple, zlayer: int):
        return self.get_layer(zlayer).get_chunk(chunk_position)

    # ------------------------------------------------------------------------ #
    # entity logic
    # ------------------------------------------------------------------------ #

    def add_entity(self, entity: "entity.Entity"):
        self._entities[hash(entity)] = entity
        entity._world = self
        entity._layer = self.get_layer(entity._zlayer)
        entity.__post_init__()

        # create chunk
        self.get_chunk(entity._chunk_pos, entity._zlayer).add_entity(entity)
        return entity

    def remove_entity(self, entity: "entity.Entity"):
        self._delta_entities.append(entity)

    def get_entity(self, entity_id: int):
        return self._entities.get(entity_id)

    # ------------------------------------------------------------------------ #
    # component logic
    # ------------------------------------------------------------------------ #

    def get_components(self, component_class: type):
        return self._gamestate._ecs.get_components(component_class)

    def get_components_by_type(self, component_class: type):
        return self._gamestate._ecs.get_components_by_type(component_class)

    def get_component(self, component_class: type, uuid: int):
        return self._gamestate._ecs.get_component(component_class, uuid)


# ======================================================================== #
# Layer
# ======================================================================== #


class Layer:
    def __init__(
        self,
        zlevel: int = 0,
        buffer: bool = False,
        buffer_size: tuple = None,
    ):
        self._zlevel = zlevel
        self._chunks = {}
        self._delta_chunks = []
        self._buffer = buffer

        # buffer information -- toggleable
        self._framebuffer = (
            None if not buffer else pygame.Surface(state.framebuffer_surface.get_size())
        )
        self._buffer_size = buffer_size

        # management information
        self._world = None

    def __post_init__(self):
        # register the death signal for an entity
        state.signal_handler.register_signal(
            f"SORA_ENTITY_DEATH-{self._zlevel}", [entity.Entity]
        )

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        # update all chunks inside of this layer
        # TODO - add valid chunk filtering
        #       - something like: self._world.get_visible_chunks(self)
        for chunk in self._chunks.values():
            chunk.update()

        # finish up by updating chunks
        for chunk in self._delta_chunks:
            self.add_chunk(chunk)
        self._delta_chunks.clear()

    # ------------------------------------------------------------------------ #
    # chunk logic
    # ------------------------------------------------------------------------ #

    def add_chunk(self, chunk: "Chunk"):
        self._chunks[chunk._chunk_id] = chunk
        chunk._layer = self
        chunk.__post_init__()

    def remove_chunk(self, chunk: "Chunk"):
        self._delta_chunks.append(chunk)

    def get_chunk(self, chunk_position: tuple):
        if Chunk.get_id(chunk_position) not in self._chunks:
            self.add_chunk(Chunk(chunk_position))
        return self._chunks[Chunk.get_id(chunk_position)]


# ======================================================================== #
# Chunk
# ======================================================================== #


class Chunk:
    @staticmethod
    def get_id(chunk_position: tuple):
        return f"{int(chunk_position[0])}||{int(chunk_position[1])}"

    # ------------------------------------------------------------------------ #
    # init
    # ------------------------------------------------------------------------ #

    def __init__(self, chunk_position: tuple):
        self._chunk_position = chunk_position
        self._chunk_size = (
            state.config.default_chunk_pixel_width,
            state.config.default_chunk_pixel_height,
        )

        # chunk information
        self._chunk_id = Chunk.get_id(self._chunk_position)

        # management information
        self._layer = None

        # entity information
        self._entities = {}

    def __post_init__(self):
        # register the death signal for an entity
        self._death_signal = state.signal_handler.register_receiver(
            f"SORA_ENTITY_DEATH-{self._layer._zlevel}", self._entity_death_logic
        )

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        # update all entities inside of this chunk
        for ent in self._entities.values():
            ent.update()
            ent.handle_components()
        if state.config.debug_mode:
            for ent in self._entities.values():
                ent.debug()

    # ------------------------------------------------------------------------ #
    # entity logic
    # ------------------------------------------------------------------------ #

    def _entity_death_logic(self, entity: "entity.Entity"):
        logger.debug("%s %s %s", "ENTITY ZLAYER", entity._zlayer, self._layer._zlevel)
        if (
            entity._zlayer != self._layer._zlevel
            or entity._zlayer != entity._prev_zlayer
        ):
            return
        self.remove_entity(entity)

    def add_entity(self, entity: "entity.Entity"):
        logger.debug("%s %s %s %s", "ADDING", entity, entity._entity_id, entity._zlayer)
        self._entities[entity._entity_id] = entity

    def remove_entity(self, entity: "entity.Entity"):
        logger.debug("%s %s", "REMOVING", entity._entity_id)
        self._entities.pop(entity._entity_id)
        entity.clean()

    def remove_not_clean(self, entity: "entity.Entity"):
        self._entities.pop(entity._entity_id)
