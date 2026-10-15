"""Q0 only: frozen input/source audit and read-only numerical reconciliation.

No fit, filter replay, RF generation, Q1 sweep or Q2/Q3 label/model creation.
The archive scorer below is independent of the original N4C score function.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
FREQ = 'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path, git=False):
    p = Path(path)
    h = hashlib.sha1() if git else hashlib.sha256()
    if git:
        h.update(b'blob ' + str(p.stat().st_size).encode() + b'\0')
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')


def exact_file(path, expected, git=False):
    require(Path(path).is_file(), 'MISSING_INPUT:' + str(path))
    got = digest(path, git)
    require(got == expected, 'HASH_MISMATCH:' + str(path))
    return got


def member(z, name):
    found = [p for p in z.namelist() if p == name or p.endswith('/' + name)]
    require(len(found) == 1, 'ARCHIVE_MEMBER_NOT_UNIQUE:' + name)
    return z.read(found[0])


def checked_archive(path, expected):
    exact_file(path, expected)
    z = zipfile.ZipFile(path)
    try:
        require(z.testzip() is None, 'ZIP_CRC_FAILED:' + str(path))
    except Exception:
        z.close()
        raise
    return z


def source_audit(config):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                   text=True).strip()
    require(head == os.environ.get('GITHUB_SHA'), 'SOURCE_COMMIT_MISMATCH')
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'PINNED_CLOUD_EXECUTION_REQUIRED')
    subprocess.run(['git', 'merge-base', '--is-ancestor', config['base_commit'], head],
                   cwd=ROOT, check=True)
    sources = {p: exact_file(ROOT/p, h, git=True)
               for p, h in config['source_blobs'].items()}
    exact_file(HERE/'PLAN_KO.md', config['plan_sha256'])
    current = {}
    for name in ('q0.py', 'test_q0.py', 'q0_lock.json', 'PLAN_KO.md'):
        current[name] = digest(HERE/name)
        if name.endswith('.py'):
            ast.parse((HERE/name).read_text(encoding='utf-8'))
    current['workflow'] = digest(ROOT/'.github/workflows/r5-n4q-q0.yml')
    wf = (ROOT/'.github/workflows/r5-n4q-q0.yml').read_text()
    require(wf.index('--phase pre') < wf.index('python -m unittest discover') < wf.index('--phase verify'),
            'AUDIT_TEST_VERIFY_ORDER')
    require('if: always()' in wf, 'PRESERVE_FAILURE_EVIDENCE')
    mf = json.loads((ROOT/MANIFEST).read_text())
    required = {c[k] for c in mf['cases'] for k in ('full_path','los_path','samples_path')}
    required.add(FREQ)
    assets = {a['path']: a for a in mf['assets']}
    checked = {}
    for p in sorted(required):
        a = assets[p]
        require((ROOT/p).stat().st_size == a['bytes'], 'INPUT_SIZE_MISMATCH:' + p)
        checked[p] = exact_file(ROOT/p, a['sha256'])
    require(len(checked) == 22, 'NOT_22_FROZEN_ASSETS')
    return dict(source_commit=head, source_blobs=sources, q0_sha256=current,
                asset_sha256=checked)


def check_binding(np, a_ids, a_time, b_ids, b_time):
    require(len(np.unique(a_ids)) == len(a_ids), 'DUPLICATE_POSE_ID')
    require(len(np.unique(b_ids)) == len(b_ids), 'DUPLICATE_POSE_ID')
    require(np.array_equal(a_ids, b_ids) and np.array_equal(a_time, b_time),
            'POSE_TIME_BINDING_MISMATCH')
    require(np.isfinite(a_time).all() and np.all(np.diff(a_time) > 0), 'TIME_NOT_MONOTONIC')


def score_archive(np, x, P, status, time, truth, bias):
    require(x.shape == (len(time),4) and P.shape == (len(time),4,4), 'POSTERIOR_SHAPE')
    require(np.isfinite(x).all() and np.isfinite(P).all(), 'POSTERIOR_NONFINITE')
    require(np.allclose(P, P.swapaxes(1,2), atol=1e-12, rtol=0), 'COV_NOT_SYMMETRIC')
    require(np.linalg.eigvalsh(P).min() > 0, 'COV_NOT_PD')
    mask = time >= 30
    require(len(time) == 979 and int(mask.sum()) == 829, 'WRONG_EVALUATION_WINDOW')
    e = x[mask,:3] - truth[mask,:3]
    e[:,2] = (e[:,2]+np.pi)%(2*np.pi)-np.pi
    C = P[mask,:3,:3]
    # Independent Cholesky whitening, instead of the original direct solve.
    whitened = np.linalg.solve(np.linalg.cholesky(C), e[...,None])[...,0]
    pn = np.sum(whitened**2, axis=1)
    hn = e[:,2]**2/C[:,2,2]
    be = x[mask,3] - math.radians(bias)
    st = status[mask]
    return dict(frames=int(mask.sum()),
        heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
        heading_nees=float(hn.mean()), heading_95coverage=float((hn<=3.841458820694124).mean()),
        xy_rmse_m=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
        pose_nees=float(pn.mean()), pose_95coverage=float((pn<=7.814727903251179).mean()),
        bias_rmse_dps=float(np.degrees(np.sqrt(np.mean(be**2)))),
        bias_final_dps=float(np.degrees(x[-1,3])),
        bias_95coverage=float((be**2/P[mask,3,3]<=3.841458820694124).mean()),
        rf_applied=int((st=='APPLIED').sum()), rf_rejected=int((st=='REJECT').sum()),
        accepted_fraction=float((st=='APPLIED').mean()),
        wrong_heading_over5deg_and_overconfident_fraction=float(
            ((abs(np.degrees(e[:,2]))>5)&(hn>3.841458820694124)).mean()))


def close(np, a, b, atol, rtol=0, label='NUMERIC_PARITY'):
    aa, bb = np.asarray(a, float), np.asarray(b, float)
    require(np.isfinite(aa).all() and np.isfinite(bb).all(), 'NONFINITE:' + label)
    require(np.allclose(aa, bb, atol=atol, rtol=rtol), label)
    return float(np.max(np.abs(aa-bb)))


def fd_check(np, lut, case, x, tol):
    """Do not compare a two-sided derivative with one branch at a LUT knot."""
    h, H = lut.model(x,case)
    eps = tol['fd_step']
    def cell(y):
        u,v=y[0]-case['anchor'][0],y[1]-case['anchor'][1]
        angles = np.array([np.degrees(np.arctan2(np.hypot(u,v),case['anchor'][2]-case['robot_z_m'])),
                           np.degrees(np.arctan2(-v,u)),
                           (np.degrees(np.arctan2(-v,-u)-y[2])-case['mount_deg']+180)%360-180])
        return np.floor((angles + np.array([0,180,180]))/2).astype(int)
    if np.hypot(x[0]-case['anchor'][0],x[1]-case['anchor'][1]) <= tol['pole_exclusion_m']:
        return dict(status='INDETERMINATE_POLE', max_error=None)
    maximum = 0.
    for j in range(3):
        a=x.copy();b=x.copy();a[j]+=eps;b[j]-=eps
        if not np.array_equal(cell(a),cell(b)):
            return dict(status='INDETERMINATE_KNOT_OR_SEAM', max_error=None)
        deriv=(lut.model(a,case)[0]-lut.model(b,case)[0])/(2*eps)
        maximum=max(maximum, close(np, deriv, H[:,j], tol['fd_atol'], label='SMOOTH_FFD_JACOBIAN'))
    require(np.array_equal(H[:,3],np.zeros(2)), 'DIRECT_BIAS_DERIVATIVE_NONZERO')
    close(np, lut.model(x+np.array([0,0,2*np.pi,0]),case)[0], h,
          tol['seam_value_atol'], label='YAW_PERIODICITY')
    return dict(status='PASS', max_error=maximum)


def angular_boundaries(np, lut, tol):
    rows=[]
    eps=tol['seam_side_eps_deg']
    for axis in (1,2):
        for knot in (-180.,-90.,0.,90.,180.):
            args=np.array([20.3,31.7,-67.3]);args[axis]=knot
            left=args.copy();right=args.copy();left[axis]-=eps;right[axis]+=eps
            vc,gc=lut(*args);vl,gl=lut(*left);vr,gr=lut(*right)
            # At knots each side has its own derivative. Jumps are legitimate.
            close(np, (vr-vc)/eps, gr[axis], tol['fd_atol'], label='KNOT_RIGHT_DERIVATIVE')
            close(np, (vc-vl)/eps, gl[axis], tol['fd_atol'], label='KNOT_LEFT_DERIVATIVE')
            periodic=args.copy();periodic[axis]+=360
            close(np, vc, lut(*periodic)[0], tol['seam_value_atol'], label='ANGULAR_SEAM_VALUE')
            rows.append(dict(axis=['theta','phi_tx','phi_rx'][axis], knot_deg=knot,
                value=vc, derivative_left=float(gl[axis]), derivative_right=float(gr[axis]),
                status='SIDES_PASS_CENTRAL_DERIVATIVE_INDETERMINATE'))
    # Polar (nonperiodic) interior knot, separately from the singular anchor pole.
    a=np.array([40.,31.7,-67.3]);l=a.copy();r=a.copy();l[0]-=eps;r[0]+=eps
    vc,_=lut(*a);vl,gl=lut(*l);vr,gr=lut(*r)
    close(np,(vr-vc)/eps,gr[0],tol['fd_atol'],label='THETA_KNOT_RIGHT')
    close(np,(vc-vl)/eps,gl[0],tol['fd_atol'],label='THETA_KNOT_LEFT')
    rows.append(dict(axis='theta',knot_deg=40.,derivative_left=float(gl[0]),
        derivative_right=float(gr[0]),status='SIDES_PASS_CENTRAL_DERIVATIVE_INDETERMINATE'))
    return rows


def setup():
    import numpy as np
    import pandas as pd
    for p in ('research/R5_N4B_20261015','research/PHYSICS_RS_STAGED_20261015/code',
              'research/R5_FULLRF_B0_GATES_20261015','research/EKF4_RANGE_S_STAGED_20261014'):
        sys.path.insert(0,str(ROOT/p))
    return np,pd


def reconcile(np,pd,config,zips,pol_path,out):
    import n4b_rf_errors as old
    from p3_rf_adapter4 import FrozenLut
    from features import extract
    tol=config['tolerances']
    spec=importlib.util.spec_from_file_location('frozen_pol_q0_reference',pol_path)
    pol=importlib.util.module_from_spec(spec);spec.loader.exec_module(pol)
    mf=json.loads((ROOT/MANIFEST).read_text());cases={c['id']:c for c in mf['cases']}
    data=old.create_dataset(np,pd,mf)
    parity=old.original_14_parity(np,data,zips['rf'])
    pd.DataFrame(parity).to_csv(out/'Q0_OBSERVER_PARITY.csv',index=False)
    full=data[data.channel=='full'].copy();los=data[data.channel=='los'].copy()
    keys=['case','pose_id']
    require(not full.duplicated(keys).any() and not los.duplicated(keys).any(),'PAIR_DUPLICATES')
    pairs=full.merge(los,on=keys,suffixes=('_full','_los'),validate='one_to_one')
    require(len(pairs)==len(full)==len(los)==9519,'PAIRED_RF_COUNT')
    for k in ('x_eval','y_eval','yaw_eval_rad'):
        close(np,pairs[k+'_full'],pairs[k+'_los'],0,label='NATIVE_LOS_POSE_PAIRING')
    lut=FrozenLut(ROOT)
    close(np,lut.dt,2.,0,label='THETA_GRID_NOT_2DEG');close(np,lut.dp,2.,0,label='PHI_GRID_NOT_2DEG')
    geo=pd.read_csv(io.BytesIO(member(zips['pol'],'POL_V1_GEOMETRY_ORACLE.csv.gz')),compression='gzip')
    require(len(geo)==9519 and not geo.duplicated(keys).any(),'POL_GEOMETRY_COUNT_OR_DUPLICATE')
    indexed=full.set_index(keys,verify_integrity=True)
    max_geo=0.;fds=[];med=[]
    for case,g in geo.groupby('case',sort=True):
        source=indexed.loc[[(case,int(v)) for v in g.pose_id]]
        close(np,source[['x_eval','y_eval','yaw_eval_rad']],g[['x_eval','y_eval','yaw_eval_rad']],0,
              label='POL_GEOMETRY_SOURCE_BINDING')
        features=[]
        for row in source.itertuples():
            x=np.array([row.x_eval,row.y_eval,row.yaw_eval_rad,0.])
            f=pol.physical_features(np,lut,x,cases[case]);features.append(f)
        ff=pd.DataFrame(features)
        for col in ('s_los_expected','p_m1_los','p_m2_los','balance_los','p_dom_los','Hpsi_lut','Ipsi_nominal'):
            max_geo=max(max_geo,close(np,ff[col],g[col],tol['geometry_atol'],label='POL_GEOMETRY_PARITY:'+col))
        med.append(dict(case=case,n=len(g),median_abs_Hpsi=float(ff.Hpsi_lut.abs().median()),
                        median_balance=float(ff.balance_los.median()),median_I_geom=float(ff.Ipsi_nominal.median())))
        for j in np.unique(np.linspace(0,len(source)-1,64).astype(int)):
            row=source.iloc[j];x=np.array([row.x_eval,row.y_eval,row.yaw_eval_rad,0.])
            fds.append(dict(case=case,pose_id=int(row.name[1]),**fd_check(np,lut,cases[case],x,tol)))
    require(sum(r['status']=='PASS' for r in fds)>0,'NO_SMOOTH_JACOBIAN_TESTS')
    require({r['case'] for r in fds if r['status']=='PASS'}==set(cases),'FD_MISSING_CASE')
    # No port reinterpretation: check that swapping measured RX ports negates s.
    freqs=np.load(ROOT/FREQ,allow_pickle=False)
    for c in mf['cases']:
        h=np.load(ROOT/c['full_path'],mmap_mode='r',allow_pickle=False)[:4,:,:,0]
        a=extract(h,freqs);b=extract(h[:,:,::-1],freqs)
        close(np,a['s_fp'],-b['s_fp'],tol['observer_atol'],label='RX_PORT_SIGN')
        close(np,a['range_m'],b['range_m'],tol['observer_atol'],label='RX_PORT_RANGE')
    splits=[]
    from scipy.spatial import cKDTree
    for held,tr,te in old.feature_splits(np,full):
        nearest=float(cKDTree(full.loc[te,['x_eval','y_eval']]).query(full.loc[tr,['x_eval','y_eval']])[0].min())
        require(nearest>1e-4 and held not in set(full.loc[tr,'route']),'TRAIN_TEST_SPATIAL_LEAK')
        splits.append(dict(held=held,train_routes=sorted(set(full.loc[tr,'route'])),train_n=int(tr.sum()),
            test_n=int(te.sum()),minimum_train_test_distance_m=nearest,
            train_keys_sha256=hashlib.sha256(full.loc[tr,keys].to_csv(index=False).encode()).hexdigest(),
            test_keys_sha256=hashlib.sha256(full.loc[te,keys].to_csv(index=False).encode()).hexdigest(),
            mount45_training_present=bool((full.loc[tr,'mount_feature']==1).any())))
    # These are frozen summaries; do not refit their historical models in Q0.
    prior=pd.read_csv(io.BytesIO(member(zips['pol'],'POL_V1_PRE_RF_PRIOR_TRANSFER.csv')))
    polmeta=json.loads(member(zips['pol'],'POL_V1_FINAL.json'))
    require(polmeta['source_sha']=='003b97bf4ba70b7bfa2669ce2c081517a24d58d5','POL_EXECUTED_SOURCE')
    require(len(prior)==8 and set(prior.n)=={979},'POL_PRIOR_WINDOW')
    for r in polmeta['pre_rf_prior_transfer']:
        q=prior[(prior.case==r['case'])&(prior.bias_level==r['bias_level'])&(prior.test_pose_source==r['test_pose_source'])]
        require(len(q)==1,'POL_PRIOR_SUMMARY_DUPLICATE')
        for col in ('mean_nll','joint95'):
            close(np,q.iloc[0][col],r[col],tol['metric_atol'],label='POL_PRIOR_SUMMARY')
    require(json.loads(member(zips['pol_review'],'POL_V1_AUDITED_CASE_REVIEW.json'))['status']=='N4B_POL_V1_INDEPENDENT_AUDIT_PASS','POL_REVIEW_STATUS')
    # Independent re-score of existing N4C x/P. No recursive filter is run.
    metrics=pd.read_csv(io.BytesIO(member(zips['n4c'],'N4C_RECURSIVE_ALL_METRICS.csv')))
    require(len(metrics)==304,'N4C_METRIC_COUNT')
    mkeys=['case','channel','bias','method','policy','gate_mode']
    require(not metrics.duplicated(mkeys).any(),'N4C_METRIC_DUPLICATE')
    traces=json.loads(member(zips['rf'],'P2_ONE_STEP_SUMMARY.json'))['per_case']
    packet={(r['case'],r['channel']):r for r in traces}
    rescored=[]
    for (case,ch,bias,method),group in metrics.groupby(['case','channel','bias','method']):
        p=packet[(case,ch)]
        raw=member(zips['rf'],p['trace_file'])
        require(hashlib.sha256(raw).hexdigest()==p['trace_sha256'],'ORIGINAL_TRACE_SHA')
        with np.load(io.BytesIO(raw),allow_pickle=False) as z:
            truth=z['truth_for_offline_scoring_only'].copy();tt=z['t_s'].copy();ids=z['pose_id'].copy()
        with np.load(io.BytesIO(member(zips['r2'],f'{case}_{ch}_{bias}_seed0_recursive.npz')),allow_pickle=False) as r2:
            check_binding(np,ids,tt,r2['pose_id'],r2['t_s'])
        with np.load(io.BytesIO(member(zips['n4c'],f'N4C_{case}_{ch}_{bias}_{method}.npz')),allow_pickle=False) as z:
            check_binding(np,ids,tt,z['pose_id'],z['t_s'])
            pairs2=list(zip(z['policies'].tolist(),z['gate_modes'].tolist()))
            require(len(set(pairs2))==len(pairs2)==len(group),'N4C_POLICY_BINDING')
            for row in group.itertuples(index=False):
                j=pairs2.index((row.policy,row.gate_mode))
                vals=score_archive(np,z['estimate'][:,j],z['covariance'][:,j],z['status'][:,j],tt,truth,row.true_gyro_bias_dps)
                maxerr=0.
                for k,v in vals.items():
                    maxerr=max(maxerr,close(np,v,getattr(row,k),tol['metric_atol'],tol['metric_rtol'],label='N4C_METRIC:'+k))
                rescored.append(dict(case=case,channel=ch,bias=bias,method=method,policy=row.policy,
                    gate_mode=row.gate_mode,max_abs_metric_difference=maxerr,**vals))
    review=json.loads(member(zips['n4c_review'],'N4C_INDEPENDENT_REVIEW.json'))
    require(review['status']=='N4C_INDEPENDENT_OUTPUT_AUDIT_PASS','N4C_REVIEW_STATUS')
    power=[]
    for r in rescored:
        if r['channel']=='full' and r['gate_mode']=='natural' and r['policy']=='POWER_JOINT':
            b=next(x for x in rescored if x['case']==r['case'] and x['bias']==r['bias'] and
                   x['method']==r['method'] and x['channel']=='full' and x['policy']=='BASE_R0' and x['gate_mode']=='natural')
            ok=all(r[k]<=b[k]+1e-9 for k in ('heading_rmse_deg','bias_rmse_dps','pose_nees')) and r['pose_95coverage']>=b['pose_95coverage']-1e-9
            power.append(dict(case=r['case'],bias=r['bias'],method=r['method'],four_metrics_nondegradation=ok))
    require(len(power)==16 and all(r['four_metrics_nondegradation'] for r in power),'POWER_JOINT_REPORT_RECONCILIATION')
    pd.DataFrame(rescored).to_csv(out/'Q0_N4C_ARCHIVE_RESCORE.csv',index=False)
    pd.DataFrame(fds).to_csv(out/'Q0_JACOBIAN_SMOOTH_CHECKS.csv',index=False)
    pd.DataFrame(angular_boundaries(np,lut,tol)).to_csv(out/'Q0_ANGULAR_BOUNDARIES.csv',index=False)
    write(out/'Q0_SPLITS.json',splits)
    write(out/'Q0_HISTORICAL_RECONCILIATION.json',dict(geometry_cases=med,geometry_max_abs_error=max_geo,
        pol_prior_transfer=prior.to_dict('records'),pol_prior_reproduction='FROZEN_SUMMARY_RECONCILIATION_NO_REFIT',
        n4c_metric_rows_rescored=len(rescored),power_joint_four_metric_checks=power,
        robust_scale_max_not_rescored='Not saved in original posterior NPZ',
        original_baseline_tolerance='Historical 1e-6 parity retained; not promoted to strict exact equality'))
    return dict(native_paired_packets=len(pairs),observer_traces=len(parity),
        observer_frames=sum(r['rows'] for r in parity),geometry_rows=len(geo),geometry_max_abs_error=max_geo,
        jacobian_smooth_pass=sum(r['status']=='PASS' for r in fds),
        jacobian_nondifferentiable_or_pole=sum(r['status']!='PASS' for r in fds),
        n4c_rescored_rows=len(rescored),power_joint_nondegradation=16,
        source_interpretation='TX0 +45 LP, RX +/-45 LP; no extra TX angle subtraction',
        oracle_policy='GT only offline geometry/parity/scoring; no model training or estimator calls')


def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['pre','verify'],required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--audit',type=Path)
    p.add_argument('--inputs',type=Path);p.add_argument('--pol-source',type=Path)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    config=json.loads((HERE/'q0_lock.json').read_text())
    receipt=dict(stage='Q0',status='FAIL',scientific_PASS=False,stop_after='Q0',
        command=sys.argv,utc=datetime.now(timezone.utc).isoformat(),config_sha256=digest(HERE/'q0_lock.json'))
    try:
        evidence=source_audit(config)
        receipt.update(evidence)
        if args.phase=='pre':
            receipt.update(status='GO',exit_code=0)
            write(args.out/'Q0_PRE_AUDIT.json',receipt)
            return 0
        require(args.audit is not None and args.inputs is not None and args.pol_source is not None,'VERIFY_ARGUMENTS')
        pre=json.loads(args.audit.read_text())
        require(pre['status']=='GO' and pre['source_commit']==evidence['source_commit'] and
                pre['config_sha256']==receipt['config_sha256'] and
                all(pre[k]==evidence[k] for k in ('q0_sha256','source_blobs','asset_sha256')),'STALE_OR_FAILED_PREAUDIT')
        np,pd=setup()
        import scipy,sklearn
        versions=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,
                      scipy=scipy.__version__,sklearn=sklearn.__version__)
        require(versions==config['runtime'],'RUNTIME_NOT_PINNED:'+str(versions))
        receipt['runtime']=versions
        exact_file(args.pol_source,config['pol_source_blob'],git=True)
        receipt['pol_reference_source_blob']=config['pol_source_blob']
        with ExitStack() as stack:
            zips={k:stack.enter_context(checked_archive(args.inputs/(str(v['id'])+'.zip'),v['sha256']))
                  for k,v in config['archives'].items()}
            receipt['archive_sha256']={k:v['sha256'] for k,v in config['archives'].items()}
            receipt['numerical_checks']=reconcile(np,pd,config,zips,args.pol_source,args.out)
        receipt.update(status='TECHNICAL_PASS',exit_code=0,
            limitations=['LUT knot/seam two-sided derivative is INDETERMINATE; side checks separately pass',
              'POL prior NLL/coverage reconciled from original summaries; no model refit',
              'Same corridor only; R4/R5 training lacks Mount45; no independent RF/noise seed',
              'Q1/Q2/Q3 and Q4+ not implemented or executed'])
        return 0
    except Exception as e:
        receipt.update(error=repr(e),exit_code=2)
        traceback.print_exc()
        return 2
    finally:
        if args.phase=='verify' or receipt['status']!='GO':
            receipt['outputs']={f.name:digest(f) for f in sorted(args.out.iterdir()) if f.is_file()}
            write(args.out/'Q0_INPUT_PARITY.json',receipt)
        print(json.dumps(dict(stage='Q0',phase=args.phase,status=receipt['status'],
                              error=receipt.get('error')),ensure_ascii=False),flush=True)


if __name__=='__main__':
    raise SystemExit(main())
