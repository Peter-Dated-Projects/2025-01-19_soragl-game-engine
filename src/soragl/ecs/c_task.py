from soragl.system import ecs

from typing import Callable


"""
Tasks are different from processes.

They run once every single frame.
- great for testing
- great for debugging
"""

# ------------------------------------------------------------------------ #
# task
# ------------------------------------------------------------------------ #


class TaskComponent(ecs.Component):
    def __init__(self, name: str, func: Callable, *args):
        super().__init__()
        self.name = name

        self._func = func
        self._args = args

    # ------------------------------------------------------------------------ #
    # task logic
    # ------------------------------------------------------------------------ #

    def update(self):
        self._func(*self._args)
