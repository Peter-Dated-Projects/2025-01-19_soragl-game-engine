from soragl.system import ecs

from soragl.graphics import buffer

# ============================================================================= #
# Mesh Component
# ============================================================================= #


class MeshComponent(ecs.Component):
    def __init__(self, manifold: buffer.RenderingManifold):
        super().__init__()

        self._manifold = manifold

    def __on_clean__(self):
        # clear up manifold data
        self._manifold.__on_clean__()

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        # update framebuffer lol
        self._manifold.handle()

    # ------------------------------------------------------------------------ #
    # special functions
    # ------------------------------------------------------------------------ #

    def __call__(self):
        return self._manifold
