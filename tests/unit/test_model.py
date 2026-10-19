import pytest

from soragl.io import model

CUBE_FACE = """
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3 4
"""


def test_quad_is_split_into_two_triangles_with_flat_normals():
    data = model.parse_obj(CUBE_FACE)

    assert data.vertex_count == 6
    assert data.vertices.shape == (6, 8)
    assert (data.vertices[:, 5:] == [0, 0, 1]).all()


def test_uvs_and_normals_are_read_from_slash_references():
    data = model.parse_obj(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "vt 0 0\nvt 1 0\nvt 0 1\n"
        "vn 0 0 -1\n"
        "f 1/1/1 2/2/1 3/3/1\n"
    )

    assert data.vertices[1].tolist() == [1, 0, 0, 1, 0, 0, 0, -1]


def test_negative_indices_count_back_from_the_latest_vertex():
    data = model.parse_obj("v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\n")

    assert data.vertices[:, :3].tolist() == [[0, 0, 0], [1, 0, 0], [0, 1, 0]]


def test_usemtl_splits_the_model_into_groups_and_mtl_supplies_the_texture(tmp_path):
    (tmp_path / "cat.mtl").write_text(
        "newmtl fur\nKd 0.5 0.25 0.1\nmap_Kd fur.png\n", encoding="utf-8"
    )
    obj = tmp_path / "cat.obj"
    obj.write_text(
        "mtllib cat.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "usemtl fur\nf 1 2 3\nusemtl bare\nf 1 2 3\n",
        encoding="utf-8",
    )

    data = model.load_obj(obj)

    assert [(g.material, g.start, g.count) for g in data.groups] == [
        ("fur", 0, 3),
        ("bare", 3, 3),
    ]
    assert data.materials["fur"].diffuse_color == (0.5, 0.25, 0.1)
    assert data.materials["fur"].diffuse_map == tmp_path / "fur.png"


def test_bounds_cover_every_vertex():
    low, high = model.parse_obj(CUBE_FACE).bounds()

    assert low.tolist() == [0, 0, 0]
    assert high.tolist() == [1, 1, 0]


def test_face_with_an_out_of_range_index_names_the_line():
    with pytest.raises(ValueError, match="line 2"):
        model.parse_obj("v 0 0 0\nf 1 2 3\n")
