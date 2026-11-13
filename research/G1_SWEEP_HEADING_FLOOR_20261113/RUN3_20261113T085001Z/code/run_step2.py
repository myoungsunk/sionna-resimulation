"""G1-FLOOR-001 causal sweep/Kalman simulation from frozen cost curves."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import chi2

from run_step1 import GRID, dump, wrap

CASES = ("R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0")
MODELS = ("cell", "independent", "markov")
M, N, B = 200, 50, 1000
GATE = chi2.ppf(.99, 1)
STEP = .25
H = np.array([-1., 0., 1.])
BETA_SD = .45
W_SD = .34


class Curves:
    """Circular-grid range minima, with fixed tie-breaking by absolute grid index."""

    def __init__(self, costs, yaw):
        self.costs = np.where(np.isfinite(costs), costs, np.inf)
        self.yaw = np.asarray(yaw)
        self.valid = np.isfinite(self.costs).any(axis=1)
        n, width = self.costs.shape
        if width != len(GRID):
            raise ValueError("Unexpected curve width")
        rows = np.arange(n)[:, None]
        table = [np.broadcast_to(np.arange(width, dtype=np.uint16), (n, width)).copy()]
        for k in range(1, width.bit_length()):
            prev = table[-1]
            d = 1 << (k - 1)
            a, b = prev[:, :-d], prev[:, d:]
            table.append(np.where(self.costs[rows, a] <= self.costs[rows, b], a, b))
        self.table = np.full((len(table), n, width), 0, dtype=np.uint16)
        for k, layer in enumerate(table):
            self.table[k, :, :layer.shape[1]] = layer

    def range_min(self, rows, lo, hi):
        valid = lo <= hi
        size = np.maximum(1, hi - lo + 1)
        k = np.floor(np.log2(size)).astype(int)
        left = self.table[k, rows, np.clip(lo, 0, len(GRID) - 1)]
        right = self.table[k, rows, np.clip(hi - (1 << k) + 1, 0, len(GRID) - 1)]
        cost_l, cost_r = self.costs[rows, left], self.costs[rows, right]
        minimum = np.where((cost_l < cost_r) | ((cost_l == cost_r) & (left <= right)), left, right)
        return minimum, np.where(valid, self.costs[rows, minimum], np.inf)

    def estimate(self, rows, center_error, half_width):
        center = wrap(self.yaw[rows] + center_error)
        width = len(GRID)
        lo = np.ceil((center - half_width - GRID[0]) / STEP - 1e-9).astype(int)
        hi = np.floor((center + half_width - GRID[0]) / STEP + 1e-9).astype(int)
        a, ca = self.range_min(rows, np.maximum(lo, 0), np.minimum(hi, width - 1))
        b, cb = self.range_min(rows, np.maximum(0, lo + width), np.minimum(width - 1, hi + width))
        c, cc = self.range_min(rows, np.maximum(0, lo - width), np.minimum(width - 1, hi - width))
        idx = np.where((cb < ca) | ((cb == ca) & (b < a)), b, a)
        cur = np.minimum(ca, cb)
        idx = np.where((cc < cur) | ((cc == cur) & (c < idx)), c, idx)
        return np.where(np.isfinite(np.minimum(cur, cc)), wrap(GRID[idx] - self.yaw[rows]), np.nan)


def load_curves(out, snr=30, span=90):
    inventories = json.loads((out / "S1_INVENTORY.json").read_bytes())
    parities = json.loads((out / "S1_PARITY.json").read_bytes())
    costs, yaw, stations = [], [], {}
    offset = 0
    for case in CASES:
        if not parities.get(case, {}).get("passed", False):
            continue
        p = out / f"S1_J_{case}.npy"
        if not p.exists():
            raise ValueError(f"Parity passed but J missing: {case}")
        data = np.load(p, mmap_mode="r", allow_pickle=False)
        chosen = {}
        groups = {int(g["group"]): g for g in inventories[case]["groups"]}
        with (out / f"S1_J_INDEX_{case}.csv").open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if (int(r["snr_db"]), int(r["span_deg"]), float(r["imu_k"]), r["xy_arm"], r["channel"]) != (
                        snr, span, .0085, "XY-P", "full"):
                    continue
                gid, seed = int(r["group"]), int(r["seed"])
                rows = chosen.setdefault(gid, {})
                if seed in rows:
                    raise ValueError(f"Duplicate J key: {case} {gid} {seed}")
                rows[seed] = int(r["row"])
        if not chosen:
            continue
        gids = sorted(chosen)
        selected = []
        for gid in gids:
            if set(chosen[gid]) != set(range(20)):
                raise ValueError(f"Incomplete seeds: {case} {gid}")
            selected.extend(chosen[gid][seed] for seed in range(20))
        costs.append(data[selected])
        coords = np.array([[groups[g]["x"], groups[g]["y"]] for g in gids])
        yaw.extend(np.repeat([groups[g]["yaw_deg"] for g in gids], 20))
        stations[case] = dict(x=coords[:, 0], y=coords[:, 1], gids=gids,
                              rows=np.arange(offset, offset + len(selected)).reshape(-1, 20))
        offset += len(selected)
    if not costs:
        raise ValueError("No usable Step 2 cost curves")
    return Curves(np.concatenate(costs), yaw), stations


def training_scales(curves, stations):
    # Calibration excludes the route evaluated, and never uses test route innovations.
    report = {}
    for case in stations:
        route = case.split("_")[0]
        rows = [s["rows"].ravel() for c, s in stations.items() if c.split("_")[0] != route]
        if not rows:
            raise ValueError(f"No independent training route for {case}")
        rows = np.concatenate(rows)
        n = curves.estimate(rows, np.zeros(len(rows)), np.full(len(rows), 10.))
        good = np.isfinite(n)
        if not good.any():
            raise ValueError(f"No valid training sweeps for {case}")
        report[case] = dict(r_deg2=float(np.mean(n[good]**2)),
                            valid=int(good.sum()), missing=int((~good).sum()),
                            boundary_fraction=float(np.mean(np.abs(n[good]) >= 9.75)))
    return report


def station_pool(stations, rng=None):
    result, route_samples = {}, {}
    for case, s in stations.items():
        x, y = s["x"], s["y"]
        key = (case.split("_")[0], tuple(zip(x, y)))
        if key not in route_samples:
            route_samples[key] = (np.arange(len(x)) if rng is None else rng.integers(len(x), size=len(x)))
        draws = route_samples[key]
        lanes = {}
        for side in np.unique(y[draws] > 0):
            q = np.unique(draws[(y[draws] > 0) == side])
            lanes[bool(side)] = q[np.argsort(x[q], kind="stable")]
        result[case] = (draws, lanes)
    return result


def pick_rows(stations, pool, case_index, rho, uniforms, model):
    all_rows = np.empty((len(case_index), N), dtype=int)
    for i, (case, s) in enumerate(stations.items()):
        mask = case_index == i
        draws, lanes = pool[case]
        u, seed_u, coin = uniforms[:, mask]
        n = len(u)
        seeds = (20 * seed_u).astype(int)
        start = draws[(len(draws) * u[:, 0]).astype(int)]
        if model == "independent":
            selected = draws[(len(draws) * u).astype(int)]
            all_rows[mask] = s["rows"][selected, seeds]
            continue
        r = np.empty((n, N), dtype=int)
        for side, leg in lanes.items():
            same = (s["y"][start] > 0) == side
            if not same.any():
                continue
            starts = start[same]
            initial = np.argmax(leg == starts[:, None], axis=1)
            if model == "markov":
                advance = np.cumsum(coin[same] >= rho[case], axis=1)
                advance -= advance[:, :1].copy()
                pos = (initial[:, None] + advance) % len(leg)
                reset = np.column_stack((np.ones(len(pos), dtype=bool), np.diff(advance, axis=1) != 0))
            else:
                x = s["x"][leg]
                period = x[-1] - x[0] + 2.
                targets = x[0] + (x[initial, None] - x[0] + .45 * np.arange(N)) % period
                pos = np.argmin(np.abs(targets[:, :, None] - x), axis=2)
                reset = np.column_stack((np.ones(len(pos), dtype=bool), np.diff(pos, axis=1) != 0))
            last_new = np.maximum.accumulate(np.where(reset, np.arange(N), 0), axis=1)
            curve_seed = np.take_along_axis(seeds[same], last_new, axis=1)
            r[same] = s["rows"][leg[pos], curve_seed]
        all_rows[mask] = r
    return all_rows


def drivers(rng, m, e0_sd=0., w_sd=W_SD):
    start = e0_sd * rng.standard_normal(m)
    beta = BETA_SD * rng.standard_normal(m)
    w = w_sd * rng.standard_normal((m, N))
    cal = start[:, None] + np.cumsum(beta[:, None] + w, axis=1)
    uncal = cal + 2.05 * np.arange(1, N + 1)
    return start, cal, uncal


def simulate(curves, rows, dr, r, rho, *, e0_sd=0., w_sd=W_SD, gate=True,
             prior="filter", gaussian=None, beta_sd=BETA_SD, return_covariance=False):
    m = len(dr)
    beta = np.zeros((m, 3))
    transition = np.broadcast_to(np.eye(3), (m, 3, 3)).copy()
    transition[:, 0, 1] = 1.
    transition[:, 2, 2] = rho
    q = np.zeros_like(transition)
    q[:, 0, 0] = w_sd**2
    q[:, 2, 2] = (1 - rho**2) * r
    p = np.zeros_like(transition)
    p[:, 0, 0] = e0_sd**2
    p[:, 1, 1] = beta_sd**2
    p[:, 2, 2] = r
    err, nees, covered = np.empty_like(dr), np.empty_like(dr), np.empty_like(dr, dtype=bool)
    miss, used, reject, invalid = (np.empty_like(dr, dtype=bool) for _ in range(4))
    covariance = np.empty_like(dr) if return_covariance else None
    for j in range(dr.shape[1]):
        beta = (transition @ beta[:, :, None])[:, :, 0]
        p = transition @ p @ transition.transpose(0, 2, 1) + q
        half = np.minimum(180., np.maximum(3 * np.sqrt(p[:, 0, 0]), 10.))
        center_error = dr[:, j] - beta[:, 0] if prior == "filter" else dr[:, j]
        if gaussian is None:
            miss[:, j] = np.abs(wrap(center_error)) > half
            n = curves.estimate(rows[:, j], center_error, half)
            resid = wrap(n - dr[:, j])
        else:
            miss[:, j] = False
            resid = gaussian[:, j] - dr[:, j]
        invalid[:, j] = ~np.isfinite(resid)
        residual = resid - (beta @ H)
        if gaussian is None:
            residual = wrap(residual)
        cross = p @ H
        variance = np.maximum(cross @ H, 1e-12)
        reject[:, j] = (~invalid[:, j]) & (residual**2 > GATE * variance) & gate
        accept = ~invalid[:, j] & ~reject[:, j]
        used[:, j] = accept
        beta[accept] += cross[accept] * (residual[accept] / variance[accept])[:, None]
        c = cross[accept]
        p[accept] -= c[:, :, None] * c[:, None, :] / variance[accept, None, None]
        p_ee = np.maximum(p[:, 0, 0], 1e-12)
        if covariance is not None:
            covariance[:, j] = p_ee
        err[:, j] = wrap(dr[:, j] - beta[:, 0])
        nees[:, j] = err[:, j]**2 / p_ee
        covered[:, j] = np.abs(err[:, j]) <= 1.959963984540054 * np.sqrt(p_ee)
    result = dict(err=err, nees=nees, covered=covered, miss=miss, used=used, reject=reject, invalid=invalid)
    if covariance is not None:
        result["p_ee"] = covariance
    return result


def gaussian_noise(rng, r, rho, n):
    w = rng.standard_normal((n, N))
    w[:, 0] *= np.sqrt(r)
    for j in range(1, N):
        w[:, j] = rho * w[:, j - 1] + np.sqrt((1 - rho**2) * r) * w[:, j]
    return w


def ratio_curve(err, dr):
    e = np.cumsum(np.mean(err**2, axis=0))
    d = np.cumsum(np.mean(dr**2, axis=0))
    return np.sqrt(e / d)


def calc_stats(result, dr, ci=None):
    e = result["err"]
    ratios = ratio_curve(e, dr)
    s = dict(ratio_1_to_17=float(ratios[16]), rmse_g1_1_to_17=float(np.sqrt(np.mean(e[:, :17]**2))),
             rmse_dr_cal_1_to_17=float(np.sqrt(np.mean(dr[:, :17]**2))),
             nees_1_to_17=float(np.mean(result["nees"][:, :17])),
             coverage_1_to_17=float(np.mean(result["covered"][:, :17])),
             rmse_g1_at_17=float(np.sqrt(np.mean(e[:, 16]**2))),
             rmse_dr_cal_at_17=float(np.sqrt(np.mean(dr[:, 16]**2))),
             nees_at_17=float(np.mean(result["nees"][:, 16])),
             coverage_at_17=float(np.mean(result["covered"][:, 16])),
             rmse_g1_41_to_50=float(np.sqrt(np.mean(e[:, 40:]**2))),
             window_miss_1_to_17=float(np.mean(result["miss"][:, :17])),
             accepted_1_to_17=float(np.mean(result["used"][:, :17])),
             gate_reject_1_to_17=float(np.mean(result["reject"][:, :17])),
             invalid_1_to_17=float(np.mean(result["invalid"][:, :17])))
    if ci is not None:
        s["ratio_ci_95_1_to_17"] = ci[:, 16].tolist()
        crosses = np.flatnonzero(ci[1] < 1.)
        s["N_star"] = int(crosses[0] + 1) if len(crosses) else None
        s["passes_dr_cal"] = bool(s["ratio_1_to_17"] <= .8 and ci[1, 16] < 1.
                                  and .5 <= s["nees_1_to_17"] <= 2. and s["coverage_1_to_17"] >= .88)
    return s


def white_check():
    rng = np.random.default_rng(3241)
    q, r = .34**2, 4.
    target = (-q + np.sqrt(q*q + 4*q*r)) / 2
    p, error = 0., np.zeros(12000)
    for _ in range(160):
        error += rng.normal(0, np.sqrt(q), size=len(error))
        k = (p + q) / (p + q + r)
        error -= k * (error + rng.normal(0, np.sqrt(r), size=len(error)))
        p = (1 - k) * (p + q)
    mse = float(np.mean(error**2))
    if abs(p-target) > 1e-10 or abs(mse / target - 1.) > .04:
        raise ValueError(f"Gaussian-white Kalman check failed: {p}, {mse}, {target}")
    count, length = 12000, 160
    dr = np.cumsum(rng.normal(0, np.sqrt(q), (count, length)), axis=1)
    noise = rng.normal(0, np.sqrt(r), dr.shape)
    got = simulate(None, None, dr, np.full(count, r), np.zeros(count),
                   gate=False, gaussian=noise, beta_sd=0., return_covariance=True)
    actual_p = float(got["p_ee"][0, -1])
    actual_mse = float(np.mean(got["err"][:, -1]**2))
    if abs(actual_p-target) > 1e-10 or abs(actual_mse / target - 1.) > .04:
        raise ValueError(f"Gaussian-white production filter check failed: {actual_p}, {actual_mse}")
    return dict(q=q, r=r, closed_form=float(target), scalar_recursion=float(p), mc_mse=mse,
                filter_p=actual_p, filter_mc_mse=actual_mse,
                covariance_abs_tol=1e-10, mc_relative_tol=.04)


def csv_curves(path, outcomes, dr, uncal, e0_dr, dr_alt=None):
    fields = "arm station rmse_deg p95_deg nees coverage window_miss used reject invalid cum_ratio_ci_lo cum_ratio_ci_hi".split()
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for arm, (o, ci) in outcomes.items():
            for k, (rmse, p95) in enumerate(zip(np.sqrt(np.mean(o["err"]**2, axis=0)),
                                                np.quantile(np.abs(o["err"]), .95, axis=0))):
                writer.writerow([arm, k+1, rmse, p95] + [
                    np.mean(o[key][:, k]) for key in ("nees", "covered", "miss", "used", "reject", "invalid")
                ] + (ci[:, k].tolist() if ci is not None else ["", ""]))
        comparisons = [("DR-cal", dr), ("DR-uncal", uncal), ("DR-cal-initial-5deg", e0_dr)]
        if dr_alt is not None:
            comparisons.append(("DR-cal-measured-increment-sigma", dr_alt))
        for arm, e in comparisons + [
                (f"DR-nosweep-{kappa}", .45*kappa*np.arange(1, N+1)[None, :]) for kappa in (0., .1, .3)]:
            for k, (rmse, p95) in enumerate(zip(np.sqrt(np.mean(e**2, axis=0)), np.quantile(np.abs(e), .95, axis=0))):
                writer.writerow([arm, k+1, rmse, p95] + [""]*8)


def run(out, reps=B, m=M):
    white = white_check()
    dump(out / "S2_WHITE_CHECK.json", white)
    curves, stations = load_curves(out)
    raw_rho = json.loads((out / "S1_RHO.json").read_bytes())
    rho = {}
    for case in stations:
        if case not in raw_rho or raw_rho[case] is None or not np.isfinite(raw_rho[case]):
            raise ValueError(f"Missing 0.45 m spatial estimate: {case}")
        rho[case] = float(np.clip(raw_rho[case], 0., 1.))
    report = training_scales(curves, stations)
    names = list(stations)
    r_cases = np.array([report[case]["r_deg2"] for case in names])
    rho_cases = np.array([rho[case] for case in names])
    cases = np.arange(m) % len(stations)
    rng = np.random.default_rng(2026111303)
    start, dr, uncal = drivers(rng, m)
    uniforms = rng.uniform(size=(3, m, N))
    pool = station_pool(stations)
    boot = {model: np.empty((reps, N)) for model in (*MODELS, "initial-5deg")}
    e0_dr = dr + 5. * np.random.default_rng(2026111304).standard_normal(m)[:, None]
    brng = np.random.default_rng(20261113)
    missing = [case for case in CASES if case not in stations]
    n_by_case = {case: len(s["gids"]) for case, s in stations.items()}
    print(f"Step 2 input: n90={n_by_case}, missing={missing}, rho={rho}", flush=True)
    for b in range(reps):
        pool_b = station_pool(stations, brng)
        cases_b = (cases + b) % len(stations)
        for model in MODELS:
            rows = pick_rows(stations, pool_b, cases_b, rho, uniforms, model)
            res = simulate(curves, rows, dr, r_cases[cases_b], rho_cases[cases_b])
            boot[model][b] = ratio_curve(res["err"], dr)
            if model == "markov":
                initial = simulate(curves, rows, e0_dr, r_cases[cases_b], rho_cases[cases_b], e0_sd=5.)
                boot["initial-5deg"][b] = ratio_curve(initial["err"], e0_dr)
        if (b + 1) % 100 == 0:
            print(f"Station bootstrap {b+1}/{reps}", flush=True)
    outcomes, stats = {}, {}
    for model in MODELS:
        rows = pick_rows(stations, pool, cases, rho, uniforms, model)
        res = simulate(curves, rows, dr, r_cases[cases], rho_cases[cases])
        ci = np.quantile(boot[model], [.025, .975], axis=0)
        outcomes[model] = res, ci
        stats[model] = calc_stats(res, dr, ci)
        stats[model]["case_diagnostics"] = {
            case: calc_stats({k: v[cases == i] for k, v in res.items()}, dr[cases == i])
            for i, case in enumerate(names)
        }
    rows = pick_rows(stations, pool, cases, rho, uniforms, "markov")
    for arm, opts in (("DR-centered", {"prior": "dr"}), ("gate-off", {"gate": False})):
        outcomes[arm] = simulate(curves, rows, dr, r_cases[cases], rho_cases[cases], **opts), None
        stats[arm] = calc_stats(outcomes[arm][0], dr)
    init_ci = np.quantile(boot["initial-5deg"], [.025, .975], axis=0)
    outcomes["initial-5deg"] = simulate(curves, rows, e0_dr, r_cases[cases], rho_cases[cases], e0_sd=5.), init_ci
    stats["initial-5deg"] = calc_stats(outcomes["initial-5deg"][0], e0_dr, init_ci)
    noise = gaussian_noise(np.random.default_rng(2026111305), r_cases[cases], rho_cases[cases], m)
    outcomes["gaussian-ar"] = simulate(curves, rows, dr, r_cases[cases], rho_cases[cases], gaussian=noise), None
    stats["gaussian-ar"] = calc_stats(outcomes["gaussian-ar"][0], dr)
    dr_alt = None
    params_path = out / "S2_PARAMS.json"
    if params_path.is_file():
        params = json.loads(params_path.read_bytes())
        sensitivity_sigma = params["alternate_sigma_w_deg"]
        _, dr_alt, _ = drivers(np.random.default_rng(2026111303), m, w_sd=sensitivity_sigma)
        result = simulate(curves, rows, dr_alt, r_cases[cases], rho_cases[cases], w_sd=sensitivity_sigma)
        outcomes["measured-increment-sigma"] = result, None
        stats["measured-increment-sigma"] = calc_stats(result, dr_alt)
    for snr, span in ((0, 90), (10, 90), (30, 40)):
        extra, sx = load_curves(out, snr, span)
        if list(sx) != names:
            raise ValueError(f"Sensitivity case set mismatch: {snr}/{span}")
        arm = f"N{snr}-span{span}"
        rr = training_scales(extra, sx)
        r = np.array([rr[c]["r_deg2"] for c in names])[cases]
        rows_x = pick_rows(sx, station_pool(sx), cases, rho, uniforms, "markov")
        res = simulate(extra, rows_x, dr, r, rho_cases[cases])
        stats[arm] = calc_stats(res, dr)
        outcomes[arm] = res, None
        del extra
    nosweep = float(np.sqrt(np.mean((.45*.1*np.arange(1, 18))**2)))
    both = all(stats[model]["passes_dr_cal"] for model in ("independent", "markov"))
    correlation_flag = ("ROBUST" if stats["cell"]["ratio_1_to_17"] < 1.
                        else "CORRELATION_SENSITIVE") if both else None
    passes_nosweep = all(stats[model]["rmse_g1_1_to_17"] < nosweep for model in ("independent", "markov"))
    diagnostic = ("PROCEED" if passes_nosweep else "RESTRICT") if both else "STOP"
    verdict = "INCOMPLETE_PARITY_GATE" if missing else diagnostic
    summary = dict(verdict=verdict, available_cases_diagnostic=diagnostic,
                   missing_primary_cases=missing, n90_by_case=n_by_case, rho_by_case=rho,
                   rf_training=report, monte_carlo_paths=m, bootstrap_replicates=reps,
                   curve_modes=list(MODELS), gate_chi2=float(GATE), correlation_flag=correlation_flag,
                   dr_nosweep_point_one_rmse_deg=nosweep, passed_dr_nosweep=passes_nosweep,
                   scientific_pass=False, generalization="GENERALIZATION_NOT_PROVEN", stats=stats)
    dump(out / "S2_VERDICT.json", summary)
    csv_curves(out / "S2_CURVES.csv", outcomes, dr, uncal, e0_dr, dr_alt)
    np.savez_compressed(out / "S2_BOOTSTRAP_RATIOS.npz", **boot)
    print(f"Step 2: {verdict}; available cases {diagnostic}", flush=True)
    if diagnostic == "STOP" or missing:
        floor_scan(out, dr)
    return summary


def floor_scan(out, dr):
    sigmas = np.geomspace(.02, 20., 41)
    with (out / "S2_REQUIRED_FLOOR.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sigma_deg", "rho", "rmse_ratio_1_to_17", "nees", "coverage", "passes_point_rules"])
        for rho in (0., .1, .25, .5, .75, .9, .95, .99):
            for sigma in sigmas:
                rv = np.full(len(dr), sigma**2)
                rr = np.full(len(dr), rho)
                n = gaussian_noise(np.random.default_rng(2026111306), rv, rr, len(dr))
                res = simulate(None, None, dr, rv, rr, gaussian=n)
                s = calc_stats(res, dr)
                passes = s["ratio_1_to_17"] <= .8 and .5 <= s["nees_1_to_17"] <= 2. and s["coverage_1_to_17"] >= .88
                writer.writerow([sigma, rho, s["ratio_1_to_17"], s["nees_1_to_17"], s["coverage_1_to_17"], passes])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=B)
    args = parser.parse_args()
    if args.bootstrap < 1:
        parser.error("--bootstrap must be positive")
    run(args.out, args.bootstrap)


if __name__ == "__main__":
    main()

