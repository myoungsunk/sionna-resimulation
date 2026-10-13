"""Generate separated input bundles once; audit frozen DR replay (I0 only)."""
from pathlib import Path
import sys, json, hashlib, platform, datetime, subprocess
from dataclasses import asdict
import numpy as np
from replay import replay, ROOT

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'research/DR_EKF_DIAGNOSIS_20261013'))
import dr_harness as H

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(p, data):
    Path(p).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')

def run(out):
    spec = json.loads((HERE / 'I0_RUN_SPEC.json').read_text())
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'FROZEN_RUN_SPEC.json', spec)
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows = []
    for arm_name in spec['reference_arms']:
        arm = H.ARMS[arm_name]
        for route in spec['routes']:
            for level in spec['levels']:
                seed = spec['seed']
                name = f'{arm_name}_{route}_d{level}_s{seed}'
                dest = out / name; dest.mkdir()
                inputs, ev, params, truth = H.make_world(arm, route, level, seed)
                cfg = H.make_cfg(arm, level, params)
                x0 = H.initial_state(arm, route, seed, params, cfg.p0_std)
                public = {k: inputs[k] for k in ('t_s','dt_s','ds_odom','dtheta_gyro','dtheta_odom')}
                public['x0'] = x0
                np.savez_compressed(dest / 'public.npz', **public)
                np.savez_compressed(dest / 'truth.npz', truth6=truth, **ev)
                write(dest / 'config.json', asdict(cfg))
                # Frozen baseline and public replay consume the SAME generated arrays.
                xs, ps, z, status, trace = H.run_ekf(arm, cfg, inputs, x0, full_trace=True)
                result = replay(dest / 'public.npz', dest / 'config.json')
                obs = result['observation_trace']
                checks = {}
                def compare(key, a, b):
                    checks[key] = bool(np.allclose(a, b, rtol=spec['rtol'], atol=spec['atol'], equal_nan=True))
                compare('post_state', xs['post'], result['est'])
                compare('post_covariance', ps['post'], result['cov_full'])
                public_status = np.array([H.STATUS_CODE[s] for s in obs['odom_status']])
                checks['gates'] = bool(np.array_equal(status, public_status))
                with np.errstate(invalid='ignore', divide='ignore'):
                    compare('normalized_innovation', z[1:], (obs['odom_innovation']/np.sqrt(obs['odom_S']))[1:])
                for key, other in [('C','odom_C'), ('Q','input_Q'), ('F','transition_F'), ('G','input_G')]:
                    compare('trace_'+key, np.array([r[key] for r in trace]), obs[other][1:])
                pred_x = np.array([H.F.transition(result['est'][k-1], inputs['ds_odom'][k], inputs['dtheta_gyro'][k], inputs['dt_s'][k], cfg.wheel_base)[0] for k in range(1,len(z))])
                pred_p = np.array([obs['transition_F'][k] @ result['cov_full'][k-1] @ obs['transition_F'][k].T + obs['input_G'][k] @ obs['input_Q'][k] @ obs['input_G'][k].T for k in range(1,len(z))])
                compare('pre_state', xs['pre'][1:], pred_x)
                compare('pre_covariance', ps['pre'][1:], pred_p)
                stats = result['stats']
                checks['odom_counts'] = stats['o_updates']==int(np.sum(status==1)) and stats['o_rejected']==int(np.sum(status==2))
                checks['rf_zero'] = all(stats[k]==0 for k in ('r_updates','r_rejected','s_updates','s_rejected')) and all(np.all(obs[k+'_status']=='disabled') for k in ('range','s'))
                # Remove scoring truth, replay in a fresh process that never imports H.
                truth_path = dest / 'truth.npz'; hidden = dest / 'truth.hidden.npz'
                truth_path.rename(hidden)
                try:
                    proc = subprocess.run([sys.executable, str(HERE/'replay.py'), str(dest/'public.npz'), str(dest/'config.json'), str(dest/'isolated.npz')], capture_output=True, text=True)
                    (dest/'isolated.log').write_text(proc.stdout+proc.stderr)
                    if proc.returncode: raise RuntimeError(proc.stderr)
                    with np.load(dest/'isolated.npz') as isolated:
                        checks['truth_absent_isolated'] = np.array_equal(result['est'],isolated['est']) and np.array_equal(result['cov_full'],isolated['cov'])
                finally:
                    hidden.rename(truth_path)
                # Poison the scoring file only, and demonstrate no inference change.
                original = truth_path.read_bytes()
                try:
                    truth_path.write_bytes(b'INVALID EVALUATION TRUTH')
                    repeated = replay(dest/'public.npz', dest/'config.json')
                    checks['truth_poison_deterministic'] = np.array_equal(result['est'],repeated['est']) and np.array_equal(result['cov_full'],repeated['cov_full'])
                finally:
                    truth_path.write_bytes(original)
                error = result['est']-truth; error[:,2] = H.DC.wrap(error[:,2])
                ref_error = xs['post']-truth; ref_error[:,2] = H.DC.wrap(ref_error[:,2])
                compare('scored_errors', ref_error, error)
                np.savez_compressed(dest/'replay.npz', est=result['est'], covariance=result['cov_full'], reference_est=xs['post'], reference_covariance=ps['post'], pre_est=pred_x, pre_covariance=pred_p, error=error, **obs)
                row = dict(episode=name, samples=len(z), checks=checks, stats=stats,
                           max_state_difference=float(np.max(np.abs(xs['post']-result['est']))),
                           max_covariance_difference=float(np.max(np.abs(ps['post']-result['cov_full']))),
                           xy_rmse=float(np.sqrt(np.mean(np.sum(error[:,:2]**2,axis=1)))),
                           status='PASS' if all(checks.values()) else 'FAIL')
                write(dest/'result.json',row); rows.append(row)
                print(name, row['status'], flush=True)
    good = all(r['status']=='PASS' for r in rows)
    write(out/'I0_REPRODUCTION.json', dict(status='PASS' if good else 'FAIL', episodes=rows, tolerance=spec))
    sources = [HERE/'replay.py', HERE/'i0_build_paired_inputs.py', HERE/'I0_RUN_SPEC.json', Path(H.__file__), ROOT/'research/DR_EKF_DIAGNOSIS_20261013/dr_consistency.py']
    sources += list(H.FROZEN_SRC.rglob('*.py'))
    sources += [H.MOTION_DIR/f'MOTION_{r}.csv' for r in spec['routes']]
    write(out/'I0_INPUT_MANIFEST.json', dict(start=start, end=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv, executable=sys.executable, python=platform.python_version(), numpy=np.__version__, platform=platform.platform(), source_reference=spec['source_reference'], source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources}, output_hashes={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}, note='Content hashes authoritative: working files include published audit changes; local HEAD is older.'))
    write(out/'I0_GATE.json', dict(code_replay='PASS' if good else 'FAIL', dr_reproduction='PASS' if good else 'FAIL', rf_integrated_reproduction='NOT_RUN', overall='INCONCLUSIVE', reasons=['R23 runner absent from inspected source tree', 'Full RF/frequency input bundle not verified available', 'New seed ranges proposed, not globally certified unused'], I1='NOT_RUN', L1_to_L7='NOT_RUN'))
    if not good: raise SystemExit(1)

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out)
