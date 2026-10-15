import pytest

from soragl import state
from soragl.system.game_state import GameState


class Recorder(GameState):
    def __init__(self, name, log):
        super().__init__(name)
        self.log = log

    def __post_init__(self):
        super().__post_init__()
        self.log.append(f"{self.name}:init")

    def on_enter(self):
        self.log.append(f"{self.name}:enter")

    def on_exit(self):
        self.log.append(f"{self.name}:exit")

    def update(self):
        self.log.append(f"{self.name}:update")


@pytest.fixture
def states(engine):
    log = []
    manager = state.game_state_manager
    for name in ("title", "play", "pause"):
        manager.add_game_state(name, Recorder(name, log))
    return manager, log


def test_update_runs_the_current_states_own_update(states):
    manager, log = states
    manager.set_game_state("title")

    manager.update()

    assert log[-1] == "title:update"


def test_switching_states_exits_the_old_one_and_enters_the_new_one(states):
    manager, log = states
    manager.set_game_state("title")
    log.clear()

    manager.set_game_state("play")

    assert log == ["title:exit", "play:init", "play:enter"]


def test_a_state_is_initialised_only_once(states):
    manager, log = states
    manager.set_game_state("title")
    manager.set_game_state("play")
    manager.set_game_state("title")

    assert log.count("title:init") == 1
    assert log.count("title:enter") == 2


def test_pop_returns_to_the_state_below_and_updates_the_world(states):
    manager, log = states
    manager.set_game_state("play")
    manager.push_state("pause")
    assert manager.get_current_state().name == "pause"

    manager.pop_state()

    assert manager.get_current_state().name == "play"
    assert state.world is manager.get_game_state("play").get_world()


def test_popping_with_nothing_pushed_is_an_error(states):
    manager, _ = states
    manager.clear_state_stack()

    with pytest.raises(IndexError):
        manager.pop_state()


def test_unknown_state_name_is_an_error(states):
    manager, _ = states

    with pytest.raises(KeyError, match="credits"):
        manager.set_game_state("credits")
