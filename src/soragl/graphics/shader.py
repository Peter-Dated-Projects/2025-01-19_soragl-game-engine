import logging
import os
from importlib import resources
from pathlib import Path

from soragl import state

logger = logging.getLogger(__name__)

# ============================================================================= #
# Shaders
# ============================================================================= #


class Shader:
    def __init__(self, file_path: str | os.PathLike):
        self._source = Path(file_path)

    @classmethod
    def builtin(cls, name: str) -> "Shader":
        """Load a shader bundled with soragl, e.g. `Shader.builtin("default_vertex")`."""
        shader = cls.__new__(cls)
        shader._source = resources.files("soragl") / "data" / "shaders" / f"{name}.glsl"
        return shader

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def get_shader_code(self) -> str:
        return self._source.read_text()


# ======================================================================== #
# shader program
# ======================================================================== #


class ShaderProgram:
    CACHE = {}
    SHADER_PROGRAM_COUNTER = 0

    @classmethod
    def generate_shader_program_uuid(cls):
        cls.SHADER_PROGRAM_COUNTER += 1
        return cls.SHADER_PROGRAM_COUNTER

    @classmethod
    def __on_clean__(cls):
        logger.debug("---- CLEANING SHADER PROGRAMS ----")
        for shader_program in cls.CACHE.values():
            logger.debug("%s", shader_program._uuid)
            shader_program.clean(clean_func=True)

    @classmethod
    def cache(cls, shader_program):
        cls.CACHE[shader_program._uuid] = shader_program

    @classmethod
    def remove_from_cache(cls, shader_program):
        cls.CACHE.pop(shader_program._uuid)
        # assume user has handled cleaning etc

    @classmethod
    def get_shader(cls, shader_uuid: int):
        return cls.CACHE[shader_uuid]

    # ------------------------------------------------------------------------ #

    def __init__(
        self,
        vertex_shader: Shader,
        fragment_shader: Shader,
        geometry_shader: Shader = None,
        tess_control_shader: Shader = None,
        tess_evaluation_shader: Shader = None,
    ):
        self._uuid = self.generate_shader_program_uuid()
        self.cache(self)

        self._shaders = {
            "vertex": vertex_shader,
            "fragment": fragment_shader,
            "geometry": geometry_shader,
            "tess_control": tess_control_shader,
            "tess_evaluation": tess_evaluation_shader,
        }

        self._program = None
        self.__create()

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def __create(self):
        self._program = state.gl_context.program(
            vertex_shader=self._shaders["vertex"].get_shader_code(),
            fragment_shader=self._shaders["fragment"].get_shader_code(),
            geometry_shader=(
                self._shaders["geometry"].get_shader_code()
                if self._shaders["geometry"] is not None
                else None
            ),
            tess_control_shader=(
                self._shaders["tess_control"].get_shader_code()
                if self._shaders["tess_control"] is not None
                else None
            ),
            tess_evaluation_shader=(
                self._shaders["tess_evaluation"].get_shader_code()
                if self._shaders["tess_evaluation"] is not None
                else None
            ),
        )

    def clean(self, clean_func: bool = False):
        self._program.release()
        if not clean_func:
            self.remove_from_cache(self)

    # ------------------------------------------------------------------------ #
    # special functions
    # ------------------------------------------------------------------------ #

    def __call__(self):
        return self._program

    def __getitem__(self, key):
        return self._program[key]

    def __setitem__(self, key, value):
        self._program[key] = value
