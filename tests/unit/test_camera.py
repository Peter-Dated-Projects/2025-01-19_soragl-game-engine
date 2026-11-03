import glm
import pytest

from soragl.graphics.camera import Camera3D


def _ndc(cam: Camera3D, point: glm.vec3) -> glm.vec3:
    clip = cam.projection * cam.view * glm.vec4(point, 1.0)
    return glm.vec3(clip) / clip.w


def _tilted(**kwargs) -> Camera3D:
    return Camera3D(
        5,
        position=glm.vec3(10, 10, 10),
        forward=glm.normalize(glm.vec3(-1, -1, -1)),
        orthogonal=True,
        width=1600,
        height=900,
        **kwargs,
    )


def test_ortho_defaults_to_pixel_units():
    cam = _tilted()
    # 450 px above the look axis is the top of the screen
    top = cam.position + cam.up * 450
    assert _ndc(cam, top).y == pytest.approx(1.0)


def test_ortho_height_sets_world_units_visible():
    cam = _tilted(ortho_height=10)
    assert _ndc(cam, cam.position + cam.up * 5).y == pytest.approx(1.0)
    right = glm.normalize(glm.cross(cam.forward, cam.up))
    assert _ndc(cam, cam.position + right * 5 * 16 / 9).x == pytest.approx(1.0)


def test_ortho_has_no_perspective_foreshortening():
    cam = _tilted(ortho_height=10)
    near = _ndc(cam, cam.position + cam.forward * 1 + cam.up)
    far = _ndc(cam, cam.position + cam.forward * 50 + cam.up)
    assert near.y == pytest.approx(far.y)


def test_ortho_height_setter_updates_projection():
    cam = _tilted(ortho_height=10)
    cam.ortho_height = 20
    assert _ndc(cam, cam.position + cam.up * 10).y == pytest.approx(1.0)
