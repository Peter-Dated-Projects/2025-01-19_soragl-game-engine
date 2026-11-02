from soragl import state
from soragl.system import ecs

# ======================================================================== #
# Audio Listener
# ======================================================================== #


class AudioListenerComponent(ecs.Component):
    """Makes the entity the player's ears.

    Position comes from the entity. A 3D entity that exposes `_forward` and
    `_up` (like `Camera3D`) also sets the listening direction.
    """

    def update(self):
        entity = self._entity
        state.audio.listener.set_pose(
            entity._position,
            forward=getattr(entity, "_forward", None),
            up=getattr(entity, "_up", None),
        )

    def debug(self):
        pass
