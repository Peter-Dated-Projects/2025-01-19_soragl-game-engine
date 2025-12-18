import glm
import math
import random

from engine.physics import entity

from engine.graphics import buffer
from engine.graphics import shader
from engine.graphics.ecs import c_mesh

# ======================================================================== #
# Cube object
# ======================================================================== #


class CubeEntity(entity.Entity):
    def __init__(
        self,
        name: str = None,
        zlayer: int = 0,
        shader_program: shader.ShaderProgram = None,
        complete_vert_data: list[tuple] = None,
        shared_vao: buffer.VAOObject = None,
    ):
        super().__init__(name, zlayer)

        # define variables
        self._c_mesh = None
        self._shader_program = shader_program
        self._complete_vert_data = complete_vert_data
        self._shared_vao = shared_vao

        # create model
        self._model_rman = glm.mat4()
        self._model_rman = glm.scale(glm.vec3(random.random() * 0.1))
        self._model_rman = glm.rotate(
            self._model_rman, random.random() * math.pi * 2, glm.vec3(0, 1, 0)
        )
        self._model_rman = glm.rotate(
            self._model_rman, random.random() * math.pi * 2, glm.vec3(1, 0, 0)
        )
        self._model_rman = glm.rotate(
            self._model_rman, random.random() * math.pi * 2, glm.vec3(0, 0, 1)
        )
        self._model_rman = glm.translate(
            self._model_rman,
            glm.vec3(
                random.random() * 20 - 5,
                random.random() * 10 - 5,
                random.random() * 10 - 5,
            ),
        )

    def __post_init__(self):
        # create objects
        # create default cube object
        # If shared VAO is provided, use it; otherwise create a new one
        if self._shared_vao:
            vao_to_use = self._shared_vao
        else:
            vao_to_use = buffer.VAOObject(
                self._shader_program,
                [
                    (
                        self._complete_vert_data(),
                        "3f 2f 1f",
                        "in_position",
                        "in_texcoords",
                        "in_tex",
                    )
                ],
            )

        self._c_mesh = self.add_component(
            c_mesh.MeshComponent(
                buffer.RenderingManifold(vao=vao_to_use)
            )
        )

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        # upload data
        self._c_mesh().write_uniform("m_model", self._model_rman)
