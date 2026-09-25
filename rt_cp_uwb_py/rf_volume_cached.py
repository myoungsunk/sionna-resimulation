"""Opt-in cached convex clipping; preserves VolumeScene boundary semantics."""
import numpy as np
from .rf_volume_events import VolumeScene
from .rf_junctions import merge_medium_intervals


class CachedPrism:
    def __init__(self, prism):
        self.triangle = prism.triangle
        self.normal = prism.normal
        self.thickness = prism.thickness
        self.material = prism.material
        self.owner = prism.owner
        self._planes = prism.planes()

    def planes(self):
        return self._planes


class CachedVolumeScene(VolumeScene):
    def __init__(self, scene):
        super().__init__([CachedPrism(p) for p in scene.prisms], scene.tolerance,
                         scene.ideal_surfaces)
        self.normals = np.array([[n for n, _ in p.planes()] for p in self.prisms]).reshape(-1, 5, 3)
        self.offsets = np.array([[d for _, d in p.planes()] for p in self.prisms]).reshape(-1, 5)

    def _union_boundary_normal(self, point, direction, prior, medium):
        # Conservative broad phase only. The original scalar implementation
        # still applies its exact tolerance and tangent-cone/edge decision.
        residual = self.normals @ point - self.offsets
        candidates = np.flatnonzero(np.all(residual <= self.tolerance+1e-10, axis=1))
        local = VolumeScene([self.prisms[i] for i in candidates], self.tolerance)
        return local._union_boundary_normal(point, direction, prior, medium)

    def intervals(self, origin, direction):
        if not len(self.prisms):
            return []
        den = self.normals @ direction
        num = self.offsets - self.normals @ origin
        parallel = abs(den) < 1e-14
        t = np.divide(num, den, out=np.zeros_like(num), where=~parallel)
        low = np.max(np.where((den < 0) & ~parallel, t, -np.inf), axis=1)
        high = np.min(np.where((den > 0) & ~parallel, t, np.inf), axis=1)
        ok = (~np.any(parallel & (num < -1e-10), axis=1)
              & (high-low > 1e-10) & np.isfinite(low) & np.isfinite(high))
        return [(float(low[i]), float(high[i]), self.prisms[i].material, self.prisms[i].owner)
                for i in np.flatnonzero(ok)]

    def _next_volume_boundary(self, origin, direction, current_material):
        origin = np.asarray(origin, float); direction = np.asarray(direction, float)
        if not np.isfinite([*origin, *direction]).all() or np.linalg.norm(direction) == 0:
            raise ValueError('INVALID_RAY')
        direction = direction / np.linalg.norm(direction)
        tol = self.tolerance
        intervals = [(max(0., lo), hi, mat, owner)
                     for lo, hi, mat, owner in self.intervals(origin, direction) if hi > tol]
        if not intervals:
            if current_material != 'air':
                raise ValueError('MEDIUM_STATE_NOT_IN_VOLUME')
            return None
        far = max(x[1] for x in intervals)
        ticks = sorted({0., far+1., *[float(x) for r in intervals for x in r[:2]]})
        merge_medium_intervals(intervals, tolerance=tol)
        prior = current_material; first = True
        for lo, hi in zip(ticks, ticks[1:]):
            if hi-lo <= tol:
                continue
            mid = (lo+hi)/2
            materials = {r[2] for r in intervals if r[0] < mid < r[1]}
            if len(materials) > 1:
                raise ValueError('OVERLAPPING_DISTINCT_MEDIA')
            medium = next(iter(materials)) if materials else 'air'
            if first:
                first = False
                if medium != current_material:
                    raise ValueError('MEDIUM_STATE_MISMATCH')
            if medium != prior:
                pos = origin+lo*direction
                normal, owners = self._union_boundary_normal(pos, direction, prior, medium)
                return dict(distance_m=lo, point=pos, normal=normal, from_material=prior,
                            to_material=medium, owners=owners)
            prior = medium
        return None
