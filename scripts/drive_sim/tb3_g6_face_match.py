"""Finite-face image matching for the axis-aligned TB3 corridor meshes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import dist, fsum
from pathlib import Path

from validate_tb3_g5 import mesh_triangles

C_M_S = 299792458.0
# Geometry only. The strict 0.05 ps delay limit is applied separately.
RECORDED_HIT_TOL_M = 1e-5
EXACT_HIT_TOL_M = 1e-9
LENGTH_CLOSURE_TOL_M = 1e-10


class ImageGeometryError(ValueError):
    """The recorded surface sequence does not produce a finite-face image."""


class ImageHitOutsideFace(ImageGeometryError):
    """An exact image intersects the plane outside its connected mesh face."""


@dataclass(frozen=True)
class Triangle:
    vertices: tuple
    axis: int
    plane_m: float
    edges_2d: tuple
    orientation: float

    @classmethod
    def from_vertices(cls, vertices):
        axes = [i for i in range(3) if len({p[i] for p in vertices}) == 1]
        if len(axes) != 1:
            raise ValueError("TB3 reflection triangles must be axis-aligned")
        axis = axes[0]
        a, b = [i for i in range(3) if i != axis]
        edges = tuple((p[a], p[b], q[a] - p[a], q[b] - p[b],
                       dist((p[a], p[b]), (q[a], q[b])))
                      for p, q in zip(vertices, vertices[1:] + vertices[:1], strict=True))
        orientation = edges[0][2] * edges[1][3] - edges[0][3] * edges[1][2]
        if orientation == 0 or any(edge[4] == 0 for edge in edges):
            raise ValueError("Degenerate TB3 reflection triangle")
        return cls(vertices, axis, vertices[0][axis], edges, 1.0 if orientation > 0 else -1.0)

    def contains(self, point, tolerance_m):
        if abs(point[self.axis] - self.plane_m) > tolerance_m:
            return False
        a, b = [point[i] for i in range(3) if i != self.axis]
        return all(self.orientation * (dx * (b - y) - dy * (a - x)) >= -tolerance_m * length
                   for x, y, dx, dy, length in self.edges_2d)


@dataclass(frozen=True)
class Face:
    label: str
    axis: int
    plane_m: float
    primitives: tuple


def shares_edge_segment(first, second):
    p, q = first
    a, b = second
    direction = tuple(y - x for x, y in zip(p, q, strict=True))
    axis = max(range(3), key=lambda j: abs(direction[j]))
    lo, hi = sorted((p[axis], q[axis]))
    other_lo, other_hi = sorted((a[axis], b[axis]))
    if min(hi, other_hi) - max(lo, other_lo) <= EXACT_HIT_TOL_M:
        return False
    for point in second:
        fraction = (point[axis] - p[axis]) / direction[axis]
        if any(abs(point[j] - (p[j] + fraction * direction[j])) > EXACT_HIT_TOL_M for j in range(3)):
            return False
    return True


def connected_faces(name, raw_triangles):
    """Join coplanar triangles with shared segments, including a tessellation T-junction."""
    triangles = tuple(Triangle.from_vertices(t) for t in raw_triangles)
    by_plane = defaultdict(list)
    for i, t in enumerate(triangles):
        for p, q in zip(t.vertices, t.vertices[1:] + t.vertices[:1], strict=True):
            by_plane[t.axis, t.plane_m].append((i, (p, q)))
    neighbors = [set() for _ in triangles]
    for edges in by_plane.values():
        for index, (i, edge) in enumerate(edges):
            for j, other in edges[index+1:]:
                if i != j and shares_edge_segment(edge, other):
                    neighbors[i].add(j)
                    neighbors[j].add(i)
    assigned = {}
    for i, triangle in enumerate(triangles):
        if i in assigned:
            continue
        component, pending = set(), [i]
        while pending:
            j = pending.pop()
            if j not in component:
                component.add(j)
                pending.extend(neighbors[j] - component)
        label = f"{name}[{'xyz'[triangle.axis]}={triangle.plane_m:g};patch={i}]"
        face = Face(label, triangle.axis, triangle.plane_m,
                    tuple((j, triangles[j]) for j in sorted(component)))
        assigned.update((j, face) for j in component)
    return triangles, assigned


def load_faces(scene, entry, scene_root: Path):
    by_name = {b["object"]: connected_faces(b["object"], mesh_triangles(scene_root / b["ply"]))
               for b in entry["material_bindings"]}
    by_id = {int(obj.object_id): by_name[name] for name, obj in scene.objects.items()}
    if len(by_id) != len(by_name):
        raise ValueError("Scene object IDs do not uniquely cover the frozen mesh bindings")
    return by_id


def fold_images(tx, rx, faces):
    """Independently find ordered finite-face hits and check folded length."""
    virtual = [tuple(rx)]
    for face in reversed(faces):
        nxt = list(virtual[-1])
        nxt[face.axis] = 2.0 * face.plane_m - nxt[face.axis]
        virtual.append(tuple(nxt))
    point = tuple(tx)
    points = [point]
    for face, image in zip(faces, reversed(virtual[1:]), strict=True):
        delta = tuple(a - b for a, b in zip(image, point, strict=True))
        axis = face.axis
        if delta[axis] == 0:
            raise ImageGeometryError("Image segment parallel to its recorded face")
        fraction = (face.plane_m - point[axis]) / delta[axis]
        if not 0 < fraction < 1:
            raise ImageGeometryError("Image intersects the faces in a different order")
        point = tuple(face.plane_m if j == axis else point[j] + fraction * delta[j]
                      for j in range(3))
        points.append(point)
    points.append(tuple(rx))
    unfolded_m = dist(tx, virtual[-1])
    folded_m = fsum(dist(a, b) for a, b in zip(points, points[1:]))
    if abs(unfolded_m - folded_m) > LENGTH_CLOSURE_TOL_M:
        raise ImageGeometryError("Folded and unfolded image lengths differ")
    return unfolded_m / C_M_S, points[1:-1]


def match_path(tx, rx, recorded_tx, recorded_rx, hits, *, raise_unmatched=False):
    """Return the timing and face sequence tied to the recorded primitives."""
    faces = [face for _, _, face, _ in hits]
    signature = ">".join(f.label for f in faces) if faces else "LOS"
    points = [recorded_tx, *(point for _, _, _, point in hits), recorded_rx]
    delay_s = fsum(dist(a, b) for a, b in zip(points, points[1:])) / C_M_S
    max_plane_offset_m = max((abs(p[tri.axis] - tri.plane_m) for _, tri, _, p in hits), default=0.0)
    try:
        image_s, image_points = fold_images(tx, rx, faces)
        switches = 0
        for (primitive, triangle, face, recorded), point in zip(hits, image_points, strict=True):
            if not triangle.contains(recorded, RECORDED_HIT_TOL_M):
                raise ImageGeometryError(f"Native hit outside its recorded primitive {face.label}/{primitive}")
            if not triangle.contains(point, EXACT_HIT_TOL_M):
                if not any(t.contains(point, EXACT_HIT_TOL_M) for _, t in face.primitives):
                    raise ImageHitOutsideFace(f"Image hit outside the connected finite face {face.label}")
                switches += 1
    except ImageGeometryError as error:
        if raise_unmatched:
            raise
        return signature, delay_s, None, 0, max_plane_offset_m, str(error)
    return signature, delay_s, image_s, switches, max_plane_offset_m, None


def check_geometry():
    # Two triangles tessellate a square; a disconnected square is a different
    # face even on the same object and plane.
    square = ((0., 0., 0.), (0., 2., 0.), (0., 2., 2.), (0., 0., 2.))
    other = tuple((x, y + 3., z) for x, y, z in square)
    triangles, faces = connected_faces("wall", [(p[0], p[1], p[2]) for p in (square, other)]
                                       + [(p[0], p[2], p[3]) for p in (square, other)])
    if faces[0] != faces[2] or faces[0] == faces[1]:
        raise ValueError("Face identity crossed a gap or split a triangulation")
    t_junction = (square[1], (0., 3., 1.), (0., 2., 1.))
    _, joined = connected_faces("wall", [(square[0], square[1], square[2]), t_junction])
    if joined[0] != joined[1]:
        raise ValueError("A partial edge shared by coplanar triangles was split")
    corner_only = (square[2], (0., 3., 2.), (0., 3., 3.))
    _, separated = connected_faces("wall", [(square[0], square[1], square[2]), corner_only])
    if separated[0] == separated[1]:
        raise ValueError("Contact at one vertex incorrectly joined two faces")
    tx, rx = (1., .5, .5), (1., 1.5, 1.5)
    result = match_path(tx, rx, tx, rx, [(0, triangles[0], faces[0], (0., 1., 1.))])
    if result[-1] or abs(result[2] - dist(tx, (-1., 1.5, 1.5)) / C_M_S) > 1e-22:
        raise ValueError("Closed-form reflection fixture failed")
    if match_path(tx, rx, tx, rx, [(1, triangles[1], faces[1], (0., 4., 1.))])[-1] is None:
        raise ValueError("Disconnected finite-face reflection was accepted")
    y, z = 1., 1.000001
    switch = match_path((1., y, z), (1., y, z), (1., y, z), (1., y, z),
                        [(0, triangles[0], faces[0], (0., y, .999999))])
    if switch[-1] or switch[3] != 1:
        raise ValueError("Face identity should survive a triangulation seam")
    direct = match_path(tx, rx, tx, rx, [])
    if direct[0] != "LOS" or direct[1] != direct[2] or direct[-1]:
        raise ValueError("LoS fixture failed")
    if match_path(tx, rx, tx, rx, [(0, triangles[0], faces[0], (0., 1., 1.))] * 2)[-1] is None:
        raise ValueError("Degenerate repeat on the same face was accepted")
