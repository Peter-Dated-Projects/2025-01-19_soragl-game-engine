import numpy as np

# ======================================================================== #
# vertex constants
# ======================================================================== #


def generate_vertex_data(vertices, indices):
    return np.array([vertices[i] for tri in indices for i in tri], dtype="float32")


class Cube:
    VERTICES = [
        # point 0
        (1.0, 1.0, 1.0),
        # point 1
        (-1.0, 1.0, 1.0),
        # point 2
        (-1.0, -1.0, 1.0),
        # point 3
        (1.0, -1.0, 1.0),
        # point 4
        (1.0, 1.0, -1.0),
        # point 5
        (-1.0, 1.0, -1.0),
        # point 6
        (-1.0, -1.0, -1.0),
        # point 7
        (1.0, -1.0, -1.0),
    ]

    VERTEX_INDICES = [
        # front face
        (0, 1, 2),
        (0, 2, 3),
        # back face
        (4, 5, 6),
        (4, 6, 7),
        # left face
        (4, 0, 3),
        (4, 3, 7),
        # right face
        (1, 5, 6),
        (1, 6, 2),
        # top face
        (3, 2, 6),
        (3, 6, 7),
        # bottom face
        (4, 5, 1),
        (4, 1, 0),
    ]

    TEXCOORDS = [(0, 0), (1, 0), (1, 1), (0, 1)]

    TEXCOORD_INDICES = [
        # front face
        (0, 1, 2),
        (0, 2, 3),
        # back face
        (0, 1, 2),
        (0, 2, 3),
        # left face
        (0, 1, 2),
        (0, 2, 3),
        # right face
        (0, 1, 2),
        (0, 2, 3),
        # top face
        (0, 1, 2),
        (0, 2, 3),
        # bottom face
        (0, 1, 2),
        (0, 2, 3),
    ]

    # ------------------------------------------------------------------------ #
    # static methods
    # ------------------------------------------------------------------------ #

    @classmethod
    def get_cube_vert(cls):
        return generate_vertex_data(cls.VERTICES, cls.VERTEX_INDICES)

    @classmethod
    def get_cube_tex(cls):
        return generate_vertex_data(cls.TEXCOORDS, cls.TEXCOORD_INDICES)


class Plane:
    VERTICES = [
        # point 0
        (1.0, 1.0, 0.0),
        # point 1
        (-1.0, 1.0, 0.0),
        # point 2
        (-1.0, -1.0, 0.0),
        # point 3
        (1.0, -1.0, 0.0),
    ]

    VERTEX_INDICES = [(0, 1, 2), (0, 2, 3)]

    TEXCOORDS = [(0, 0), (1, 0), (1, 1), (0, 1)]

    TEXCOORD_INDICES = [(2, 3, 0), (2, 0, 1)]

    # ------------------------------------------------------------------------ #
    # static methods
    # ------------------------------------------------------------------------ #

    @classmethod
    def get_plane_vert(cls, width=1, height=1):
        return generate_vertex_data(
            [
                (width, height, 0.0),
                (-width, height, 0.0),
                (-width, -height, 0.0),
                (width, -height, 0.0),
            ],
            cls.VERTEX_INDICES,
        )

    @classmethod
    def get_plane_tex(cls):
        return generate_vertex_data(cls.TEXCOORDS, cls.TEXCOORD_INDICES)


class Triangle:
    VERTICES = [
        # point 0
        (0.0, 1.0, 0.0),
        # point 1
        (-1.0, -1.0, 0.0),
        # point 2
        (1.0, -1.0, 0.0),
    ]

    VERTEX_INDICES = [(0, 1, 2)]

    TEXCOORDS = [(0, 0), (1, 0), (0.5, 1)]

    TEXCOORD_INDICES = [(0, 1, 2)]

    # ------------------------------------------------------------------------ #
    # static methods
    # ------------------------------------------------------------------------ #

    @classmethod
    def get_triangle_vert(cls):
        return generate_vertex_data(cls.VERTICES, cls.VERTEX_INDICES)

    @classmethod
    def get_triangle_tex(cls):
        return generate_vertex_data(cls.TEXCOORDS, cls.TEXCOORD_INDICES)
