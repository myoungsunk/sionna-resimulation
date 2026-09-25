from __future__ import annotations

from itertools import product

import numpy as np

from .core import C0, PathRecord, Scene, Surface, normalize


def _reflect_point(point: np.ndarray, surface: Surface) -> np.ndarray:
    p = np.asarray(point, dtype=float)
    return p - 2.0 * float(np.dot(p - surface.point, surface.normal)) * surface.normal


def _line_plane_intersection(a: np.ndarray, b: np.ndarray, surface: Surface):
    ab = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    denom = float(np.dot(ab, surface.normal))
    if abs(denom) <= 1e-9:
        return None
    t = float(np.dot(surface.point - a, surface.normal) / denom)
    return np.asarray(a, dtype=float) + t * ab


def _segment_plane_intersection(a: np.ndarray, b: np.ndarray, surface: Surface, eps: float):
    ab = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    denom = float(np.dot(ab, surface.normal))
    if abs(denom) <= eps:
        return None
    t = float(np.dot(surface.point - a, surface.normal) / denom)
    if t < -eps or t > 1.0 + eps:
        return None
    hit = np.asarray(a, dtype=float) + t * ab
    if not surface.contains_point(hit, eps=max(eps, 1e-7)):
        return None
    if eps < t < 1.0 - eps:
        return hit
    return None


def _segment_blocked(a: np.ndarray, b: np.ndarray, scene: Scene, eps: float = 1e-7) -> bool:
    for surface in scene.surfaces:
        hit = _segment_plane_intersection(a, b, surface, eps)
        if hit is None:
            continue
        return True
    return False


def _enumerate_sequences(num_surfaces: int, bounce_count: int):
    if bounce_count == 0:
        yield tuple()
        return
    for seq in product(range(num_surfaces), repeat=bounce_count):
        if any(seq[i] == seq[i - 1] for i in range(1, len(seq))):
            continue
        yield seq


def _construct_points_source_images(tx: np.ndarray, rx: np.ndarray, surfaces: tuple[Surface, ...]):
    if not surfaces:
        return [tx, rx]
    images = [tx]
    for surface in surfaces:
        images.append(_reflect_point(images[-1], surface))
    target = rx
    refl = [None] * len(surfaces)
    for idx in range(len(surfaces) - 1, -1, -1):
        hit = _line_plane_intersection(images[idx + 1], target, surfaces[idx])
        if hit is None:
            return None
        refl[idx] = hit
        target = hit
    return [tx, *refl, rx]


def _construct_points_receiver_images(tx: np.ndarray, rx: np.ndarray, surfaces: tuple[Surface, ...]):
    if not surfaces:
        return [tx, rx]
    images = [rx]
    for surface in reversed(surfaces):
        images.append(_reflect_point(images[-1], surface))
    points = [tx]
    current = tx
    for idx, surface in enumerate(surfaces):
        hit = _line_plane_intersection(current, images[len(surfaces) - idx], surface)
        if hit is None:
            return None
        points.append(hit)
        current = hit
    points.append(rx)
    return points


def _path_key(points: list[np.ndarray], surface_ids: tuple[int, ...], tol_m: float = 1e-6) -> tuple:
    q = tuple(tuple(int(round(float(c) / tol_m)) for c in p) for p in points[1:-1])
    return surface_ids, q


def enumerate_paths(scene: Scene, tx_pos: np.ndarray, rx_pos: np.ndarray, max_reflections: int) -> list[PathRecord]:
    tx = np.asarray(tx_pos, dtype=float).reshape(3)
    rx = np.asarray(rx_pos, dtype=float).reshape(3)
    max_reflections = max(0, int(round(max_reflections)))
    out: list[PathRecord] = []
    seen: set[tuple] = set()
    for bounce_count in range(max_reflections + 1):
        for seq_idx in _enumerate_sequences(len(scene.surfaces), bounce_count):
            surfaces = tuple(scene.surfaces[i] for i in seq_idx)
            points = _construct_points_source_images(tx, rx, surfaces)
            if points is None:
                points = _construct_points_receiver_images(tx, rx, surfaces)
            if points is None:
                continue
            if any(np.linalg.norm(points[i + 1] - points[i]) <= 1e-9 for i in range(len(points) - 1)):
                continue
            if any(not s.contains_point(points[i + 1], eps=1e-6) for i, s in enumerate(surfaces)):
                continue
            if any(_segment_blocked(points[i], points[i + 1], scene) for i in range(len(points) - 1)):
                continue
            key = _path_key(points, tuple(s.surface_id for s in surfaces))
            if key in seen:
                continue
            seen.add(key)
            length = float(sum(np.linalg.norm(points[i + 1] - points[i]) for i in range(len(points) - 1)))
            inc = []
            normals = []
            for i, surface in enumerate(surfaces):
                kin = normalize(points[i + 1] - points[i])
                normal = surface.normal
                if float(np.dot(kin, normal)) > 0:
                    normal = -normal
                normals.append(normal)
                inc.append(float(np.arccos(np.clip(-float(np.dot(kin, normal)), 0.0, 1.0))))
            out.append(
                PathRecord(
                    points=tuple(np.asarray(p, dtype=float) for p in points),
                    surface_ids=tuple(s.surface_id for s in surfaces),
                    surface_names=tuple(s.name for s in surfaces),
                    materials=tuple(s.material for s in surfaces),
                    bounce_count=bounce_count,
                    path_length_m=length,
                    delay_s=length / C0,
                    launch_dir=normalize(points[1] - points[0]),
                    arrival_dir=normalize(points[-1] - points[-2]),
                    incidence_angles_rad=tuple(inc),
                    normals=tuple(normals),
                )
            )
    out.sort(key=lambda p: (p.delay_s, p.surface_ids))
    return out
