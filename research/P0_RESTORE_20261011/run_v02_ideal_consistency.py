#!/usr/bin/env python3
"""P0 V02 numerical and statistical sensor/filter controls. No ray tracing.
Ideal s is explicitly SYNTHETIC, not antenna performance. No fitting after results.
"""
from __future__ import annotations
import argparse,json,math,sys
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import chi2,binom
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
DT=.2;N=240;CHECK=[0,60,120,240]
SMALL=np.array([.03,.03,np.radians(2),.001,.002,.003])
ARMS=['MATCHED_OFF','MATCHED_RANGE','MATCHED_RANGE_S','NO_SHARED_C','EXACT_PRIMITIVE_Q',
      'LARGE_GAUSSIAN_RANGE','EULER_TRUTH_OFF','MATCHED_BIAS_RW','ENCODER_SLIP_OFF',
      'LEGACY_LOW_OFF','LEGACY_MID_OFF','LEGACY_HIGH_OFF']

def numeric_checks():
    tests=[]
    for angle in [0.,1e-7,.01,-.1]:
        x=np.array([2.,.5,.3,.003,.002,.005]);d=.04;g=angle;dt=.2;b=.287
        h,Fm,Gm=F.transition(x,d,g,dt,b);JF=np.zeros((6,6));JG=np.zeros((6,3))
        def diff(a,z):
            r=a-z;r[2]=V.wrap(r[2]);return r
        for j in range(6):
            xx=x.copy();xm=x.copy();xx[j]+=1e-7;xm[j]-=1e-7
            JF[:,j]=diff(F.transition(xx,d,g,dt,b)[0],F.transition(xm,d,g,dt,b)[0])/2e-7
        for j in range(2):
            args1=[d,g];args2=[d,g];args1[j]+=1e-7;args2[j]-=1e-7
            JG[:,j]=diff(F.transition(x,*args1,dt,b)[0],F.transition(x,*args2,dt,b)[0])/2e-7
        h0,H,B=F.odometry_model(x,d,g,dt,b);JH=np.zeros(6)
        for j in range(6):
            xp=x.copy();xm=x.copy();xp[j]+=1e-7;xm[j]-=1e-7
            JH[j]=(F.odometry_model(xp,d,g,dt,b)[0]-F.odometry_model(xm,d,g,dt,b)[0])/2e-7
        tests.append(dict(gyro=angle,F_error=float(abs(Fm-JF).max()),G_error=float(abs(Gm-JG).max()),
                          H_odom_error=float(abs(H-JH).max())))
    assert max(max(r['F_error'],r['G_error'],r['H_odom_error']) for r in tests)<1e-5
    # Exact no-noise, no-prior-uncertainty reproduction, SE2 versus SE2.
    ds=np.r_[0.,np.full(N,.04)];a=np.r_[0.,.02*np.sin(np.arange(N)/20)]
    t=np.arange(N+1)*DT;truth=V.integrate(ds,a,(2.,.5,.2))
    inputs,_=V.generate(t,ds,a,V.SensorV2Config(condition='none'),0)
    cfg=FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_s=False,use_range=False,
         k_s=0.,k_theta=0.,k_stheta=0.,gyro_N_rad_sqrt_s=0.,bias_rw_std=0.)
    f=F.SensorV2Filter(cfg,None,np.r_[truth[0],0.,0.,0.],P0=np.zeros((6,6)))
    err=0.
    for k in range(1,N+1):
        f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],DT)
        ee=truth[k]-f.mean_cov()[0][:3];ee[2]=V.wrap(ee[2]);err=max(err,float(abs(ee).max()))
    assert err<1e-10
    return tests,err

def modified_step(f,d,g,o,dt,q,no_C=False):
    c=f.comps[0];cfg=f.cfg;xp=c.x.copy();b=cfg.wheel_base
    c.x,ff,gg=F.transition(xp,d,g,dt,b);c.P=ff@c.P@ff.T+gg@q@gg.T
    h,H,B=F.odometry_model(xp,d,g,dt,b);C=np.zeros(6) if no_C else -gg@q@B
    rr=float(B@q@B);nu=o-h
    # Same frozen source gate constant; only advertised C/Q is changed.
    S=float(H@c.P@H+rr+2*H@C)
    if S>1e-20 and nu*nu/S<=F.CHI2_1_999:
        c.x,c.P,_=F.correlated_update(c.x,c.P,H,nu,rr,C)
    c.P[3,3]+=cfg.bias_rw_std**2*dt

def trial(arm,seed):
    legacy=arm.startswith('LEGACY_');level={'LEGACY_LOW_OFF':0,'LEGACY_MID_OFF':1,'LEGACY_HIGH_OFF':2}.get(arm,1)
    pstd=np.asarray(FilterConfig().p0_std) if legacy or arm=='LARGE_GAUSSIAN_RANGE' else SMALL.copy()
    P0=np.diag(pstd*pstd);nominal=np.array([2.,.5,.2,0.,0.,0.])
    rng=np.random.default_rng([20261011,seed,2002]);initial_error=rng.normal(size=6)*pstd
    if legacy:
        true_initial=nominal.copy();est0=nominal.copy();est0[:3]-=initial_error[:3]
        parameters=None
    else:
        true_initial=nominal+initial_error;est0=nominal.copy()
        parameters=dict(gyro_bias=float(true_initial[3]),gyro_sf=float(true_initial[4]),
                        wheel_asymmetry=float(true_initial[5]),wheelbase=0.,common_scale=0.)
    t=np.arange(N+1)*DT;ds=np.r_[0.,np.full(N,.04)];ang=np.r_[0.,.012*np.sin(np.arange(N)/17)]
    ds[181:201]=0.;ang[181:201]=.04 # deliberate in-place turn to expose slip assumptions
    rw=math.radians(.005) if arm=='MATCHED_BIAS_RW' else 0.
    gen=V.SensorV2Config(level=level,condition='all',slip_mode=('time' if legacy or arm=='ENCODER_SLIP_OFF' else 'off'),bias_rw_rad_s_sqrt_s=rw)
    inp,ev=V.generate(t,ds,ang,gen,seed,parameters=parameters)
    pars=dict(zip([str(s) for s in ev['parameter_names']],ev['true_parameters']))
    true=V.integrate(ds,ang,true_initial[:3])
    if arm=='EULER_TRUTH_OFF':
        for k in range(1,N+1):true[k,:2]=true[k-1,:2]+ds[k]*np.array([np.cos(true[k-1,2]),np.sin(true[k-1,2])])
    true6=np.c_[true,ev['true_bias_rad_s'],np.full(N+1,pars['gyro_sf']),np.full(N+1,pars['wheel_asymmetry'])]
    isrange=arm in ('MATCHED_RANGE','MATCHED_RANGE_S','LARGE_GAUSSIAN_RANGE')
    cfg=FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_s=False,use_range=isrange,
        anchor_xyz=(4.,0.,2.65),robot_z=.45,range_offset=0.,range_sigma=.08,range_extra_sigma=0.,range_quant_var=0.,
        bias_rw_std=rw,gate=float('inf'))
    f=F.SensorV2Filter(cfg,None,est0,P0=P0)
    obs_rng=np.random.default_rng([20261011,seed,8002]);noise_r=obs_rng.normal(0,.08,N+1);noise_s=obs_rng.normal(0,.06,N+1)
    rows=[];innov=[]
    for k in range(N+1):
        if k:
            d,g,o=[float(inp[n][k]) for n in ['ds_odom','dtheta_gyro','dtheta_odom']]
            if arm=='NO_SHARED_C':
                Q=np.diag([cfg.k_s*abs(d),cfg.gyro_N_rad_sqrt_s**2*DT,cfg.k_theta*abs(o)+cfg.k_stheta*abs(d)])
                modified_step(f,d,g,o,DT,Q,True)
            elif arm=='EXACT_PRIMITIVE_Q':
                Q=np.diag([gen.k_distance_m*abs(ds[k]),gen.gyro_N_rad_sqrt_s**2*DT,gen.k_yaw_rad*abs(ang[k])+gen.k_yaw_distance_rad2_m*abs(ds[k])])
                modified_step(f,d,g,o,DT,Q,False)
            else:f.step(d,g,o,DT)
        if isrange:
            rr=float(np.linalg.norm(true[k]-np.array([4.,0.,0.]))) if False else float(np.sqrt((true[k,0]-4)**2+true[k,1]**2+2.2**2))
            r=f.range_record(rr+noise_r[k]);innov.append(dict(arm=arm,seed=seed,k=k,kind='range',NIS=float(r[0]**2/r[2])))
        if arm=='MATCHED_RANGE_S':
            x=f.mean_cov()[0];h=-np.cos(2*x[2]);H=np.zeros(6);H[2]=2*np.sin(2*x[2])
            r=f.scalar(-np.cos(2*true[k,2])+noise_s[k],h,H,.06**2,'s');innov.append(dict(arm=arm,seed=seed,k=k,kind='analytic_s',NIS=float(r[0]**2/r[2])))
        if k in CHECK:
            x,P=f.mean_cov();e=true6[k]-x;e[2]=V.wrap(e[2]);ne=float(e[:3]@np.linalg.solve(P[:3,:3],e[:3]))
            rows.append(dict(arm=arm,seed=seed,k=k,time_s=k*DT,NEES_pose=ne,NEES_6=float(e@np.linalg.solve(P,e)),
                error=e.tolist(),P6=P.tolist(),sigma_psi=float(np.sqrt(P[2,2]))))
    return rows,innov

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);ap.add_argument('--seeds',default=128,type=int);a=ap.parse_args();o=a.out;o.mkdir(parents=True,exist_ok=True)
    numeric,deterministic=numeric_checks();pd.DataFrame(numeric).to_csv(o/'Q_F_G_C_PARITY.csv',index=False)
    allr=[];inn=[]
    for arm in ARMS:
        for seed in range(a.seeds):
            r,i=trial(arm,seed);allr+=r;inn+=i
        print('V02_ARM_DONE',arm,a.seeds,flush=True)
    table=pd.DataFrame(allr);table.to_json(o/'MC_RAW_CHECKPOINTS.json.gz',orient='records',compression='gzip')
    stats=[]
    for (arm,k),g in table.groupby(['arm','k']):
        errors=np.stack(g.error);p=np.stack(g.P6);bias=errors.mean(axis=0);MSE=errors.T@errors/len(g);C=np.cov(errors,rowvar=False)
        dof=3*len(g);bounds=chi2.ppf([.025,.975],dof)/len(g)
        bonf=chi2.ppf([.025/(len(ARMS)*len(CHECK)),1-.025/(len(ARMS)*len(CHECK))],dof)/len(g)
        hit=int((g.NEES_pose<=chi2.ppf(.95,3)).sum());cb=binom.ppf([.025,.975],len(g),.95)/len(g)
        stats.append(dict(arm=arm,k=int(k),n=len(g),mean_NEES_pose=float(g.NEES_pose.mean()),mean_NEES6=float(g.NEES_6.mean()),
            pose95coverage=hit/len(g),mean_NEES95_lower=float(bounds[0]),mean_NEES95_upper=float(bounds[1]),
            mean_NEES_bonf_lower=float(bonf[0]),mean_NEES_bonf_upper=float(bonf[1]),
            pose_coverage95_lower=float(cb[0]),pose_coverage95_upper=float(cb[1]),
            mean_pose_NEES_nominal_PASS=bool(bounds[0]<=g.NEES_pose.mean()<=bounds[1]),
            mean_pose_NEES_family_PASS=bool(bonf[0]<=g.NEES_pose.mean()<=bonf[1]),
            bias_xy_m=float(np.linalg.norm(bias[:2])),bias_psi_deg=float(np.degrees(bias[2])),
            heading_rmse_deg=float(np.degrees(np.sqrt(MSE[2,2]))),
            centered_heading_var=float(C[2,2]),heading_MSE=float(MSE[2,2]),pred_heading_P=float(p[:,2,2].mean()),
            pos_rmse_m=float(np.sqrt(np.trace(MSE[:2,:2])))))
    result=pd.DataFrame(stats);result.to_csv(o/'TIMEPOINT_MC_NEES.csv',index=False)
    result[result.k==0].to_csv(o/'INITIAL_EMPIRICAL_MOMENTS.csv',index=False)
    pd.DataFrame(inn).groupby(['arm','kind']).NIS.agg(['mean','median','count']).to_csv(o/'IDEAL_INNOVATION_NIS.csv')
    status={'id':'V02','execution':'COMPLETE','independent_seeds_per_arm':a.seeds,'arms':ARMS,'timepoints':CHECK,
       'deterministic_SE2_max_error':deterministic,'numerical_F_G_H_gate':'PASS',
       'statistical_gate':'EVALUATE_PER_ARM_NOT_AUTOMATIC_PASS','nominal_gate_fail_count':int((~result.mean_pose_NEES_nominal_PASS).sum()),
       'familywise_gate_fail_count':int((~result.mean_pose_NEES_family_PASS).sum()),
       'source_model':'native Sensor-v2 without RF detector; explicit analytic ideal s sanity only',
       'scientific_PASS':False}
    (o/'STATUS.json').write_text(json.dumps(status,indent=2));print('V02_RESULT',json.dumps(status),flush=True)
    (o/'run_v02_ideal_consistency.py').write_bytes(Path(__file__).read_bytes())

if __name__=='__main__':main()
