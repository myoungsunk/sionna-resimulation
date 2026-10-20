"""Exact impl1 replay on precomputed train-only parameters and canonical controls.

Input JSON: {"cases":[{"case":{source SourceFFD case metadata},"bias":"B0",
"bias_dps":0,"npz":"relative.npz","training_scope":"route-heldout:R2",
"tau_s":0.6,"fraction":0.9,"historical_power1_trace":"optional.npz"}]}.
NPZ keys: t, initial_pose, z, mu, C, risk, controls_dt, controls_ds,
controls_dyaw, truth (Nx3). Future/GT are passed only to independent scoring.
Parameter fitting and T2 sensor creation remain in their pinned upstream code.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import traceback
import numpy as np
import pandas as pd
from unit_tests import load_engine, ROOT, HERE


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def score(state, cov, truth, bias, mask, scalar=False):
    e = state[mask, :4]-np.c_[truth[mask], np.full(mask.sum(), np.radians(bias))]
    e[:, 2] = (e[:, 2]+np.pi) % (2*np.pi)-np.pi
    P = cov[mask, :4, :4]
    h = np.degrees(e[:, 2]); var = np.degrees(np.sqrt(P[:, 2, 2]))**2
    if scalar:
        pose = np.array([v[:3]@np.linalg.solve(p[:3, :3], v[:3]) for v, p in zip(e, P)])
        cond = []
        for v, p in zip(e, P):
            r = v[:2]-p[:2, 2]*v[2]/p[2, 2]
            S = p[:2, :2]-np.outer(p[:2, 2], p[2, :2])/p[2, 2]
            cond.append(r@np.linalg.solve(S, r))
        cond = np.array(cond)
    else:
        pose = np.einsum('ni,ni->n', e[:, :3], np.linalg.solve(P[:, :3, :3], e[:, :3, None])[..., 0])
        residual = e[:, :2]-P[:, :2, 2]*e[:, 2, None]/P[:, 2, 2, None]
        S = P[:, :2, :2]-P[:, :2, 2, None]*P[:, None, 2, :2]/P[:, 2, 2, None, None]
        cond = np.einsum('ni,ni->n', residual, np.linalg.solve(S, residual[..., None])[..., 0])
    return dict(heading_rmse_deg=float(np.sqrt(np.mean(h*h))), signed_heading_deg=float(h.mean()),
                heading_sigma_rms_deg=float(np.sqrt(var.mean())), heading95=float(np.mean(h*h/var <= 3.841458820694124)),
                heading_nees=float(np.mean(h*h/var)), pose_nees=float(pose.mean()),
                conditional_xy_nees=float(cond.mean()), xy_rmse_m=float(np.sqrt(np.mean(np.sum(e[:, :2]**2, axis=1)))),
                bias_rmse_dps=float(np.degrees(np.sqrt(np.mean(e[:, 3]**2)))),
                bias_mean_dps=float(np.degrees(state[mask, 3].mean())), bias_final_dps=float(np.degrees(state[-1, 3])))


def specifications(tau, fraction):
    return [dict(name='JOINT4', base='r0'), dict(name='POWER1', base='power'),
            dict(name='POWER_SR4', base='power', order='sr'),
            *[dict(name=name, base='power', latent=True, tau=value, fraction=fraction, **extra)
              for name, value, extra in [('MEMORY', tau, {}), ('MEMORY_RHO0', 0., {}),
               ('MEMORY_NO_CROSS', tau, {'no_cross': True}),
               ('MEMORY_TAU_HALF', tau/2, {}), ('MEMORY_TAU_DOUBLE', tau*2, {})]]]


def dead_reckoning(engine, controls, initial, n):
    # Same physical transition/process covariance as pinned engine.run.
    x = np.zeros(4); x[:3] = initial; P = engine.PINIT.copy()
    states, covariances = [], []
    for i in range(n):
        if i:
            ds, dt = float(controls['ds_odom'][i]), float(controls['dt_s'][i])
            x, F, G = engine.transition(x, ds, float(controls['dtheta_gyro'][i]), dt)
            Qi = np.diag([2e-5*abs(ds), np.radians(.015)**2*dt, 0.])
            P = F@P@F.T + G@Qi@G.T
            P = (P+P.T)/2
        states.append(x.copy()); covariances.append(P.copy())
    return np.asarray(states), np.asarray(covariances)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--source-root', type=Path, default=ROOT); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'traces').mkdir(exist_ok=True)
    rows, checks, inputs = [], [], []
    try:
        engine, engine_path = load_engine(args.source_root)
        sys.path.insert(0, str(args.source_root/'research/FFD_P0P3_20261016'))
        from source_model import SourceFFD
        model = SourceFFD()
        bundle = json.loads(args.bundle.read_text())
        baseline = pd.read_csv(args.source_root/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv')
        for rec in bundle['cases']:
            path = args.bundle.parent/rec['npz']; inputs.append(dict(file=str(path), sha256=sha(path)))
            with np.load(path, allow_pickle=False) as data:
                d = {key: data[key].copy() for key in data.files}
            t = d['t']; mask = t >= 30
            if not mask.any(): raise ValueError('No evaluation frames')
            controls = dict(dt_s=d['controls_dt'], ds_odom=d['controls_ds'], dtheta_gyro=d['controls_dyaw'])
            specs = specifications(rec['tau_s'], rec['fraction'])
            result = engine.run(t, controls, d['initial_pose'], d['z'], d['mu'], d['C'], d['risk'], rec['case'], model, specs)
            names = list(result['names']); j, k = names.index('POWER1'), names.index('MEMORY_RHO0')
            dx = float(np.max(abs(result['state'][:, j, :4]-result['state'][:, k, :4])))
            dp = float(np.max(abs(result['cov'][:, j, :4, :4]-result['cov'][:, k, :4, :4])))
            flips = int(np.count_nonzero(result['accepted'][:, j] != result['accepted'][:, k]))
            check = dict(case=rec['case']['id'], bias=rec['bias'], rho0_state_max=dx, rho0_cov_max=dp,
                         rho0_gate_mismatch=flips, historical_gate_status='BLOCKED_INPUT')
            if max(dx, dp) > 1e-10 or flips: raise RuntimeError('RHO0_PARITY')
            drx, drp = dead_reckoning(engine, controls, d['initial_pose'], len(t))
            methods = [(name, result['state'][:, i], result['cov'][:, i]) for i, name in enumerate(names)]
            methods.append(('DR4', drx, drp))
            scorer_max = 0.
            for name, state, cov in methods:
                values = score(state, cov, d['truth'], rec['bias_dps'], mask)
                independent = score(state, cov, d['truth'], rec['bias_dps'], mask, scalar=True)
                scorer_max = max(scorer_max, max(abs(values[key]-independent[key]) for key in values))
                row = dict(case=rec['case']['id'], bias=rec['bias'], arm=name, n=int(mask.sum()), **values)
                rows.append(row)
                if name == 'POWER1' and rec['bias'] == 'B0':
                    target = baseline[(baseline.case == rec['case']['id']) & (baseline.method == 'POWER1')]
                    if len(target):
                        delta = abs(values['heading_rmse_deg']-target.heading_rmse_deg.iloc[0])
                        check['historical_heading_delta_deg'] = float(delta)
                        if delta > 1e-6: raise RuntimeError('HISTORICAL_POWER1_HEADING')
            check['independent_scorer_max_abs'] = scorer_max
            if scorer_max > 1e-9: raise RuntimeError('INDEPENDENT_SCORER')
            historical = rec.get('historical_power1_trace')
            if historical:
                gate_path = args.bundle.parent/historical
                inputs.append(dict(file=str(gate_path), sha256=sha(gate_path)))
                with np.load(gate_path, allow_pickle=False) as reference:
                    reference_names = list(reference['names'])
                    old = reference['accepted'][:, reference_names.index('POWER1')]
                    if old.shape != result['accepted'][:, j].shape: raise RuntimeError('HISTORICAL_GATE_SHAPE')
                    count = int(np.count_nonzero(old != result['accepted'][:, j]))
                check['historical_gate_mismatch'] = count
                check['historical_gate_status'] = 'PASS' if count == 0 else 'FAIL'
                if count: raise RuntimeError('HISTORICAL_POWER1_GATE')
            checks.append(check)
            result.update(truth_for_offline_scoring_only=d['truth'], controls_dt=d['controls_dt'],
                          controls_ds=d['controls_ds'], controls_dyaw=d['controls_dyaw'], observations=d['z'])
            np.savez_compressed(args.out/'traces'/f"{rec['case']['id']}_{rec['bias']}.npz", **result)
        pd.DataFrame(rows).to_csv(args.out/'CANONICAL_RESULTS.csv', index=False)
        pd.DataFrame(checks).to_csv(args.out/'REPLAY_CHECKS.csv', index=False)
        gate_complete = all(c['historical_gate_status'] == 'PASS' for c in checks)
        manifest = dict(engine_sha256=sha(engine_path), protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),
                        bundle_sha256=sha(args.bundle), inputs=inputs, technical='TECHNICAL_PASS' if gate_complete else 'BLOCKED_INPUT',
                        scientific='NOT_ESTABLISHED', unresolved=[] if gate_complete else ['historical POWER1 gate trace'])
        (args.out/'MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    except Exception as error:
        pd.DataFrame(rows).to_csv(args.out/'PARTIAL_RESULTS.csv', index=False)
        (args.out/'ERRORS.json').write_text(json.dumps([dict(error=str(error), traceback=traceback.format_exc(), retry='not automatic')], indent=2))
        raise


if __name__ == '__main__': main()
