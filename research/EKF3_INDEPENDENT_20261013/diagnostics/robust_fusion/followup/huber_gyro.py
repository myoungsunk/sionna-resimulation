"""Frozen Huber-only extension to D5 gyro_bias; no receiver or parameter changes."""
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
sys.path.insert(0, str(HERE.parent/'ablation'))
sys.path.insert(0, str(HERE))
import rf_components as rf
from rf_components import (make_filter, update_filter, key, write_csv, pooled_metrics,
    KEYS, PARITY, check_inputs, original_lut, case_motion, initial_state, wrap,
    eval_covariance, file_sha, atomic_json, archived_direct_s_model)
from d6_d9_common import RS, RR, P3_MODEL, ARCHIVE, PROJECT, FROZEN_BLOB_SHA1, REPO
from run_d5_regimes import run_one

MODELS = ('M0', 'RF_HUBER_ONLY')


def extension_contract(condition, level):
    if condition not in ('noise_pair', 'gyro_bias') or level not in (0, 1, 2):
        raise ValueError('Unsupported condition or level')
    if condition == 'noise_pair' and level != 1:
        raise ValueError('noise_pair reproduction must use frozen level 1')
    contract = rf.component_contract()
    contract.update(schema='HUBER_GYRO_EXTENSION_V1', models=list(MODELS),
        condition=condition, level=level, bias_state=False, mean_correction=False,
        covariance='FROZEN_R0', huber_delta=1.345,
        gyro_bias_condition=('ONLY_GYRO_BIAS_WHITE_WHEEL_GYRO_NOISE_OFF'
            if condition=='gyro_bias' else 'FROZEN_NOISE_PAIR_WHITE_WHEEL_GYRO_NOISE'),
        gyro_bias_magnitude_dps={0: .01, 1: .05, 2: .20}[level] if condition=='gyro_bias' else 0.,
        gyro_bias_sign='FROZEN_SENSOR_SEED_DRIFT_STREAM',
        independent_D5_parity='SMOKE_CASE_SEED0_ALL_12_M0_CELLS_SAME_FROZEN_CACHE_S_RANGE')
    return contract


def check_parity(rows, references, tolerance=1e-8, expected=None):
    maximum = 0.
    counts = dict.fromkeys(MODELS, 0)
    seen = set()
    for row in rows:
        name = row['model']
        if name not in counts:
            raise RuntimeError('Unexpected parity model')
        identity = (name, key(row))
        if identity in seen:
            raise RuntimeError('Duplicate parity cell')
        seen.add(identity)
        if key(row) not in references[name]:
            raise RuntimeError('Missing reference cell')
        ref = references[name][key(row)]
        for field in ('n', 'accepted_updates', 'rejected_updates'):
            if int(row[field]) != int(ref[field]):
                raise RuntimeError('Parity count mismatch '+field)
        for field in PARITY:
            delta = abs(float(row[field])-float(ref[field]))
            if not math.isfinite(delta) or delta>tolerance:
                raise RuntimeError(f'Parity failure {name} {key(row)} {field}: {delta}')
            maximum = max(maximum, delta)
        counts[name] += 1
    if not all(counts.values()) or (expected is not None and any(n != expected for n in counts.values())):
        raise RuntimeError('Incomplete parity grid')
    return dict(status='PASS', cells_per_model=counts, max_abs_difference=maximum, tolerance=tolerance)


def check_d0(rows, tolerance=1e-8):
    references = {key(row): row for row in rows if row['model']=='M0' and row['arm']=='D0'}
    maximum = 0.
    count = 0
    for row in rows:
        if row['model']!='RF_HUBER_ONLY' or row['arm']!='D0':
            continue
        ref=references[key(row)]
        for field in PARITY + ('heading95',):
            difference=abs(float(row[field])-float(ref[field]))
            if not math.isfinite(difference) or difference>tolerance:
                raise RuntimeError('D0 neutral invariance failed '+field)
            maximum=max(maximum,difference)
        for field in ('n','accepted_updates','rejected_updates'):
            if int(row[field])!=int(ref[field]): raise RuntimeError('D0 count mismatch')
        count += 1
    if not count: raise RuntimeError('Missing D0 cells')
    return dict(status='PASS', cells=count, max_abs_difference=maximum, tolerance=tolerance)


def independent_d5_parity(rows, frozen_rows, tolerance):
    refs={key(row):row for row in frozen_rows}
    selected=[row for row in rows if row['model']=='M0' and key(row) in refs]
    maximum=0.
    for row in selected:
        ref=refs[key(row)]
        for field in PARITY:
            difference=abs(float(row[field])-float(ref[field]))
            if not math.isfinite(difference) or difference>tolerance:
                raise RuntimeError('Independent D5 parity failed '+field)
            maximum=max(maximum,difference)
        for field in ('n','accepted_updates','rejected_updates'):
            if int(row[field])!=int(ref[field]): raise RuntimeError('Independent D5 count mismatch')
    if len(selected)!=12 or len(refs)!=12: raise RuntimeError('Incomplete independent D5 parity')
    return dict(status='PASS',cells=12,max_abs_difference=maximum,tolerance=tolerance,
        reference='FROZEN_D5_RUN_ONE_SAME_CACHE_PHYSICAL_RANGE',
        E1='FROZEN_CASE_ROUTE_LORO_NO_NEW_FIT')


def source_hashes():
    paths={HERE/'huber_gyro.py',HERE/'test_huber_gyro.py',HERE/'rf_components.py'}
    paths.update(HERE.parent.glob('*.py'))
    paths.update((HERE.parent/'ablation').glob('*.py'))
    paths.update((HERE.parent.parent).glob('*.py'))
    paths.update([PROJECT/'ekf3.py', ARCHIVE/'qclean_uwb/drivesim/sensor_v2.py',
        ARCHIVE/'qclean_uwb/drivesim/hs_lut.py', ARCHIVE/'qclean_uwb/drivesim/sensors.py'])
    paths.update(REPO/path for path in FROZEN_BLOB_SHA1)
    return {str(path.relative_to(REPO)):file_sha(path) for path in sorted(paths) if path.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'reference', 'out'): ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--condition', choices=('noise_pair','gyro_bias'), default='noise_pair')
    ap.add_argument('--level', type=int, choices=(0,1,2), default=1)
    args = ap.parse_args()
    contract = extension_contract(args.condition,args.level)
    args.out.mkdir(exist_ok=False); start = time.time(); started_utc = datetime.now(timezone.utc).isoformat()
    im = json.loads((args.inputs/'MANIFEST.json').read_text())
    for name, sha in im['sha256'].items():
        if file_sha(args.inputs/name) != sha: raise RuntimeError('Input cache drift '+name)
    if json.loads((args.inputs/'M0_PARITY.json').read_text())['status'] != 'PASS': raise RuntimeError('M0 input gate failed')
    references = {}
    reference_hashes = {}
    ref_manifest = json.loads((args.reference/'RESULT_MANIFEST.json').read_text())
    filename='RF_FULL_RF_COMPONENT_METRICS.csv'; path=args.reference/filename
    if file_sha(path)!=ref_manifest['sha256'][filename]: raise RuntimeError('Reference hash drift')
    archived=list(csv.DictReader(path.open()))
    for name in MODELS:
        references[name]={key(r):r for r in archived if r['model']==name}
    reference_hashes[filename]=file_sha(path)
    p0 = check_inputs(); lut = original_lut(p0); metrics = []; writer = None; d5_rows=[]
    atomic_json(args.out/'EXECUTION_CONTRACT.json', dict(contract=contract, command=sys.argv,
        started_utc=started_utc, reference_manifest_sha256=file_sha(args.reference/'RESULT_MANIFEST.json'),
        input_manifest_sha256=file_sha(args.inputs/'MANIFEST.json'), input_sha256=im['sha256'],
        reference_sha256=reference_hashes, source_sha256=source_hashes(),
        frozen_E1_model_sha256=file_sha(P3_MODEL)))
    with gzip.open(args.out/'RF_COMPONENT_TRACE.csv.gz', 'wt', newline='') as trace:
        for case in p0['cases']:
            if args.smoke and case['id'] != contract['smoke_case']: continue
            model = archived_direct_s_model(lut, anchor_xyz_m=tuple(case['anchor']),
                tag_height_m=case['robot_z_m'], mount_deg=case['mount_deg'])
            for channel in contract['channels']:
                with np.load(args.inputs/(case['id']+'_'+channel+'.npz')) as cache:
                    t, truth, pids = cache['t'], cache['truth'], cache['pose_ids']
                    for rm in contract['range_models']:
                        if rm not in cache: continue
                        mu, cov = np.zeros(2), np.diag([RS,RR])
                        if channel=='full' and rm=='E1_FULL_LORO':
                            if not np.array_equal(cache[rm],cache['E1_outer_'+case['route']]):
                                raise RuntimeError('E1 cache is not frozen case-route LORO')
                        for seed in ([contract['smoke_seed']] if args.smoke else contract['seeds']):
                            mt, mtruth, mpids, motion, oracle = case_motion(p0, case, seed, contract['level'], contract['condition'])
                            if not all(np.array_equal(a,b) for a,b in ((t,mt),(truth,mtruth),(pids,mpids))): raise RuntimeError('Motion/cache mismatch')
                            if case['id']==contract['smoke_case'] and seed==contract['smoke_seed']:
                                _, independent = run_one(case,channel,contract['level'],contract['condition'],seed,
                                    t,truth,pids,dict(s=cache['s']),rm,cache[rm],lut)
                                d5_rows.extend(independent)
                            x0 = initial_state(truth[0], seed)
                            for arm in contract['arms']:
                                d0_baseline=[]
                                for name in MODELS:
                                    f = make_filter(name, x0, contract); values = []
                                    for k in range(len(t)):
                                        if k: f.predict(float(motion['ds_odom'][k]),float(motion['dtheta_gyro'][k]),float(motion['dt_s'][k]))
                                        prior_error = f.pose-truth[k]; prior_error[2] = wrap(prior_error[2]); prior_P=f.Ppose.copy()
                                        st = update_filter(name, f, arm, float(cache['s'][k]),float(cache[rm][k]),model,case,mu,cov,contract['huber_delta'])
                                        if not np.isfinite(f.pose).all() or not np.isfinite(f.Ppose).all():
                                            raise RuntimeError('Nonfinite filter state/covariance')
                                        if np.linalg.eigvalsh((f.Ppose+f.Ppose.T)/2).min()<=0:
                                            raise RuntimeError('Non-positive filter covariance')
                                        if arm=='D0':
                                            if name=='M0': d0_baseline.append((f.pose.copy(),f.Ppose.copy()))
                                            elif not (np.array_equal(f.pose,d0_baseline[k][0]) and np.array_equal(f.Ppose,d0_baseline[k][1])):
                                                raise RuntimeError('D0 per-step state/covariance invariance failed')
                                        if t[k] < contract['eval_start_s']: continue
                                        e = f.pose-truth[k]; e[2] = wrap(e[2]); nees, hn, cover = eval_covariance(e,f.Ppose)
                                        bias = False; bx = None
                                        bp = f.P[3,3] if bias else None
                                        row = dict(case=case['id'],channel=channel,range_model=rm,condition=contract['condition'],level=contract['level'],seed=seed,arm=arm,model=name,
                                            sample_index=k,t_s=t[k],x=f.pose[0],y=f.pose[1],psi=f.pose[2],error_x=e[0],error_y=e[1],heading_error_deg=math.degrees(e[2]),
                                            Pxx=f.Ppose[0,0],Pyy=f.Ppose[1,1],Ppsi=f.Ppose[2,2],Pxy=f.Ppose[0,1],Pxpsi=f.Ppose[0,2],Pypsi=f.Ppose[1,2],
                                            pose_NEES=nees,heading_NEES=hn,pose95=int(cover),heading95=int(hn<=3.841458820694124),
                                            prior_heading_error_deg=math.degrees(prior_error[2]),prior_error_x=prior_error[0],prior_error_y=prior_error[1],
                                            heading_squared_error_change=e[2]**2-prior_error[2]**2,position_squared_error_change=float(e[:2]@e[:2]-prior_error[:2]@prior_error[:2]),
                                            bias_est_rad_s=bx,bias_true_rad_s=oracle['true_bias_rad_s'][k],
                                            true_bias_dps=math.degrees(float(oracle['true_bias_rad_s'][k])),
                                            bias_std_rad_s=math.sqrt(bp) if bias else None,bias_heading_corr=f.P[2,3]/math.sqrt(f.P[2,2]*bp) if bias else None,
                                            NIS=st['NIS'],status=st['status'],huber_weight=st.get('huber_weight'),iterations=st['iterations'],
                                            prior_Pxx=prior_P[0,0],prior_Pyy=prior_P[1,1],prior_Ppsi=prior_P[2,2],R_s=st['R_s'],R_r=st['R_r'])
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
    write_csv(args.out/'RF_COMPONENT_METRICS.csv',metrics)
    expected = contract['smoke_cells_per_model'] if args.smoke else contract['cells_per_model']
    if any(sum(r['model']==m for r in metrics)!=expected for m in MODELS): raise RuntimeError('Incomplete grid')
    parity = dict(
        previous_noise_pair=(check_parity(metrics,references,contract['parity_abs_tolerance'],expected)
            if args.condition=='noise_pair' else dict(status='NOT_AVAILABLE',reason='NO_GYRO_REFERENCE_IN_PRIOR_FOLLOWUP')),
        independent_D5=independent_d5_parity(metrics,d5_rows,contract['parity_abs_tolerance']),
        D0_neutral=check_d0(metrics,contract['parity_abs_tolerance']))
    parity['status']='PASS'
    write_csv(args.out/'D5_INDEPENDENT_METRICS.csv',d5_rows)
    atomic_json(args.out/'PARITY.json',parity)
    write_csv(args.out/'POOLED_METRICS.csv',pooled_metrics(metrics))
    atomic_json(args.out/'MANIFEST.json',dict(status='COMPLETED',scientific_PASS=False,elapsed_s=time.time()-start,
        started_utc=started_utc,completed_utc=datetime.now(timezone.utc).isoformat(),exit_code=0,
        cells_per_model=expected,total_cells=len(metrics),models=MODELS,condition=args.condition,level=args.level,parity=parity,E1_scope='WHOLE_ROUTE_EXPLORATORY_NOT_SPATIALLY_INDEPENDENT',
        sha256={p.name:file_sha(p) for p in args.out.iterdir() if p.is_file()}))

if __name__ == '__main__': main()
