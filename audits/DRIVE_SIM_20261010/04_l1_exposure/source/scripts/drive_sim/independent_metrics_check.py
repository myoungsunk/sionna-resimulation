"""Stage 1 only: deterministic trajectory capture and independent metric arithmetic."""
import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.stats import chi2
import validation_repair as V

OUT = V.OUT / 'METRICS_INDEPENDENT_CHECK_20261008'

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def dump(name, obj):
    (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def inputs():
    manifest=json.loads((V.OUT/'INPUT_MANIFEST.json').read_text())
    paths=[Path(p) for p in manifest['inputs']]
    paths += list(V.OUT.glob('*.*'))
    paths += [V.ROOT/'scripts/drive_sim/validation_repair.py', V.ROOT/'src/qclean_uwb/drivesim/filters.py', V.ROOT/'src/qclean_uwb/drivesim/uncertainty.py']
    return {str(p):digest(p) for p in sorted(set(paths)) if p.is_file()}

def independent(est, fullcov, truth, keep):
    if keep.dtype != bool or not keep.any(): raise ValueError('EMPTY_OR_INVALID_EVALUATION')
    err=est[keep,:3]-truth[keep]
    err[:,2]=np.arctan2(np.sin(err[:,2]),np.cos(err[:,2]))
    p=fullcov[keep][:,[0,1,2]][:,:,[0,1,2]]
    if not np.isfinite(err).all() or not np.isfinite(p).all(): raise ValueError('NONFINITE_RUN')
    if not np.allclose(p,p.swapaxes(1,2),rtol=0,atol=1e-12): raise ValueError('ASYMMETRIC_COVARIANCE')
    chol=np.linalg.cholesky(p)
    z=np.linalg.solve(chol,err[...,None])[...,0]
    nees=np.sum(z*z,axis=1)
    lo,hi=chi2.ppf([.025,.975],df=3)
    result=dict(n_eval=int(keep.sum()),pos_rmse_m=float(np.sqrt(np.average(np.square(err[:,0])+np.square(err[:,1])))),heading_rmse_deg=float(np.sqrt(np.average(np.square(err[:,2])))*180/math.pi),
        nees_mean=float(np.average(nees)),pose_cov95=float(np.count_nonzero(nees<=chi2.ppf(.95,3))/len(nees)),
        heading_cov95=float(np.mean(np.abs(err[:,2])<=1.95996398454*np.sqrt(p[:,2,2]))),
        nees_lower_tail=float(np.mean(nees<lo)),nees_upper_tail=float(np.mean(nees>hi)),
        pos_max_m=float(np.sqrt(np.square(err[:,:2]).sum(1)).max()),heading_max_deg=float(np.abs(err[:,2]).max()*180/math.pi),
        cov_trace_mean=float(np.trace(p,axis1=1,axis2=2).mean()),min_cov_eig=float(np.linalg.eigvalsh(p).min()))
    return result,err,nees

def arithmetic_checks():
    cov=np.eye(6)[None,:,:];cov[0,:3,:3]=[[2,1,0],[1,2,0],[0,0,.5]]
    est=np.zeros((1,6));est[0,:3]=[1,0,2*math.pi+.1]
    m,e,n=independent(est,cov,np.zeros((1,3)),np.array([True]))
    assert abs(n[0]-(2/3+.02))<1e-12
    assert abs(e[0,2]-.1)<1e-12 and abs(m['pos_rmse_m']-1)<1e-12
    assert abs(m['heading_rmse_deg']-math.degrees(.1))<1e-12
    empty_rejected=False
    try: independent(est,cov,np.zeros((1,3)),np.array([False]))
    except ValueError: empty_rejected=True
    assert empty_rejected
    bad=cov.copy();bad[0,0,0]=-1
    psd_rejected=False
    try: independent(est,bad,np.zeros((1,3)),np.array([True]))
    except np.linalg.LinAlgError: psd_rejected=True
    assert psd_rejected
    from scipy.optimize import brentq
    from scipy.special import gammainc
    thresholds={str(q):brentq(lambda x:gammainc(1.5,x/2)-q,0,100) for q in (.025,.95,.975)}
    assert all(abs(x-chi2.ppf(float(q),3))<1e-10 for q,x in thresholds.items())
    return dict(offdiagonal_covariance=True,radian_wrap=True,rmse_units=True,empty_rejected=True,non_psd_rejected=True,independent_cdf_inversion=thresholds)

class RecordingFilter(V.F.DriveFilter):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.k=0; self.kind=None; self.events=[]
    def predict(self,*a,**kw):
        self.k+=1; return super().predict(*a,**kw)
    def _gate_ok(self,nis):
        accepted=super()._gate_ok(nis)
        self.events.append((self.k,0 if self.kind=='range' else 1,float(nis),bool(accepted)))
        return accepted
    def update_range(self,*a,**kw):
        self.kind='range'
        x,p=self.mean_cov();cfg=self.cfg
        d=math.sqrt((x[0]-cfg.anchor_xyz[0])**2+(x[1]-cfg.anchor_xyz[1])**2+(cfg.anchor_xyz[2]-cfg.robot_z)**2)
        h=np.zeros(6);h[:2]=(x[:2]-cfg.anchor_xyz[:2])/d
        var=cfg.range_sigma**2+cfg.range_quant_var+cfg.range_extra_sigma**2
        nis=float((a[0]-d-cfg.range_offset)**2/(h@p@h+var))
        rejected=self.stats['r_rejected']
        result=super().update_range(*a,**kw)
        self.events.append((self.k,0,nis,self.stats['r_rejected']==rejected))
        return result
    def update_s(self,*a,**kw):
        self.kind='s'; return super().update_s(*a,**kw)

def capture(data,cfg,inp,obs,x0):
    f=RecordingFilter(cfg,data['lut'],x0); states=[]; covs=[]
    for k in range(len(data['t'])):
        if k:
            f.predict(inp['ds_odom'][k],inp['dtheta_gyro'][k])
            f.update_odom_heading(inp['dtheta_odom'][k],inp['dtheta_gyro'][k],inp['ds_odom'][k])
            if obs['detected'][k]:
                f.update_range(obs['range_m'][k]); f.update_s(obs['s'][k],*obs['power'][k])
        x,p=f.mean_cov();states.append(x.copy());covs.append(p.copy())
    return np.array(states),np.array(covs),np.array(f.events,float),f.stats

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');a=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    if a.prepare:
        if (OUT/'PLAN.json').exists(): raise ValueError('DO_NOT_OVERWRITE_PLAN')
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=V.ROOT,text=True).strip()
        if head!=V.REV: raise ValueError('REVISION_DRIFT')
        dump('PLAN.json',dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),revision=head,
            scope='Only user step 1; no model edits, no RF generation, no step 2',
            reason='Historical estimate/covariance arrays not saved; capture deterministic replay, then independently calculate metrics.',
            models=['constant','distance','joint'],seeds=list(range(5000,5024)),
            split='Reuse stored STEP5 evaluation_indices, independently verify against t>=30 and final40% excluding calibration pose IDs.',
            independent_arithmetic='atan2(sin,cos) radian wrapping, full6x6 covariance indices [0,1,2], Cholesky whitening; df3 ellipsoid95, df1 marginal heading95; equal seed means.',
            comparisons='all72 expected runs; report every failure, never drop/replace failed seeds; abs tolerance1e-8, relative1e-10',
            nis='record actual pre-gate scalar NIS and acceptance; distinguish all/accepted/rejected and held-out/full replay',
            command='py -3.10 -X utf8 scripts/drive_sim/independent_metrics_check.py',hashes=inputs(),script_sha256=digest(__file__)))
        print('PLAN RECORDED');return
    plan=json.loads((OUT/'PLAN.json').read_text())
    for p,h in plan['hashes'].items():
        if digest(p)!=h: raise ValueError('INPUT_DRIFT '+p)
    amendment=json.loads((OUT/'INSTRUMENTATION_AMENDMENT.json').read_text()) if (OUT/'INSTRUMENTATION_AMENDMENT.json').exists() else {}
    if digest(__file__)!=amendment.get('corrected_script_sha256',plan['script_sha256']): raise ValueError('SCRIPT_DRIFT')
    data=V.load();cal,ev,models,_=V.tables(data)
    stored=json.loads((V.OUT/'STEP5_CALIBRATION.json').read_text())
    evstored=np.zeros(len(data['t']),bool);evstored[stored['evaluation_indices']]=True
    if not np.array_equal(ev,evstored): raise ValueError('MASK_MISMATCH')
    ids=np.arange(len(data['t']))
    independent_cal=(ids<math.floor(.4*len(ids)))&(data['t']>=30)
    independent_eval=(ids>=math.floor(.6*len(ids)))&(data['t']>=30)&~np.isin(data['ids'],data['ids'][independent_cal])
    if not np.array_equal(independent_eval,evstored): raise ValueError('INDEPENDENT_MASK_MISMATCH')
    checks=arithmetic_checks()
    original=json.loads((V.OUT/'STEP6_JOINT_EVALUATION.json').read_text())
    refs={(r['seed'],r['model']):r for r in original['runs']}
    if len(refs)!=72 or len(original['runs'])!=72: raise ValueError('MISSING_OR_DUPLICATE_LEGACY_RUN')
    results=[];failures=[];npzfiles={}
    for seed in plan['seeds']:
        inp,x0=V.physical(seed,data);obs=V.makeobs(data,seed)
        for name,table in models.items():
            try:
                cfg=V.cfg0(table.scalar_rms);cfg.s_residual_table=table
                est,cov,events,st=capture(data,cfg,inp,obs,x0)
                met,err,nees=independent(est,cov,data['truth'],evstored)
                comparisons={k:dict(independent=v,reported=refs[seed,name][k],abs_difference=abs(v-refs[seed,name][k]),matches=bool(np.isclose(v,refs[seed,name][k],atol=1e-8,rtol=1e-10))) for k,v in met.items()}
                nis={}
                for kind,label in [(0,'range'),(1,'s')]:
                    mask=(events[:,1]==kind)&evstored[events[:,0].astype(int)]
                    vals=events[mask,2];acc=events[mask,3].astype(bool)
                    nis[label]=dict(n_all=len(vals),n_accepted=int(acc.sum()),n_rejected=int((~acc).sum()),pre_gate_mean=float(vals.mean()),accepted_only_mean=float(vals[acc].mean()) if acc.any() else None,rejected_only_mean=float(vals[~acc].mean()) if (~acc).any() else None,reported_mean=refs[seed,name]['nis_r_mean' if kind==0 else 'nis_s_mean'],reported_matches_pre_gate=bool(np.isclose(vals.mean(),refs[seed,name]['nis_r_mean' if kind==0 else 'nis_s_mean'],atol=1e-8,rtol=1e-10)),full_replay_rejected=int(np.sum((events[:,1]==kind)&(events[:,3]==0))))
                    if nis[label]['full_replay_rejected']!=refs[seed,name]['r_rejected' if kind==0 else 's_rejected']: raise ValueError('REJECTION_COUNT_MISMATCH')
                path=OUT/f'{name}_{seed}.npz'
                np.savez_compressed(path,estimate=est,covariance6=cov,truth=data['truth'],time_s=data['t'],pose_ids=data['ids'],evaluation_mask=evstored,error3=err,nees=nees,gate_events=events)
                npzfiles[path.name]=digest(path)
                results.append(dict(seed=seed,model=name,metrics=met,comparisons=comparisons,nis=nis))
            except Exception as exc:
                failures.append(dict(seed=seed,model=name,error=repr(exc)))
        print('CAPTURED SEED',seed,flush=True)
    summary={name:{k:float(np.mean([r['metrics'][k] for r in results if r['model']==name])) if any(r['model']==name for r in results) else None for k in ('pos_rmse_m','heading_rmse_deg','nees_mean','pose_cov95','heading_cov95')} for name in models}
    preserved=all(digest(p)==h for p,h in plan['hashes'].items())
    passed=len(results)==72 and not failures and preserved and all(c['matches'] for r in results for c in r['comparisons'].values()) and all(n['reported_matches_pre_gate'] for r in results for n in r['nis'].values())
    dump('RESULT.json',dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),status='ARITHMETIC_CONFIRMED' if passed else 'REDIRECT',not_rf_pass=True,
        historical_arrays_available=False,evaluation_samples=int(ev.sum()),calibration_samples=int(cal.sum()),
        arithmetic_checks=checks,independent_mask_matches=True,
        thresholds=dict(df_pose=3,coverage95=float(chi2.ppf(.95,3)),tail_lower=float(chi2.ppf(.025,3)),tail_upper=float(chi2.ppf(.975,3))),
        runs=results,failures=failures,summary=summary,preserved=preserved,npz_hashes=npzfiles))
    print(json.dumps(dict(status=passed,summary=summary,failures=failures),ensure_ascii=False))
    if not passed: raise SystemExit(1)

if __name__=='__main__':main()
