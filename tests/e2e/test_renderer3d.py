import shutil

import numpy as np
import pytest

from soragl.graphics.camera import Camera3D
from soragl.graphics.recorder import FrameRecorder
from soragl.graphics.renderer3d import Renderer
from soragl.graphics.scene3d import (
    DirectionalLight,
    Material,
    Mesh,
    MeshInstance,
    ParticleEmitter,
    Scene,
    Sprite3D,
)
from soragl.graphics.shot import Key, Shot

SIZE = (64, 64)
RED = (255, 0, 0)


def solid(gl_context, rgba=(255, 0, 0, 255)):
    return gl_context.texture((1, 1), 4, bytes(rgba))


def front_camera():
    """Orthographic, looking straight down -z from +z, 10 units tall."""
    camera = Camera3D(
        0, orthogonal=True, ortho_height=10, width=SIZE[0], height=SIZE[1]
    )
    Shot([Key(0, (0, 1, 0), yaw=0, pitch=0, height=10)]).apply(camera, 0)
    return camera


def render(gl_context, scene, camera, pixel_scale=1):
    renderer = Renderer(gl_context, SIZE, pixel_scale=pixel_scale)
    renderer.render(scene, camera)
    pixels = renderer.read_pixels()
    renderer.release()
    return pixels


def test_sprite_hides_behind_a_wall_and_shows_in_front(gl_context):
    wall = MeshInstance(Mesh.box((4, 4, 1)), Material((0, 0, 1, 1), unlit=True))
    centre = (SIZE[1] // 2, SIZE[0] // 2)
    for z, visible in ((-3, False), (3, True)):
        sprite = Sprite3D(solid(gl_context), (0, 0, z), (2, 4), unlit=True)
        scene = Scene(meshes=[wall], sprites=[sprite])
        pixel = tuple(render(gl_context, scene, front_camera())[centre])
        assert (pixel == RED) is visible, (z, pixel)


def test_transparent_sprite_pixels_are_cut_out(gl_context):
    clear = Sprite3D(solid(gl_context, (255, 0, 0, 0)), (0, 0, 0), (4, 4), unlit=True)
    scene = Scene(sprites=[clear], background=(0, 1, 0))
    assert tuple(render(gl_context, scene, front_camera())[32, 32]) == (0, 255, 0)


def test_box_casts_a_shadow_on_the_ground(gl_context):
    camera = Camera3D(
        0, orthogonal=True, ortho_height=20, width=SIZE[0], height=SIZE[1]
    )
    Shot([Key(0, (0, 0, 0), yaw=0, pitch=89, height=20)]).apply(camera, 0)
    scene = Scene(
        meshes=[
            MeshInstance(Mesh.plane(40, 40), Material((1, 1, 1, 1))),
            MeshInstance(Mesh.box((2, 6, 2), (-5, 0, 0)), Material((1, 1, 1, 1))),
        ],
        light=DirectionalLight(direction=(1, -1, 0), shadow_extent=15),
        toon_bands=0,
    )
    pixels = render(gl_context, scene, camera).astype(int)
    # light travels toward +x, so the shadow lies right of the box; left of it is lit
    shadowed = pixels[32, 32 + 4].sum()
    lit = pixels[32, 32 - 26].sum()
    assert shadowed < lit * 0.7, (shadowed, lit)


def test_rendering_is_deterministic(gl_context):
    def frame():
        emitter = ParticleEmitter((0, 1, 0), seed=7, size=(0.5, 0.5))
        emitter.burst(30)
        emitter.update(0.1)
        scene = Scene(
            meshes=[MeshInstance(Mesh.box((3, 3, 3)))],
            sprites=[Sprite3D(solid(gl_context), (2, 0, 2), (1, 2))],
            emitters=[emitter],
        )
        return render(gl_context, scene, front_camera(), pixel_scale=2)

    assert np.array_equal(frame(), frame())


def test_pixel_scale_renders_blocky_pixels(gl_context):
    sprite = Sprite3D(solid(gl_context), (0.3, 0, 0), (3.3, 3.3), unlit=True)
    pixels = render(gl_context, Scene(sprites=[sprite]), front_camera(), pixel_scale=4)
    blocks = pixels.reshape(16, 4, 16, 4, 3)
    assert (blocks == blocks[:, :1, :, :1]).all()  # each 4x4 block is one colour


def test_output_size_must_divide_by_pixel_scale(gl_context):
    with pytest.raises(ValueError):
        Renderer(gl_context, (65, 64), pixel_scale=4)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_recorder_writes_an_image_sequence(gl_context, tmp_path):
    renderer = Renderer(gl_context, SIZE, pixel_scale=1)
    with FrameRecorder(tmp_path / "f_%03d.png", SIZE, fps=30) as recorder:
        for _ in range(3):
            renderer.render(Scene(), front_camera())
            recorder.write(renderer.read_pixels())
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "f_001.png",
        "f_002.png",
        "f_003.png",
    ]
    with pytest.raises(ValueError), FrameRecorder(tmp_path / "x.mp4", SIZE) as recorder:
        recorder.write(np.zeros((2, 2, 3), np.uint8))
