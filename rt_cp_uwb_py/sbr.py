"""Shooting-and-Bouncing-Rays (SBR) path finder — drop-in for trace.enumerate_paths.

설계: 이 프로젝트의 scene은 유한 평면 사각형 집합이므로, SBR을 두 단계 하이브리드로
구현한다.
  (1) 발견(discovery): tx에서 ray 다발을 방출해 표면에 정반사로 튕기며(max_depth),
      각 ray가 지나간 표면 시퀀스를 수집한다. — 조합 열거 대신 '실제로 도달 가능한'
      시퀀스만 발견하므로 표면 수·반사차수가 커져도 확장된다(SBR의 본질 이점).
  (2) 폐합(closure): 발견된 각 시퀀스를 image-method로 정확히 닫아(trace.py 재사용)
      정확한 반사점·PathRecord를 만든다. → build_channel 물리(Fresnel·handedness)가
      enumerate_paths와 완전 동일.

시그니처는 enumerate_paths와 호환 (sweep.py:650에서 1줄 스위치). 향후 비평면/확산
확장 시 (2)의 폐합을 근사 폐합으로 바꾸거나 (1)에서 산란 ray를 추가하면 된다.
"""
from __future__ import annotations

import numpy as np

from .core import C0, PathRecord, Scene, normalize
from .trace import (
    _construct_points_receiver_images,
    _construct_points_source_images,
    _path_key,
    _segment_blocked,
)


def _fibonacci_sphere(n: int) -> np.ndarray:
    """n개의 준균일 단위 방향 (결정론)."""
    i = np.arange(n, dtype=float) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)
    theta = np.pi * (1.0 + 5.0 ** 0.5) * i
    return np.column_stack([np.sin(phi) * np.cos(theta),
                            np.sin(phi) * np.sin(theta),
                            np.cos(phi)])


def _nearest_hit(origin: np.ndarray, direction: np.ndarray, scene: Scene,
                 exclude_id, eps: float = 1e-7):
    """ray(origin + t·dir, t>eps)의 최근접 유한-사각형 교차."""
    best_t, best_surf = np.inf, None
    for s in scene.surfaces:
        if exclude_id is not None and s.surface_id == exclude_id:
            continue
        denom = float(np.dot(direction, s.normal))
        if abs(denom) <= eps:
            continue
        t = float(np.dot(s.point - origin, s.normal) / denom)
        if t <= eps or t >= best_t:
            continue
        hit = origin + t * direction
        if s.contains_point(hit, eps=1e-7):
            best_t, best_surf = t, s
    return best_surf, best_t


def _shoot_from(origin0: np.ndarray, scene: Scene, max_depth: int,
                dirs: np.ndarray, id2idx: dict) -> set[tuple[int, ...]]:
    seqs: set[tuple[int, ...]] = set()
    for d in dirs:
        origin = origin0.copy()
        direction = normalize(d)
        chain: list[int] = []
        last_id = None
        for _ in range(max_depth):
            surf, t = _nearest_hit(origin, direction, scene, exclude_id=last_id)
            if surf is None:
                break
            chain.append(id2idx[surf.surface_id])
            seqs.add(tuple(chain))
            hit = origin + t * direction
            n = surf.normal
            direction = normalize(direction - 2.0 * float(np.dot(direction, n)) * n)
            origin = hit
            last_id = surf.surface_id
    return seqs


def discover_sequences(scene: Scene, tx: np.ndarray, max_depth: int, n_rays: int,
                       rx: np.ndarray | None = None) -> set[tuple[int, ...]]:
    """ray 다발로 표면 index 시퀀스 발견 (직접경로 () 포함).

    rx 지정 시 **양방향**(tx·rx 양단 발사) — dense scene의 forward-shooting 사각을
    보완. rx에서 발견한 시퀀스는 역순으로 뒤집어 union (image 폐합은 순서 무관 검증)."""
    id2idx = {s.surface_id: i for i, s in enumerate(scene.surfaces)}
    seqs: set[tuple[int, ...]] = {tuple()}
    if max_depth <= 0 or not scene.surfaces:
        return seqs
    dirs = _fibonacci_sphere(n_rays)
    seqs |= _shoot_from(tx, scene, max_depth, dirs, id2idx)
    if rx is not None:
        for s in _shoot_from(rx, scene, max_depth, dirs, id2idx):
            seqs.add(tuple(reversed(s)))
    return seqs


def _build_record(scene: Scene, tx: np.ndarray, rx: np.ndarray,
                  seq_idx: tuple[int, ...], seen: set) -> PathRecord | None:
    """발견 시퀀스를 image-method로 정확 폐합 → 검증된 PathRecord (trace.py 로직 동일)."""
    surfaces = tuple(scene.surfaces[i] for i in seq_idx)
    points = _construct_points_source_images(tx, rx, surfaces)
    if points is None:
        points = _construct_points_receiver_images(tx, rx, surfaces)
    if points is None:
        return None
    if any(np.linalg.norm(points[i + 1] - points[i]) <= 1e-9 for i in range(len(points) - 1)):
        return None
    if any(not s.contains_point(points[i + 1], eps=1e-6) for i, s in enumerate(surfaces)):
        return None
    if any(_segment_blocked(points[i], points[i + 1], scene) for i in range(len(points) - 1)):
        return None
    key = _path_key(points, tuple(s.surface_id for s in surfaces))
    if key in seen:
        return None
    seen.add(key)
    length = float(sum(np.linalg.norm(points[i + 1] - points[i]) for i in range(len(points) - 1)))
    inc, normals = [], []
    for i, surface in enumerate(surfaces):
        kin = normalize(points[i + 1] - points[i])
        normal = surface.normal
        if float(np.dot(kin, normal)) > 0:
            normal = -normal
        normals.append(normal)
        inc.append(float(np.arccos(np.clip(-float(np.dot(kin, normal)), 0.0, 1.0))))
    return PathRecord(
        points=tuple(np.asarray(p, dtype=float) for p in points),
        surface_ids=tuple(s.surface_id for s in surfaces),
        surface_names=tuple(s.name for s in surfaces),
        materials=tuple(s.material for s in surfaces),
        bounce_count=len(surfaces),
        path_length_m=length,
        delay_s=length / C0,
        launch_dir=normalize(points[1] - points[0]),
        arrival_dir=normalize(points[-1] - points[-2]),
        incidence_angles_rad=tuple(inc),
        normals=tuple(normals),
    )


def sbr_paths(scene: Scene, tx_pos: np.ndarray, rx_pos: np.ndarray,
              max_reflections: int, *, n_rays: int = 20000,
              bidirectional: bool = True) -> list[PathRecord]:
    """enumerate_paths 대체 (동일 시그니처 + n_rays). ray 발견 → image 폐합.

    bidirectional=True: tx·rx 양단에서 발사(dense scene 사각 보완; 권장 기본)."""
    tx = np.asarray(tx_pos, dtype=float).reshape(3)
    rx = np.asarray(rx_pos, dtype=float).reshape(3)
    max_depth = max(0, int(round(max_reflections)))
    seqs = discover_sequences(scene, tx, max_depth, n_rays,
                              rx=rx if bidirectional else None)
    seen: set = set()
    out: list[PathRecord] = []
    for seq in sorted(seqs, key=lambda s: (len(s), s)):
        rec = _build_record(scene, tx, rx, seq, seen)
        if rec is not None:
            out.append(rec)
    out.sort(key=lambda p: (p.delay_s, p.surface_ids))
    return out
