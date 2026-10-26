#!/usr/bin/env python3
"""Explicit staged Office -> Corridor transfer (nothing runs on import).

fetch:   DOWNLOAD RELEASES only (explicit)
prepare: AUDIT + EXTRACT + Office GT labels only (no fit)
fit:     Office-only POWER/PCIR/PWIDE models + source-only gate (no replay)
replay:  Frozen Office models, frozen Corridor P2 RF / controls (no training)
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from office_transfer_core import (load_lock,sha256,download_release,safe_extract_tar,source_dataset_one,
                                  load_source_ffd,PowerTransfer,ResidualTransfer,gate_decision,as_pwide_features)


def save_json(path, data):
    def conv(x):
        if isinstance(x,np.integer):return int(x)
        if isinstance(x,np.floating):return float(x)
        if isinstance(x,Path):return str(x)
        raise TypeError(type(x).__name__)
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False,default=conv)+'\n',encoding='utf-8')


def verify_checkout(checkout: Path, expected: str, label: str) -> str:
    """Fail closed if the source/T2 or target/P2 code revision has moved."""
    root=Path(checkout).resolve()
    try:
        current=subprocess.check_output(
            ['git','-C',str(root),'rev-parse','HEAD'],
            text=True,stderr=subprocess.PIPE).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f'{label}_GIT_CHECKOUT_UNVERIFIED: {root}') from exc
    if current != expected:
        raise ValueError(f'{label}_COMMIT_MISMATCH: expected={expected} got={current}')
    return current


def prepare_office(args):
    lock=load_lock(args.lock)
    source=Path(args.audit_checkout).resolve()
    verify_checkout(source,lock['source_audit_commit'],'SOURCE_AUDIT')
    output=Path(args.out).resolve();output.mkdir(parents=True,exist_ok=True)
    model=load_source_ffd(source)
    qa=[]; frames=[]
    parity_limit=float(lock.get('source_los_model_max_abs_tol',0.05))
    for route in ('O01','O02','O03'):
        archive=Path(args.cache)/lock['paths'][route]['archive']
        if not archive.exists():raise FileNotFoundError('RUN_FETCH_FIRST:'+str(archive))
        dest=Path(args.extracted)/route
        if not dest.exists() or not list(dest.rglob('ARCHIVE_CONTENTS_AND_SHA.json')):
            if dest.exists():raise ValueError('EXTRACTED_DIRECTORY_INCOMPLETE_NO_OVERWRITE:'+str(dest))
            safe_extract_tar(archive,dest,lock['paths'][route]['archive_sha256'])
        else:
            from office_transfer_core import verify_digest
            verify_digest(archive,lock['paths'][route]['archive_sha256'])
        frame,info=source_dataset_one(dest,route,source,model,lock)
        frames.append(frame);qa.append(info)
        if not info['n_los_visible'] or info['model_vs_direct_los_max_abs']>parity_limit:
            save_json(output/'OFFICE_SOURCE_QA_BLOCKED.json',{'technical':'BLOCKED_SOURCE_LoS_MODEL_PARITY',
                'limit_abs':parity_limit,'checked_routes':qa,'training':'NOT_RUN','replay':'NOT_RUN'})
            raise ValueError(f'SOURCE_LoS_MODEL_PARITY_FAIL:{route}:observed={info["model_vs_direct_los_max_abs"]}:limit={parity_limit}')
    data=pd.concat(frames,ignore_index=True)
    if not (set(data.route)=={'O01','O02','O03'}):raise AssertionError('OFFICE_SOURCE_ROUTE_SET')
    if data['pose_id'].isna().any() or data.duplicated(['route','pose_id']).any():
        raise ValueError('SOURCE_POSE_ALIGNMENT_NONUNIQUE')
    if data.loc[~data.los_exists,['e_r','e_s']].notna().any().any():
        raise ValueError('BLOCKED_LOS_LABEL_LEAK')
    if data.loc[data.valid_for_training,['e_r','e_s']].isna().any().any():
        raise ValueError('SOURCE_LABEL_NOT_FINITE')
    f=output/'OFFICE_SOURCE_LABELS.csv.gz'
    data.to_csv(f,index=False,compression='gzip')
    save_json(output/'OFFICE_SOURCE_QA.json',{'technical':'SOURCE_DATASET_PREPARED','model_fitting':'NOT_RUN',
        'recursive_eval':'NOT_RUN','source_checkout':str(source),'label_file_sha256':sha256(f),
        'routes':qa,'valid_training_rows':int(data.valid_for_training.sum())})
    print('SOURCE_PREPARED',f)


def fit_office(args):
    root=Path(args.audit_checkout).resolve()
    verify_checkout(root,load_lock(args.lock)['source_audit_commit'],'SOURCE_AUDIT')
    data=pd.read_csv(args.source_table)
    if not {'route','scene','valid_for_training','los_exists','e_r','e_s','d0_gt_source'}.issubset(data):
        raise ValueError('OFFICE_SOURCE_TABLE_REQUIRED_COLUMNS')
    # Numeric frame flags written as CSV by pandas; enforce robust bool interpretation.
    for key in ['valid_for_training','los_exists']:
        if data[key].dtype!='bool':
            low=data[key].astype(str).str.lower()
            if not low.isin(['true','false']).all():raise ValueError('INVALID_SOURCE_FLAG:'+key)
            data[key]=low=='true'
    tr=data.loc[data.valid_for_training].copy().reset_index(drop=True)
    if not (tr.los_exists.all() and (tr.scene=='OFFICE_E').all()):raise AssertionError('TRAIN_SOURCE_LEAK')
    if set(tr.route.unique())!={'O01','O02','O03'}:raise ValueError('ALL_SOURCE_ROUTES_NEED_VISIBLE_LOS')
    model=load_source_ffd(root)
    power=PowerTransfer.fit(tr)
    residual=ResidualTransfer.fit(tr,model)
    output=Path(args.out);output.mkdir(parents=True,exist_ok=True)
    package={'POWER':power,'RESIDUAL':residual,'source_route_set':sorted(tr.route.unique()),
             'source_only':True,'target_training_used':False,'threshold':residual.gate_tau_d0,
             'status':'TRAINING_ONLY_NO_TARGET_REPLAY'}
    job=output/'OFFICE_TRAINED_MODELS.joblib';joblib.dump(package,job,compress=3)
    save_json(output/'OFFICE_TRAIN_QA.json',{'model_sha256':sha256(job),'training_rows':len(tr),
        'source_count':tr.groupby('route').size().to_dict(),'training_file_sha256':sha256(args.source_table),
        'power_features':['log_fp_power'],'pwide_features':list(residual.medians.index)+['d0'],
        'gate_tau_source_gt_proxy':residual.gate_tau_d0,
        'warning':'source-GT calibrated gate threshold is not a source-prior distribution; evaluate caution',
        'target_replay':'NOT_RUN','status':'SOURCE_TRAINING_COMPLETE'})
    print('TRAINED_SOURCE_ONLY',job)


def load_p2_environment(root):
    """Target P2 checkout must contain the frozen legacy Corridor experiment."""
    root=Path(root).resolve()
    paths=['research/PJ_D0_CIR_P2_RECURSIVE_20261022','research/PJ_DS_GATED_20261021',
           'research/PJ_D0_CIR_PRIOR_P1R_20261022']
    for path in paths:
        a=str(root/path)
        if not Path(a).is_dir():raise FileNotFoundError('LEGACY_P2_CHECKOUT_REQUIRED:'+a)
        if a not in sys.path:sys.path.insert(0,a)
    import p2_replay as R2
    return R2


def common_update(x,P,z,h,H,mu,R,range_only=False):
    """P2 strict_common chi-square gate + Joseph update; never use GT."""
    from scipy.stats import chi2
    active=[0] if range_only else [0,1]
    H0=H[active,:];v=z[active]-h[active]-mu[active];R0=R[np.ix_(active,active)]
    S=H0@P@H0.T+R0;S=(S+S.T)*.5
    nis=float(v@np.linalg.solve(S,v))
    if nis>float(chi2.ppf(.99,len(active))):return x.copy(),P.copy(),False,nis,np.zeros(4)
    K=np.linalg.solve(S,H0@P).T
    nextx=x+K@v;nextx[2]=(nextx[2]+np.pi)%(2*np.pi)-np.pi
    A=np.eye(4)-K@H0
    nextp=A@P@A.T+K@R0@K.T;nextp=(nextp+nextp.T)/2
    return nextx,nextp,True,nis,K[:, -1] if not range_only else np.zeros(4)


def replay_corridor(args):
    """P2 frozen target - full data is required; no auto fit or download."""
    root=Path(args.target_checkout).resolve()
    lock=load_lock(args.lock)
    verify_checkout(root,lock['corridor_p2_commit'],'TARGET_P2')
    R2=load_p2_environment(root);V=R2.V
    package=joblib.load(args.models)
    assert package['source_only'] and not package['target_training_used']
    power=package['POWER'];res=package['RESIDUAL']
    if power.training_scene!='OFFICE_E' or set(res.training_routes)!={'O01','O02','O03'}:
        raise ValueError('TRAIN_PACKAGE_NOT_OFFICE_ONLY')
    case=next(c for c in V.MANIFEST['cases'] if c['id']==args.case)
    if case['route'] not in ('R2','R4','R5'):raise ValueError('EVALUATION_CORRIDOR_ONLY')
    stem=f'{args.case}_full_{args.bias}'
    trace=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
    t=trace['t_s'].astype(float);ids=trace['pose_id'].astype(int)
    truth=trace['truth_scoring_only']
    controls,x0=V.build_positive_bias_controls(t,truth,args.bias)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    sub=obs[(obs.case==args.case)&(obs.channel=='full')].set_index('pose_id').loc[ids]
    z=sub[['range_m','s_fp']].to_numpy(float)
    pk=pd.read_csv(root/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    pk=pk[pk.case==args.case].sort_values('pose_id')
    features,_=R2.full_features(pk,ids)
    if len(features)!=len(t) or np.max(abs(features['sF_+0'].to_numpy(float)-z[:,1]))>1e-9:
        raise AssertionError('TARGET_OBSERVER_PARITY')
    # Frozen in-domain POWER OOF reference; not fit or tuned on this target.
    oldparams=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    mu_corr,R_corr=V.base_params(oldparams,args.case,'full',ids,'POWER_DIAG')
    q_target=features['log_fp_power'].to_numpy(float)
    mu_off,R_off=power.predict(q_target,diag=True)
    q_oob=(q_target<power.q_train_range[0]) | (q_target>power.q_train_range[1])
    names=['C_POWER','O_POWER','O_PWIDE','O_POWER_G','O_PWIDE_G','O_PCIR','O_POWER_STATE_G','O_PWIDE_STATE_G']
    J=len(names);xs=np.tile(np.r_[x0,0.],(J,1))
    P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]);P=np.tile(P0,(J,1,1))
    source_model=V.SourceFFD();log=[]
    for k in range(len(t)):
        if k:
            for j in range(J):
                xs[j],P[j]=V.predict_one(xs[j],P[j],float(controls['ds_odom'][k]),
                                       float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        prior=xs.copy();h,H=source_model.batch(xs,case,gradient=True)
        for j,name in enumerate(names):
            d0=float(z[k,1]-h[j,1]);mm=(mu_corr[k] if name=='C_POWER' else mu_off[k]).copy()
            RR=(R_corr[k] if name=='C_POWER' else R_off[k]).copy()
            zz=z[k].copy(); dhat=0.
            if 'PWIDE' in name:
                dhat=float(res.predict(features.iloc[[k]],np.array([d0]),'PWIDE')[0]);zz[1]-=dhat
            elif name=='O_PCIR':
                dhat=float(res.predict(features.iloc[[k]],np.array([d0]),'PCIR')[0]);zz[1]-=dhat
            policy='STATE' if 'STATE_G' in name else ('D0' if name.endswith('_G') else 'NONE')
            flag=gate_decision(d0,H[j,1],P[j],res.gate_tau_d0,policy)
            xnext,pnext,accept,nis,Kpsi=common_update(xs[j],P[j],zz,h[j],H[j],mm,RR,flag)
            xs[j],P[j]=xnext,pnext
            if not (np.isfinite(xs[j]).all() and np.isfinite(P[j]).all()) or np.min(np.linalg.eigvalsh(P[j]))<-1e-10:
                raise FloatingPointError(f'REPLAY_INVALID {name} {k}')
            # Ground truth enters scoring ONLY after a complete update.
            errpsi=float((xs[j,2]-truth[k,2]+np.pi)%(2*np.pi)-np.pi)*180/np.pi
            xy=float(np.linalg.norm(xs[j,:2]-truth[k,:2]))
            sig=float(np.sqrt(max(P[j,2,2],1e-300)))*180/np.pi
            log.append({'case':args.case,'route':case['route'],'bias':args.bias,'k':k,'t_s':t[k],
                'arm':name,'accepted':bool(accept),'range_only':bool(flag),'d0_raw':d0,'dhat':dhat,
                'nis':nis,'heading_error_deg':errpsi,'xy_error_m':xy,'heading_sigma_deg':sig,
                'gyro_bias_est_radps':xs[j,3],
                'heading_nees':errpsi**2/max(sig**2,1e-300),
                'mu_s':mm[1],'Vs':RR[1,1],'psi_prior_rad':prior[j,2],
                'q_log_fp_power':q_target[k], 'office_q_out_of_range':bool(q_oob[k])})
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    df=pd.DataFrame(log)
    df.to_csv(out/f'{stem}_TRANSFER_SERIES.csv.gz',index=False,compression='gzip')
    rows=[]
    for name,group in df[df.t_s>=30].groupby('arm'):
        rows.append({'case':args.case,'bias':args.bias,'arm':name,'n':len(group),
          'heading_rmse_deg':float(np.sqrt(np.mean(group.heading_error_deg**2))),
          'heading_signed_bias_deg':float(group.heading_error_deg.mean()),
          'heading_q99_deg':float(np.quantile(abs(group.heading_error_deg),.99)),
          'xy_rmse_m':float(np.sqrt(np.mean(group.xy_error_m**2))),
          'heading_nees':float(group.heading_nees.mean()),
          'heading_coverage95':float(np.mean(group.heading_nees<=3.84145882)),
          'accept_frac':float(group.accepted.mean()),'range_only_frac':float(group.range_only.mean()),
          'gyro_bias_mean_radps':float(group.gyro_bias_est_radps.mean()),
          'office_power_out_of_range_frac':float(group.office_q_out_of_range.mean())})
    pd.DataFrame(rows).to_csv(out/f'{stem}_TRANSFER_SCORES.csv',index=False)
    save_json(out/f'{stem}_TRANSFER_QA.json',{'technical':'REPLAY_COMPLETED',
        'model_sha256':sha256(args.models),'source_office_only':True,
        'target_fit_or_tuning':'NONE','target':'Corridor '+args.case,
        'n_steps':len(t),'bias':args.bias,'source_P2_model':str(root)})
    print('TARGET_REPLAY_FINISHED',args.case,args.bias)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lock',type=Path,default=Path(__file__).with_name('lock.json'))
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('fetch',help='EXPLICIT network fetch: 3 Office release assets and digest checks')
    a.add_argument('--cache',type=Path,required=True)
    a=sub.add_parser('prepare',help='Office dataset from EXISTING checked archives, no training')
    a.add_argument('--audit-checkout',type=Path,required=True)
    a.add_argument('--cache',type=Path,required=True)
    a.add_argument('--extracted',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('fit',help='Office-only model training, no Corridor evaluation')
    a.add_argument('--audit-checkout',type=Path,required=True)
    a.add_argument('--source-table',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('replay',help='Explicit frozen Corridor P2 EKF evaluation')
    a.add_argument('--target-checkout',type=Path,required=True)
    a.add_argument('--models',type=Path,required=True)
    a.add_argument('--case',choices=['R2_aA_m0','R2_aA_m45','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0'],required=True)
    a.add_argument('--bias',choices=['B0','L2'],required=True)
    a.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    if args.command=='fetch':
        for r in ('O01','O02','O03'):
            x=download_release(r,args.cache,load_lock(args.lock));print('FETCHED',r,x)
    elif args.command=='prepare':prepare_office(args)
    elif args.command=='fit':fit_office(args)
    elif args.command=='replay':replay_corridor(args)
    else:raise ValueError('UNKNOWN_MODE')

if __name__=='__main__':main()
