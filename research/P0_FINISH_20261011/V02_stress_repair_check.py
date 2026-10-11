#!/usr/bin/env python3
"""Stage A only. No RF raytracing, no P1. Predeclared V02 failure dissection.
Gaussian range moment update is an explicitly marked candidate, not hidden
R inflation or a replacement of legacy evidence. Legacy cases remain scored.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import chi2,binom
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.body_ekf_bridge import V2BodyFilterConfig as Config
from qclean_uwb.drivesim.sensors import DRIFT_LEVELS
DT=.2;N=240;CHECK=(0,60,120,240)
SMALL=np.array([.03,.03,np.radians(2),.001,.002,.003])
MODES=('SMALL_OFF','SMALL_IDEAL_RANGE','SMALL_IDEAL_RANGE_S','LARGE_IDEAL_RANGE','LARGE_GH5_RANGE','LARGE_GH9_RANGE',
       'HIGH_LEGACY_OFF','HIGH_NO_WHEELBASE','HIGH_NO_SLIP','HIGH_PRIOR_MATCHED','HIGH_MATCHED_NO_WHEELBASE','HIGH_MATCHED_NO_WHEELBASE_NO_SLIP',
       'HIGH_GAUSSIAN_MODELED_OFF','HIGH_GAUSSIAN_MODELED_RANGE')
GH={n:np.polynomial.hermite.hermgauss(n) for n in (5,9)}

def gh_range(f,z,n):
    c=f.comps[0];x,P=c.x,c.P;xy=P[:2,:2];L=np.linalg.cholesky(xy)
    points,weights=GH[n];u,v=np.meshgrid(points,points,indexing='ij');w=(weights[:,None]*weights[None,:]/np.pi).ravel()
    dx=np.sqrt(2)*np.c_[u.ravel(),v.ravel()]@L.T;p=x[:2]+dx
    h=np.sqrt((p[:,0]-4.)**2+p[:,1]**2+2.2**2);hm=float(w@h);e=h-hm
    crossxy=(dx*w[:,None]).T@e
    cross=P[:,:2]@np.linalg.solve(xy,crossxy)
    S=float(w@(e*e)+.08**2);K=cross/S
    c.x=x+K*(z-hm);c.x[2]=V.wrap(c.x[2]);c.P=P-np.outer(cross,cross)/S;c.P=(c.P+c.P.T)/2
    assert np.linalg.eigvalsh(c.P).min()>-1e-10

def trial(mode,seed):
    large=mode.startswith('LARGE');high=mode.startswith('HIGH');high_gauss=mode.startswith('HIGH_GAUSSIAN')
    nominal=np.array([2.,.5,.2,0.,0.,0.]);std=np.asarray(Config().p0_std,float).copy() if large or high else SMALL.copy()
    if high and ('MATCHED' in mode or high_gauss):
        lev=DRIFT_LEVELS[2];std[3:]=[np.radians(lev.gyro_bias_dps),lev.gyro_sf,lev.wheel_ratio]
    initial_rng=np.random.default_rng([20261011,int(seed),2002]);eps=initial_rng.normal(size=6)*std
    if high and not high_gauss:
        truth0=nominal.copy();est0=nominal.copy();est0[:3]-=eps[:3]
        parameters={'wheelbase':0.} if 'NO_WHEELBASE' in mode else None
    else:
        truth0=nominal+eps;est0=nominal.copy()
        parameters=dict(gyro_bias=float(truth0[3]),gyro_sf=float(truth0[4]),wheel_asymmetry=float(truth0[5]),wheelbase=0.,common_scale=0.)
    slip='time' if high and not high_gauss and 'NO_SLIP' not in mode else 'off'
    t=np.arange(N+1)*DT;ds=np.r_[0.,np.full(N,.04)];ang=np.r_[0.,.012*np.sin(np.arange(N)/17)]
    ds[181:201]=0.;ang[181:201]=.04
    gen=V.SensorV2Config(level=2 if high else 1,condition='all',slip_mode=slip)
    inp,ev=V.generate(t,ds,ang,gen,seed,parameters=parameters)
    parameters_true=dict(zip([str(s) for s in ev['parameter_names']],ev['true_parameters']))
    true=V.integrate(ds,ang,truth0[:3]);true6=np.c_[true,ev['true_bias_rad_s'],np.full(N+1,parameters_true['gyro_sf']),np.full(N+1,parameters_true['wheel_asymmetry'])]
    cfg=Config(model_version='sensor-v2',kind='ekf',s_mode='direct',use_s=False,use_range=False,anchor_xyz=(4.,0.,2.65),robot_z=.45,range_offset=0.,range_sigma=.08,range_extra_sigma=0.,range_quant_var=0.,bias_rw_std=0.,gate=float('inf'))
    f=F.SensorV2Filter(cfg,None,est0,P0=np.diag(std**2))
    rng=np.random.default_rng([20261011,int(seed),8002]);noise_r=rng.normal(0,.08,N+1);noise_s=rng.normal(0,.06,N+1)
    with_range=(('RANGE' in mode) and not mode.endswith('OFF'))
    errs=[];covs=[];n_odom_reject=0
    # Pre-RF prior is retained separately; k0 after ideal observation never labeled prior.
    prior_error=true6[0]-est0;prior_error[2]=V.wrap(prior_error[2]);initial_P=np.diag(std**2)
    for k in range(N+1):
        if k:
            rec=f.step(float(inp['ds_odom'][k]),float(inp['dtheta_gyro'][k]),float(inp['dtheta_odom'][k]),DT);n_odom_reject+=rec['status']=='rejected'
        if with_range:
            r=float(np.sqrt((true[k,0]-4.)**2+true[k,1]**2+2.2**2))+noise_r[k]
            if 'GH5' in mode:gh_range(f,r,5)
            elif 'GH9' in mode:gh_range(f,r,9)
            else:f.range_record(r)
        if mode=='SMALL_IDEAL_RANGE_S':
            x,P=f.mean_cov();hh=-np.cos(2*x[2]);H=np.zeros(6);H[2]=2*np.sin(2*x[2])
            f.scalar(-np.cos(2*true[k,2])+noise_s[k],hh,H,.06**2,'s')
        if k in CHECK:
            x,P=f.mean_cov();e=true6[k]-x;e[2]=V.wrap(e[2]);errs.append(e);covs.append(P.copy())
    return np.asarray(errs),np.asarray(covs),prior_error,initial_P,n_odom_reject

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);ap.add_argument('--seeds',default=128,type=int);ap.add_argument('--start-seed',default=256,type=int);a=ap.parse_args();o=a.out;o.mkdir(parents=True,exist_ok=True)
    results=[];arrays={}
    for mode in MODES:
        vals=[trial(mode,s) for s in range(a.start_seed,a.start_seed+a.seeds)]
        e=np.stack([v[0] for v in vals]);P=np.stack([v[1] for v in vals]);pe=np.stack([v[2] for v in vals]);pP=np.stack([v[3] for v in vals]);reject=[v[4] for v in vals]
        arrays[mode+'__error']=e;arrays[mode+'__P6']=P;arrays[mode+'__prior_error']=pe;arrays[mode+'__prior_P6']=pP
        for it,k in enumerate(CHECK):
            x=e[:,it,:3];C=P[:,it,:3,:3];nees=np.einsum('ni,ni->n',x,np.linalg.solve(C,x[...,None])[...,0]);mean=float(nees.mean());coverage=float(np.mean(nees<=chi2.ppf(.95,3)))
            n=len(x);family_count=len(MODES)*len(CHECK);lo,hi=chi2.ppf([.025/family_count,1-.025/family_count],3*n)/n
            clo,chi=binom.ppf([.025/family_count,1-.025/family_count],n,.95)/n
            results.append(dict(mode=mode,k=k,time_s=k*DT,n=n,mean_pose_NEES=mean,pose95coverage=coverage,mean_NEES_family_low=float(lo),mean_NEES_family_high=float(hi),coverage_family_low=float(clo),coverage_family_high=float(chi),NEES_family_PASS=bool(lo<=mean<=hi),coverage_family_PASS=bool(clo<=coverage<=chi),heading_bias_deg=float(np.degrees(x[:,2].mean())),position_bias_m=float(np.linalg.norm(x[:,:2].mean(axis=0))),heading_RMSE_deg=float(np.degrees(np.sqrt(np.mean(x[:,2]**2)))),position_RMSE_m=float(np.sqrt(np.mean(np.sum(x[:,:2]**2,axis=1)))),mean_odom_rejections=float(np.mean(reject))))
        pd.DataFrame(results).to_csv(o/'V02_STRESS_CHECKPOINTS.csv',index=False)
        print('V02_STRESS_MODE',mode,[z for z in results if z['mode']==mode and z['k']==240],flush=True)
    np.savez_compressed(o/'V02_STRESS_EXACT_FLOAT64_TENSORS.npz',**arrays,seeds=np.arange(a.start_seed,a.start_seed+a.seeds),checkpoints=np.asarray(CHECK))
    data=pd.DataFrame(results)
    # Unmodified failed arms are retained and cannot be waived by candidate success.
    status=dict(execution='COMPLETE',V02_overall_PASS=bool(data.NEES_family_PASS.all() and data.coverage_family_PASS.all()),n_modes=len(MODES),n_seeds=a.seeds,start_seed=a.start_seed,n_filter_runs=len(MODES)*a.seeds,failed_checkpoints=data[~(data.NEES_family_PASS&data.coverage_family_PASS)].to_dict('records'),candidate_only_modes=['LARGE_GH5_RANGE','LARGE_GH9_RANGE'],high_prior_matching='known distribution RMS, not true per-run parameters',limitations=['Gaussian chi-square coverage test is diagnostic for non-Gaussian legacy signed priors; retained failed arms remain unapproved','GH5/GH9 change nonlinear range moment update only and are not adopted production code','No P1 execution until final all-gate approval'],stage_B_allowed=False)
    (o/'STATUS.json').write_text(json.dumps(status,indent=2,allow_nan=False));print('V02_STRESS_RESULT',json.dumps(status),flush=True)
    # Original source bytes for independent local reanalysis.
    files=list((ROOT/'src/qclean_uwb/drivesim').glob('*.py'))+list((ROOT/'research/P0_RESTORE_20261011').glob('*.py'))+[Path(__file__)]
    for p in files:
        d=o/'source_snapshot'/p.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True);d.write_bytes(p.read_bytes())
    (o/'SOURCE_SHA256.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
if __name__=='__main__':main()
