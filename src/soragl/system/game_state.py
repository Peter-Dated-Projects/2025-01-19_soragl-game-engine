import logging
from soragl import state

from soragl.system import world, ecs

logger = logging.getLogger(__name__)


# ======================================================================== #
# Game State
# ======================================================================== #


class GameState:
    def __init__(self, name: str):
        self._name = name

        self._world = world.World2D(name)
        self._ecs = ecs.ECSHandler()

        # set parent
        self._world._gamestate = self
        self._ecs._gamestate = self

    def __post_init__(self):
        self._world.__post_init__()
        self._ecs.__post_init__()

    def __on_clean__(self):
        self._world.__on_clean__()
        self._ecs.__on_clean__()

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def get_world(self):
        return self._world

    def get_ecs(self):
        return self._ecs


# ======================================================================== #
# Game State Manager
# ======================================================================== #


class GameStateManager:
    def __init__(self):
        self._current_state = None
        self._states = {}

        self._state_stack = []

        # default initial state
        self.add_game_state("default", GameState("default"))
        self.set_game_state("default")

    def __on_clean__(self):
        logger.debug("---- CLEANING GAME STATE MANAGER ----")
        for game_state in self._states.values():
            logger.debug("%s", game_state._name)
            game_state.__on_clean__()

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        if self._current_state is not None:
            self._current_state.get_world().update()
        else:
            logger.warning("No current state")

    # ------------------------------------------------------------------------ #
    # state logic
    # ------------------------------------------------------------------------ #

    def get_game_state(self, name: str):
        return self._states.get(name)

    def set_game_state(self, name: str):
        self._current_state = self._states.get(name)
        state.ecs_handler = self._current_state.get_ecs()
        state.world = self._current_state.get_world()
        self._current_state.__post_init__()

    def add_game_state(self, name: str, game_state: GameState):
        self._states[name] = game_state

    def remove_game_state(self, name: str):
        # check if current state is the one being removed
        if self._current_state._name == name:
            self.pop_state()

        self._states.pop(name)

    def get_current_state(self):
        return self._current_state

    def get_current_world(self):
        return self._current_state.get_world()

    def push_state(self, name: str):
        self._state_stack.append(self._current_state)
        self.set_game_state(name)

    def pop_state(self):
        self.set_game_state(self._state_stack.pop())
        # update current state
        self._current_state = (
            self._state_stack[-1] if len(self._state_stack) > 0 else None
        )

    def clear_state_stack(self):
        self._state_stack.clear()
        self._current_state = None

    def is_current_state_empty(self):
        return self._current_state is None

    def is_state_stack_empty(self):
        return len(self._state_stack) == 0

    # ecs

    def get_current_ecs(self):
        return self._current_state.get_ecs()
