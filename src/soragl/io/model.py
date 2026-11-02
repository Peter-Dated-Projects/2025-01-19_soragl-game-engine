"""Wavefront .obj / .mtl parsing into GPU-ready vertex data."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

VERTEX_FORMAT = "3f 2f 3f"
"""moderngl buffer format of `ModelData.vertices`: position, uv, normal."""

FLOATS_PER_VERTEX = 8


@dataclass(frozen=True)
class Material:
    name: str
    diffuse_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    diffuse_map: Path | None = None


@dataclass(frozen=True)
class MeshGroup:
    """A run of vertices drawn with a single material."""

    material: str | None
    start: int
    count: int


@dataclass
class ModelData:
    vertices: np.ndarray
    groups: list[MeshGroup] = field(default_factory=list)
    materials: dict[str, Material] = field(default_factory=dict)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def nbytes(self) -> int:
        return self.vertices.nbytes

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """The axis-aligned bounding box as (min corner, max corner)."""
        positions = self.vertices[:, :3]
        return positions.min(axis=0), positions.max(axis=0)


# ======================================================================== #
# obj
# ======================================================================== #


def load_obj(path: Path) -> ModelData:
    path = Path(path)
    return parse_obj(path.read_text(), base_dir=path.parent)


def parse_obj(text: str, base_dir: Path | None = None) -> ModelData:
    """Parse .obj text into unindexed triangles.

    Polygons are fan-triangulated (so they must be convex). Missing normals
    become flat face normals and missing uvs become (0, 0).
    """
    positions: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    normals: list[tuple[float, float, float]] = []
    rows: list[list[float]] = []
    materials: dict[str, Material] = {}
    groups: list[MeshGroup] = []
    current_material: str | None = None
    group_start = 0

    def close_group():
        nonlocal group_start
        if len(rows) > group_start:
            groups.append(
                MeshGroup(current_material, group_start, len(rows) - group_start)
            )
        group_start = len(rows)

    for line_number, raw in enumerate(text.splitlines(), start=1):
        parts = raw.split("#", 1)[0].split()
        if not parts:
            continue
        keyword, args = parts[0], parts[1:]

        if keyword == "v":
            positions.append(_floats(args[:3], line_number))
        elif keyword == "vt":
            uvs.append(_floats(args[:2], line_number))
        elif keyword == "vn":
            normals.append(_floats(args[:3], line_number))
        elif keyword == "f":
            corners = [
                _resolve_corner(arg, positions, uvs, normals, line_number)
                for arg in args
            ]
            if len(corners) < 3:
                raise ValueError(f"line {line_number}: face needs at least 3 vertices")
            for i in range(1, len(corners) - 1):
                rows.extend(_triangle(corners[0], corners[i], corners[i + 1]))
        elif keyword == "usemtl":
            close_group()
            current_material = args[0] if args else None
        elif keyword == "mtllib" and base_dir is not None:
            for name in args:
                materials.update(_load_mtl(base_dir / name))

    close_group()
    vertices = (
        np.array(rows, dtype=np.float32)
        if rows
        else np.empty((0, FLOATS_PER_VERTEX), dtype=np.float32)
    )
    return ModelData(vertices=vertices, groups=groups, materials=materials)


def _floats(tokens: list[str], line_number: int) -> tuple[float, ...]:
    try:
        return tuple(float(token) for token in tokens)
    except ValueError:
        raise ValueError(
            f"line {line_number}: expected numbers, got {tokens}"
        ) from None


def _resolve_corner(token, positions, uvs, normals, line_number):
    """Turn `v`, `v/vt`, `v//vn` or `v/vt/vn` into concrete (position, uv, normal)."""
    fields = token.split("/")

    def pick(values, field_index):
        if field_index >= len(fields) or not fields[field_index]:
            return None
        index = int(fields[field_index])
        index = index - 1 if index > 0 else len(values) + index
        if not 0 <= index < len(values):
            raise ValueError(
                f"line {line_number}: index {fields[field_index]} out of range"
            )
        return values[index]

    return pick(positions, 0), pick(uvs, 1), pick(normals, 2)


def _triangle(a, b, c):
    p0, p1, p2 = (np.array(corner[0], dtype=np.float32) for corner in (a, b, c))
    face_normal = np.cross(p1 - p0, p2 - p0)
    length = np.linalg.norm(face_normal)
    flat = face_normal / length if length else np.array([0, 0, 1], dtype=np.float32)

    for position, uv, normal in (a, b, c):
        yield [*position, *(uv or (0.0, 0.0)), *(normal if normal else flat)]


def _load_mtl(path: Path) -> dict[str, Material]:
    if not path.exists():
        logger.warning("material library %s not found", path)
        return {}

    materials: dict[str, Material] = {}
    name = None
    color = (1.0, 1.0, 1.0)
    diffuse_map = None

    def save():
        if name is not None:
            materials[name] = Material(name, color, diffuse_map)

    for raw in path.read_text().splitlines():
        parts = raw.split("#", 1)[0].split()
        if not parts:
            continue
        if parts[0] == "newmtl":
            save()
            name, color, diffuse_map = parts[1], (1.0, 1.0, 1.0), None
        elif parts[0] == "Kd":
            color = tuple(float(v) for v in parts[1:4])
        elif parts[0] == "map_Kd":
            diffuse_map = path.parent / parts[-1]
    save()
    return materials
