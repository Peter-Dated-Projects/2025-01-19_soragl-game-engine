import pygame

from soragl import state

from soragl.physics import interact

# ======================================================================== #
# SoraBox2D
# ======================================================================== #


class SoraBox2DColliderComponent(interact.ShapeComponent):
    def __init__(self, width: float, height: float, collision_conserve_coef: float = 0):
        super().__init__(
            [
                pygame.Vector2(-width / 2, -height / 2),
                pygame.Vector2(width / 2, -height / 2),
                pygame.Vector2(width / 2, height / 2),
                pygame.Vector2(-width / 2, height / 2),
            ],
        )

        self._width = width
        self._height = height
        self._rect = pygame.FRect(0, 0, width, height)

        # custom physics things
        self._collision_conserve_coef = collision_conserve_coef

    def __post_init__(self):
        self._rect.center = self._entity._position

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        self._rect.center = self._entity._position

    def debug(self):
        pygame.draw.rect(state.framebuffer_surface, (255, 0, 255), self._rect, 1)
