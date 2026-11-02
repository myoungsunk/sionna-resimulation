"""P2: frozen matched-model synthetic experiment, GitHub Actions only.

All algorithms receive identical noisy increments, observations, initial pose.
Ground truth is only used for generating synthetic data and for scoring.
Independent complex-integral motion generates truth (not core.transition).
Input noise variances are the declared known synthetic control-noise schedule.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import traceback
from datetime import datetime, timezone
import numpy as np
from core import SyntheticRF, predict, gaussian_update, map_update, wrap
from validate import sha, write

HERE=Path(__file__).resolve().parent


def table(path, rows):
    if not rows:
        return
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)


def generate(spec, path_index, trial, bias_dps):
    dt=spec['dt_s']; steps=round(spec['duration_s']/dt)
    name=spec['paths'][path_index]
    rng=np.random.default_rng(np.random.SeedSequence([spec['seed_start']+trial,path_index]))
    truth=np.zeros((steps+1,4));truth[0,:3]=spec['initial_true_pose']
    truth[:,3]=math.radians(bias_dps)
    ds=np.zeros(steps);dtheta=np.zeros(steps)
    q=np.zeros((steps,2,2))
    model=SyntheticRF()
    R=np.diag([spec['range_noise_sd_m']**2,spec['s_noise_sd']**2])
    R[0,1]=R[1,0]=spec['RF_cross_covariance']
    z=np.zeros((steps,2))
    initial_noise=rng.normal(size=3)*np.asarray(spec['initial_estimate_error_sd'])
    initial=truth[0,:3]+initial_noise
    initial[2]=wrap(initial[2])
    for k in range(steps):
        t=k*dt
        v=.2 if name!='return' or t<30 else -.2
        omega=.015 if name=='turn' else 0.
        d=v*dt;a=omega*dt
        integral=1. if a==0 else np.expm1(1j*a)/(1j*a)
        movement=d*np.exp(1j*truth[k,2])*integral
        truth[k+1,:2]=truth[k,:2]+[movement.real,movement.imag]
        truth[k+1,2]=wrap(truth[k,2]+a)
        q[k]=np.diag([spec['distance_variance_per_m']*abs(d),
                      math.radians(spec['gyro_arw_dps_per_sqrt_s'])**2*dt])
        ds[k]=d+math.sqrt(q[k,0,0])*rng.normal()
        dtheta[k]=a+truth[k,3]*dt+math.sqrt(q[k,1,1])*rng.normal()
        z[k]=model(truth[k+1])[0]+np.linalg.cholesky(R)@rng.normal(size=2)
    return {'truth':truth,'initial':initial,'initial_noise':initial_noise,
            'ds':ds,'gyro':dtheta,'Q2':q,'z':z,'R':R,'dt':np.full(steps,dt)}


def score(truth, states, covs, bias_dps):
    truth=truth[1:len(states)+1]
    e=states[:,:3]-truth[:,:3]
    e[:,2]=wrap(e[:,2])
    Cp=covs[:,:3,:3]
    sol=np.linalg.solve(Cp,e[...,None])[...,0]
    nees=np.einsum('ij,ij->i',e,sol)
    heading_nees=e[:,2]**2/covs[:,2,2]
    row={'samples':len(e),'heading_MSE_deg2':float(np.mean(np.degrees(e[:,2])**2)),
         'position_MSE_m2':float(np.mean(np.sum(e[:,:2]**2,axis=1))),
         'mean_pose_NEES':float(np.mean(nees)),
         'mean_heading_NEES':float(np.mean(heading_nees)),
         'pose95':float(np.mean(nees<=7.814727903251179)),
         'heading95':float(np.mean(heading_nees<=3.841458820694124)),
         'final_heading_error_deg':float(np.degrees(e[-1,2])),
         'final_bias_error_dps':None,'bias95':None}
    if states.shape[1]==4:
        be=states[:,3]-math.radians(bias_dps)
        row['final_bias_error_dps']=float(np.degrees(be[-1]))
        row['bias95']=float(np.mean(be**2/covs[:,3,3]<=3.841458820694124))
    if not all(np.isfinite(v) for v in row.values() if v is not None):
        raise RuntimeError('nonfinite score')
    return row


def run_model(data, name, spec, cell, out):
    n=4 if name.endswith('4') else 3
    x=data['initial'].copy()
    P=np.diag(np.asarray(spec['initial_estimate_error_sd'])**2)
    if n==4:
        x=np.r_[x,math.radians(spec['bias_prior_mean_dps'])]
        P4=np.zeros((4,4));P4[:3,:3]=P
        P4[3,3]=math.radians(spec['bias_prior_sd_dps'])**2;P=P4
    model=SyntheticRF();states=[];covs=[];iters=[];costs=[]
    failed=False
    try:
        for k in range(len(data['ds'])):
            Q=data['Q2'][k]
            if n==4:
                Q4=np.zeros((3,3));Q4[:2,:2]=Q
                Q4[2,2]=spec['bias_random_walk']*data['dt'][k];Q=Q4
            xm,Pm,_,_=predict(x,P,data['ds'][k],data['gyro'][k],data['dt'][k],Q)
            if name.startswith('MAP'):
                result=map_update(xm,Pm,data['z'][k],model,data['R'],range_first=True,
                                  max_iter=spec['MAP_max_iter'],gradient_tol=spec['MAP_gradient_tol'])
                if result.status!='CONVERGED':
                    np.savez_compressed(out/'FAILED_STEP.npz',prior_x=xm,prior_P=Pm,
                                        z=data['z'][k],R=data['R'],solution=result.x,
                                        prior_delta=result.prior_delta)
                    write(out/'FAILURE.json',{'cell':cell,'model':name,'step':k,
                         't_s':float((k+1)*data['dt'][k]),'solver_status':result.status,
                         'cost':result.cost,'gradient_inf':result.gradient_inf,
                         'history':result.history,'classification':'NUMERICAL_SOLVER_NOT_CONVERGED',
                         'scientific_contradiction':False})
                    raise RuntimeError('MAP nonconvergence; evidence preserved, no silent fallback')
                x,P=result.x,result.P
                iters.append(result.iterations);costs.append(result.cost)
            else:
                x,P,_=gaussian_update(xm,Pm,data['z'][k],model,data['R'])
                iters.append(1);costs.append(0.)
            states.append(x.copy());covs.append(P.copy())
    except Exception:
        failed=True
        raise
    finally:
        np.savez_compressed(out/(name+('_PARTIAL' if failed else '')+'.npz'),
                            states=np.asarray(states),covariances=np.asarray(covs),
                            iterations=np.asarray(iters),costs=np.asarray(costs))
    result=score(data['truth'],np.asarray(states),np.asarray(covs),cell['true_bias_dps'])
    result['max_iterations']=max(iters)
    # Read-back all saved state/covariance arrays and recompute every trial metric.
    with np.load(out/(name+'.npz'),allow_pickle=False) as saved:
        repeated=score(data['truth'],saved['states'],saved['covariances'],cell['true_bias_dps'])
    for key,value in repeated.items():
        if value is not None and abs(value-result[key])>1e-12:
            raise RuntimeError('saved trace score mismatch')
    return result


def summarize(rows,spec,out):
    summary=[];contrasts=[]
    boot=np.random.default_rng(spec['bootstrap_seed'])
    for path in spec['paths']:
        for bias in spec['true_bias_dps']:
            subset=[r for r in rows if r['path']==path and r['true_bias_dps']==bias]
            for model in spec['models']:
                group=[r for r in subset if r['model']==model]
                assert len(group)==spec['trials_per_path_bias']
                d={'path':path,'true_bias_dps':bias,'model':model,'trials':len(group)}
                d['heading_RMSE_deg']=float(np.sqrt(np.mean([r['heading_MSE_deg2'] for r in group])))
                d['position_RMSE_m']=float(np.sqrt(np.mean([r['position_MSE_m2'] for r in group])))
                for key in ['mean_pose_NEES','mean_heading_NEES','pose95','heading95','final_bias_error_dps','bias95']:
                    values=[r[key] for r in group if r[key] is not None]
                    d[key]=float(np.mean(values)) if values else None
                d['max_iterations']=max(r['max_iterations'] for r in group)
                summary.append(d)
            for low,high in [('MAP3','MAP4'),('EKF3','EKF4'),('EKF4','MAP4')]:
                a={r['trial']:r for r in subset if r['model']==low}
                b={r['trial']:r for r in subset if r['model']==high}
                ids=sorted(a);assert ids==sorted(b)
                delta=np.array([b[i]['heading_MSE_deg2']-a[i]['heading_MSE_deg2'] for i in ids])
                samples=boot.integers(0,len(delta),size=(spec['bootstrap_draws'],len(delta)))
                limits=np.quantile(np.mean(delta[samples],axis=1),[.025,.975])
                verdict='SUPPORT' if limits[1]<0 else ('CONTRADICTED' if limits[0]>0 else 'INCONCLUSIVE')
                contrasts.append({'path':path,'true_bias_dps':bias,'contrast':high+'-'+low,
                                  'mean_heading_MSE_delta_deg2':float(delta.mean()),
                                  'CI95_low':float(limits[0]),'CI95_high':float(limits[1]),
                                  'verdict':verdict,'trials':len(delta),
                                  'primary':bias==.05 and high=='MAP4' and low=='MAP3'})
    table(out/'SUMMARY.csv',summary);table(out/'PAIRED_CONTRASTS.csv',contrasts)
    write(out/'SUMMARY.json',summary);write(out/'PAIRED_CONTRASTS.json',contrasts)
    return summary,contrasts


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--gates',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('P2 experiment must execute in GitHub Actions')
    gate=json.loads((args.gates/'FINAL.json').read_text())
    assert gate['git_sha']==os.environ['GITHUB_SHA']
    assert gate['stages']['P0']==gate['stages']['P1']=='PASS'
    assert gate['source_sha256']['core.py']==sha(HERE/'core.py')
    spec=json.loads((HERE/'P2_SPEC.json').read_text())
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    start={'stage':'P2','started_utc':datetime.now(timezone.utc).isoformat(),
           'git_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
           'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'python':platform.python_version(),
           'spec':spec,'spec_sha256':sha(HERE/'P2_SPEC.json'),
           'source_sha256':{p.name:sha(p) for p in HERE.glob('*.py')},
           'gate_receipt_sha256':sha(args.gates/'FINAL.json'),'command':sys.argv,
           'scientific_PASS':False}
    write(out/'START.json',start)
    rows=[];summary=[];contrasts=[];exit_code=0;status='NOT_RUN'
    try:
        for pi,path in enumerate(spec['paths']):
            for bias in spec['true_bias_dps']:
                for trial in range(spec['trials_per_path_bias']):
                    cell={'path':path,'true_bias_dps':bias,'trial':trial}
                    directory=out/'trials'/path/str(bias)/f'{trial:03d}'
                    directory.mkdir(parents=True,exist_ok=False)
                    data=generate(spec,pi,trial,bias)
                    np.savez_compressed(directory/'INPUTS.npz',**data)
                    for model in spec['models']:
                        result=run_model(data,model,spec,cell,directory)
                        rows.append({**cell,'model':model,**result})
                    table(out/'TRIAL_METRICS.csv',rows)
                    if (trial+1)%10==0:
                        print('PROGRESS',path,bias,trial+1,'complete_trials',len(rows)//4,flush=True)
        summary,contrasts=summarize(rows,spec,out)
        primaries=[c for c in contrasts if c['primary']]
        assert len(primaries)==3
        status='SYNTHETIC_HYPOTHESIS_SUPPORTED' if all(c['verdict']=='SUPPORT' for c in primaries) else 'HYPOTHESIS_REVIEW_REQUIRED'
        exit_code=0 if status=='SYNTHETIC_HYPOTHESIS_SUPPORTED' else 2
    except Exception as exc:
        status='FAIL_CLOSED_NUMERICAL_OR_IMPLEMENTATION'
        exit_code=1
        (out/'TRACEBACK.log').write_text(traceback.format_exc(),encoding='utf-8')
        print(traceback.format_exc(),flush=True)
        table(out/'PARTIAL_TRIAL_METRICS.csv',rows)
    final={**start,'status':status,'exit_code':exit_code,'completed_model_trials':len(rows),
           'completed_paired_trials':len(rows)//4,'summary':summary,'contrasts':contrasts,
           'ended_utc':datetime.now(timezone.utc).isoformat(),
           'later_stages':{f'P{i}':'NOT_RUN' for i in range(3,7)},
           'input_truth_role':'synthetic generation/scoring only; not passed to estimator updates',
           'output_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}}
    write(out/'FINAL.json',final)
    compact={k:v for k,v in final.items() if k not in ('output_sha256','spec','source_sha256')}
    print('P2_FINAL '+json.dumps(compact,ensure_ascii=False,allow_nan=False),flush=True)
    return exit_code


if __name__=='__main__':
    raise SystemExit(main())
