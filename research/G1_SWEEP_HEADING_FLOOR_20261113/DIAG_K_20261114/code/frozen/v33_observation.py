"""Stationary XY prior, exact snap-grid lookup and held-out E1 for v3.3."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from functools import partial
from pathlib import Path

import numpy as np

from run_step1 import dump, sha
from v32_filter import fit_e1, training_features, wrap
from v32_observation import GRID, SEEDS, ObservationCase, ObservationInputs

SIGMA_XY = 0.13
RHO_XY = 0.90
INNOVATION_XY = SIGMA_XY * np.sqrt(1.0 - RHO_XY**2)
GRID_CM = np.arange(-30, 31, 5)
XY_AXIS = GRID_CM / 100.0
XY_MIDPOINTS = (GRID_CM[:-1] + GRID_CM[1:]) / 200.0
TRAIN_SEED = 2026111336
ARM = "M1-R"
NODE_FILES = ("J", "MIN_CHI2")


def stationary_xy(rng, n_paths, n_visits):
    """Draw p0, followed by path-local chronological x/y innovations."""
    normals = rng.standard_normal((n_paths, n_visits + 1, 2))
    previous = SIGMA_XY * normals[:, 0]
    xy = np.empty((n_paths, n_visits, 2))
    for k in range(n_visits):
        previous = RHO_XY * previous + INNOVATION_XY * normals[:, k + 1]
        xy[:, k] = previous
    return xy


def snap_xy(xy):
    """Return evaluated XY, lower-midpoint-tie node indices, and direct mask."""
    xy = np.asarray(xy, dtype=np.float64)
    if xy.ndim == 0 or xy.shape[-1] != 2 or not np.isfinite(xy).all():
        raise ValueError("Expected finite (x, y) offsets")
    indices = np.searchsorted(XY_MIDPOINTS, xy, side="left")
    direct = np.any(np.abs(xy) > XY_AXIS[-1], axis=-1)
    evaluated = np.where(direct[..., None], xy, XY_AXIS[indices])
    return evaluated, indices, direct


def snap_summary(xy):
    evaluated, _, direct = snap_xy(xy)
    if direct.ndim != 2 or not direct.size:
        raise ValueError("Expected a nonempty path-by-visit array for G-SNAP")
    offsets = evaluated - xy

    def errors(points):
        if not len(points):
            return None
        return {
            "axis_mean_m": points.mean(axis=0).tolist(),
            "axis_rms_m": np.sqrt(np.mean(points**2, axis=0)).tolist(),
            "axis_abs_p95_m": np.quantile(np.abs(points), .95, axis=0).tolist(),
        }

    n_direct = direct.sum(axis=1)
    return {
        "all_station_quantization": errors(offsets.reshape(-1, 2)),
        "in_grid_quantization": errors(offsets[~direct]),
        "stations": int(direct.size),
        "direct_stations": int(direct.sum()),
        "direct_station_rate": float(direct.mean()),
        "direct_counts_by_path": n_direct.tolist(),
        "direct_path_rate": float((n_direct > 0).mean()),
    }


def projected_sigma(case, group, dx, dy):
    """Project the constant XY prior at the same coordinate as d_geo."""
    g = case.groups[group]
    horizontal = np.hypot(g.x + dx - case.anchor[0], g.y + dy - case.anchor[1])
    distance = np.hypot(horizontal, case.z - case.anchor[2])
    return SIGMA_XY * horizontal / distance


def _curves(case, group, dx, dy, *, seeds=slice(None), yaw_indices=None):
    sigma = projected_sigma(case, group, dx, dy)
    value = next(case.costs_for_axes(group, dx, dy, [sigma], ARM, seeds=seeds,
                                     yaw_indices=yaw_indices))
    return tuple(curve.astype(np.float32) for curve in value)


def _stem(name):
    return f"S1P_{name}_M1R_JOINT"


def _node(case, group, ix, iy):
    return _curves(case, group, XY_AXIS[ix], XY_AXIS[iy])


def build_grid(root, banks, out, name, workers=1):
    """Write J_joint and minimum residual using one independently owned group per task."""
    case = ObservationCase(root, name, banks)
    groups = sorted(case.group_ids)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = _stem(name)
    paths = [out / f"{stem}_{suffix}.npy" for suffix in NODE_FILES]
    index_path = out / f"{stem}_INDEX.json"
    if any(p.exists() for p in [*paths, index_path]):
        raise FileExistsError(f"Refusing to overwrite existing grid {stem}")
    shape = (len(groups), SEEDS, len(XY_AXIS), len(XY_AXIS), len(GRID))
    arrays = [np.lib.format.open_memmap(p, mode="w+", dtype=np.float32, shape=shape)
              for p in paths]

    def fill(item):
        index, group = item
        for ix in range(len(XY_AXIS)):
            for iy in range(len(XY_AXIS)):
                for array, values in zip(arrays, _node(case, group, ix, iy)):
                    array[index, :, ix, iy] = values
        return group

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for complete, group in enumerate(pool.map(fill, enumerate(groups)), 1):
            print(f"{name} grid {complete}/{len(groups)}: group {group}", flush=True)
    for array in arrays:
        array.flush()

    index = {
        "case": name,
        "model": "M1-R(J_joint)",
        "xy": XY_AXIS.tolist(),
        "sigma_xy_m": SIGMA_XY,
        "dtype": "float32",
        "shape": list(shape),
        "axis_order": ["physical_station", "rf_seed", "ix", "iy", "yaw"],
        "groups": [{"group": g, "x": case.groups[g].x, "y": case.groups[g].y,
                    "yaw_deg": case.groups[g].yaw_deg} for g in groups],
        "sigma_d": [[[float(projected_sigma(case, g, dx, dy)) for dy in XY_AXIS]
                     for dx in XY_AXIS] for g in groups],
        "sigma_s0_sq": case.sigma_s0_sq,
        "n_valid": [[case.n_valid(g, seed) for seed in range(SEEDS)] for g in groups],
        "observed_index": [case.taps[:, case.groups[g].ids].tolist() for g in groups],
        "inputs": case.hashes,
        "files": {p.name: sha(p) for p in paths},
    }
    dump(index_path, index)
    return index


def build_stations(root, banks, names):
    """Build the fixed RF row index used by the original selection rules."""
    inputs = ObservationInputs(root, banks)
    stations = {}
    offset = 0
    for name in names:
        case = ObservationCase(inputs, name)
        groups = sorted(case.group_ids)
        count = len(groups) * SEEDS
        stations[name] = {
            "x": np.array([case.groups[g].x for g in groups]),
            "y": np.array([case.groups[g].y for g in groups]),
            "gids": groups,
            "rows": np.arange(offset, offset + count).reshape(len(groups), SEEDS),
        }
        offset += count
    return stations


class CurveBank:
    """Access stored snap nodes or direct curves in an immutable Monte Carlo XY array."""

    def __init__(self, root, banks, grid, stations, xy, mode="snap", workers=1, *,
                 direct_bytes=384 * 1024**2, direct_all_seeds=False):
        if mode not in {"snap", "continuous"}:
            raise ValueError(f"Unknown XY evaluation mode: {mode}")
        self.mode = mode
        self.xy = np.array(xy, dtype=np.float64, copy=True)
        if self.xy.ndim != 3 or self.xy.shape[-1] != 2 or not np.isfinite(self.xy).all():
            raise ValueError("XY paths must be a finite (path, visit, 2) array")
        self.xy.flags.writeable = False
        self.evaluated, self.indices, self.outside = snap_xy(self.xy)
        self.workers = workers
        self._pool = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
        self._all_seeds = direct_all_seeds
        self._budget = direct_bytes
        self._bytes = 0
        self._direct_cache = OrderedDict()
        self.last_direct = np.empty(0, dtype=bool)
        self.nodes_accessed = set()
        self.requests = self.direct_requests = self.direct_calculations = 0
        inputs = ObservationInputs(root, banks)
        self.cases = {name: ObservationCase(inputs, name) for name in stations}
        self.rows = {}
        self.grids = {}
        for name, station in stations.items():
            groups = sorted(self.cases[name].group_ids)
            if sorted(station["gids"]) != groups or len(station["gids"]) != len(groups):
                raise ValueError(f"{name}: incomplete or repeated station IDs")
            if np.shape(station["rows"]) != (len(groups), SEEDS):
                raise ValueError(f"{name}: expected an RF row for each group and seed")
            for group, row_group in zip(station["gids"], station["rows"]):
                for seed, row in enumerate(row_group):
                    if row in self.rows:
                        raise ValueError(f"Duplicate global RF row ID: {row}")
                    self.rows[row] = name, group, seed, self.cases[name].n_valid(group, seed)
            if mode == "snap":
                base = Path(grid) / _stem(name)
                arrays = [np.load(f"{base}_{suffix}.npy", mmap_mode="r", allow_pickle=False)
                          for suffix in NODE_FILES]
                shape = (len(groups), SEEDS, len(XY_AXIS), len(XY_AXIS), len(GRID))
                if any(a.dtype != np.float32 or a.shape != shape for a in arrays):
                    raise ValueError(f"Bad grid shape or dtype for {name}")
                self.grids[name] = {group: i for i, group in enumerate(groups)}, arrays

    def close(self):
        if self._pool is not None:
            self._pool.shutdown()

    def _compute(self, key):
        name, group, dx, dy, seed = key
        seeds = slice(None) if seed is None else slice(seed, seed + 1)
        return _curves(self.cases[name], group, dx, dy, seeds=seeds)

    def _remember(self, key, value):
        size = sum(a.nbytes for a in value)
        if size > self._budget:
            return
        while self._bytes + size > self._budget:
            _, previous = self._direct_cache.popitem(last=False)
            self._bytes -= sum(a.nbytes for a in previous)
        self._direct_cache[key] = value
        self._bytes += size

    def access(self, rows, k, path_indices=None):
        """Return full-yaw J, residual, valid pose counts and RF truth in input order."""
        rows = np.asarray(rows)
        paths = np.arange(len(self.xy)) if path_indices is None else np.asarray(path_indices)
        if (rows.shape != paths.shape or rows.ndim != 1 or paths.dtype.kind not in "iu"
                or np.any(paths < 0) or np.any(paths >= len(self.xy))
                or not 0 <= k < self.xy.shape[1]):
            raise ValueError("Access requires one RF row per valid path at a valid visit")
        costs = np.empty((len(rows), len(GRID)), dtype=np.float64)
        residuals = np.empty_like(costs)
        n_valid = np.empty(len(rows), dtype=int)
        truth = np.empty(len(rows))
        self.last_direct = (self.outside[paths, k].copy() if self.mode == "snap"
                            else np.ones(len(rows), dtype=bool))
        requests = {}
        for index, (row, path) in enumerate(zip(rows, paths)):
            name, group, seed, n_valid[index] = self.rows[row]
            truth[index] = self.cases[name].groups[group].yaw_deg
            if self.last_direct[index]:
                dx, dy = self.xy[path, k]
                key = (name, group, dx, dy, None if self._all_seeds else seed)
                requests.setdefault(key, []).append((index, seed if self._all_seeds else 0))
                continue
            ix, iy = self.indices[path, k]
            groups, arrays = self.grids[name]
            node = (groups[group], seed, ix, iy)
            costs[index], residuals[index] = (array[node] for array in arrays)
            self.nodes_accessed.add((name, group, seed, int(ix), int(iy)))

        def populate(value, positions):
            for index, seed in positions:
                costs[index], residuals[index] = (curve[seed] for curve in value)

        missing = {}
        for key, positions in requests.items():
            value = self._direct_cache.get(key)
            if value is None:
                missing[key] = positions
            else:
                self._direct_cache.move_to_end(key)
                populate(value, positions)
        computed = (map(self._compute, missing) if self._pool is None
                    else self._pool.map(self._compute, missing))
        for (key, positions), value in zip(missing.items(), computed):
            populate(value, positions)
            self._remember(key, value)
        self.requests += len(rows)
        self.direct_requests += int(self.last_direct.sum())
        self.direct_calculations += len(missing)
        expected = n_valid >= 3
        if (not np.isfinite(costs[expected]).all() or not np.isfinite(residuals[expected]).all()
                or not np.isnan(costs[~expected]).all() or not np.isnan(residuals[~expected]).all()):
            raise ValueError("Cost or residual mask differs from the valid-pose rule")
        return costs, residuals, n_valid, truth

    def validate_nodes(self):
        """Independently reevaluate the first 16 sorted unique touched nodes."""
        records = []
        for name, group, seed, ix, iy in sorted(self.nodes_accessed)[:16]:
            case = self.cases[name]
            g, arrays = self.grids[name]
            dx, dy = XY_AXIS[[ix, iy]]
            sigma = projected_sigma(case, group, dx, dy)
            direct64 = next(case.costs_for_axes(group, dx, dy, [sigma], ARM))
            results = {}
            for label, array, curves in zip(NODE_FILES, arrays, direct64):
                stored = array[g[group], seed, ix, iy]
                raw = curves[seed]
                rounded = raw.astype(np.float32)
                finite = np.isfinite(raw)
                results[label] = {
                    "mask_match": bool(np.array_equal(np.isfinite(stored), finite)),
                    "float32_identical": bool(np.array_equal(stored.view(np.uint32),
                                                            rounded.view(np.uint32))),
                    "float64_max_abs": float(np.max(np.abs(raw[finite] - stored[finite]), initial=0.0)),
                }
            records.append(dict(case=name, group=group, seed=seed, ix=ix, iy=iy, arrays=results))
        return {
            "passed": bool(records) and all(result["mask_match"] and result["float32_identical"]
                                           for record in records for result in record["arrays"].values()),
            "unique_nodes_accessed": len(self.nodes_accessed),
            "samples": records,
        }

    def stats(self):
        return dict(requests=self.requests, direct_requests=self.direct_requests,
                    direct_calculations=self.direct_calculations,
                    direct_cache_bytes=self._bytes, unique_nodes_accessed=len(self.nodes_accessed))


def _train_group(item):
    case, group, evaluated = item
    truth = case.groups[group].yaw_deg
    indices = np.flatnonzero(np.abs(wrap(GRID - truth)) <= 12. + 1e-10)
    costs, residuals = (np.full((SEEDS, len(GRID)), np.nan) for _ in range(2))
    for seed, (dx, dy) in enumerate(evaluated):
        cost, residual = _curves(case, group, dx, dy, seeds=slice(seed, seed + 1),
                                 yaw_indices=indices)
        costs[seed, indices], residuals[seed, indices] = cost[0], residual[0]
    counts = [case.n_valid(group, seed) for seed in range(SEEDS)]
    valid = np.asarray(counts) >= 3
    if not np.isfinite(costs[valid][:, indices]).all() or not np.isfinite(residuals[valid][:, indices]).all():
        raise ValueError(f"Nonfinite calibration curves: {case.name}/{group}")
    features = training_features(costs, residuals, counts, truth)
    if len(features.winner_error) != int(valid.sum()):
        raise ValueError(f"Missing aligned calibration winner: {case.name}/{group}")
    return features


def train_loro(root, banks, names, holdout, workers=1):
    """Fit the primary E1 using all eligible training cases and the fixed XY stream."""
    inputs = ObservationInputs(root, banks)
    rng = np.random.Generator(np.random.PCG64(TRAIN_SEED))
    tasks = []
    counts = {}
    for name in sorted(names):
        case = ObservationCase(inputs, name)
        groups = sorted(case.group_ids)
        offsets = rng.normal(0., SIGMA_XY, (len(groups), SEEDS, 2))
        if case.route == holdout:
            continue
        evaluated, _, direct = snap_xy(offsets)
        tasks.extend((case, group, coords) for group, coords in zip(groups, evaluated))
        counts[name] = {"stations": len(groups), "sweeps": len(groups) * SEEDS,
                        "direct_sweeps": int(direct.sum()), "sample_a": 0, "sample_b": 0}

    training = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for (case, _, _), features in zip(tasks, pool.map(_train_group, tasks)):
            counts[case.name]["sample_a"] += len(features.cap_sample)
            counts[case.name]["sample_b"] += len(features.winner_error)
            training.append(features)
    calibration = fit_e1(training)
    return calibration, {"holdout": holdout, "xy_seed": TRAIN_SEED, "training_cases": counts,
                         "calibration": asdict(calibration)}
