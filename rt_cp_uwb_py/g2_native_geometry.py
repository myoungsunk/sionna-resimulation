"""Reference-sheet geometry for native Sionna slabs, not a volume solver."""
from pathlib import Path

import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon
from shapely.ops import unary_union

POSITION_TOLERANCE = 1e-6
AREA_TOLERANCE = 1e-8


def basis(corners):
    q = np.asarray(corners, dtype=float)
    u = q[1] - q[0]
    u /= np.linalg.norm(u)
    n = np.cross(u, q[-1] - q[0])
    n /= np.linalg.norm(n)
    return q[0], np.array([u, np.cross(n, u), n])


def polygon_from_triangles(triangles, frame):
    o, axes = frame
    return unary_union([Polygon(((t - o) @ axes.T)[:, :2]) for t in triangles])


def clip_coplanar_owners(triangles, corners, owners):
    """Remove only positive-area overlap with a coplanar architectural sheet."""
    frame = basis(corners)
    o, axes = frame
    polygon = polygon_from_triangles(triangles, frame)
    cuts = []
    for owner_id, owner_triangles in owners:
        if not len(owner_triangles):
            continue
        local = (np.asarray(owner_triangles).reshape(-1, 3) - o) @ axes.T
        if np.max(np.abs(local[:, 2])) > POSITION_TOLERANCE:
            continue
        overlap = polygon.intersection(polygon_from_triangles(owner_triangles, frame))
        if overlap.area > AREA_TOLERANCE:
            polygon = polygon.difference(overlap)
            cuts.append(dict(owner_wall_id=owner_id, removed_area_m2=float(overlap.area)))
    if not cuts:
        return np.asarray(triangles).copy(), cuts
    output = []
    for triangle in constrained_delaunay_triangles(polygon).geoms:
        xy = np.asarray(triangle.exterior.coords)[:3]
        q = o + xy[:, :1] * axes[0] + xy[:, 1:2] * axes[1]
        normal = np.cross(q[1] - q[0], q[2] - q[0])
        if np.linalg.norm(normal) / 2 <= 1e-12:
            continue
        output.append(q if normal @ axes[2] > 0 else q[[0, 2, 1]])
    result = np.asarray(output, dtype=float).reshape(-1, 3, 3)
    if polygon_from_triangles(result, frame).symmetric_difference(polygon).area > AREA_TOLERANCE:
        raise ValueError('CLIP_COVERAGE')
    return result, cuts


def hollow_column_thickness(corners, maximum=0.05):
    """Synthetic concrete panels: retain at least half the narrow transverse span as air."""
    points = np.asarray(corners).reshape(-1, 3)
    spans = np.ptp(points, axis=0)
    if np.any(spans <= POSITION_TOLERANCE):
        raise ValueError('COLUMN_REQUIRES_POSITIVE_XYZ_EXTENT')
    # Source columns are vertical and axis-aligned, independently checked by caller.
    return min(float(maximum), float(min(spans[:2])) / 4)


def read_ply(path):
    with Path(path).open(encoding='ascii') as stream:
        if stream.readline().strip() != 'ply' or stream.readline().strip() != 'format ascii 1.0':
            raise ValueError('EXPECTED_ASCII_PLY')
        for line in stream:
            if line.startswith('element vertex'):
                nv = int(line.split()[-1])
            elif line.startswith('element face'):
                nf = int(line.split()[-1])
            elif line.strip() == 'end_header':
                break
        vertices = np.array([[float(x) for x in stream.readline().split()] for _ in range(nv)])
        faces = np.array([[int(x) for x in stream.readline().split()[1:]] for _ in range(nf)], dtype=np.uint32)
    return vertices, faces


def write_ply(path, triangles):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='ascii', newline='\n') as stream:
        stream.write(f'ply\nformat ascii 1.0\nelement vertex {3*len(triangles)}\n'
                     f'property float x\nproperty float y\nproperty float z\nelement face {len(triangles)}\n'
                     'property list uchar int vertex_indices\nend_header\n')
        for triangle in triangles:
            for vertex in triangle:
                stream.write(' '.join(format(float(x), '.17g') for x in vertex) + '\n')
        for i in range(len(triangles)):
            stream.write(f'3 {3*i} {3*i+1} {3*i+2}\n')
