import numpy as np
import pytest
from pyglm import glm

from soragl.graphics.camera import Camera3D
from soragl.graphics.scene3d import Mesh, ParticleEmitter, strip_uvs
from soragl.graphics.shot import Key, Shake, Shot


def test_box_faces_wind_outward():
    tris = Mesh.box((2, 2, 2)).vertices.reshape(-1, 3, 8)
    a, b, c = tris[:, 0, :3], tris[:, 1, :3], tris[:, 2, :3]
    winding_normal = np.cross(b - a, c - a)
    stored_normal = tris[:, 0, 5:8]
    assert ((winding_normal * stored_normal).sum(axis=1) > 0).all()


def test_mesh_rejects_wrong_vertex_layout():
    with pytest.raises(ValueError):
        Mesh(np.zeros((3, 5), "f4"))


def test_strip_uvs():
    assert strip_uvs(2, 2, count=3) == [
        (0, 0, 0.5, 0.5),
        (0.5, 0, 1, 0.5),
        (0, 0.5, 0.5, 1),
    ]


def test_particles_replay_from_their_seed():
    def run():
        emitter = ParticleEmitter(seed=5, rate=50, lifetime=(0.3, 0.6))
        for _ in range(20):
            emitter.update(1 / 30)
        return emitter.instance_data()

    first = run()
    assert len(first) > 0
    assert np.array_equal(first, run())


def test_particles_die_and_fade():
    emitter = ParticleEmitter(lifetime=(1, 1), color_end=(1, 1, 1, 0))
    emitter.burst(10)
    emitter.update(0.5)
    assert emitter.instance_data()[:, 7] == pytest.approx(0.5)
    emitter.update(0.6)
    assert emitter.count == 0


def test_shot_interpolates_holds_and_cuts():
    shot = Shot(
        [Key(0, (0, 0, 0), height=10), Key(2, (4, 0, 0), height=20, ease="linear")]
    )
    assert shot.pose(1)[0] == glm.vec3(2, 0, 0)
    assert shot.pose(1)[3] == 15
    assert shot.pose(5)[0] == glm.vec3(4, 0, 0)  # holds after the last key

    cut = Shot([Key(0, (0, 0, 0)), Key(2, (4, 0, 0), ease="cut")])
    assert cut.pose(1.99)[0] == glm.vec3(0, 0, 0)
    assert cut.pose(2)[0] == glm.vec3(4, 0, 0)


def test_shot_tracks_a_moving_target_and_shake_decays():
    shot = Shot([Key(0, lambda t: (t, 0, 0))], shakes=[Shake(1, duration=0.5)])
    assert shot.pose(3)[0] == glm.vec3(3, 0, 0)
    assert glm.length(shot.shake_offset(1.1)) > 0
    assert glm.length(shot.shake_offset(1.6)) == 0


def test_shot_points_the_camera_at_the_target():
    camera = Camera3D(0, orthogonal=True, width=90, height=160)
    Shot([Key(0, (1, 0, 2), yaw=30, pitch=40, height=8)]).apply(camera, 0)
    clip = camera.projection * camera.view * glm.vec4(1, 0, 2, 1)
    assert (clip.x / clip.w, clip.y / clip.w) == pytest.approx(
        (0, 0), abs=1e-5
    )  # centred
    assert camera.ortho_height == 8
