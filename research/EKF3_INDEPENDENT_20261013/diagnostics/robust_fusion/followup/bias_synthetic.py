"""Controlled matched-model M0/M1-A diagnostics; no actual RF claim.

Truth is generated with the same conditional noisy motion equation as the EKF:
arc(true, measured_ds + eta_ds, measured_gyro - true_bias*dt + eta_yaw).
Fixed true bias with an uncertain prior gives CONDITIONAL coverage only.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from d6_d9_common import (DiagnosticFilter, P0_COV, RS, RR, arc, range_h,
                         wrap, GATE_1D_99, GATE_2D_99)

ANCHOR = np.array([3., -2., 2.])
HEIGHT = .5


def heading_model(x):
    """Analytic signed-power-like feature; deliberately not an FFD/LUT."""
    return .8*math.sin(x[2]), np.array([0., 0., .8*math.cos(x[2])])


def motion_cov(ds, dt):
    return np.diag([2e-5*abs(ds), math.radians(.015)**2*dt])


def nominal_motion(path, step, steps, dt):
    ds = .2*dt
    if path == 'straight':
        return ds, 0.
    if path == 'turn':
        return ds, .06*dt
    if path == 'return':
        return ds, (math.pi/(steps//3) if steps//3 <= step < 2*(steps//3) else 0.)
    raise ValueError(path)


def update_diagnostic(f, arm, zs, zr):
    """Expose pre-gate S/K without changing the original update policy."""
    p = f.P.copy() if f.bias_state else f.f.P.copy()
    hs, js = heading_model(f.pose)
    hr, jr = range_h(f.pose, ANCHOR, HEIGHT)
    indices = {'D0': [], 'A': [0], 'B': [1], 'C': [0, 1]}[arm]
    if indices:
        h = np.array([js, jr])[indices]
        if f.bias_state:
            h = np.column_stack([h, np.zeros(len(indices))])
        r = np.diag([RS, RR])[np.ix_(indices, indices)]
        innovation = (np.array([zs, zr])-np.array([hs, hr]))[indices]
        s = h@p@h.T+r
        gain = np.linalg.solve(s, h@p).T
        nis = float(innovation@np.linalg.solve(s, innovation))
        gate = GATE_1D_99 if len(indices) == 1 else GATE_2D_99
    else:
        innovation, s, gain, nis, gate = np.array([]), np.empty((0, 0)), np.empty((len(p), 0)), None, None
    status, actual_nis = f.update(arm, zs, zr, heading_model, ANCHOR, HEIGHT)
    if nis is not None and not math.isclose(nis, actual_nis, rel_tol=1e-10, abs_tol=1e-10):
        raise RuntimeError('Diagnostic NIS disagrees with frozen update')
    return {'status': status, 'nis': nis, 'gate': gate,
            'innovation': innovation.tolist(), 'S': s.tolist(), 'K': gain.tolist(),
            'Pprior': p.tolist(), 'Kbias': gain[-1].tolist() if f.bias_state else []}


def run_pair(path, true_bias_dps, noisy, trial, steps=300, dt=.2, trace=False):
    # Seed explicitly excludes arm/model so every paired comparison sees identical data.
    path_index = ['straight', 'turn', 'return'].index(path)
    rng = np.random.default_rng(np.random.SeedSequence([20261013, path_index, trial, int(noisy)]))
    x0 = np.array([0., 0., .2])
    truth = x0.copy()
    if noisy:
        truth += rng.multivariate_normal(np.zeros(3), P0_COV)
    true_bias = math.radians(true_bias_dps)
    filters = {(arm, name): DiagnosticFilter(x0.copy(), bias_state=name == 'M1-A',
               bias_std_dps=.1, bias_rw_dps_sqrt_s=0.)
               for arm in ('D0', 'A', 'B', 'C') for name in ('M0', 'M1-A')}
    stats = {key: [] for key in filters}
    traces = []
    pair_counts = {arm: 0 for arm in ('D0', 'A', 'B', 'C')}
    invariant_max = 0.
    for step in range(steps):
        ds, yaw = nominal_motion(path, step, steps, dt)
        gyro = yaw+true_bias*dt
        eta = rng.multivariate_normal(np.zeros(2), motion_cov(ds, dt)) if noisy else np.zeros(2)
        truth = arc(truth, ds+eta[0], gyro-true_bias*dt+eta[1])
        zs = heading_model(truth)[0]
        zr = range_h(truth, ANCHOR, HEIGHT)[0]
        if noisy:
            zs += rng.normal(0., math.sqrt(RS))
            zr += rng.normal(0., math.sqrt(RR))
        diagnostics = {}
        for (arm, name), f in filters.items():
            f.predict(ds, gyro, dt)
            prior = f.pose.copy()
            diag = update_diagnostic(f, arm, zs, zr)
            diagnostics[(arm, name)] = diag
            e = f.pose-truth
            e[2] = wrap(e[2])
            p = f.Ppose
            nees = float(e@np.linalg.solve(p, e))
            bias_error = f.x[3]-true_bias if f.bias_state else None
            bias_nees = bias_error**2/f.P[3, 3] if f.bias_state else None
            stats[(arm, name)].append([float(e[:2]@e[:2]), math.degrees(e[2])**2,
                nees, int(nees <= 7.814727903251179),
                int(e[2]**2/p[2, 2] <= 3.841458820694124),
                math.degrees(bias_error) if f.bias_state else None,
                bias_nees, int(bias_nees <= 3.841458820694124) if f.bias_state else None,
                int(diag['status'] == 'rejected_NIS')])
            if not noisy and true_bias_dps == 0:
                invariant_max = max(invariant_max, float(np.max(np.abs(e))),
                                    abs(float(f.x[3])) if f.bias_state else 0.)
                if diag['status'] == 'rejected_NIS' or invariant_max > 1e-10:
                    raise RuntimeError('NOISELESS_ZERO_BIAS_INVARIANCE_FAILED')
            if trace:
                traces.append(dict(path=path, true_bias_dps=true_bias_dps, noisy=noisy,
                    trial=trial, step=step, time_s=(step+1)*dt, arm=arm, model=name,
                    truth=truth.tolist(), prior_pose=prior.tolist(), pose=f.pose.tolist(),
                    estimated_bias_dps=math.degrees(f.x[3]) if f.bias_state else None,
                    Ppost=(f.P if f.bias_state else f.f.P).tolist(), **diag))
        for arm in pair_counts:
            pair_counts[arm] += int(diagnostics[(arm, 'M0')]['status'] != diagnostics[(arm, 'M1-A')]['status'])
    rows = []
    for (arm, name), values in stats.items():
        a = np.asarray(values, float)
        rows.append(dict(path=path, true_bias_dps=true_bias_dps, noisy=int(noisy),
            trial=trial, arm=arm, model=name, samples=steps,
            position_rmse_m=float(np.sqrt(np.mean(a[:, 0]))),
            heading_rmse_deg=float(np.sqrt(np.mean(a[:, 1]))), mean_pose_nees=float(np.mean(a[:, 2])),
            pose95=float(np.mean(a[:, 3])), heading95=float(np.mean(a[:, 4])),
            mean_bias_error_dps=float(np.mean(a[:, 5])) if name == 'M1-A' else None,
            final_bias_error_dps=float(a[-1, 5]) if name == 'M1-A' else None,
            bias_rmse_dps=float(np.sqrt(np.mean(a[:, 5]**2))) if name == 'M1-A' else None,
            bias95=float(np.mean(a[:, 7])) if name == 'M1-A' else None,
            gate_reject_fraction=float(np.mean(a[:, 8])),
            paired_gate_disagreements=pair_counts[arm], noiseless_invariant_max=invariant_max))
    return rows, traces


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    started_utc = datetime.now(timezone.utc).isoformat()
    started_clock = time.perf_counter()
    trials, steps = (2, 30) if args.smoke else (100, 300)
    args.out.mkdir(parents=True, exist_ok=False)
    contract = dict(synthetic_only=True, scientific_PASS=False, dt_s=.2, steps=steps,
        trials_noisy=trials, trials_noiseless=1, paths=['straight', 'turn', 'return'],
        actual_bias_dps=[0., .05], initial_bias_mean_dps=0., bias_prior_std_dps=.1,
        bias_rw_dps_sqrt_s=0., noise_cov='diag(2e-5*abs(ds), radians(.015)^2*dt)',
        R0=[RS, RR], pose_prior=P0_COV.tolist(), gate=[GATE_1D_99, GATE_2D_99],
        coverage_interpretation='conditional on fixed true bias, not unconditional prior calibration',
        D0='unobservable bias; no convergence requirement',
        noiseless_zero_bias_invariance_tolerance=1e-10,
        noisy_initialization='truth initial pose drawn from N(x0,P0); estimate initialized at x0',
        stochastic_motion='truth arc(measured_ds+eta_ds, measured_gyro-true_bias*dt+eta_yaw)',
        noiseless_mode='noise draws disabled; filter retains R0/Q and uncertain prior; nominal invariance only, not stochastic calibration',
        trace_scope='all noiseless trials and first noisy trial per scenario; metrics all trials',
        started_utc=started_utc, command=[sys.executable, *sys.argv],
        expected_cells=3*2*(trials+1)*8,
        source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__), Path(__file__).resolve().parents[2]/'d6_d9_common.py',
             Path(__file__).resolve().parents[3]/'ekf3.py']})
    (args.out/'CONTRACT.json').write_text(json.dumps(contract, indent=2), encoding='utf-8')
    all_rows = []
    with gzip.open(args.out/'TRACE.jsonl.gz', 'wt', encoding='utf-8') as stream:
        for path in contract['paths']:
            for bias in contract['actual_bias_dps']:
                for noisy in (False, True):
                    for trial in range(trials if noisy else 1):
                        rows, traces = run_pair(path, bias, noisy, trial, steps,
                                               trace=trial == 0)
                        all_rows.extend(rows)
                        for row in traces:
                            stream.write(json.dumps(row, allow_nan=False)+'\n')
                    print(f'completed {path} bias={bias} noisy={noisy}', flush=True)
    with (args.out/'CASE_METRICS.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
        writer.writeheader(); writer.writerows(all_rows)
    if len(all_rows) != contract['expected_cells']:
        raise RuntimeError('Incomplete synthetic comparison cells')
    result = dict(status='EXECUTED_SYNTHETIC_ONLY', cells=len(all_rows),
                  expected_cells=contract['expected_cells'], exit_code=0,
                  started_utc=started_utc, completed_utc=datetime.now(timezone.utc).isoformat(),
                  elapsed_s=time.perf_counter()-started_clock,
                  command=contract['command'], source_sha256=contract['source_sha256'],
                  output_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [args.out/'CONTRACT.json', args.out/'TRACE.jsonl.gz',
                                args.out/'CASE_METRICS.csv']},
                  noiseless_zero_bias_invariance='PASS', scientific_PASS=False)
    (args.out/'RECEIPT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
