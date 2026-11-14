"""M0 grid and held-out E0 for the v3.3 B0 comparison."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from run_step1 import dump, sha
from v32_filter import fit_e0, training_features, wrap
from v32_observation import GRID, SEEDS, ObservationCase, ObservationInputs
from v33_observation import SIGMA_XY, TRAIN_SEED, XY_AXIS, snap_xy

M0_EXCLUDED = frozenset({"R2_aB_m0"})


def _stem(name):
    return f"S1P_{name}_M0"


def _curve(case, group, dx, dy, seeds=slice(None), yaw_indices=None):
    cost, _ = next(case.costs_for_axes(group, dx, dy, [0.], "M0", seeds=seeds,
                                     yaw_indices=yaw_indices))
    return cost.astype(np.float32)


def build_grid(root, banks, out, name, workers=1):
    """Evaluate the M0 LUT at every snap node; J is also the E1 residual."""
    if name in M0_EXCLUDED:
        raise ValueError(f"Excluded by frozen M0 parity: {name}")
    case = ObservationCase(root, name, banks)
    groups = sorted(case.group_ids)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = _stem(name)
    path = out / f"{stem}_J.npy"
    index_path = out / f"{stem}_INDEX.json"
    if path.exists() or index_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing M0 grid: {name}")
    shape = (len(groups), len(XY_AXIS), len(XY_AXIS), SEEDS, len(GRID))
    array = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=shape)

    def fill(item):
        i, group = item
        for ix, dx in enumerate(XY_AXIS):
            for iy, dy in enumerate(XY_AXIS):
                array[i, ix, iy] = _curve(case, group, dx, dy)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(fill, enumerate(groups)):
            pass
    array.flush()
    del array
    index = {
        "case": name, "model": "M0", "dtype": "float32", "shape": list(shape),
        "axis_order": ["physical_station", "ix", "iy", "rf_seed", "yaw"],
        "xy": XY_AXIS.tolist(), "sigma_xy_m": SIGMA_XY, "sigma_s0_sq": case.sigma_s0_sq,
        "groups": [{"group": g, "x": case.groups[g].x, "y": case.groups[g].y,
                    "yaw_deg": case.groups[g].yaw_deg} for g in groups],
        "n_valid": [[case.n_valid(g, seed) for seed in range(SEEDS)] for g in groups],
        "observed_index": [case.taps[:, case.groups[g].ids].tolist() for g in groups],
        "inputs": case.hashes, "files": {path.name: sha(path)},
        "minimum_residual": path.name,
    }
    dump(index_path, index)
    return index


class CurveBank:
    """M0 J and its shared residual on the frozen snap and direct XY paths."""

    def __init__(self, root, banks, grid, stations, xy, workers=1, *,
                 direct_bytes=384 * 1024**2):
        if M0_EXCLUDED.intersection(stations):
            raise ValueError("B0 requires M0-parity-eligible cases")
        self.xy = np.array(xy, dtype=np.float64, copy=True)
        if self.xy.ndim != 3 or self.xy.shape[-1] != 2:
            raise ValueError("XY paths must be a finite (path, visit, 2) array")
        self.xy.flags.writeable = False
        _, self.indices, self.outside = snap_xy(self.xy)
        if direct_bytes < 0:
            raise ValueError("Direct cache byte budget must be nonnegative")
        self._budget = direct_bytes
        self._bytes = 0
        self._cache = OrderedDict()
        self._pool = None
        self.requests = self.direct_requests = self.direct_calculations = 0
        self.last_direct = np.empty(0, dtype=bool)

        inputs = ObservationInputs(root, banks)
        self.cases = {}
        self.grids = {}
        self.rows = {}
        for case_index, (name, station) in enumerate(stations.items()):
            case = self.cases[name] = ObservationCase(inputs, name)
            stem = Path(grid) / _stem(name)
            receipt = json.loads(Path(f"{stem}_INDEX.json").read_bytes())
            groups = [entry["group"] for entry in receipt["groups"]]
            if (groups != sorted(case.group_ids) or sorted(station["gids"]) != groups
                    or list(receipt["xy"]) != XY_AXIS.tolist()
                    or receipt["inputs"] != case.hashes):
                raise ValueError(f"M0 grid identity differs: {name}")
            group_axis = {group: i for i, group in enumerate(groups)}
            shape = (len(groups), len(XY_AXIS), len(XY_AXIS), SEEDS, len(GRID))
            array = np.load(f"{stem}_J.npy", mmap_mode="r", allow_pickle=False)
            if array.dtype != np.float32 or array.shape != shape:
                raise ValueError(f"Bad M0 grid shape or dtype: {name}")
            self.grids[case_index] = (case, array)
            if np.shape(station["rows"]) != (len(groups), SEEDS):
                raise ValueError(f"Expected one row per station and RF seed: {name}")
            for group, row_ids in zip(station["gids"], station["rows"]):
                for seed, row in enumerate(row_ids):
                    if row in self.rows:
                        raise ValueError(f"Duplicate RF row ID: {row}")
                    self.rows[row] = (case_index, group, group_axis[group], seed,
                                      case.n_valid(group, seed), case.groups[group].yaw_deg)
        self._pool = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None

    def close(self):
        if self._pool is not None:
            self._pool.shutdown()
        self.grids.clear()

    def _direct(self, key):
        case_index, group, dx, dy = key
        return _curve(self.grids[case_index][0], group, dx, dy)

    def _remember(self, key, values):
        if values.nbytes > self._budget:
            return
        while self._bytes + values.nbytes > self._budget:
            _, previous = self._cache.popitem(last=False)
            self._bytes -= previous.nbytes
        self._cache[key] = values
        self._bytes += values.nbytes

    def access(self, rows, k, path_indices=None):
        """Return full-yaw (J, J, n_valid, truth) in requested path order."""
        rows = np.asarray(rows)
        paths = np.arange(len(self.xy)) if path_indices is None else np.asarray(path_indices)
        if (rows.shape != paths.shape or rows.ndim != 1 or paths.dtype.kind not in "iu"
                or np.any(paths < 0) or np.any(paths >= len(self.xy))
                or not 0 <= k < self.xy.shape[1]):
            raise ValueError("Access requires a valid path index for each RF row")
        meta = [self.rows[row] for row in rows]
        case_index, group, group_axis, seeds, n_valid = np.array([r[:5] for r in meta], dtype=int).reshape(-1, 5).T
        truth = np.array([r[5] for r in meta])
        costs = np.empty((len(rows), len(GRID)), dtype=np.float64)
        self.last_direct = self.outside[paths, k].copy()
        for case_id in np.unique(case_index[~self.last_direct]):
            pos = np.flatnonzero((case_index == case_id) & ~self.last_direct)
            ix, iy = self.indices[paths[pos], k].T
            array = self.grids[case_id][1]
            costs[pos] = array[group_axis[pos], ix, iy, seeds[pos]]

        missing = {}
        for pos in np.flatnonzero(self.last_direct):
            dx, dy = self.xy[paths[pos], k]
            key = (case_index[pos], group[pos], dx, dy)
            curves = self._cache.get(key)
            if curves is None:
                missing.setdefault(key, []).append(pos)
            else:
                self._cache.move_to_end(key)
                costs[pos] = curves[seeds[pos]]
        calculated = (map(self._direct, missing) if self._pool is None
                      else self._pool.map(self._direct, missing))
        for (key, pos), curves in zip(missing.items(), calculated):
            costs[pos] = curves[seeds[pos]]
            self._remember(key, curves)

        self.requests += len(rows)
        self.direct_requests += int(self.last_direct.sum())
        self.direct_calculations += len(missing)
        expected = n_valid >= 3
        if not np.isfinite(costs[expected]).all() or not np.isnan(costs[~expected]).all():
            raise ValueError("M0 cost mask differs from the valid-pose rule")
        return costs, costs, n_valid, truth

    def stats(self):
        return dict(requests=self.requests, direct_requests=self.direct_requests,
                    direct_calculations=self.direct_calculations, direct_cache_bytes=self._bytes)


def _train_group(item):
    case, group, evaluated = item
    truth = case.groups[group].yaw_deg
    indices = np.flatnonzero(np.abs(wrap(GRID - truth)) <= 12. + 1e-10)
    costs = np.full((SEEDS, len(GRID)), np.nan)
    for seed, (dx, dy) in enumerate(evaluated):
        costs[seed, indices] = _curve(case, group, dx, dy, slice(seed, seed + 1), indices)[0]
    counts = np.array([case.n_valid(group, seed) for seed in range(SEEDS)])
    valid = counts >= 3
    if not np.isfinite(costs[valid][:, indices]).all():
        raise ValueError(f"Nonfinite M0 calibration curves: {case.name}/{group}")
    features = training_features(costs, costs, counts, truth)
    if len(features.winner_error) != int(valid.sum()):
        raise ValueError(f"Missing aligned M0 calibration winner: {case.name}/{group}")
    return features


def train_loro(root, banks, names, holdout, workers=1):
    """Fit B0 E0; include all six M1-eligible names for matched XY draw offsets."""
    inputs = ObservationInputs(root, banks)
    rng = np.random.Generator(np.random.PCG64(TRAIN_SEED))
    tasks = []
    counts = {}
    for name in sorted(names):
        case = ObservationCase(inputs, name)
        groups = sorted(case.group_ids)
        offsets = rng.normal(0., SIGMA_XY, (len(groups), SEEDS, 2))
        if case.route == holdout or name in M0_EXCLUDED:
            continue
        evaluated, _, direct = snap_xy(offsets)
        tasks.extend((case, group, coords) for group, coords in zip(groups, evaluated))
        counts[name] = {"stations": len(groups), "sweeps": len(groups) * SEEDS,
                        "direct_sweeps": int(direct.sum()), "sample_b": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        training = list(pool.map(_train_group, tasks))
    errors = {name: [] for name in counts}
    for (case, _, _), features in zip(tasks, training):
        errors[case.name].append(features.winner_error)
    for name, parts in errors.items():
        values = np.concatenate(parts)
        counts[name]["sample_b"] = int(values.size)
        counts[name]["mean_signed_error_deg"] = float(np.mean(values)) if values.size else None
        counts[name]["fraction_below_minus_5_deg"] = float(np.mean(values < -5.)) if values.size else None
    calibration = fit_e0(training)
    return calibration, {"holdout": holdout, "xy_seed": TRAIN_SEED, "training_cases": counts,
                         "excluded_m0_parity": sorted(M0_EXCLUDED.intersection(names)),
                         "calibration": asdict(calibration)}
