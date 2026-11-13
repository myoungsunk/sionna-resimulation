"""Replay the frozen Step 2 trajectories and diagnose heading undercoverage."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

import run_step2 as s2
from run_step1 import dump, sha, wrap

END = 17


class Record:
    def __init__(self, curves, oracle=False):
        self.curves = curves
        self.oracle = oracle
        self.data = []

    def estimate(self, rows, center, half):
        if self.oracle:
            z = self.curves.estimate(rows, np.zeros_like(center), np.full_like(half, 10.))
        else:
            z = self.curves.estimate(rows, center, half)
        self.data.append((z.copy(), center.copy(), half.copy()))
        return z


def innovations(z, dr, r, rho, result):
    """Reconstruct the innovation using the actual acceptance mask."""
    n, steps = z.shape
    h = np.array([-1., 0., 1.])
    x = np.zeros((n, 3))
    f = np.broadcast_to(np.eye(3), (n, 3, 3)).copy()
    f[:, 0, 1] = 1.
    f[:, 2, 2] = rho
    p, q = np.zeros_like(f), np.zeros_like(f)
    p[:, 1, 1] = s2.BETA_SD**2
    p[:, 2, 2] = r
    q[:, 0, 0] = s2.W_SD**2
    q[:, 2, 2] = (1 - rho**2)*r
    value, var = np.empty_like(z), np.empty_like(z)
    for j in range(steps):
        x = np.einsum("nij,nj->ni", f, x)
        p = f @ p @ f.swapaxes(-1, -2) + q
        cross = p @ h
        var[:, j] = cross @ h
        value[:, j] = wrap(wrap(z[:, j] - dr[:, j]) - x @ h)
        keep = result["used"][:, j]
        k = cross[keep] / var[keep, j, None]
        x[keep] += k * value[keep, j, None]
        p[keep] -= np.einsum("ni,nj->nij", k, cross[keep])
        np.testing.assert_allclose(p[:, 0, 0], result["p_ee"][:, j], rtol=0, atol=1e-11)
        np.testing.assert_allclose(wrap(dr[:, j] - x[:, 0]), result["err"][:, j], rtol=0, atol=1e-11)
    np.testing.assert_array_equal(np.isfinite(value) & (value**2 > s2.GATE*var), result["reject"])
    return value, var


def describe(result, dr):
    err = result["err"][:, :END]
    sd = np.sqrt(result["p_ee"][:, :END])
    bad = ~result["covered"][:, :END]
    return s2.calc_stats(result, dr) | dict(
        n=int(bad.size), uncovered=int(bad.sum()), error_bias_deg=float(err.mean()),
        positive_tail=int(((err > 0) & bad).sum()), negative_tail=int(((err < 0) & bad).sum()),
        mean_posterior_sd_deg=float(sd.mean()), p95_abs_standardized=float(np.quantile(np.abs(err/sd), .95)))


def count(mask, bad):
    return dict(n=int(mask.sum()), uncovered=int((mask&bad).sum()),
                uncovered_fraction=float(np.mean(bad[mask])) if mask.any() else None)


def lag1(values):
    x, y = values[:, :-1].ravel(), values[:, 1:].ravel()
    good = np.isfinite(x) & np.isfinite(y)
    return float(np.corrcoef(x[good], y[good])[0, 1]) if good.sum() > 1 and np.std(x[good]) and np.std(y[good]) else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    run, out = a.run.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    curves, stations = s2.load_curves(run)
    rho_all = json.loads((run/"S1_RHO.json").read_bytes())
    frozen = json.loads((run/"S2_VERDICT.json").read_bytes())
    fit = s2.training_scales(curves, stations)
    names = list(stations)
    cases = np.arange(frozen["monte_carlo_paths"]) % len(names)
    rng = np.random.default_rng(2026111303)
    _, dr, _ = s2.drivers(rng, len(cases))
    uniforms = rng.uniform(size=(3, len(cases), s2.N))
    pool = s2.station_pool(stations)
    r = np.array([fit[c]["r_deg2"] for c in names])[cases]
    rho = np.array([rho_all[c] for c in names])[cases]
    summaries, by_case, by_station = {}, {}, {}
    for mode in ("independent", "markov"):
        rows = s2.pick_rows(stations, pool, cases, rho_all, uniforms, mode)
        watcher = Record(curves)
        result = s2.simulate(watcher, rows, dr, r, rho, return_covariance=True)
        z, center, half = np.stack(watcher.data).transpose(1, 2, 0)
        original = s2.simulate(curves, rows, dr, r, rho, return_covariance=True)
        for key in original:
            np.testing.assert_array_equal(result[key], original[key])
        innovation, variance = innovations(z, dr, r, rho, result)
        summaries[mode] = describe(result, dr)
        for key in ("coverage_1_to_17","ratio_1_to_17","nees_1_to_17","window_miss_1_to_17"):
            np.testing.assert_allclose(summaries[mode][key], frozen["stats"][mode][key], rtol=0, atol=1e-12)
        fixed = curves.estimate(rows[:, :END].ravel(), np.zeros(rows[:, :END].size),
                                np.full(rows[:, :END].size, 10.)).reshape(-1, END)
        by_case[mode] = {}
        for j, case in enumerate(names):
            m = cases == j
            e = z[m, :END]
            norm = innovation[m, :END]/np.sqrt(variance[m, :END])
            by_case[mode][case] = describe({k: v[m] for k, v in result.items()}, dr[m]) | dict(
                assumed_rho=float(rho[m][0]), model_measurement_sd_deg=float(np.sqrt(r[m][0])),
                sweep_error_mean_deg=float(np.nanmean(e)), sweep_error_rms_deg=float(np.sqrt(np.nanmean(e**2))),
                sweep_error_lag1=lag1(e), fixed_center_sweep_error_lag1=lag1(fixed[m]),
                fixed_center_sweep_error_rms_deg=float(np.sqrt(np.nanmean(fixed[m]**2))),
                normalized_innovation_rms=float(np.sqrt(np.nanmean(norm**2))),
                same_J_fraction=float(np.mean(rows[m, 1:END] == rows[m, :END-1])))
        by_station[mode] = [dict(
            station=j+1, uncovered=int((~result["covered"][:,j]).sum()),
            missed=int(result["miss"][:,j].sum()), rejected=int(result["reject"][:,j].sum()),
            mean_sd_deg=float(np.sqrt(result["p_ee"][:,j]).mean()),
            rmse_deg=float(np.sqrt(np.mean(result["err"][:,j]**2)))) for j in range(END)]
    bad = ~result["covered"][:, :END]
    miss = result["miss"][:, :END]
    reject = result["reject"][:, :END]
    used = result["used"][:, :END]
    seen_miss = np.maximum.accumulate(miss, axis=1)
    seen_reject = np.maximum.accumulate(reject, axis=1)
    repeat = np.column_stack([np.zeros(len(rows),dtype=bool), rows[:, 1:END] == rows[:, :END-1]])
    obs_error = np.abs(z[:, :END])
    edge = np.abs(wrap(z[:, :END]-center[:, :END])) >= half[:, :END]-.25-1e-10
    exposure = {key: count(mask,bad) for key,mask in dict(
        current_window_miss=miss, earlier_miss_only=seen_miss&~miss, no_miss_so_far=~seen_miss,
        current_gate_reject=reject, earlier_reject_only=seen_reject&~reject, no_reject_so_far=~seen_reject,
        accepted=used, same_j=repeat, new_j=~repeat, within_one_grid_step_of_edge=edge,
        abs_sweep_error_gt5=obs_error > 5., abs_sweep_error_le5=obs_error <= 5.,
        branch_flip_45=obs_error > 45.).items()}
    comparisons = {}
    for label, kwargs in (("gate_off",dict(gate=False)),("DR_centered",dict(prior="dr")),
                          ("oracle_truth_center_10deg",{}),("Gaussian_AR",{}),("Gaussian_AR_gate_off",dict(gate=False))):
        estimator = Record(curves, oracle=label.startswith("oracle"))
        if label.startswith("Gaussian"):
            kwargs["gaussian"] = s2.gaussian_noise(np.random.default_rng(2026111305),r,rho,len(cases))
        alt = s2.simulate(estimator,rows,dr,r,rho,return_covariance=True,**kwargs)
        other = ~alt["covered"][:, :END]
        comparisons[label] = describe(alt,dr) | dict(
            paired_coverage_recovered=int((bad&~other).sum()), paired_coverage_lost=int((~bad&other).sum()))
    with (out/"MARKOV_TRACE.csv").open("w",newline="",encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(("path","case","step","group","seed","same_J","DR_error_deg","sweep_error_deg","prior_error_deg",
                    "half_window_deg","innovation_deg","innovation_var_deg2","accepted","rejected","window_miss",
                    "post_error_deg","post_var_deg2","covered"))
        index = {int(row):(gid,seed) for c in names for gid,rs in zip(stations[c]["gids"],stations[c]["rows"])
                 for seed,row in enumerate(rs)}
        for k,j in np.ndindex((len(rows),END)):
            gid,seed = index[rows[k,j]]
            w.writerow((k,names[cases[k]],j+1,gid,seed,repeat[k,j],dr[k,j],z[k,j],center[k,j],half[k,j],
                        innovation[k,j],variance[k,j],used[k,j],reject[k,j],miss[k,j],result["err"][k,j],
                        result["p_ee"][k,j],result["covered"][k,j]))
    dump(out/"MARKOV_DIAGNOSTIC.json",dict(
        question_id="G1-FLOOR-001", analyses="post hoc conditional on frozen point-run cases and CRN",
        summaries=summaries, case=by_case, station=by_station, exposure=exposure, counterfactual=comparisons,
        scope="Exposure groups overlap; actual replay is descriptive. Oracle jointly replaces center and width. Simulator counterfactuals do not identify field causes."))
    inputs = ["S2_VERDICT.json","S1_RHO.json","S1_INVENTORY.json","S1_PARITY.json"]
    inputs += [name for c in names for name in (f"S1_J_{c}.npy",f"S1_J_INDEX_{c}.csv")]
    dump(out/"MANIFEST.json",dict(
        question_id="G1-FLOOR-001", source_run=str(run), started_utc=started,
        ended_utc=datetime.now(timezone.utc).isoformat(), command=[sys.executable,*sys.argv], exit_code=0,
        environment=dict(python=sys.version,numpy=np.__version__), inputs={x:sha(run/x) for x in inputs},
        code={x.name:sha(x) for x in (Path(__file__),Path(s2.__file__),Path(s2.__file__).with_name("run_step1.py"))},
        outputs={x:sha(out/x) for x in ("MARKOV_TRACE.csv","MARKOV_DIAGNOSTIC.json")},
        checks=["traced production filter exactly matches untraced filter",
                "independent posterior covariance/heading update recomputation within 1e-11",
                "innovation gate decisions exactly reproduced", "frozen point metrics within 1e-12"]))


if __name__=="__main__":
    main()
