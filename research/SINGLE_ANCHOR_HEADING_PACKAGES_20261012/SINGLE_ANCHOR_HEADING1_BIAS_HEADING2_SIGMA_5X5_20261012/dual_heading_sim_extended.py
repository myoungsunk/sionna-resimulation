#!/usr/bin/env python3
"""Reproducible single-anchor, DR (gyro/odom) + RF range/heading EKF Monte Carlo.

- 4 paths preserved from 2026-10-12 route experiment.
- Single 3D range: anchor (4,0,2.65), tag body-centred at z=0.45.
- Heading 1 = measured *relative yaw increment* in EKF motion prediction.
- Heading 2 = synthetic absolute yaw observation (optional relative anchor bearing).
- Joint RF range/heading updates, full within-epoch covariance R.
- Optional same-epoch correlation between DR yaw input error and RF heading
  observation noise: exact cross-covariance C=Cov(true-predicted_state, RF noise).
- Sweep persistent per-step gyro bias (specified accumulated deg at 100 steps),
  gyro increment std, RF yaw bias and RF yaw std.
- No dual LP, no physical RF multipath, no GNSS, no wall-based map constraints.

All numbers are synthetic. The RF absolute-heading observation is an *assumption*,
NOT an demonstrated measurement of world yaw by this single-anchor RF setup.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import time
import zipfile

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

# Fixed study design (fixed seed per route ensures paired Monte-Carlo comparisons).
CHI2_2_95 = 5.991464547107979
D2R = np.pi/180.0
ROUTES = {
    'straight': {'name':'Straight','ko':'직선', 'start':(4.0,0.0), 'segments':[(100,0.0)]},
    'rectangle': {'name':'Rectangle (two loops)','ko':'네모', 'start':(4.0,-.30), 'segments':[(19,0.),(6,90.),(19,180.),(6,-90.)]*2},
    'rieul': {'name':'Rieul (reversing)','ko':'ㄹ자', 'start':(4.0,-.30), 'segments':[(31,0.),(3,90.),(31,180.),(3,90.),(32,0.)]},
    'zigzag': {'name':'Zigzag','ko':'지그재그', 'start':(4.0,-.30), 'segments':[(17,21.1),(16,-21.1),(17,21.1),(17,-21.1),(16,21.1),(17,-21.1)]},
}

@dataclasses.dataclass(frozen=True)
class Config:
    runs:int=1000
    seed:int=20261012
    steps:int=100
    dt_s:float=.5
    distance_step_m:float=.10
    anchor_xyz_m:tuple[float,float,float]=(4.,0.,2.65)
    tag_z_m:float=.45
    corridor_dims_m:tuple[float,float,float]=(20.,2.4,2.7)
    robot_center_ymax_m:float=(2.4/2 -0.10- math.hypot(.60,.40)/2)
    init_xy_std_m:float=.10
    init_yaw_std_deg:float=3.
    true_actuator_ds_std_m:float=.002
    true_actuator_yaw_std_deg:float=.035
    odom_ds_std_m:float=.008
    range_std_m:float=.080
    dr_yaw_std_deg:float=.23
    rf_heading_std_deg:float=1.0


def wrap(x):
    return (x+np.pi) % (2*np.pi)-np.pi


def controls(route:str, cfg:Config):
    v=ROUTES[route]
    theta=np.concatenate([np.full(n,float(h)*D2R) for n,h in v['segments']])
    assert len(theta)==cfg.steps
    dpsi=np.zeros(cfg.steps)
    dpsi[1:]=wrap(theta[1:]-theta[:-1])
    return np.full(cfg.steps,cfg.distance_step_m),dpsi,theta


def motion(x, ds, dpsi):
    out=x.copy();h=x[...,2]+dpsi*.5
    out[...,0]+=ds*np.cos(h)
    out[...,1]+=ds*np.sin(h)
    out[...,2]=wrap(x[...,2]+dpsi)
    return out


def true_range(cfg,pose):
    a=cfg.anchor_xyz_m
    return np.sqrt((pose[...,0]-a[0])**2+(pose[...,1]-a[1])**2+(cfg.tag_z_m-a[2])**2)


def generate(cfg:Config,route:str):
    i=list(ROUTES).index(route)
    rng=np.random.default_rng(cfg.seed+101*i)
    n,k=cfg.runs,cfg.steps
    ds_nom,dy_nom,theta=controls(route,cfg)
    # Independent physical actuation, odometry, gyro, RF range and RF yaw streams.
    ds_true=ds_nom[None,:]+cfg.true_actuator_ds_std_m*rng.standard_normal((n,k))
    dy_true=dy_nom[None,:]+cfg.true_actuator_yaw_std_deg*D2R*rng.standard_normal((n,k))
    n_odo=rng.standard_normal((n,k))
    n_gyro=rng.standard_normal((n,k))
    n_range=rng.standard_normal((n,k))
    n_rf=rng.standard_normal((n,k))
    initial_err_xy=rng.standard_normal((n,2))*cfg.init_xy_std_m
    initial_err_psi=rng.standard_normal(n)*cfg.init_yaw_std_deg*D2R
    gt=np.zeros((n,k+1,3));gt[:,0,:2]=ROUTES[route]['start'];gt[:,0,2]=theta[0]
    ref=np.zeros((k+1,3));ref[0]=gt[0,0]
    for step in range(k):
        gt[:,step+1]=motion(gt[:,step],ds_true[:,step],dy_true[:,step])
        ref[step+1]=motion(ref[step],ds_nom[step],dy_nom[step])
    prior=gt[:,0].copy()
    prior[:,:2]+=initial_err_xy
    prior[:,2]=wrap(prior[:,2]+initial_err_psi)
    return dict(gt=gt,ref=ref,ds_true=ds_true,dpsi_true=dy_true,
                n_odo=n_odo,n_gyro=n_gyro,n_range=n_range,n_rf=n_rf,
                initial=prior)


def measure(cfg,d,gyro_std_deg=.23,gyro_accum_bias_deg=0.,rf_std_deg=1.,rf_bias_deg=0.,
            corr_range_rf=0.,corr_gyro_rf=0.,heading_kind='absolute', range_bias_m=0.):
    if corr_range_rf**2+corr_gyro_rf**2>=.999999:
        raise ValueError('Need rho_r^2+rho_g^2 < 1 for independent n_range and n_gyro')
    if gyro_std_deg<=0 or rf_std_deg<=0:
        raise ValueError('Positive σ values needed')
    eta_rf=(corr_range_rf*d['n_range']+corr_gyro_rf*d['n_gyro']+
            math.sqrt(1-corr_range_rf**2-corr_gyro_rf**2)*d['n_rf'])
    us=d['ds_true']+cfg.odom_ds_std_m*d['n_odo']
    uy=d['dpsi_true']+gyro_std_deg*D2R*d['n_gyro']+gyro_accum_bias_deg*D2R/cfg.steps
    zr=true_range(cfg,d['gt'][:,1:])+cfg.range_std_m*d['n_range']+range_bias_m
    if heading_kind=='absolute':
        true_h=d['gt'][:,1:,2]
    elif heading_kind=='bearing':
        p=d['gt'][:,1:,:2]
        true_h=wrap(np.arctan2(cfg.anchor_xyz_m[1]-p[...,1],cfg.anchor_xyz_m[0]-p[...,0])-d['gt'][:,1:,2])
    else: raise ValueError(heading_kind)
    zh=wrap(true_h+rf_std_deg*D2R*eta_rf+rf_bias_deg*D2R)
    return dict(ds=us,dpsi=uy,zrange=zr,zheading=zh,
                yaw1_error_deg=(uy-d['dpsi_true'])/D2R,
                yaw2_error_deg=wrap(zh-true_h)/D2R,
                range_error_m=zr-true_range(cfg,d['gt'][:,1:]),heading_kind=heading_kind)


def filter_run(cfg,d,obs,*,method='both',dr_std_deg=.23,rf_std_deg=1.,
               rho_range_rf=0.,rho_gyro_rf=0.,rho_gyro_range=0.,use_correct_cov=True,
               subtract_dr_bias_deg=0.,subtract_rf_bias_deg=0.,retain_trace=False,heading_period_steps=1):
    """EKF with proper P, Q, R and optional process/observation cross covariance.

    e^- = true-state minus predicted-state; u_meas=u_true+noise_u.
    C = Cov(e^-,v) = -G Cov(noise_u, measurement_noise) for same-epoch
    independent prior state and input/measurement innovations.
    K=(P H.T + C) [H P H.T + R + H C + C.T H.T]^-1.
    Joseph cross form: (I-KH)P(I-KH)^T + K R K^T
                       - (I-KH) C K^T - K C^T (I-KH)^T.
    """
    if heading_period_steps < 1:
        raise ValueError('heading_period_steps >= 1 required')
    if method not in ('dr','range','heading','both'):
        raise ValueError(method)
    use_r=method in ('range','both')
    use_h=method in ('heading','both')
    n,k=cfg.runs,cfg.steps
    est=d['initial'].copy()
    P=np.broadcast_to(np.diag([cfg.init_xy_std_m**2,cfg.init_xy_std_m**2,
                               (cfg.init_yaw_std_deg*D2R)**2]),(n,3,3)).copy()
    I=np.eye(3)[None,:,:]
    qus=cfg.odom_ds_std_m**2; quh=(dr_std_deg*D2R)**2
    rr=cfg.range_std_m**2; rh=(rf_std_deg*D2R)**2
    rho_rh= rho_range_rf if use_correct_cov else 0.0
    rho_gh= rho_gyro_rf if use_correct_cov else 0.0
    rho_gr= rho_gyro_range if use_correct_cov else 0.0
    sum_err=np.zeros(n);sum_x=np.zeros(n);sum_y=np.zeros(n);sum_psi=np.zeros(n)
    sum_nees=np.zeros(n);sum_nis=np.zeros(n);nis_samples=np.zeros(n)
    nees_fin=np.empty(n);e_fin=np.empty((n,3));P_fin=np.empty((n,3,3));x_fin=np.empty((n,3))
    if retain_trace: trace=np.empty((n,k+1,3)); trace[:,0]=est
    for t in range(k):
        do_h=use_h and ((t+1) % heading_period_steps == 0)
        ds=obs['ds'][:,t]
        dy=obs['dpsi'][:,t]-subtract_dr_bias_deg*D2R/cfg.steps
        phi=est[:,2]+.5*dy
        co=np.cos(phi);si=np.sin(phi)
        F=np.broadcast_to(np.eye(3),(n,3,3)).copy()
        F[:,0,2]=-ds*si;F[:,1,2]=ds*co
        G=np.zeros((n,3,2));G[:,0,0]=co;G[:,1,0]=si
        G[:,0,1]=-.5*ds*si;G[:,1,1]=.5*ds*co;G[:,2,1]=1.
        # e^- = true - prediction; P gets +G Q G^T independent of sign.
        gs=G[:,:,0];gh=G[:,:,1]
        P= F@P@np.swapaxes(F,1,2) + qus*gs[:,:,None]*gs[:,None,:]+quh*gh[:,:,None]*gh[:,None,:]
        est=motion(est,ds,dy)
        if use_r or do_h:
            if use_r:
                rad=true_range(cfg,est)
                Hr=np.zeros((n,3))
                Hr[:,0]=(est[:,0]-cfg.anchor_xyz_m[0])/rad
                Hr[:,1]=(est[:,1]-cfg.anchor_xyz_m[1])/rad
                v_r=obs['zrange'][:,t]-rad
            if do_h:
                if obs['heading_kind']=='absolute':
                    Hh=np.zeros((n,3));Hh[:,2]=1.
                    angle=est[:,2]
                    isvalid=np.ones(n,dtype=bool)
                else:
                    dx=cfg.anchor_xyz_m[0]-est[:,0];ddy=cfg.anchor_xyz_m[1]-est[:,1]
                    r2=dx*dx+ddy*ddy
                    # No meaningful azimuth at the anchor's XY location.
                    isvalid=r2>=.50**2
                    Hh=np.zeros((n,3))
                    r2s=np.maximum(r2,.50**2)
                    Hh[:,0]=ddy/r2s;Hh[:,1]=-dx/r2s;Hh[:,2]=-1.
                    Hh[~isvalid]=0.
                    angle=wrap(np.arctan2(ddy,dx)-est[:,2])
                v_h=wrap(obs['zheading'][:,t]-subtract_rf_bias_deg*D2R-angle)
                v_h=np.where(isvalid,v_h,0.)
            if use_r and do_h:
                H=np.stack((Hr,Hh),axis=1)
                v=np.stack((v_r,v_h),axis=1)
                R=np.zeros((n,2,2));R[:,0,0]=rr;R[:,1,1]=rh
                R[:,0,1]=rho_rh*cfg.range_std_m*(rf_std_deg*D2R)
                R[:,1,0]=R[:,0,1]
                if not np.all(isvalid):
                    # Suppress near-anchor bearing observations with formally
                    # infinite uncertainty; zero cross term at invalid epochs.
                    R[~isvalid,1,1]=1e12
                    R[~isvalid,0,1]=0.;R[~isvalid,1,0]=0.
                C=np.zeros((n,3,2))
                C[:,:,0] = -G[:,:,1]*(dr_std_deg*D2R)*cfg.range_std_m*rho_gr
                # Gyro input error shares same random draw as heading2 error.
                C[:,:,1] = -G[:,:,1]*(dr_std_deg*D2R)*(rf_std_deg*D2R)*rho_gh
                if not np.all(isvalid):C[~isvalid,:,1]=0.
            else:
                H=Hr[:,None,:] if use_r else Hh[:,None,:]
                v=v_r[:,None] if use_r else v_h[:,None]
                R=np.full((n,1,1),rr if use_r else rh)
                if do_h and not np.all(isvalid):R[~isvalid,0,0]=1e12
                C=np.zeros((n,3,1))
                if use_r:
                    C[:,:,0] = -G[:,:,1]*(dr_std_deg*D2R)*cfg.range_std_m*rho_gr
                if do_h:
                    C[:,:,0]= -G[:,:,1]*(dr_std_deg*D2R)*(rf_std_deg*D2R)*rho_gh
                    if not np.all(isvalid):C[~isvalid,:,0]=0.
            # P innovation terms, including input/observation noise correlation.
            PhT=P@np.swapaxes(H,1,2)
            HC=H@C
            S=H@PhT+R+HC+np.swapaxes(HC,1,2)
            S=.5*(S+np.swapaxes(S,1,2))
            if S.shape[1]==1:
                assert np.all(S[:,0,0]>0), ('bad S',t)
                K=(PhT+C)/S[:,0:1,0:1]
                nis=(v[:,0]**2)/S[:,0,0]
            else:
                # Analytic 2x2 inverse for fast deterministic batched updates.
                det=S[:,0,0]*S[:,1,1]-S[:,0,1]*S[:,1,0]
                if not np.all(det>0):raise ValueError(('bad det',t,det.min()))
                rhs=PhT+C
                K=np.empty((n,3,2))
                K[:,:,0]=(rhs[:,:,0]*S[:,1,1,None]-rhs[:,:,1]*S[:,1,0,None])/det[:,None]
                K[:,:,1]=(rhs[:,:,1]*S[:,0,0,None]-rhs[:,:,0]*S[:,0,1,None])/det[:,None]
                nis=(S[:,1,1]*v[:,0]**2+S[:,0,0]*v[:,1]**2-2*S[:,0,1]*v[:,0]*v[:,1])/det
            est+=np.einsum('nij,nj->ni',K,v)
            est[:,2]=wrap(est[:,2])
            A=I-K@H
            # Exact Joseph cross covariance for correlated prediction/measurement noises.
            # Corr(e^-,v)=C, e^+=A e^- - K v.
            AK=A@C@np.swapaxes(K,1,2)
            P=A@P@np.swapaxes(A,1,2) + (K@R)@np.swapaxes(K,1,2)-AK-np.swapaxes(AK,1,2)
            P=.5*(P+np.swapaxes(P,1,2))
            sum_nis+=nis;nis_samples+=1.
        err=est-d['gt'][:,t+1,:]
        err[:,2]=wrap(err[:,2])
        sum_x+=err[:,0]**2;sum_y+=err[:,1]**2
        sum_err+=err[:,0]**2+err[:,1]**2
        sum_psi+=err[:,2]**2
        detP=P[:,0,0]*P[:,1,1]-P[:,0,1]**2
        if not np.all(detP>1e-22):raise ValueError(('bad covariance det xy',t,detP.min()))
        nees=(P[:,1,1]*err[:,0]**2+P[:,0,0]*err[:,1]**2-2*P[:,0,1]*err[:,0]*err[:,1])/detP
        sum_nees+=nees
        if retain_trace:trace[:,t+1]=est
    e_fin=est-d['gt'][:,-1,:];e_fin[:,2]=wrap(e_fin[:,2])
    P_fin=P.copy();x_fin=est.copy();nees_fin=nees
    return dict(per_run_mse_2d=sum_err/k,per_run_rmse_2d=np.sqrt(sum_err/k),
        rmse_2d_m=math.sqrt(float(np.mean(sum_err)/k)),rmse_x_m=math.sqrt(float(np.mean(sum_x)/k)),
        rmse_y_m=math.sqrt(float(np.mean(sum_y)/k)),
        rmse_heading_deg=math.sqrt(float(np.mean(sum_psi)/k))/D2R,
        final_rmse_2d_m=math.sqrt(float(np.mean(e_fin[:,0]**2+e_fin[:,1]**2))),
        mean_nees_xy=float(np.mean(sum_nees)/k),
        final_nees_xy=float(np.mean(nees_fin)),
        final_coverage_pct=float(100*np.mean(nees_fin<=CHI2_2_95)),
        mean_nis=(float(np.sum(sum_nis)/np.sum(nis_samples)) if np.sum(nis_samples)>0 else float('nan')),
        final_ellipse_area_m2=float(np.mean(np.pi*CHI2_2_95*np.sqrt(np.linalg.det(P_fin[:,:2,:2])))),
        per_run_final_in=(nees_fin<=CHI2_2_95),
        per_run_final_err_m=np.sqrt(e_fin[:,0]**2+e_fin[:,1]**2),
        per_run_final_nees=nees_fin,
        final_est=x_fin,final_cov=P_fin,
        trajectory=(trace if retain_trace else None))


def compact(res):
    return {k:v for k,v in res.items() if np.isscalar(v) or isinstance(v,(str,int,float))}


def df_line(route,study,label,params,res,d,obs):
    pred=dict(route=route,route_ko=ROUTES[route]['ko'],study=study,model=label,
              runs=len(d['gt']),heading_kind=obs['heading_kind'],
              gyro_sigma_per_step_deg=params.get('gyro_std_deg',.23),
              gyro_accumulated_bias_deg=params.get('gyro_accum_bias_deg',0.),
              rf_heading_sigma_deg=params.get('rf_std_deg',1.),rf_heading_bias_deg=params.get('rf_bias_deg',0.),
              corr_range_rf=params.get('corr_range_rf',0.),corr_gyro_rf=params.get('corr_gyro_rf',0.),
              range_std_m=.08,range_bias_m=params.get('range_bias_m',0.),
              **compact(res))
    y=d['gt'][:,:,1]
    pred['invalid_gt_run_pct']=float(100*np.mean(np.any(np.abs(y)>Config().robot_center_ymax_m,axis=1)))
    return pred


def run_studies(cfg:Config, out:Path, *, no_fig=False):
    out.mkdir(parents=True,exist_ok=True)
    tstart=time.monotonic()
    cases=[];traces={};heat_gyro={};heat_rf={};corr_recs=[];qa=[];example_data={};perrun=[]
    for route in ROUTES:
        d=generate(cfg,route)
        example_data[route]=d
        kwargs=dict(gyro_std_deg=cfg.dr_yaw_std_deg,gyro_accum_bias_deg=0.,rf_std_deg=1.,rf_bias_deg=0.)
        obs=measure(cfg,d,**kwargs)
        baseline={}
        for meth in ('dr','range','heading','both'):
            rs=filter_run(cfg,d,obs,method=meth,dr_std_deg=cfg.dr_yaw_std_deg,rf_std_deg=1.,retain_trace=True)
            baseline[meth]=rs
            cases.append(df_line(route,'method_baseline',meth,kwargs,rs,d,obs))
            if meth in ('range','both'):
                for i in range(cfg.runs):
                    perrun.append(dict(route=route,method=meth,run=i,
                        final_inside_95=int(rs['per_run_final_in'][i]),
                        final_nees_xy=float(rs['per_run_final_nees'][i]),
                        final_2d_error_m=float(rs['per_run_final_err_m'][i])))
        traces[route]=baseline
        print(f'BASE {route}: range {baseline["range"]["rmse_2d_m"]:.3f}m; both {baseline["both"]["rmse_2d_m"]:.3f}m; final coverage {baseline["both"]["final_coverage_pct"]:.1f}%',flush=True)
        # Heading 1: independent DR gyro bias & per-step variance.
        for s in (.08,.15,.23,.4,.6):
            for b in (-5.,-2.,0.,2.,5.):
                p=dict(gyro_std_deg=s,gyro_accum_bias_deg=b,rf_std_deg=1.,rf_bias_deg=0.)
                zz=measure(cfg,d,**p)
                rs=filter_run(cfg,d,zz,method='both',dr_std_deg=s,rf_std_deg=1.)
                cases.append(df_line(route,'gyro_2d_sweep','both',p,rs,d,zz))
        print(f'  gyro grid done {route}',flush=True)
        # Heading 2: RF independent heading bias & variance.
        for s in (.5,1.,2.,3.,5.,10.):
            for b in (-5.,-2.,0.,2.,5.):
                p=dict(gyro_std_deg=.23,gyro_accum_bias_deg=0.,rf_std_deg=s,rf_bias_deg=b)
                zz=measure(cfg,d,**p)
                rs=filter_run(cfg,d,zz,method='both',dr_std_deg=.23,rf_std_deg=s)
                cases.append(df_line(route,'rf_2d_sweep','both',p,rs,d,zz))
        print(f'  rf grid done {route}',flush=True)
        # Joint bias x bias (sensor disagreement can look deceptively small).
        for b1 in (-5.,0.,5.):
            for b2 in (-5.,0.,5.):
                p=dict(gyro_std_deg=.23,gyro_accum_bias_deg=b1,rf_std_deg=1.,rf_bias_deg=b2)
                zz=measure(cfg,d,**p)
                rs=filter_run(cfg,d,zz,method='both',dr_std_deg=.23,rf_std_deg=1.)
                cases.append(df_line(route,'joint_bias','both',p,rs,d,zz))
        # Same-epoch RF range-to-heading correlation. Matched noise and kinematics.
        for rho in (-.8,-.5,0.,.5,.8):
            p=dict(gyro_std_deg=.23,gyro_accum_bias_deg=0.,rf_std_deg=1.,rf_bias_deg=0.,corr_range_rf=rho)
            zz=measure(cfg,d,**p)
            for correct in (True,False):
                rs=filter_run(cfg,d,zz,method='both',dr_std_deg=.23,rf_std_deg=1.,rho_range_rf=rho,use_correct_cov=correct)
                nm='cov_correct' if correct else 'cov_ignored'
                cases.append(df_line(route,'rho_range_heading',nm,p,rs,d,zz))
        # Same-epoch IMU yaw increment error to RF heading noise cross-covariance.
        for rho in (-.6,0.,.6):
            p=dict(gyro_std_deg=.23,gyro_accum_bias_deg=0.,rf_std_deg=1.,rf_bias_deg=0.,corr_gyro_rf=rho)
            zz=measure(cfg,d,**p)
            for correct in (True,False):
                rs=filter_run(cfg,d,zz,method='both',dr_std_deg=.23,rf_std_deg=1.,rho_gyro_rf=rho,use_correct_cov=correct)
                nm='cov_correct' if correct else 'cov_ignored'
                cases.append(df_line(route,'rho_gyro_rfheading',nm,p,rs,d,zz))
        # Bias corrected with external knowledge: an oracle diagnostic, NOT estimated.
        p=dict(gyro_std_deg=.23,gyro_accum_bias_deg=5.,rf_std_deg=1.,rf_bias_deg=2.)
        zz=measure(cfg,d,**p)
        for tag,b1,b2 in [('uncompensated',0.,0.),('external_calibration',5.,2.)]:
            rs=filter_run(cfg,d,zz,method='both',dr_std_deg=.23,rf_std_deg=1.,subtract_dr_bias_deg=b1,subtract_rf_bias_deg=b2)
            cases.append(df_line(route,'known_bias_calibration',tag,p,rs,d,zz))
        # RF heading physically relative to anchor (not absolute yaw). Define a
        # new observation function, do not represent it as world-heading.
        p=dict(gyro_std_deg=.23,gyro_accum_bias_deg=0.,rf_std_deg=1.,rf_bias_deg=0.,heading_kind='bearing')
        zz=measure(cfg,d,**p)
        rs=filter_run(cfg,d,zz,method='both',dr_std_deg=.23,rf_std_deg=1.)
        cases.append(df_line(route,'heading_interpretation','rf_relative_bearing',p,rs,d,zz))
        print(f'  correlation/bias/relative model done {route} ({time.monotonic()-tstart:.1f}s)',flush=True)

    df=pd.DataFrame(cases)
    df.to_csv(out/'all_cases.csv',index=False,float_format='%.12g')
    pd.DataFrame(perrun).to_csv(out/'final_coverage_per_run.csv',index=False,float_format='%.12g')
    for st,f in [('method_baseline','01_sensor_ablation.csv'),('gyro_2d_sweep','02_heading1_bias_variance_grid.csv'),
                 ('rf_2d_sweep','03_heading2_bias_variance_grid.csv'),('joint_bias','04_joint_heading_bias_grid.csv'),
                 ('rho_range_heading','05_range_rf_heading_correlation.csv'),('rho_gyro_rfheading','06_gyro_rf_heading_correlation.csv'),
                 ('known_bias_calibration','07_oracle_calibration_diagnostic.csv'),('heading_interpretation','08_absolute_vs_relative_heading.csv')]:
        df[df.study==st].to_csv(out/f,index=False,float_format='%.12g')
    if not no_fig:
        fig_path_comparison(cfg,example_data,traces,out/'01_four_routes_fusion_paths.png')
        fig_precision_heatmap(df,'gyro_2d_sweep','gyro_sigma_per_step_deg','gyro_accumulated_bias_deg',
                              out/'02_gyro_heading_bias_variance_sweep.png',main_title='Heading 1 / DR gyro bias & noise')
        fig_precision_heatmap(df,'rf_2d_sweep','rf_heading_sigma_deg','rf_heading_bias_deg',
                              out/'03_rf_heading_bias_variance_sweep.png',main_title='Heading 2 / RF heading bias & noise')
        fig_correlation(df,out/'04_correlated_sensor_covariance.png')
        fig_bias_cross(df,out/'05_two_heading_bias_interaction.png')
        fig_pose_metrics(df,out/'06_methods_accuracy_consistency.png')
    qa_info=qa_tests(cfg,df,example_data,traces)
    (out/'QA_REPORT.json').write_text(json.dumps(qa_info,ensure_ascii=False,indent=2))
    snapshot=dataclasses.asdict(cfg)
    snapshot['model_notes']='Synthetic RF world yaw, not a demonstrated radio observable; corridor geometry from GitHub placeholders; no dual LP.'
    snapshot['route_segments']={name:row['segments'] for name,row in ROUTES.items()}
    snapshot['runtime_seconds']=round(time.monotonic()-tstart,2)
    (out/'CONFIG_SNAPSHOT.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('COMPLETED',snapshot['runtime_seconds'],'seconds,',len(df),'scenarios, QA',qa_info['passed'],flush=True)
    return df


def qa_tests(cfg,df,data,traces):
    checks={}
    checks['complete_4_routes']=list(sorted(df.route.unique()))==list(sorted(ROUTES))
    checks['finite_rmse_nees_nis']=bool(np.isfinite(df[['rmse_2d_m','mean_nees_xy','final_coverage_pct']].values).all())
    checks['ranging_rmse_reference']=bool(all(abs(np.sqrt(np.mean(data[name]['n_range']**2))*cfg.range_std_m-.08)<.004 for name in data))
    checks['sensor_ablation_covers_all_4_methods']=bool(df[df.study=='method_baseline'].shape[0]==16)
    checks['gyro_grid_complete']=bool(df[df.study=='gyro_2d_sweep'].shape[0]==100)
    checks['rf_grid_complete']=bool(df[df.study=='rf_2d_sweep'].shape[0]==120)
    checks['crosscov_experiments_complete']=bool(df[df.study.str.startswith('rho_')].shape[0]==64)
    checks['all_paths_nominal_within_bounds']=True
    checks['covariance_symmetric_psd']=True
    for route in ROUTES:
        ref=data[route]['ref'];checks['all_paths_nominal_within_bounds'] &= bool(np.all(np.abs(ref[:,1])<=cfg.robot_center_ymax_m+.001))
        for model in traces[route].values():
            Pf=model['final_cov'];checks['covariance_symmetric_psd'] &= bool(np.allclose(Pf,np.swapaxes(Pf,1,2),atol=1e-12) and np.linalg.eigvalsh(Pf).min()>0)
    checks['heading_fusion_improves_straight_rmse']=bool(df[(df.route=='straight')&(df.study=='method_baseline')&(df.model=='both')].rmse_2d_m.iloc[0] <df[(df.route=='straight')&(df.study=='method_baseline')&(df.model=='range')].rmse_2d_m.iloc[0])
    return dict(passed=bool(all(checks.values())),checks=checks)


def fig_env(ax,cfg):
    ax.axhspan(-1.2,1.2,color='#cba58f',alpha=.10)
    for val in (-1.2,1.2):ax.axhline(val,color='#808080',lw=1,ls='--')
    for val in (-cfg.robot_center_ymax_m,cfg.robot_center_ymax_m):ax.axhline(val,color='#aaa',lw=.9,ls=':')
    ax.scatter(cfg.anchor_xyz_m[0],cfg.anchor_xyz_m[1],marker='*',s=130,color='#8a59b8',zorder=9)
    ax.set_xlim(3.3,14.5);ax.set_ylim(-1.35,1.35)
    ax.grid(alpha=.20)
    ax.set_ylabel('y (m) lateral');ax.set_xlabel('x (m) longitudinal')


def fig_path_comparison(cfg,data,traces,path):
    fig,axes=plt.subplots(4,1,figsize=(12.7,11.7),layout='constrained')
    for ax,route in zip(axes,ROUTES):
        d=data[route];f=traces[route];idx=0
        fig_env(ax,cfg)
        ax.plot(d['ref'][:,0],d['ref'][:,1],ls='--',lw=1.4,color='gray',label='Reference path')
        ax.plot(d['gt'][idx,:,0],d['gt'][idx,:,1],color='#1b75bb',lw=2,label='True path')
        styles=[('dr','#c3a443','DR'),('range','#b8662f','DR+range'),('heading','#a34a95','DR+RF heading'),('both','#12885b','DR+range+RF heading')]
        for key,col,lbl in styles:
            ax.plot(f[key]['trajectory'][idx,:,0],f[key]['trajectory'][idx,:,1],lw=1.7,color=col,label=lbl)
        ax.set_title(f'{ROUTES[route]["name"]} | 10 m traveled | run #0',loc='left',fontsize=11)
    h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='lower center',bbox_to_anchor=(.5,-.016),ncol=3,fontsize=8)
    fig.suptitle('Single-anchor corridor: two heading channels (relative DR + synthetic absolute RF)',fontsize=13)
    fig.savefig(path,dpi=165,bbox_inches='tight');plt.close(fig)


def fig_precision_heatmap(df,study,sigfield,biasfield,path,main_title):
    fig,axs=plt.subplots(2,2,figsize=(11.5,8.0),layout='constrained')
    for ax,route in zip(axs.flat,ROUTES):
        d=df[(df.route==route)&(df.study==study)]
        pivot=d.pivot(index=sigfield,columns=biasfield,values='rmse_2d_m').sort_index()
        z=pivot.values;im=ax.imshow(z,origin='lower',cmap='viridis',aspect='auto',vmin=0,vmax=max(0.3,np.max(z)))
        ax.set_xticks(range(len(pivot.columns)),[f'{v:+g}' for v in pivot.columns]);ax.set_yticks(range(len(pivot.index)),[f'{v:g}' for v in pivot.index])
        for ii in range(z.shape[0]):
            for jj in range(z.shape[1]):
                ax.text(jj,ii,f'{z[ii,jj]:.2f}',ha='center',va='center',fontsize=8,color='white' if z[ii,jj]>.16 else 'black')
        ax.set(xlabel='Bias (deg)',ylabel='Noise sigma (deg)',title=ROUTES[route]['name'])
    fig.suptitle(main_title+' -> Position RMSE (m)',fontsize=13)
    fig.savefig(path,dpi=170,bbox_inches='tight');plt.close(fig)


def fig_correlation(df,path):
    fig,axs=plt.subplots(2,2,figsize=(12.3,8.7),layout='constrained')
    for ax,route in zip(axs.flat,ROUTES):
        for typ,colour,marker,tag in [
            ('rho_range_heading','#3f85c5','o','Range-RF heading'),
            ('rho_gyro_rfheading','#c47335','s','Gyro-RF heading')]:
            d=df[(df.route==route)&(df.study==typ)]
            for model,ls in [('cov_correct','-'),('cov_ignored','--')]:
                d1=d[d.model==model].sort_values('corr_range_rf' if typ=='rho_range_heading' else 'corr_gyro_rf')
                col='corr_range_rf' if typ=='rho_range_heading' else 'corr_gyro_rf'
                ax.plot(d1[col],d1['final_coverage_pct'],color=colour,ls=ls,marker=marker,ms=4,
                        label=tag+(' / modeled' if model=='cov_correct' else ' / ignored'))
        ax.axhline(95,color='gray',ls=':',lw=1.1)
        ax.set(title=ROUTES[route]['name'],xlabel='Same-step noise correlation',ylabel='Final 95% coverage (%)',ylim=(0,101))
        ax.grid(alpha=.2)
    h,l=axs.flat[0].get_legend_handles_labels();fig.legend(h,l,loc='lower center',bbox_to_anchor=(.5,-.02),ncol=2,fontsize=9)
    fig.suptitle('Correlated observation/input error: correctly modeled vs ignored',fontsize=13)
    fig.savefig(path,dpi=175,bbox_inches='tight');plt.close(fig)


def fig_bias_cross(df,path):
    fig,axes=plt.subplots(2,2,figsize=(12.1,8.7),layout='constrained')
    for ax,route in zip(axes.flat,ROUTES):
        d=df[(df.route==route)&(df.study=='joint_bias')]
        pv=d.pivot(index='gyro_accumulated_bias_deg',columns='rf_heading_bias_deg',values='final_coverage_pct').sort_index()
        im=ax.imshow(pv.values,origin='lower',cmap='RdYlGn',vmin=0,vmax=100,aspect='auto')
        ax.set_xticks(range(3),[f'{v:+g}' for v in pv.columns]);ax.set_yticks(range(3),[f'{v:+g}' for v in pv.index])
        for i in range(3):
            for j in range(3):ax.text(j,i,f'{pv.values[i,j]:.1f}%',va='center',ha='center',fontsize=10)
        ax.set(xlabel='RF absolute heading bias (deg)',ylabel='Integrated gyro bias (deg)',title=ROUTES[route]['name'])
    fig.suptitle('Two heading biases: final 95% confidence ellipse coverage',fontsize=13)
    fig.savefig(path,dpi=175,bbox_inches='tight');plt.close(fig)


def fig_pose_metrics(df,path):
    d=df[df.study=='method_baseline']
    fig,axs=plt.subplots(2,2,figsize=(12.,8.2),layout='constrained')
    names=list(ROUTES);meths=['dr','range','heading','both']
    for ax,(fld,yl) in zip(axs.flat,[('rmse_2d_m','2D Position RMSE (m)'),('rmse_heading_deg','Heading RMSE (deg)'),
                                   ('mean_nees_xy','Mean 2D NEES'),('final_coverage_pct','Final 95% coverage (%)')]):
        xx=np.arange(4)
        for k,m in enumerate(meths):
            vals=[d[(d.route==route)&(d.model==m)].iloc[0][fld] for route in names]
            ax.bar(xx+(k-1.5)*.19,vals,width=.185,label=m)
        ax.set_xticks(xx,['Straight','Rectangle','Rieul','Zigzag']);ax.set_ylabel(yl);ax.grid(axis='y',alpha=.18)
        if fld=='final_coverage_pct':ax.axhline(95,c='gray',ls=':',lw=1)
        if fld=='mean_nees_xy':ax.axhline(2,c='gray',ls=':',lw=1)
    h,l=axs[0,0].get_legend_handles_labels();fig.legend(h,l,loc='lower center',bbox_to_anchor=(.5,-.02),ncol=4)
    fig.suptitle('Sensor ablations / 4 paths / same physical trajectories',fontsize=13)
    fig.savefig(path,dpi=175,bbox_inches='tight');plt.close(fig)


def write_report(cfg:Config,df:pd.DataFrame,out:Path):
    def tab(rows,columns,rename=None,n=4):
        def fmt(x):
            if isinstance(x,(int,np.integer)):return str(x)
            if isinstance(x,(float,np.floating)):return f'{x:.{n}f}'
            return str(x)
        table=['| '+' | '.join((rename or {}).get(k,k) for k in columns)+' |', '| '+' | '.join('---' for _ in columns)+' |']
        for _,r in rows.iterrows():table.append('| '+' | '.join(fmt(r[k]) for k in columns)+' |')
        return '\n'.join(table)
    sel=['route_ko','model','rmse_2d_m','rmse_y_m','final_rmse_2d_m','rmse_heading_deg','mean_nees_xy','final_coverage_pct']
    bas=df[df.study=='method_baseline']
    gyro=df[(df.study=='gyro_2d_sweep')&(df.route=='straight')&(df.gyro_sigma_per_step_deg==.23)]
    rf=df[(df.study=='rf_2d_sweep')&(df.route=='straight')&(df.rf_heading_sigma_deg==1.)]
    rr=df[(df.study=='rho_range_heading')&(df.route=='straight')]
    gg=df[(df.study=='rho_gyro_rfheading')&(df.route=='straight')]
    bb=df[(df.study=='joint_bias')&(df.route=='straight')]
    lines=[
      '# Single-anchor DR + RF range + two Heading channels — synthetic EKF study',
      '',
      '## Scope and caution',
      '- Environment: github `myoungsunk/sionna-resimulation`, `src/qclean_uwb/scenarios/corridor.py`, 20×2.4×2.7 m corridor, anchor (4,0,2.65)m, tag z=0.45m; GitHub values explicitly preliminary placeholders.',
      '- Four 10m routes preserve 2026-10-12 planned segment headings. Corners use idealized instantaneous yaw changes; no collision dynamics; no dual-LP or actual RF heading estimator.',
      '- Heading 1 is measured **relative** IMU/Odom yaw increment used once in EKF prediction; Heading 2 is an **independent world-yaw measurement** in the main study (synthetic upper-bound assumption).',
      '- `rf_relative_bearing` is a distinct **anchor-relative** observation model, not an absolute-heading performance claim.',
      '- Ground truth, range noise and initial pose samples are matched across bias-variance sweeps. Independent drive and RF error streams unless explicitly correlated.',
      '',
      '## Model (heading 1, heading 2, range)',
      '$$u_{1,k}=\\Delta\\psi_k^{GT}+b_{1,step}+n_{1,k},\\quad n_1\\sim\\mathcal N(0,\\sigma_1^2).$$',
      '$$z_{2,k}=\\psi_k^{GT}+b_2+n_{2,k},\\qquad z_{r,k}=r(\\mathbf p_k)+n_{r,k},$$',
      '$$r(\\mathbf p)=\\sqrt{(x-4)^2+y^2+(2.2)^2}.$$',
      '$$Q_u=\\operatorname{diag}(\\sigma_{\\Delta s}^2,\\sigma_1^2),\\quad R_{RF}=\\begin{bmatrix}\\sigma_r^2&\\rho_{r2}\\sigma_r\\sigma_2\\\\\\rho_{r2}\\sigma_r\\sigma_2&\\sigma_2^2\\end{bmatrix}.$$',
      'If RF heading and the current gyro input share instantaneous noise, let $D_{u,z}=\\operatorname{Cov}(n_u,n_z)$. The prediction-to-observation noise cross covariance is $C=\\operatorname{Cov}(e_k^-,n_z)=-G_kD_{u,z}$ with $e_k^-=x_k^{GT}-\\hat x_k^-$.',
      '$$S=HP^-H^T+R+HC+C^TH^T,\\quad K=(P^-H^T+C)S^{-1}.$$',
      '$$P^+=(I-KH)P^-(I-KH)^T+KRK^T-(I-KH)CK^T-KC^T(I-KH)^T.$$',
      'When $C=0$, recover standard correlated-R joint EKF update and Joseph form.',
      'Important: the gyro-related correlation here is between sensor noise streams *within a step*, not merely between two estimated headings (which already share state P). The two RF observation noises are correlated using $\\rho_{r2}$; their covariance must not be double counted.',
      '',
      '## Baseline sensor ablation: matched 1000-run Monte Carlo',
      tab(bas,sel,{'route_ko':'경로','model':'센서','rmse_2d_m':'2D RMSE (m)','rmse_y_m':'Y RMSE (m)','final_rmse_2d_m':'Final RMSE (m)','rmse_heading_deg':'Heading RMSE (deg)','mean_nees_xy':'Mean NEES','final_coverage_pct':'Final 95% (%)'},3),
      '',
      '## Heading 1 (IMU/Odom) bias-variance sweep: straight path, RF sigma 1deg, RF bias zero',
      'Cumulative gyro bias is distributed evenly over 100 increments and is unmodeled by EKF.',
      tab(gyro,['gyro_accumulated_bias_deg','rmse_2d_m','rmse_heading_deg','mean_nees_xy','final_coverage_pct'],n=3),
      '',
      '## Heading 2 (RF) bias-variance sweep: straight path, gyro sigma 0.23deg/step, zero gyro bias',
      'RF bias is a fixed offset in every observation, whereas RF Gaussian sigma is per-observation random scatter.',
      tab(rf,['rf_heading_bias_deg','rmse_2d_m','rmse_heading_deg','mean_nees_xy','final_coverage_pct'],n=3),
      '',
      '## Joint biases (selected combinations; straight)',
      tab(bb,['gyro_accumulated_bias_deg','rf_heading_bias_deg','rmse_2d_m','final_rmse_2d_m','mean_nees_xy','final_coverage_pct'],n=3),
      '',
      '## Same-epoch RF range-heading error correlation (same true trajectory)',
      'R is modeled with offdiagonal covariance in `cov_correct`, forced diagonal in `cov_ignored`.',
      tab(rr,['corr_range_rf','model','rmse_2d_m','mean_nees_xy','final_coverage_pct'],n=3),
      '',
      '## Same-epoch gyro error–RF heading error correlation',
      'Physical coupling (e.g. RF heading algorithm reusing gyro information) is hypothetically synthesized. Joint update must use prediction-observation cross covariance C, not only offdiagonal R.',
      tab(gg,['corr_gyro_rf','model','rmse_2d_m','mean_nees_xy','final_coverage_pct'],n=3),
      '',
      '## Interpretation boundaries',
      '1. These are simulated measurement observations, not Sionna-generated range or polarization-derived RF Heading. No causal claim that RF actually provides absolute yaw.',
      '2. Two reported headings can disagree for reasons of bias, noise, or misaligned coordinates; a small disagreement is not proof they are both correct (common-mode bias).',
      '3. A gyro bias is an *increment* bias, RF yaw bias a *pose* bias. Their degree units should never be equated without specifying 100-step cumulative convention.',
      '4. RF bearing = azimuth(anchor - robot) minus robot yaw retains rotation-gauge ambiguity with one anchor; it is not equivalent to world yaw.',
      '5. The simulation does not add corridor-wall measurements, collision response, path replanning, lever arm, outage, AR(1) time memory, or true RF multipath.',
      '6. Q and R are set to actual *random* variances in the sweep; biases remain deliberately unmodeled unless listed as `external_calibration` (diagnostic oracle using known biases).',
      '',
      '## Files',
      '- `dual_heading_sim.py`: complete generator, filter, plots, QA.',
      '- `all_cases.csv`: all hypotheses and results.',
      '- `01` to `08` CSV files: factorized sweeps, RF correlation and interpretation checks.',
      '- `01` to `06` PNG plots: individual trajectory/heatmap/correlation/accuracy.',
      '- `CONFIG_SNAPSHOT.json`, `QA_REPORT.json`, `SHA256SUMS.txt`: provenance.',
    ]
    (out/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'README_KO.md').write_text(
        '# 두 Heading + Range 공동 EKF 시뮬레이션\n\n'
        '실행: `python dual_heading_sim.py --runs 1000 --out .`\n\n'
        '의존성: numpy, pandas, matplotlib (버전 정보는 `ENVIRONMENT.json`).\n\n'
        'GitHub 복도 구성을 숫자로만 재사용했으며 저장소 코드는 변경하지 않았습니다. '
        '특히 RF Heading은 인공적인 절대 Heading 관측이며 실제 RF 근거는 아직 없습니다.\n\n'
        '자세한 수학 모델·지표·주의 사항: `REPORT_KO.md` 참조.\n',encoding='utf-8')


def hashes(out:Path):
    rows=[]
    for p in sorted(out.iterdir()):
        if p.is_file() and p.name not in ('SHA256SUMS.txt','PACKAGE.zip'):
            rows.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
    (out/'SHA256SUMS.txt').write_text('\n'.join(rows)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runs',type=int,default=1000)
    parser.add_argument('--seed',type=int,default=20261012)
    parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--no-figures',action='store_true')
    a=parser.parse_args()
    cfg=Config(runs=a.runs,seed=a.seed)
    out=a.out;out.mkdir(parents=True,exist_ok=True)
    df=run_studies(cfg,out,no_fig=a.no_figures)
    write_report(cfg,df,out)
    env={'numpy':np.__version__,'pandas':pd.__version__,'matplotlib':matplotlib.__version__, 'python':__import__('platform').python_version()}
    (out/'ENVIRONMENT.json').write_text(json.dumps(env,indent=2))
    hashes(out)

if __name__=='__main__':main()
