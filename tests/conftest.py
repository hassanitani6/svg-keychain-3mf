from pathlib import Path

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_svg():
    return lambda name: str(FIXTURES / name)


def footprint(mesh, z=None):
    """2-D outline (with holes) of what a mesh puts on the print bed: the union of its
    downward-facing triangles that lie at its lowest height."""
    floor = mesh.bounds[0][2] if z is None else z
    down = (mesh.face_normals[:, 2] < -0.99) & (abs(mesh.triangles[:, :, 2] - floor).max(axis=1) < 1e-6)
    tris = [Polygon(t[:, :2]) for t in mesh.triangles[down]]
    return unary_union([t for t in tris if t.area > 0]) if tris else Polygon()


def union_footprint(meshes):
    return unary_union([footprint(m) for m in meshes.values()])
