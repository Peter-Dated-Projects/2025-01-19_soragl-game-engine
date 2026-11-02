import pygame
import random

from soragl import constants
from soragl import state

from soragl.system import ecs

# ======================================================================== #
# Particle Handler
# ======================================================================== #


class ParticleHandlerComponent(ecs.Component):
    def __init__(self, updates_per_second: float = 30):
        super().__init__()

        self._particles = {}
        self._dead_particles = []
        self._particle_count = 0
        self._particle_id_counter = 0
        self._max_particles = 1000

        # particle logic
        self._updates_per_second = updates_per_second
        self._update_time = 1 / self._updates_per_second
        self._timer = 0

        # default functions
        self._create_func = default_create_func
        self._update_func = default_update_func
        self._death_func = default_death_func

    # ------------------------------------------------------------------------ #
    # particle logic
    # ------------------------------------------------------------------------ #

    def update(self):
        self._create_func(self)
        self._update_func(self)
        self._death_func(self)

    def update_functions(self, create_func=None, update_func=None, death_func=None):
        if create_func:
            self._create_func = create_func
        if update_func:
            self._update_func = update_func
        if death_func:
            self._death_func = death_func

    def generate_particle_id(self):
        self._particle_id_counter += 1
        return self._particle_id_counter


# default particle handler logic


def default_create_func(self):
    self._timer += state.delta_time
    if self._timer < self._update_time:
        return
    self._timer = 0

    # create a default square particle with rotation
    # 0 - id
    # 1 - position
    # 2 - velocity
    # 3 - rotation
    # 4 - rotation_speed
    # 5 - size
    # 6 - alive time
    if self._particle_count >= self._max_particles:
        return

    self._particles[self.generate_particle_id()] = [
        self.generate_particle_id(),
        self._entity._position.copy(),
        pygame.Vector2(random.random() - 0.5, random.random() - 0.5).normalize() * 30,
        random.randint(0, 360),
        random.randint(30, 80) * random.choice([-1, 1]),
        random.randint(10, 30),
        0,
        (231 + random.randint(-10, 10), 168 + random.randint(-10, 10), 0),
    ]
    self._particle_count += 1


def default_update_func(self):

    for p in self._particles:
        particle = self._particles[p]

        # check alive
        if particle[6] > 2:
            self._dead_particles.append(p)
            continue

        # update position
        particle[1] += particle[2] * state.delta_time
        particle[2] *= 0.99
        # update rotation
        particle[3] += particle[4] * state.delta_time
        particle[4] *= 0.99
        # update time
        particle[6] += state.delta_time

        # render
        corners = [
            pygame.Vector2(constants.Constants.UP * particle[5]).rotate(particle[3]),
            pygame.Vector2(constants.Constants.RIGHT * particle[5]).rotate(particle[3]),
            pygame.Vector2(constants.Constants.DOWN * particle[5]).rotate(particle[3]),
            pygame.Vector2(constants.Constants.LEFT * particle[5]).rotate(particle[3]),
        ]
        pygame.draw.lines(
            state.framebuffer_surface,
            particle[7],
            True,
            [particle[1] + corner for corner in corners],
            1,
        )


def default_death_func(self):
    for p in self._dead_particles:
        del self._particles[p]
        self._particle_count -= 1
    self._dead_particles = []
