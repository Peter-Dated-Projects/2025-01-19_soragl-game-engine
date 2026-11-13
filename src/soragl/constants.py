from pyglm import glm
import pygame

ENGINE_NAME = "SORAGL"


class Constants:
    UP = pygame.Vector2(0, -1)
    DOWN = pygame.Vector2(0, 1)
    LEFT = pygame.Vector2(-1, 0)
    RIGHT = pygame.Vector2(1, 0)

    GRAVITY_VECTOR = DOWN * 9.8


class GlmConstants:
    UP = glm.vec3(0, 1, 0)
    DOWN = glm.vec3(0, -1, 0)
    RIGHT = glm.vec3(1, 0, 0)
    LEFT = glm.vec3(-1, 0, 0)
    FORWARD = glm.vec3(0, 0, 1)
    BACKWARD = glm.vec3(0, 0, -1)

    ORIGIN = glm.vec3(0, 0, 0)
