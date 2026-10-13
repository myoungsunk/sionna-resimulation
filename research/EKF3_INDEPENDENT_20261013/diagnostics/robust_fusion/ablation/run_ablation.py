"""Frozen noise_pair component ablation; M0/C must reproduce archived metrics."""
import argparse
import csv
import gzip
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from m1_bias_robust_ekf import RobustBiasEKF
from robust_pose_ekf import RobustPoseEKF
from rf_error_model import load_models
from d6_d9_common import (DiagnosticFilter, check_inputs, original_lut, case_motion,
    initial_state, wrap, eval_covariance, file_sha, B_OLD, atomic_json)
from ekf3 import archived_direct_s_model

KEYS = ('case', 'channel', 'range_model', 'condition', 'level', 'seed', 'arm')
PARITY = ('heading_rmse_deg', 'xy_rmse_m', 'mean_pose_NEES', 'mean_heading_NEES', 'pose95')
MODELS = ('M0', 'M1-A', 'M1-B', 'M1-C')

def validate_contract(contract, parent):
    for field in ('arms','channels','range_models','seeds','eval_start_s',
                  'parity_abs_tolerance','bias_prior_std_dps','bias_rw_dps_sqrt_s','huber_delta','receiver'):
        if contract[field] != parent[field]: raise RuntimeError('Parent contract mismatch '+field)
    if contract['level'] not in parent['levels'] or contract['condition'] not in parent['conditions']:
        raise RuntimeError('Ablation outside initial grid')
    if contract['models'] != list(MODELS) or contract['parameter_retuning']:
        raise RuntimeError('Ablation model contract changed')
    if contract['parity_abs_tolerance'] != 1e-8:
        raise RuntimeError('Frozen parity tolerance changed')

def make_filter(name, x0, contract):
    if name == 'M0': return DiagnosticFilter(x0)
    if name == 'M1-A':
        return DiagnosticFilter(x0, bias_state=True,
            bias_std_dps=contract['bias_prior_std_dps'],
            bias_rw_dps_sqrt_s=contract['bias_rw_dps_sqrt_s'])
    if name == 'M1-B': return RobustPoseEKF(x0)
    if name == 'M1-C':
        return RobustBiasEKF(x0, contract['bias_prior_std_dps'], contract['bias_rw_dps_sqrt_s'])
    raise ValueError(name)

def update_filter(name, f, arm, zs, zr, model, case, mu, cov, delta):
    if name in ('M0', 'M1-A'):
        # Frozen baseline forms raw-compatible z_r then subtracts B_OLD.
        # Retain that floating-point round trip also in the bias-only arm.
        if name == 'M1-A' and math.isfinite(zr): zr = (zr + B_OLD) - B_OLD
        status, nis = f.update(arm, zs, zr, model, case['anchor'], case['robot_z_m'])
        return dict(status=status, NIS=nis, iterations=0, huber_weight=None)
    return f.update(arm, zs, zr, model, case['anchor'], case['robot_z_m'], mu, cov, delta)

def key(row): return tuple(str(row[k]) for k in KEYS)

def check_parity(rows, references, tolerance=1e-8):
    maximum = 0.
    counts = {'M0': 0, 'M1-C': 0}
    for row in rows:
        name = row['model']
        if name not in counts: continue
        ref = references[name][key(row)]
        if int(row['n']) != int(ref['n']): raise RuntimeError('Parity sample count mismatch')
        if name == 'M0':
            for field in ('accepted_updates', 'rejected_updates'):
                if int(row[field]) != int(ref[field]): raise RuntimeError('M0 parity update count mismatch')
        for field in PARITY:
            delta = abs(float(row[field]) - float(ref[field]))
            if not math.isfinite(delta) or delta > tolerance:
                raise RuntimeError(f'Parity failure {name} {key(row)} {field}: {delta}')
            maximum = max(maximum, delta)
        counts[name] += 1
    if not all(counts.values()): raise RuntimeError('Missing parity model')
    return dict(status='PASS', cells_per_model=counts, max_abs_difference=maximum, tolerance=tolerance)

def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)

def pooled_metrics(rows):
    groups = {}
    for row in rows:
        group = tuple(row[k] for k in ('model', 'channel', 'range_model', 'arm'))
        groups.setdefault(group, []).append(row)
    result = []
    for group, values in groups.items():
        n = sum(r['n'] for r in values)
        item = dict(zip(('model', 'channel', 'range_model', 'arm'), group), n=n, cells=len(values))
        for field in PARITY + ('heading95',):
            square = field in ('heading_rmse_deg', 'xy_rmse_m')
            value = sum(r['n'] * r[field]**(2 if square else 1) for r in values) / n
            item[field] = math.sqrt(value) if square else value
        result.append(item)
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'structure', 'reference', 'out'): ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--smoke', action='store_true'); args = ap.parse_args()
    args.out.mkdir(exist_ok=False); start = time.time(); started_utc = datetime.now(timezone.utc).isoformat()
    contract = json.loads((HERE/'contract.json').read_text())
    validate_contract(contract,json.loads((HERE.parent/'experiment_contract.json').read_text()))
    im = json.loads((args.inputs/'MANIFEST.json').read_text())
    for name, sha in im['sha256'].items():
        if file_sha(args.inputs/name) != sha: raise RuntimeError('Input cache drift '+name)
    if json.loads((args.inputs/'M0_PARITY.json').read_text())['status'] != 'PASS': raise RuntimeError('M0 input gate failed')
    references = {}
    reference_hashes = {}
    ref_manifest = json.loads((args.reference/'RESULT_MANIFEST.json').read_text())
    for name, filename in (('M0', 'M0_METRICS.csv'), ('M1-C', 'M1_METRICS.csv')):
        path = args.reference/filename
        if file_sha(path) != ref_manifest['sha256'][filename]: raise RuntimeError('Reference hash drift '+filename)
        references[name] = {key(r): r for r in csv.DictReader(path.open())}
        reference_hashes[filename] = file_sha(path)
    models, rf_contract = load_models(args.structure)
    p0 = check_inputs(); lut = original_lut(p0); metrics = []; writer = None
    atomic_json(args.out/'EXECUTION_CONTRACT.json', dict(contract=contract, command=sys.argv,
        started_utc=started_utc, reference_manifest_sha256=file_sha(args.reference/'RESULT_MANIFEST.json'),
        input_manifest_sha256=file_sha(args.inputs/'MANIFEST.json'), reference_sha256=reference_hashes,
        rf_contract=rf_contract, source_sha256={str(p.relative_to(HERE.parent)):file_sha(p)
        for p in list(HERE.glob('*.py')) + list(HERE.parent.glob('*.py'))}))
    with gzip.open(args.out/'ABLATION_TRACE.csv.gz', 'wt', newline='') as trace:
        for case in p0['cases']:
            if args.smoke and case['id'] != contract['smoke_case']: continue
            model = archived_direct_s_model(lut, anchor_xyz_m=tuple(case['anchor']),
                tag_height_m=case['robot_z_m'], mount_deg=case['mount_deg'])
            for channel in contract['channels']:
                with np.load(args.inputs/(case['id']+'_'+channel+'.npz')) as cache:
                    t, truth, pids = cache['t'], cache['truth'], cache['pose_ids']
                    for rm in contract['range_models']:
                        if rm not in cache: continue
                        mu, cov = models[(case['route'], channel, rm)]
                        for seed in ([contract['smoke_seed']] if args.smoke else contract['seeds']):
                            mt, mtruth, mpids, motion, oracle = case_motion(p0, case, seed, contract['level'], contract['condition'])
                            if not all(np.array_equal(a,b) for a,b in ((t,mt),(truth,mtruth),(pids,mpids))): raise RuntimeError('Motion/cache mismatch')
                            x0 = initial_state(truth[0], seed)
                            for arm in contract['arms']:
                                for name in MODELS:
                                    f = make_filter(name, x0, contract); values = []
                                    for k in range(len(t)):
                                        if k: f.predict(float(motion['ds_odom'][k]),float(motion['dtheta_gyro'][k]),float(motion['dt_s'][k]))
                                        prior_error = f.pose-truth[k]; prior_error[2] = wrap(prior_error[2])
                                        st = update_filter(name, f, arm, float(cache['s'][k]),float(cache[rm][k]),model,case,mu,cov,contract['huber_delta'])
                                        if t[k] < contract['eval_start_s']: continue
                                        e = f.pose-truth[k]; e[2] = wrap(e[2]); nees, hn, cover = eval_covariance(e,f.Ppose)
                                        bias = name in ('M1-A','M1-C'); bx = f.x[3] if bias else None
                                        bp = f.P[3,3] if bias else None
                                        row = dict(case=case['id'],channel=channel,range_model=rm,condition=contract['condition'],level=contract['level'],seed=seed,arm=arm,model=name,
                                            sample_index=k,t_s=t[k],x=f.pose[0],y=f.pose[1],psi=f.pose[2],error_x=e[0],error_y=e[1],heading_error_deg=math.degrees(e[2]),
                                            Pxx=f.Ppose[0,0],Pyy=f.Ppose[1,1],Ppsi=f.Ppose[2,2],Pxy=f.Ppose[0,1],Pxpsi=f.Ppose[0,2],Pypsi=f.Ppose[1,2],
                                            pose_NEES=nees,heading_NEES=hn,pose95=int(cover),heading95=int(hn<=3.841458820694124),
                                            prior_heading_error_deg=math.degrees(prior_error[2]),prior_error_x=prior_error[0],prior_error_y=prior_error[1],
                                            heading_squared_error_change=e[2]**2-prior_error[2]**2,position_squared_error_change=float(e[:2]@e[:2]-prior_error[:2]@prior_error[:2]),
                                            bias_est_rad_s=bx,bias_true_rad_s=oracle['true_bias_rad_s'][k] if bias else None,
                                            bias_std_rad_s=math.sqrt(bp) if bias else None,bias_heading_corr=f.P[2,3]/math.sqrt(f.P[2,2]*bp) if bias else None,
                                            NIS=st['NIS'],status=st['status'],huber_weight=st.get('huber_weight'),iterations=st['iterations'])
                                        if writer is None: writer=csv.DictWriter(trace,fieldnames=row); writer.writeheader()
                                        writer.writerow(row); values.append(row)
                                    mean=lambda field:float(np.mean([r[field] for r in values]))
                                    rms=lambda field:float(np.sqrt(np.mean([r[field]**2 for r in values])))
                                    metric = {k:row[k] for k in KEYS}; metric.update(model=name,n=len(values),heading_rmse_deg=rms('heading_error_deg'),
                                        xy_rmse_m=float(np.sqrt(np.mean([r['error_x']**2+r['error_y']**2 for r in values]))),mean_pose_NEES=mean('pose_NEES'),
                                        mean_heading_NEES=mean('heading_NEES'),pose95=mean('pose95'),heading95=mean('heading95'),
                                        bias_rmse_dps=float(np.sqrt(np.mean([(r['bias_est_rad_s']-r['bias_true_rad_s'])**2 for r in values]))*180/np.pi) if bias else None,
                                        accepted_updates=sum(r['status']=='applied' for r in values),rejected_updates=sum(r['status']=='rejected_NIS' for r in values),
                                        mean_heading_squared_error_change=mean('heading_squared_error_change'),mean_position_squared_error_change=mean('position_squared_error_change'))
                                    metrics.append(metric)
                            print(case['id'],channel,rm,seed,len(metrics),flush=True)
    write_csv(args.out/'ABLATION_METRICS.csv',metrics)
    expected = contract['smoke_cells_per_model'] if args.smoke else contract['cells_per_model']
    if any(sum(r['model']==m for r in metrics)!=expected for m in MODELS): raise RuntimeError('Incomplete grid')
    parity = check_parity(metrics,references,contract['parity_abs_tolerance'])
    atomic_json(args.out/'PARITY.json',parity)
    write_csv(args.out/'POOLED_METRICS.csv',pooled_metrics(metrics))
    atomic_json(args.out/'MANIFEST.json',dict(status='COMPLETED',scientific_PASS=False,elapsed_s=time.time()-start,
        started_utc=started_utc,completed_utc=datetime.now(timezone.utc).isoformat(),exit_code=0,
        cells_per_model=expected,models=MODELS,parity=parity,E1_scope='WHOLE_ROUTE_EXPLORATORY_NOT_SPATIALLY_INDEPENDENT',
        sha256={p.name:file_sha(p) for p in args.out.iterdir() if p.is_file()}))

if __name__ == '__main__': main()
