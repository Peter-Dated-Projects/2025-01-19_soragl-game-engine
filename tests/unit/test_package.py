import subprocess
import sys

import pytest

from soragl import EngineConfig, state
from soragl.graphics.shader import Shader


def test_importing_soragl_does_not_load_opengl():
    code = "import sys, soragl; assert 'OpenGL' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_state_reset_restores_defaults():
    state.running = True
    state.config.window_width = 5
    state.reset()

    assert state.running is False
    assert state.config.window_width == EngineConfig().window_width


def test_engine_configs_do_not_share_gravity_vector():
    first, second = EngineConfig(), EngineConfig()
    first.default_physics_gravity.y = 99

    assert second.default_physics_gravity.y == -9.8


@pytest.mark.parametrize(
    "name",
    [
        "default_vertex",
        "default_fragment",
        "default_post_vertex",
        "default_post_fragment",
        "model_vertex",
        "model_fragment",
    ],
)
def test_builtin_shaders_ship_with_the_package(name):
    assert "#version" in Shader.builtin(name).get_shader_code()
