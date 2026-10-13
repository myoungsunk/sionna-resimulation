"""D6-0: independent audit of ORIGINAL LOCAL D5 trace NPZ (USER-RUN).

Requires the original 1.73GB+ local trace evidence, immutable SHA-256 index,
and published D5 cell metrics. No trace is generated, modified or fabricated.
Missing/incomplete evidence is an ERROR, never a quietly skipped comparison.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np

from d6_d9_common import (EVAL_START, THRESHOLD_2D_95, THRESHOLD_3D_95,
                          check_inputs, file_sha, finish, make_out, read_csv,
                          write_csv, wrap)
from run_d5_regimes import timelines

D5_REF = Path('research/EKF3_INDEPENDENT_20261013/diagnostics/results/'
              'AUDITED_RUN_20261013_701b8d2/D5_MULTI_SEED_FULL_ROUTE_METRICS.csv')
INDEX_REF = Path('research/EKF3_INDEPENDENT_20261013/diagnostics/results/'
                 'AUDITED_RUN_20261013_701b8d2/LOCAL_TRACE_INDEX.json')
TRACE_NAME = re.compile(
    r'^(.+?)_(los|full)_(B_OLD|E1_FULL_LORO)_(.+)_L([012])_seed(\d+)_FILTER\.npz$')
ARMS = ('D0','A','B','C')


def acf1(values):
    a = np.asarray(values,float)
    return (float(np.corrcoef(a[:-1],a[1:])[0,1]) if len(a)>2 and
            np.std(a[:-1])>1e-14 and np.std(a[1:])>1e-14 else None)


def audit_trace(file: Path, case: dict, metric_lookup: dict, timeline) -> list[dict]:
    match = TRACE_NAME.match(file.name)
    if match is None:
        raise RuntimeError('D5 trace basename does not match frozen key: '+file.name)
    cid,ch,model,cond,lev,seed = match.groups()
    if cid!=case['id']:
        raise RuntimeError('D5 trace case mismatch')
    t,truth,pids = timeline
    rows=[]
    with np.load(file,allow_pickle=False) as z:
        if not (np.array_equal(z['t_s'],t) and np.array_equal(z['pose_id'],pids) and
                list(z['arms'])==list(ARMS) and list(z['events'])==['predict','update']):
            raise RuntimeError('D5 trace time/pose/arm provenance mismatch')
        n=len(t)
        for arr,shape in (('post_x',(n,4,2,3)),('post_P',(n,4,2,3,3)),
                          ('prior_P',(n,4,2,3,3)),('NIS',(n,4,2)),
                          ('valid',(n,4,2)),('status',(n,4,2))):
            if z[arr].shape!=shape:
                raise RuntimeError(f'D5 trace invalid {arr} shape')
        mask=t>=EVAL_START
        n_eval=int(mask.sum())
        if n_eval==0:
            raise RuntimeError('D5 trace has no evaluated samples')
        for arm_idx, arm in enumerate(ARMS):
            ev=0 if arm=='D0' else 1
            valid=z['valid'][mask,arm_idx,ev]
            if not valid.all():
                raise RuntimeError(f'D5 missing {arm} state/cov snapshot')
            x=np.asarray(z['post_x'][mask,arm_idx,ev],float)
            P=np.asarray(z['post_P'][mask,arm_idx,ev],float)
            Ppre=(P.copy() if arm=='D0' else
                  np.asarray(z['prior_P'][mask,arm_idx,ev],float))
            if not (np.isfinite(x).all() and np.isfinite(P).all() and np.isfinite(Ppre).all()):
                raise RuntimeError('D5 nonfinite audited state or covariance')
            if (np.linalg.eigvalsh(P).min()<=0 or np.linalg.eigvalsh(Ppre).min()<=0):
                raise RuntimeError('D5 nonpositive covariance')
            e=x-truth[mask]
            e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
            pose_nees=np.einsum('ni,ni->n',e,
                  np.linalg.solve(P,e[...,None])[...,0])
            position_nees=np.einsum('ni,ni->n',e[:,:2],
                  np.linalg.solve(P[:,:2,:2],e[:,:2,None])[...,0])
            head_nees=e[:,2]**2/P[:,2,2]
            xy_abs=np.linalg.norm(e[:,:2],axis=1)
            head_abs=np.abs(np.degrees(e[:,2]))
            u=np.column_stack([np.cos(truth[mask,2]),np.sin(truth[mask,2])])
            forward=np.einsum('ni,ni->n',e[:,:2],u)
            Pforward=np.einsum('ni,nij,nj->n',u,P[:,:2,:2],u)
            Ppre_forward=np.einsum('ni,nij,nj->n',u,Ppre[:,:2,:2],u)
            status=z['status'][mask,arm_idx,ev]
            accept=int(np.sum(status=='applied')) if arm!='D0' else 0
            reject=int(np.sum(status=='rejected_NIS')) if arm!='D0' else 0
            nis=np.asarray(z['NIS'][mask,arm_idx,ev],float)
            if arm!='D0' and not np.isfinite(nis).all():
                raise RuntimeError('D5 pre-gate NIS missing')
            observed={'heading_rmse_deg':float(np.sqrt(np.mean(np.degrees(e[:,2])**2))),
                      'xy_rmse_m':float(np.sqrt(np.mean(xy_abs**2))),
                      'mean_pose_NEES':float(np.mean(pose_nees)),
                      'mean_heading_NEES':float(np.mean(head_nees)),
                      'pose95':float(np.mean(pose_nees<=THRESHOLD_3D_95))}
            key=(cid,ch,model,cond,int(lev),int(seed),arm)
            ref=metric_lookup.get(key)
            if ref is None:
                raise RuntimeError('No published D5 metric for audit trace: '+str(key))
            if int(ref['n'])!=n_eval or int(ref['accepted_updates'])!=accept or int(ref['rejected_updates'])!=reject:
                raise RuntimeError('D5 trace count/status parity FAIL: '+str(key))
            for field,val in observed.items():
                if not math.isclose(val,float(ref[field]),rel_tol=1e-10,abs_tol=1e-9):
                    raise RuntimeError(f'D5 trace metric parity FAIL {key} {field}: {val} vs {ref[field]}')
            rows.append({'case':cid,'route':case['route'],'channel':ch,
                'range_model':model,'condition':cond,'level':int(lev),'seed':int(seed),
                'arm':arm,'n':n_eval,
                **observed,
                'pose_xy95':float(np.mean(position_nees<=THRESHOLD_2D_95)),
                'p95_position_error_m':float(np.percentile(xy_abs,95)),
                'p95_absolute_heading_error_deg':float(np.percentile(head_abs,95)),
                'mean_actual_forward_error_m':float(np.mean(forward)),
                'rms_actual_forward_error_m':float(np.sqrt(np.mean(forward**2))),
                'mean_pred_forward_sigma_m':float(np.mean(np.sqrt(Ppre_forward))),
                'mean_post_forward_sigma_m':float(np.mean(np.sqrt(Pforward))),
                'mean_pred_heading_sigma_deg':float(np.mean(np.degrees(np.sqrt(Ppre[:,2,2])))),
                'mean_post_heading_sigma_deg':float(np.mean(np.degrees(np.sqrt(P[:,2,2])))),
                'mean_position_cov_min_eig_m2':float(np.mean(np.linalg.eigvalsh(P[:,:2,:2])[:,0])),
                'mean_position_cov_max_eig_m2':float(np.mean(np.linalg.eigvalsh(P[:,:2,:2])[:,1])),
                'NIS_pre_gate_lag1':acf1(nis) if arm!='D0' else None,
                'accepted_updates':accept,'rejected_updates':reject,
                'comparison_to_published_D5':'EXACT_MATCH_TO_TOLERANCE'})
    return rows


def load_ref(path):
    lookup={}
    for r in read_csv(path):
        key=(r['case'],r['channel'],r['range_model'],r['condition'],
             int(r['level']),int(r['seed']),r['arm'])
        if key in lookup:
            raise RuntimeError('Duplicate D5 reference metric cell')
        lookup[key]=r
    return lookup


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--local-root',type=Path,required=True,
                    help='D5 local_root containing D5_PARTS/ folders; never write here')
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--index',type=Path,default=None)
    ap.add_argument('--reference',type=Path,default=None)
    ap.add_argument('--cases',nargs='*',default=[],
                    help='Optional partial smoke audit; result marked PARTIAL')
    args=ap.parse_args()
    p0=check_inputs()
    from d6_d9_common import REPO
    idxpath=args.index or (REPO/INDEX_REF)
    baseline=args.reference or (REPO/D5_REF)
    if not (idxpath.is_file() and baseline.is_file()):
        raise FileNotFoundError('Immutable D5 index/metric reference is required')
    index=json.loads(idxpath.read_text(encoding='utf-8'))
    entries=index['files']
    if not entries or len({f['path'] for f in entries})!=len(entries):
        raise RuntimeError('D5 trace hash index empty/duplicate')
    bycase={c['id']:c for c in p0['cases']}
    if len(args.cases)!=len(set(args.cases)) or any(c not in bycase for c in args.cases):
        raise ValueError('Invalid D5 audit case selection')
    selected=[entry for entry in entries if not args.cases or
              any(('/'+cid+'_') in ('/'+Path(entry['path']).name) for cid in args.cases)]
    # Filenames include case name in basename; motion entries are route-named,
    # so motion blobs are required for a COMPLETE audit, and declared separately.
    if args.cases:
        selected=[e for e in entries if e['path'].endswith('_FILTER.npz') and
                  any(Path(e['path']).name.startswith(cid+'_') for cid in args.cases)]
    if not selected:
        raise RuntimeError('No D5 trace evidence selected')
    lookup=load_ref(baseline)
    routes=timelines(p0)
    result=[];sha_rows=[];evaluated=set()
    for entry in selected:
        relative=Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe D5 index relative path')
        path=args.local_root/relative
        if not path.is_file() or path.stat().st_size != int(entry['bytes']):
            raise RuntimeError('D5 original local trace missing/size changed: '+str(path))
        actual=file_sha(path)
        if actual!=entry['sha256']:
            raise RuntimeError('D5 original local trace hash changed: '+str(path))
        sha_rows.append({'relative_path':entry['path'],'bytes':int(entry['bytes']),
                         'sha256':actual,'original_index_verified':True})
        if path.name.endswith('_FILTER.npz'):
            match=TRACE_NAME.match(path.name)
            if match is None:
                raise RuntimeError('Invalid D5 named trace')
            cid=match.group(1)
            if cid not in bycase:
                raise RuntimeError('D5 unknown case ID')
            output=audit_trace(path,bycase[cid],lookup,routes[bycase[cid]['route']])
            for row in output:
                key=(row['case'],row['channel'],row['range_model'],row['condition'],
                     row['level'],row['seed'],row['arm'])
                if key in evaluated:
                    raise RuntimeError('Duplicate D5 audited filter cell')
                evaluated.add(key)
            result.extend(output)
    if not result:
        raise RuntimeError('No original D5 FILTER trace was independently scored')
    if not args.cases:
        if len(selected)!=len(entries) or len(evaluated)!=len(lookup):
            raise RuntimeError('D5 full trace/metric closure mismatch: not COMPLETE')
    out=make_out(args.out)
    a=out/'D6_D5_TRACE_COVARIANCE_AUDIT.csv'
    b=out/'D6_D5_VERIFIED_TRACE_INDEX.csv'
    write_csv(a,result);write_csv(b,sha_rows)
    finish(out,'D6_D5_TRACE_AUDIT',vars(args)|{
          'D5_INDEX_SHA256':file_sha(idxpath),
          'D5_METRIC_REFERENCE_SHA256':file_sha(baseline),
          'audit_completeness':'PARTIAL_SMOKE' if args.cases else 'COMPLETE',
          'verified_filter_cells':len(evaluated)},[a,b],caveats=[
              'Local D5 trace NPZ inputs remain untouched and SHA verified',
              'D5 repeated RF scene not an iid ensemble',
              'Prior means after prediction and before RF update; D0 prior=DR-only predicted state',
              'Partial cases are not a full-run provenance PASS'])
    print('D6_D5_TRACE_AUDIT_DONE',str(out))

if __name__=='__main__':
    main()
