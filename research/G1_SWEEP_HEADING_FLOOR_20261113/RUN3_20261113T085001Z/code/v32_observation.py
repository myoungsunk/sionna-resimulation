"""G1-MODEL-001 v3.2 primary RF observations and sweep cost cache."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.special import logsumexp

from run_step1 import BLOCK, GRID, LUT, dump, get_groups, get_selections, sha, wrap


BANK_SHA256 = {
    "LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
    "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
}
PRIMARY_IMU_K = .0085
SEEDS = 20
XY_AXIS = np.linspace(-.3, .3, 7)
SIGMA_AXIS = np.array([0., .03, .06, .09, .12, .16])
NODES, WEIGHTS = np.polynomial.hermite.hermgauss(5)
LOG_WEIGHTS = np.log(WEIGHTS / np.sqrt(np.pi))


@dataclass(frozen=True)
class Sweep:
    x: float
    y: float
    yaw_deg: float
    ids: np.ndarray
    relative: np.ndarray


def cost_curves(observed, predictions, variance, log_weights):
    """Return -2 log marginal likelihood (up to a constant) and best-node SSE/variance."""
    observed = np.asarray(observed)
    valid = np.isfinite(observed)
    observed = np.where(valid, observed, 0.)
    # Contract all valid pose errors for each *common* distance node.
    # Using the Gram expansion avoids a large node×seed×yaw×pose temporary.
    squared_error = (
        (observed**2).sum(axis=-1)[None, :, None]
        - 2 * np.einsum("gyp,sp->gsy", predictions, observed, optimize=True)
        + np.einsum("gyp,sp->gsy", predictions**2, valid, optimize=True)
    )
    normalized = np.maximum(squared_error, 0.) / variance
    chi2_min = normalized.min(axis=0)
    cost = chi2_min - 2 * logsumexp(
        log_weights[:, None, None] - .5 * (normalized - chi2_min), axis=0
    )
    insufficient = valid.sum(axis=-1) < 3
    cost[insufficient] = np.nan
    chi2_min[insufficient] = np.nan
    return cost, chi2_min


class ObservationInputs:
    """Pinned observation code and inputs shared by multiple cases in one process."""

    def __init__(self, root, banks_dir=None):
        self.root = Path(root)
        self.block = self.root / BLOCK / "BLOCK_C"
        sys.path.insert(0, str(self.root / LUT / "retrieved/source/src"))
        from qclean_uwb.drivesim import hs_lut, observation, pattern_apply

        self.hs, self.obs, self.pattern = hs_lut, observation, pattern_apply
        self.freqs = np.load(self.root / BLOCK / "freqs_hz.npy", allow_pickle=False)
        self.df = float(self.freqs[1] - self.freqs[0])
        self.cases = {c["case"]: c for c in json.loads((self.block / "CASES.json").read_bytes())}
        self.banks = []
        for name, expected in BANK_SHA256.items():
            path = Path(banks_dir or root) / name
            if sha(path) != expected:
                raise ValueError(f"FFD bank hash mismatch: {path}")
            with np.load(path, allow_pickle=False) as z:
                self.banks.append(pattern_apply.Bank(dict(z)))
        if not all(np.array_equal(self.freqs, f) for f in
                   [np.load(self.block / "freqs_hz.npy", allow_pickle=False),
                    *(bank.freqs_hz for bank in self.banks)]):
            raise ValueError("Frequency bins differ between BLOCK_C and FFD banks")
        self.lut = hs_lut.HsLut(dict(
            theta_deg=np.arange(0., 91., 2.), phi_deg=np.arange(-180., 180., 2.),
            s=np.load(self.root / LUT / "INPUTS/hs_lut_2deg.npy", allow_pickle=False),
        ))

        # Bank.sample clips its periodic phase coordinate to the supplied grid;
        # its exact linear segments end at these knots, plus the wrap boundary.
        a, b = self.banks
        if not np.array_equal(a.phi, b.phi):
            raise ValueError("FFD banks have different azimuth knots")
        self.phi_knots = a.p0 + a.dp * np.arange(a.np)
        if self.phi_knots[-1] > a.p0 + 2*np.pi + 1e-12:
            raise ValueError("FFD azimuth grid exceeds one turn")

    def channel_knots(self, unit, indices=None):
        """LOS frequency response at each RX azimuth knot, before propagation."""
        rx_direction = -unit
        tx_theta = np.array([np.arccos(np.clip(unit[2], -1., 1.))])
        tx_phi = np.array([np.arctan2(unit[1], unit[0])])
        tx_field = self.pattern.field_world(
            self.banks[0], self.hs.ANCHOR_ROTATION, tx_theta, tx_phi,
        )[:, 0, :]
        phi = self.phi_knots.copy()
        if phi[-1] >= phi[0] + 2*np.pi - 1e-12:
            phi[-1] = np.nextafter(phi[0] + 2*np.pi, phi[0])
        if indices is not None:
            phi = phi[indices]
        rx_theta = np.full(len(phi), np.arccos(np.clip(rx_direction[2], -1., 1.)))
        rx_az = np.arctan2(rx_direction[1], rx_direction[0])
        world_theta, world_phi = self.pattern.sph_basis(rx_theta[:1], np.array([rx_az]))
        # The antenna-frame spherical vectors rotate to the same world vectors
        # at every yaw. Only the bank coefficients depend on local azimuth.
        projections = np.column_stack((tx_field @ world_theta[0], tx_field @ world_phi[0]))
        rx = []
        for bank in self.banks:
            eth, eph = bank.sample(rx_theta, phi)
            rx.append(self.pattern.SCALE * (
                eth * projections[:, :1] + eph * projections[:, 1:]
            ).T)
        return np.stack(rx, axis=-1)

    def azimuth_interpolation(self, unit, antenna_yaw_deg):
        bank = self.banks[0]
        rx_az = np.arctan2(-unit[1], -unit[0])
        phi = rx_az - np.radians(antenna_yaw_deg)
        local = phi - bank.p0
        local -= np.floor(local / (2*np.pi)) * (2*np.pi)
        pos = np.clip(local / bank.dp, 0., bank.np - 1.)
        lower = np.minimum(pos.astype(np.intp), bank.np - 2)
        return lower, pos - lower

    def s_at_distance(self, knot_channel, d_m, lower, alpha):
        """Interpolate exact complex CIRs, then run the pinned first-path rule."""
        if d_m <= 0.:
            raise ValueError(f"Nonpositive quadrature distance: {d_m}")
        phase = np.exp(-2j * np.pi * self.freqs * d_m / self.hs.C0)
        scale = self.hs.C0 / self.freqs / (4*np.pi*d_m)
        cir = self.obs.cir_batch(knot_channel * (phase * scale)[None, :, None])
        n_tap = cir.shape[1]
        # Most tap power is concentrated around the geometric first path. The
        # convex endpoint bound certifies both branch peaks and leading taps.
        center = round(d_m * n_tap * self.df / self.hs.C0)
        lo, hi = max(0, center - 10), min(n_tap, center + 14)
        if lo >= hi:
            return self._full_cir_s(cir, lower, alpha)
        tail_bound = np.zeros((len(cir), 2))
        if lo:
            tail_bound = np.maximum(tail_bound, np.abs(cir[:, :lo]).max(axis=1))
        if hi < n_tap:
            tail_bound = np.maximum(tail_bound, np.abs(cir[:, hi:]).max(axis=1))
        local = cir[lower, lo:hi] + alpha[:, None, None] * (
            cir[lower + 1, lo:hi] - cir[lower, lo:hi]
        )
        measured = self.obs.first_path_batch(local, self.df)
        outside = np.maximum(tail_bound[lower], tail_bound[lower + 1]).max(axis=-1)
        needs_full = outside >= self.obs.LEADING_EDGE * measured["peak"] * (1. - 1e-12)
        measured["s"][needs_full] = self._full_cir_s(cir, lower[needs_full], alpha[needs_full])
        return measured["s"]

    def _full_cir_s(self, cir, lower, alpha):
        values = np.empty(len(lower))
        for start in range(0, len(lower), 512):
            sub = slice(start, start + 512)
            i = lower[sub]
            full = cir[i] + alpha[sub, None, None] * (cir[i + 1] - cir[i])
            values[sub] = self.obs.first_path_batch(full, self.df)["s"]
        return values


class ObservationCase:
    """A BLOCK_C case with primary RF draws, exact observations and gate checks."""

    def __init__(self, root, name, banks_dir=None):
        self.inputs = root if isinstance(root, ObservationInputs) else ObservationInputs(root, banks_dir)
        self.root = self.inputs.root
        self.name = name
        c = self.inputs.cases[name]
        self.route = name.split("_")[0]
        self.anchor = np.asarray(c["anchor_xyz"])
        self.z = float(c["robot_z"])
        self.mount = float(c["mount_deg"])
        block = self.inputs.block
        paths = [block / "FULL_RF" / f"H_{name}.npy", block / f"H_LoS_{name}.npy",
                 block / name / "SAMPLES.json"]
        self.hashes = {k: sha(p) for k, p in
                       zip(("input_H_sha256", "H_sha256", "samples_sha256"), paths)}
        if any(c[k] != v for k, v in self.hashes.items()) or (
            self.hashes["samples_sha256"] != c["input_rf_poses_sha256"]
        ):
            raise ValueError(f"BLOCK_C input identity mismatch: {name}")
        full, los = (np.load(p, allow_pickle=False) for p in paths[:2])
        samples = json.loads(paths[2].read_bytes())
        expected_shape = (len(samples), len(self.inputs.freqs), 2, 2)
        if full.shape != expected_shape or los.shape != expected_shape or (
            [r["pose_id"] for r in samples] != list(range(len(samples)))
        ):
            raise ValueError(f"BLOCK_C input shape or pose order mismatch: {name}")
        self.x, self.y, self.yaw = (np.array([r[k] for r in samples]) for k in ("x", "y", "yaw_body_deg"))
        self.all_groups = get_groups(samples)
        self.groups = {}
        for group, ids in enumerate(self.all_groups):
            rel, cuts = get_selections(self.yaw[ids])
            if cuts[0][0] == 90:
                first = ids[0]
                self.groups[group] = Sweep(self.x[first], self.y[first], self.yaw[first], ids, rel)
        if not self.groups:
            raise ValueError(f"No full-span stations: {name}")
        self.los_clean = self.inputs.obs.observe(los, self.inputs.freqs, None, None, tx=0)["s"]
        self.full_clean = self.inputs.obs.observe(full, self.inputs.freqs, None, None, tx=0)["s"]
        nv = self.inputs.obs.noise_var_from_snr(30)
        obs, tap, los_noisy = [], [], []
        for seed in range(SEEDS):
            rng = np.random.default_rng(seed)
            draw = self.inputs.obs.observe(full, self.inputs.freqs, nv, rng, tx=0)
            obs.append(draw["s"])
            tap.append(draw["index"])
            los_noisy.append(self.inputs.obs.observe(los, self.inputs.freqs, nv, rng, tx=0)["s"])
        self.observed, self.taps = np.asarray(obs), np.asarray(tap)
        self.sigma_s0_sq = float(np.nanmedian(np.nanvar(los_noisy, axis=0, ddof=1)))
        if not np.isfinite(self.sigma_s0_sq) or self.sigma_s0_sq <= 0:
            raise ValueError(f"Invalid thermal variance: {name}: {self.sigma_s0_sq}")

    @property
    def group_ids(self):
        return tuple(self.groups)

    def n_valid(self, group, seed):
        return int(np.isfinite(self.observed[seed, self.groups[group].ids]).sum())

    def projected_sigma(self, group, k, dx=0., dy=0.):
        g = self.groups[group]
        rho_h = np.hypot(g.x + dx - self.anchor[0], g.y + dy - self.anchor[1])
        d = np.hypot(rho_h, self.z - self.anchor[2])
        return np.sqrt(.1**2 + np.asarray(k) * .03**2) * rho_h / d

    def _node_predictions(self, group, dx, dy, sigma_values, imu_k, yaw_deg):
        g = self.groups[group]
        rel = g.relative + imu_k * np.abs(g.relative)
        yaw = yaw_deg[:, None] + rel
        xyz = np.array([g.x + dx, g.y + dy, self.z])
        v = xyz - self.anchor
        d = np.linalg.norm(v)
        unit = v / d
        lower, alpha = self.inputs.azimuth_interpolation(unit, (yaw + self.mount).ravel())
        # The sparse validation only uses a bounded heading window. Retain all
        # knots bracketing that subset, preserving indices for every adjacent pair.
        knots = np.union1d(lower, lower + 1)
        channel = self.inputs.channel_knots(unit, knots)
        lower = np.searchsorted(knots, lower)
        predictions = {}
        for sigma in sigma_values:
            distances = [d] if sigma == 0 else d + np.sqrt(2.) * sigma * NODES
            rows = []
            for distance in distances:
                # The central Hermite node is shared across every sigma value.
                if distance not in predictions:
                    predictions[distance] = self.inputs.s_at_distance(
                        channel, distance, lower, alpha,
                    ).reshape(yaw.shape)
                rows.append(predictions[distance])
            yield np.asarray(rows), np.zeros(1) if sigma == 0 else LOG_WEIGHTS

    def costs_for_axes(self, group, dx, dy, sigma_values, arm, *, seeds=slice(None),
                       imu_k=PRIMARY_IMU_K, clean=False, yaw_indices=None):
        g = self.groups[group]
        observed = self.los_clean[None, g.ids] if clean else self.observed[seeds][:, g.ids]
        variance = 1e-8 if clean else self.sigma_s0_sq
        yaw_deg = GRID if yaw_indices is None else GRID[yaw_indices]
        if arm == "M0":
            yaw = yaw_deg[:, None] + g.relative + imu_k * np.abs(g.relative)
            pred = self.inputs.hs.s_model(self.inputs.lut, self.anchor, self.z, g.x + dx, g.y + dy,
                                          np.radians(yaw), self.mount)
            costs = cost_curves(observed, pred[None], variance, np.zeros(1))
            for _ in sigma_values:
                yield costs
        elif arm == "M1-R":
            for prediction, log_weights in self._node_predictions(group, dx, dy, sigma_values, imu_k,
                                                                 yaw_deg):
                yield cost_curves(observed, prediction, variance, log_weights)
        else:
            raise ValueError(f"Unknown primary arm: {arm}")

    def direct(self, group, seed, dx, dy, sigma, arm="M1-R"):
        cost, residual = next(self.costs_for_axes(group, dx, dy, [sigma], arm,
                                                  seeds=slice(seed, seed + 1)))
        return cost[0], residual[0]

    def parity(self):
        obs = self.inputs.obs
        xyz = np.column_stack((self.x, self.y, np.full_like(self.x, self.z)))
        v = xyz - self.anchor
        distance = np.linalg.norm(v, axis=1)
        direct = []
        for start in range(0, len(v), 128):
            sl = slice(start, start + 128)
            h = np.stack([
                self.inputs.hs.los_h(self.inputs.banks, q / d, psi + self.mount, d)
                for q, psi, d in zip(v[sl], self.yaw[sl], distance[sl])
            ])
            direct.extend(obs.observe(h, self.inputs.freqs, None, None, tx=0)["s"])
        delta = np.abs(self.los_clean - direct)
        good = np.isfinite(delta)
        p90 = float(np.quantile(delta[good], .9))
        checks = {"G-OBS-1": dict(passed=bool(p90 <= 1e-5 and good.all()),
                                   p90_abs=p90, median_abs=float(np.median(delta[good])),
                                   n=int(good.sum()), n_expected=len(delta))}
        lut_s = self.inputs.hs.s_model(self.inputs.lut, self.anchor, self.z, self.x, self.y,
                                       np.radians(self.yaw), self.mount)
        lut_delta = np.abs(self.los_clean - lut_s)
        m0_med, m0_p90 = np.quantile(lut_delta[np.isfinite(lut_delta)], [.5, .9])
        checks["M0"] = dict(passed=bool(m0_med <= .005 and m0_p90 <= .02),
                            p90_abs=float(m0_p90), median_abs=float(m0_med))

        errors = []
        for group, g in self.groups.items():
            cost, _ = next(self.costs_for_axes(group, 0., 0., [.10], "M1-R", imu_k=0., clean=True))
            for seed in range(SEEDS):
                center = g.yaw_deg + np.random.default_rng(seed).normal(0., 5.)
                allowed = (np.abs(wrap(GRID - center)) <= 30. + 1e-10) & np.isfinite(cost[0])
                if allowed.any():
                    best = np.argmin(np.where(allowed, cost[0], np.inf))
                    errors.append(abs(float(wrap(GRID[best] - g.yaw_deg))))
        med, p95 = np.quantile(errors, [.5, .95]) if errors else (None, None)
        checks["G-OBS-2"] = dict(
            passed=bool(len(errors) == len(self.groups) * SEEDS and med <= .5 and p95 <= 1.),
            median_deg=None if med is None else float(med), p95_deg=None if p95 is None else float(p95),
            bad5=None if not errors else float(np.mean(np.asarray(errors) > 5.)),
            n=len(errors), n_expected=len(self.groups) * SEEDS, n_station=len(self.groups),
            seed_rule="default_rng(seed).normal(0, 5), shared seed shift across stations",
        )
        return checks


def extended_sigma_axis(maximum):
    if maximum <= SIGMA_AXIS[-1]:
        return SIGMA_AXIS.copy()
    intervals = int(np.ceil((maximum - SIGMA_AXIS[-1]) / .04))
    return np.r_[SIGMA_AXIS, np.linspace(SIGMA_AXIS[-1], maximum, intervals + 1)[1:]]


def _stem(name, arm):
    return f"S1P_{name}_{arm}"


def write_grid(case, out, xy_axis, sigma_axis, arm="M1-R", only_groups=None):
    """Write primary J and residual curves in shape (group,seed,dx,dy,sigma,yaw)."""
    out = Path(out)
    groups = tuple(case.groups if only_groups is None else only_groups)
    xy = np.asarray(xy_axis, dtype=float)
    sigma = np.asarray(sigma_axis if arm != "M0" else [0.], dtype=float)
    stem = _stem(case.name, arm)
    paths = [out / f"{stem}_{label}.npy" for label in ("J", "MIN_CHI2")]
    if any(p.exists() for p in paths) or (out / f"{stem}_INDEX.json").exists():
        raise FileExistsError(f"Refusing to overwrite {stem} in {out}")
    shape = (len(groups), SEEDS, len(xy), len(xy), len(sigma), len(GRID))
    j_mem, r_mem = (np.lib.format.open_memmap(p, mode="w+", dtype="float32", shape=shape) for p in paths)
    start = time.monotonic()
    for k, group in enumerate(groups):
        for i, dx in enumerate(xy):
            for j, dy in enumerate(xy):
                for m, (curve, residual) in enumerate(case.costs_for_axes(group, dx, dy, sigma, arm)):
                    j_mem[k, :, i, j, m] = curve
                    r_mem[k, :, i, j, m] = residual
        print(f"{case.name} {arm} group {group}: {k + 1}/{len(groups)}; "
              f"{time.monotonic() - start:.1f}s", flush=True)
    j_mem.flush()
    r_mem.flush()
    index = dict(case=case.name, arm=arm, group_ids=list(groups), xy=xy.tolist(), sigma=sigma.tolist(),
                 sigma_s0_sq=case.sigma_s0_sq, shape=list(shape), dtype="float32",
                 n_valid=[[case.n_valid(group, seed) for seed in range(SEEDS)] for group in groups],
                 groups=[dict(group=group, x=case.groups[group].x, y=case.groups[group].y,
                              yaw_deg=case.groups[group].yaw_deg) for group in groups],
                 elapsed_s=time.monotonic()-start,
                 inputs=case.hashes, files={p.name: sha(p) for p in paths})
    dump(out / f"{stem}_INDEX.json", index)
    with (out / f"{stem}_INDEX.csv").open("x", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["axis_group", "physical_group", "seed", "x", "y", "yaw_deg", "n_valid"])
        for i, group in enumerate(groups):
            g = case.groups[group]
            for seed in range(SEEDS):
                writer.writerow([i, group, seed, g.x, g.y, g.yaw_deg, index["n_valid"][i][seed]])
    return index


class GridCase:
    """Trilinear interpolation of cached yaw curves with out-of-range detection."""

    def __init__(self, out, name, arm="M1-R"):
        out = Path(out)
        stem = _stem(name, arm)
        self.index = json.loads((out / f"{stem}_INDEX.json").read_bytes())
        self.groups = {group: i for i, group in enumerate(self.index["group_ids"])}
        self.xy = np.asarray(self.index["xy"])
        self.sigma = np.asarray(self.index["sigma"])
        self.arm = arm
        self.j, self.residual = (np.load(out / f"{stem}_{label}.npy", mmap_mode="r", allow_pickle=False)
                                 for label in ("J", "MIN_CHI2"))

    @staticmethod
    def _bracket(axis, values):
        if len(axis) == 1:
            return np.zeros(len(values), dtype=int), np.zeros(len(values))
        left = np.clip(np.searchsorted(axis, values, side="right") - 1, 0, len(axis) - 2)
        weight = (values - axis[left]) / (axis[left + 1] - axis[left])
        return left, weight

    def in_bounds(self, dx, dy, sigma):
        return ((self.xy[0] <= dx) & (dx <= self.xy[-1])
                & (self.xy[0] <= dy) & (dy <= self.xy[-1])
                & ((self.arm == "M0") | ((self.sigma[0] <= sigma) & (sigma <= self.sigma[-1]))))

    def interpolate_batch(self, group, seed, dx, dy, sigma):
        """Return J and minimum-node residual arrays (row,yaw); invalid rows are NaN."""
        group, seed, dx, dy, sigma = np.broadcast_arrays(
            *(np.atleast_1d(x) for x in (group, seed, dx, dy, sigma))
        )
        if group.ndim != 1:
            raise ValueError("Batched interpolation expects one-dimensional arguments")
        valid = self.in_bounds(dx, dy, sigma)
        result = np.full((2, len(group), len(GRID)), np.nan, dtype=float)
        if not valid.any():
            return tuple(result)
        rows = np.array([self.groups[int(g)] for g in group[valid]])
        i, tx = self._bracket(self.xy, dx[valid])
        j, ty = self._bracket(self.xy, dy[valid])
        k, ts = self._bracket(self.sigma, sigma[valid])
        curves = np.zeros((2, len(rows), len(GRID)), dtype=float)
        for ox, wx in enumerate((1. - tx, tx)):
            for oy, wy in enumerate((1. - ty, ty)):
                for oz, wz in enumerate((1. - ts, ts) if len(self.sigma) > 1 else (1. - ts,)):
                    weight = wx * wy * wz
                    indices = rows, seed[valid], i + ox, j + oy, k + oz
                    for result_index, source in enumerate((self.j, self.residual)):
                        curves[result_index] += weight[:, None] * source[indices]
        result[:, valid] = curves
        return tuple(result)

    def interpolate(self, group, seed, dx, dy, sigma):
        if not self.in_bounds(dx, dy, sigma):
            return None
        cost, residual = self.interpolate_batch(group, seed, dx, dy, sigma)
        return cost[0], residual[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--banks", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--arm", choices=("M1-R", "M0"), default="M1-R")
    parser.add_argument("--sigma", type=float, nargs="+")
    parser.add_argument("--xy-step", type=float, choices=(.1, .05), default=.1)
    parser.add_argument("--only-group", type=int, action="append")
    parser.add_argument("--parity-only", action="store_true")
    args = parser.parse_args()
    case = ObservationCase(args.inputs, args.case, args.banks)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.parity_only:
        result = case.parity()
        with (args.out / f"S1P_GATES_{case.name}.json").open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, allow_nan=False)
        print(case.name, result, flush=True)
        return
    if args.sigma is None:
        maximum = max(case.projected_sigma(group, 50) for group in case.groups)
        args.sigma = extended_sigma_axis(maximum)
    xy = np.linspace(-.3, .3, round(.6 / args.xy_step) + 1)
    write_grid(case, args.out, xy, args.sigma, args.arm, args.only_group)


if __name__ == "__main__":
    main()
