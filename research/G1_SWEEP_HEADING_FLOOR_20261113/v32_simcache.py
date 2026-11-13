"""Exact, bounded curve reuse for paired v3.2 bootstrap paths."""

from collections import OrderedDict

import numpy as np

from v32_observation import GridCase, ObservationCase, ObservationInputs
from run_step1 import GRID


class _CurveCache:
    def __init__(self, budget):
        self.budget = budget
        self.bytes = 0
        self.evicted = 0
        self.items = OrderedDict()

    def get(self, key):
        value = self.items.get(key)
        if value is not None:
            self.items.move_to_end(key)
        return value

    def put(self, key, value):
        size = sum(x.nbytes for x in value)
        if size > self.budget:
            return
        while self.bytes + size > self.budget:
            _, old = self.items.popitem(last=False)
            self.bytes -= sum(x.nbytes for x in old)
            self.evicted += 1
        self.items[key] = value
        self.bytes += size


class CurveBank:
    """Look up actual RF group/seed selections at fixed Monte Carlo XY draws.

    Cache keys refer to this bank's immutable XY path IDs and visit indices,
    so a shared DR/XY path uses identical curves across bootstrap repeats.
    `access` accepts an optional subset or reordering of those path IDs.
    The bank retains the original observation/interpolation precision.
    """

    def __init__(self, root, banks, grid, stations, xy, arm="M1-R", *,
                 direct_bytes=4 * 1024**3, interp_bytes=512 * 1024**2):
        self.xy = np.array(xy, dtype=np.float64, copy=True)
        if self.xy.ndim != 3 or self.xy.shape[-1] != 2 or not np.isfinite(self.xy).all():
            raise ValueError("XY paths must be a finite (path, visit, 2) array")
        self.xy.flags.writeable = False
        self.arm = arm
        if direct_bytes < 0 or interp_bytes < 0:
            raise ValueError("Cache byte budgets must be nonnegative")
        inputs = ObservationInputs(root, banks)
        self.cases = {name: ObservationCase(inputs, name) for name in stations}
        self.grids = {name: GridCase(grid, name, arm) for name in stations}
        self.rows = {}
        for name, s in stations.items():
            row_ids = np.asarray(s["rows"])
            groups = np.asarray(s["gids"])
            if row_ids.shape != (len(groups), 20):
                raise ValueError(f"{name}: expected one global row ID per group and RF seed")
            for group, row_group in zip(groups, row_ids):
                truth = self.cases[name].groups[group].yaw_deg
                for seed, row in enumerate(row_group):
                    if row in self.rows:
                        raise ValueError(f"Duplicate global RF row ID: {row}")
                    n = self.cases[name].n_valid(group, seed)
                    self.rows[row] = name, group, seed, n, truth
        self._direct = _CurveCache(direct_bytes)
        self._interp = _CurveCache(interp_bytes)
        self.last_direct = np.empty(0, dtype=bool)
        self._counts = dict(requests=0, direct_requests=0, direct_geometries=0,
                            direct_hits=0, interpolated_hits=0, interpolated_computed=0)

    def stats(self):
        return dict(self._counts, direct_cache_bytes=self._direct.bytes,
                    interp_cache_bytes=self._interp.bytes,
                    direct_evictions=self._direct.evicted, interp_evictions=self._interp.evicted)

    def access(self, rows, k, path_indices=None):
        """Return (J, minimum-node chi², n_valid, truth) in input row order.

        `k` is the zero-based curve accessor index. The first measurement
        follows the first DR increment, so the projection uses station k+1.
        `xy[:, k]` supplies that measurement's XY draw.
        """
        rows = np.asarray(rows)
        paths = np.arange(len(self.xy)) if path_indices is None else np.asarray(path_indices)
        if (rows.shape != paths.shape or rows.ndim != 1 or paths.dtype.kind not in "iu"
                or np.any(paths < 0) or np.any(paths >= len(self.xy))
                or not 0 <= k < self.xy.shape[1]):
            raise ValueError("Access needs one RF row per valid path ID at a valid visit")
        dx, dy = self.xy[paths, k].T
        n_valid = np.empty(len(rows), dtype=int)
        truth = np.empty(len(rows))
        j = np.empty((len(rows), len(GRID)))
        residual = np.empty_like(j)
        by_case = {name: [] for name in self.cases}
        for pos, row in enumerate(rows):
            name, group, seed, n_valid[pos], truth[pos] = self.rows[row]
            by_case[name].append((pos, group, seed))

        self.last_direct = np.zeros(len(rows), dtype=bool)
        for name, selected in by_case.items():
            if not selected:
                continue
            case = self.cases[name]
            grid = self.grids[name]
            pos, groups, seeds = np.asarray(selected, dtype=int).T
            # The group-specific projection uses the same XY as interpolation.
            sigma = np.array([case.projected_sigma(g, k + 1, dx[p], dy[p])
                              for p, g in zip(pos, groups)])
            use_grid = grid.in_bounds(dx[pos], dy[pos], sigma)
            self.last_direct[pos] = ~use_grid
            missing_interp = {}
            for i, p in enumerate(pos):
                if use_grid[i]:
                    key = (k, paths[p], rows[p])
                    value = self._interp.get(key)
                    if value is None:
                        missing_interp.setdefault(key, []).append(i)
                    else:
                        j[p], residual[p] = value
                        self._counts["interpolated_hits"] += 1
                else:
                    key = (k, paths[p], name, groups[i])
                    value = self._direct.get(key)
                    if value is None:
                        value = next(case.costs_for_axes(groups[i], dx[p], dy[p], [sigma[i]], self.arm))
                        self._direct.put(key, value)
                        self._counts["direct_geometries"] += 1
                    else:
                        self._counts["direct_hits"] += 1
                    j[p] = value[0][seeds[i]]
                    residual[p] = value[1][seeds[i]]
            if missing_interp:
                first = np.array([indices[0] for indices in missing_interp.values()])
                p = pos[first]
                cost, chi2 = grid.interpolate_batch(groups[first], seeds[first], dx[p], dy[p], sigma[first])
                for i, (key, indices) in enumerate(missing_interp.items()):
                    value = cost[i].copy(), chi2[i].copy()
                    self._interp.put(key, value)
                    j[pos[indices]], residual[pos[indices]] = value
                self._counts["interpolated_computed"] += len(first)
                self._counts["interpolated_hits"] += sum(len(v) - 1 for v in missing_interp.values())

        self._counts["requests"] += len(rows)
        self._counts["direct_requests"] += int(self.last_direct.sum())
        return j, residual, n_valid, truth
