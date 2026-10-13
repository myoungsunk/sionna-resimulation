#!/usr/bin/env python3
"""Four paths in the same synthetic GitHub corridor: reproducible Monte-Carlo EKF.

Physics and EKF: midpoint unicycle, 3D single-anchor range, zero lever arm,
matching motion-noise covariance and Joseph measurement update. No dual-LP,
no Sionna/multipath, no walls as measurement or collision response.
Controls include abrupt idealized turns between directed segments; they are
NOT a real TurtleBot motion controller or dynamically feasible trajectory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

ROOT=Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import base_corridor_ekf as base
CHI95=base.CHI2_95_2

# 100 x 0.10m displacement samples = 10m for every route.
# Commands are per-segment (steps, heading in world XY, degrees).
# Each corner is approximated by the model's midpoint heading for the first moving sample.
ROUTES={
    'straight': {'ko':'직선', 'en':'Straight corridor', 'start':(4.0,0.0),
                 'segments':[(100,0.)]},
    'rectangle': {'ko':'네모: 직사각형 2바퀴', 'en':'Rectangle: 2 loops', 'start':(4.0,-0.30),
                  'segments':[(19,0.),(6,90.),(19,180.),(6,-90.)]*2},
    'rieul': {'ko':'ㄹ자(왕복 3개 구간)', 'en':'Rieul / serpentine', 'start':(4.0,-0.30),
              'segments':[(31,0.),(3,90.),(31,180.),(3,90.),(32,0.)]},
    'zigzag': {'ko':'지그재그(6개 대각선)', 'en':'Zigzag: 6 diagonals', 'start':(4.0,-0.30),
               'segments':[(17,21.1),(16,-21.1),(17,21.1),(17,-21.1),(16,21.1),(17,-21.1)]},
}

def ctl(name):
    r=ROUTES[name]; headings=np.concatenate([np.full(steps,np.deg2rad(h)) for steps,h in r['segments']]);assert len(headings)==100
    dtheta=np.empty_like(headings);dtheta[0]=0.;dtheta[1:]=base.wrap(headings[1:]-headings[:-1])
    return np.full(100,.10),dtheta,headings

def rmse(x):return float(np.sqrt(np.mean(np.asarray(x)**2)))

def sample_common(cfg):
    """Reuse exact noise streams from preceding 2026-10-12 straight-line study."""
    old=base.generate(cfg)
    true=old['true']
    ds_noise=np.linalg.norm(np.diff(true[:,:,:2],axis=1),axis=-1)-cfg.step_m
    dyaw_noise=base.wrap(np.diff(true[:,:,2],axis=1))
    prior_xy=old['initial_est'][:,:2]-true[:,0,:2]
    prior_yaw=base.wrap(old['initial_est'][:,2]-true[:,0,2])
    eps=old['z_ideal']-old['r_true'][:,1:]
    eps*=cfg.range_std_m/rmse(eps) # globally matched to previous study
    return dict(ds_noise=ds_noise,dyaw_noise=dyaw_noise,prior_xy=prior_xy,prior_yaw=prior_yaw,eps=eps)

def colored(eps,rho,sigma):
    val=np.empty_like(eps);val[:,0]=eps[:,0]
    for j in range(1,val.shape[1]):val[:,j]=rho*val[:,j-1]+np.sqrt(1-rho*rho)*eps[:,j]
    return val*(sigma/rmse(val))

def generate(cfg,commons,name,heading_drift_final_deg=0.,eps=None):
    n,t=cfg.runs,cfg.n_steps
    ds,dpsi,heads=ctl(name)
    start=ROUTES[name]['start'];drift=np.deg2rad(heading_drift_final_deg/t)
    gt=np.zeros((n,t+1,3));gt[:,0,:2]=start;gt[:,0,2]=heads[0]
    reference=np.zeros((1,t+1,3));reference[:,0,:2]=start;reference[:,0,2]=heads[0]
    for k in range(t):
        reference[:,k+1]=base.f_motion(reference[:,k],np.array([ds[k]]),np.array([dpsi[k]]))
        gt[:,k+1]=base.f_motion(gt[:,k],ds[k]+commons['ds_noise'][:,k],
                                dpsi[k]+commons['dyaw_noise'][:,k]+drift)
    prior=gt[:,0].copy()
    prior[:,:2]+=commons['prior_xy'];prior[:,2]=base.wrap(prior[:,2]+commons['prior_yaw'])
    if eps is None:eps=commons['eps']
    ranges=base.true_3d_range(cfg,gt[:,:,:2]);z=ranges[:,1:]+eps
    return dict(gt=gt,reference=reference[0],initial_est=prior,ds=ds,dpsi=dpsi,z=z,range_true=ranges,
                eps=eps,heading_drift_final_deg=heading_drift_final_deg)

def filter_ekf(cfg,dat, do_update=True):
    n=cfg.runs;t=cfg.n_steps
    est=dat['initial_est'].copy();P=np.zeros((n,3,3))
    p0=np.array([cfg.initial_xy_std_m**2,cfg.initial_xy_std_m**2,np.deg2rad(cfg.initial_yaw_std_deg)**2])
    for i in range(3):P[:,i,i]=p0[i]
    q_control=np.diag([cfg.dr_step_std_m**2,np.deg2rad(cfg.dr_yaw_step_std_deg)**2]);R=cfg.range_std_m**2
    eye=np.eye(3)[None]
    trace=np.empty((n,t+1,3));cov=np.empty((n,t+1,3,3));error=np.empty((n,t+1,3))
    nees=np.empty((n,t+1));nis=np.full((n,t+1),np.nan)
    def record(j):
        trace[:,j]=est;cov[:,j]=P
        error[:,j]=est-dat['gt'][:,j];error[:,j,2]=base.wrap(error[:,j,2])
        nees[:,j]=np.einsum('ni,ni->n',error[:,j,:2],np.linalg.solve(P[:,:2,:2],error[:,j,:2,None])[:,:,0])
    record(0)
    for k in range(t):
        ds,dtheta=dat['ds'][k],dat['dpsi'][k]
        F,G=base.f_F_G(est,ds,dtheta,3)
        P=F@P@np.swapaxes(F,1,2)+(G@q_control)@np.swapaxes(G,1,2)
        est=base.f_motion(est,np.full(n,ds),np.full(n,dtheta))
        if do_update:
            hh=base.true_3d_range(cfg,est[:,:2])
            H=base.range_jacobian(cfg,est)
            ph=(P@H[:,:,None])[:,:,0];S=(H*ph).sum(axis=1)+R
            nu=dat['z'][:,k]-hh
            nis[:,k+1]=nu**2/S
            gain=ph/S[:,None]
            est+=gain*nu[:,None];est[:,2]=base.wrap(est[:,2])
            A=eye-gain[:,:,None]*H[:,None,:]
            P=A@P@np.swapaxes(A,1,2)+R*gain[:,:,None]*gain[:,None,:]
            P=0.5*(P+np.swapaxes(P,1,2))
        record(k+1)
    return dict(estimate=trace,cov=cov,error=error,nees_xy=nees,nis=nis)

def metrics(cfg,dat,filt,route,condition):
    e=filt['error'][:,1:,:];e_final=e[:,-1,:2]
    nees=filt['nees_xy'][:,1:];nis=filt['nis'][:,1:]
    invalid=np.any(np.abs(dat['gt'][:,:,1])>cfg.robot_y_limit_m,axis=1)
    # Also report nominal reference validity, so false out-of-corridor assumptions are visible.
    ref=dat['reference']
    return dict(route=route,route_ko=ROUTES[route]['ko'],condition=condition,n_runs=cfg.runs,
      path_length_m=float(np.sum(dat['ds'])),nominal_endpoint_x_m=float(ref[-1,0]),nominal_endpoint_y_m=float(ref[-1,1]),
      nominal_max_abs_y_m=float(np.max(np.abs(ref[:,1]))),nominal_within_corridor=bool(np.all(np.abs(ref[:,1])<=cfg.robot_y_limit_m)),
      raw_range_rmse_m=rmse(dat['eps']),
      rmse_x_m=rmse(e[:,:,0]),rmse_y_m=rmse(e[:,:,1]),rmse_2d_m=rmse(np.linalg.norm(e[:,:,:2],axis=2)),
      final_rmse_2d_m=rmse(np.linalg.norm(e_final,axis=1)),
      mean_nis=float(np.nanmean(nis)),mean_nees_2d=float(np.mean(nees)),final_mean_nees_2d=float(np.mean(nees[:,-1])),
      coverage_2d_95_pct=100*float(np.mean(nees<=CHI95)),
      final_coverage_2d_95_pct=100*float(np.mean(nees[:,-1]<=CHI95)),
      final_inside_count=int(np.sum(nees[:,-1]<=CHI95)),
      gt_out_of_legal_y_any_pct=100*float(np.mean(invalid)),
      gt_valid_run_count=int(np.sum(~invalid)),
      final_coverage_on_valid_runs_pct=(100*float(np.mean(nees[~invalid,-1]<=CHI95)) if np.any(~invalid) else float('nan')),
      final_rmse_2d_valid_runs_m=(rmse(np.linalg.norm(e_final[~invalid],axis=1)) if np.any(~invalid) else float('nan')))

def dr_metrics(cfg,dat,dr,route):
    e=dr['error'][:,1:,:2]
    final=dr['nees_xy'][:,-1]
    return dict(route=route, route_ko=ROUTES[route]['ko'],
        dr_rmse_x_m=rmse(e[:,:,0]), dr_rmse_y_m=rmse(e[:,:,1]),
        dr_rmse_2d_m=rmse(np.linalg.norm(e,axis=2)),
        dr_final_rmse_2d_m=rmse(np.linalg.norm(e[:,-1],axis=1)),
        dr_mean_nees_2d=float(np.mean(dr['nees_xy'][:,1:])),
        dr_final_coverage_2d_95_pct=100*float(np.mean(final<=CHI95)))

def add_env(ax,cfg,xlim=None,zoom=False):
    ax.axhline(cfg.corridor_width_m/2,ls='--',lw=1.15,c='#8a8989')
    ax.axhline(-cfg.corridor_width_m/2,ls='--',lw=1.15,c='#8a8989')
    ax.axhline(cfg.robot_y_limit_m,ls=':',lw=.8,c='#9b9b9b')
    ax.axhline(-cfg.robot_y_limit_m,ls=':',lw=.8,c='#9b9b9b')
    ax.scatter(cfg.anchor_x_m,cfg.anchor_y_m,marker='*',s=125,c='#8b52a6',zorder=6,label='Anchor XY')
    ax.grid(alpha=.18)
    ax.set_xlabel('x (m) along corridor');ax.set_ylabel('y (m) lateral')
    if xlim:ax.set_xlim(*xlim)
    ax.set_ylim(-1.32,1.32) if not zoom else None

def plot_overview(cfg,datas,filt,filename):
    # Four routes, same XY scale; first of 1000 trials selected in advance.
    fig,axs=plt.subplots(4,1,figsize=(13,11.6),sharex=True,sharey=True,layout='constrained')
    for ax,(name,d) in zip(axs,datas.items()):
        add_env(ax,cfg,xlim=(3.65,14.55))
        ref=d['reference'];gt=d['gt'][0];p=filt[name]
        ax.plot(ref[:,0],ref[:,1],c='#787878',ls='--',lw=2,label='Noiseless reference')
        ax.plot(gt[:,0],gt[:,1],c='#2176b5',lw=2.5,label='Actual GT (run #0)')
        ax.plot(p['DR']['estimate'][0,:,0],p['DR']['estimate'][0,:,1],c='#d78238',lw=1.8,label='DR only')
        ax.plot(p['EKF']['estimate'][0,:,0],p['EKF']['estimate'][0,:,1],c='#16885a',lw=2,label='Range EKF')
        ax.plot(gt[-1,0],gt[-1,1],marker='o',ms=7,color='#2176b5')
        ax.plot(p['EKF']['estimate'][0,-1,0],p['EKF']['estimate'][0,-1,1],marker='x',ms=8,mew=2.2,color='#16885a')
        ax.set_title(f'{ROUTES[name]["en"]} — 10 m travelled',loc='left',fontsize=12)
    hs,ls=axs[0].get_legend_handles_labels();fig.legend(hs,ls,ncol=5,loc='lower center',bbox_to_anchor=(.5,-.015),fontsize=9)
    fig.suptitle('GitHub corridor (20 x 2.4 m): four motion patterns | synthetic run #0',fontsize=14)
    fig.savefig(filename,dpi=180,bbox_inches='tight');plt.close(fig)

def ci_ellipse(ax, mean, cov, color='#16885a',alpha=.13):
    vals,vecs=np.linalg.eigh(cov)
    major=vecs[:,np.argmax(vals)];ang=np.rad2deg(np.arctan2(major[1],major[0]))
    dims=2*np.sqrt(CHI95*np.maximum(vals,1e-15))
    patch=Ellipse(mean,width=dims[np.argmax(vals)],height=dims[np.argmin(vals)],angle=ang,
                   ec=color,fc=color,alpha=alpha,lw=2,zorder=2)
    ax.add_patch(patch)
    ax.add_patch(Ellipse(mean,width=dims[np.argmax(vals)],height=dims[np.argmin(vals)],angle=ang,
                         fill=False,ec=color,lw=1.6,zorder=3))
    return patch

def plot_each(cfg,name,d,filters,filename):
    gt=d['gt'][0];ref=d['reference'];ek=filters['EKF'];dr=filters['DR']
    fig,ax=plt.subplots(figsize=(10.9,5.1),layout='constrained')
    add_env(ax,cfg)
    ax.plot(ref[:,0],ref[:,1],ls='--',c='#797979',lw=2,label='Reference')
    ax.plot(gt[:,0],gt[:,1],lw=2.7,c='#2176b5',label='Actual GT (run #0)')
    ax.plot(dr['estimate'][0,:,0],dr['estimate'][0,:,1],lw=1.9,c='#d78238',label='DR only')
    ax.plot(ek['estimate'][0,:,0],ek['estimate'][0,:,1],lw=2.2,c='#16885a',label='Range EKF')
    center=ek['estimate'][0,-1,:2];P=ek['cov'][0,-1,:2,:2];ci_ellipse(ax,center,P)
    ax.scatter(gt[-1,0],gt[-1,1],c='#2176b5',marker='o',s=75,zorder=10,label='Final GT')
    ax.scatter(center[0],center[1],c='#16885a',marker='x',s=95,lw=2.5,zorder=10,label='Final EKF')
    contained=ek['nees_xy'][0,-1]<=CHI95
    minx=min(gt[:,0].min(),ref[:,0].min(),ek['estimate'][0,:,0].min(),dr['estimate'][0,:,0].min())
    maxx=max(gt[:,0].max(),ref[:,0].max(),ek['estimate'][0,:,0].max(),dr['estimate'][0,:,0].max())
    ax.set_xlim(min(3.65,minx-.6),maxx+.6)
    ax.set_title(f'{ROUTES[name]["en"]} | Single anchor + range-only EKF | run #0\n'
                 f'Final 95% ellipse contains GT: {"YES" if contained else "NO"}',fontsize=12)
    ax.legend(fontsize=8,loc='upper right',ncol=2)
    fig.savefig(filename,dpi=185,bbox_inches='tight');plt.close(fig)

def plot_drift(cfg,ref_data,drift_data,filename):
    fig,axes=plt.subplots(4,1,figsize=(12.4,11.3),sharex=True,layout='constrained')
    for ax,name in zip(axes,ROUTES):
        add_env(ax,cfg,xlim=(3.6,14.5))
        a=ref_data[name];b=drift_data[name]
        ax.plot(a['reference'][:,0],a['reference'][:,1],ls='--',lw=1.9,c='#737373',label='Nominal path')
        ax.plot(a['gt'][0,:,0],a['gt'][0,:,1],lw=2.0,c='#2176b5',label='Actual GT: no added drift')
        ax.plot(b['gt'][0,:,0],b['gt'][0,:,1],lw=2.0,c='#c6664b',label='Actual GT: +5 deg cumulative drift')
        ax.scatter(a['gt'][0,-1,0],a['gt'][0,-1,1],c='#2176b5',s=30)
        ax.scatter(b['gt'][0,-1,0],b['gt'][0,-1,1],c='#c6664b',s=30)
        shift=float(np.linalg.norm(a['gt'][0,-1,:2]-b['gt'][0,-1,:2]))
        ax.set_title(f'{ROUTES[name]["en"]} | GT final displacement change (run #0): {shift:.3f} m',loc='left',fontsize=11)
    hs,ls=axes[0].get_legend_handles_labels();fig.legend(hs,ls,ncol=3,loc='lower center',bbox_to_anchor=(.5,-.012),fontsize=9)
    fig.suptitle('Same motion noise: physical paths with / without unmodelled yaw drift',fontsize=13)
    fig.savefig(filename,dpi=175,bbox_inches='tight');plt.close(fig)

def plot_stats(df,filename):
    iid=df[df.condition=='iid'].set_index('route').loc[list(ROUTES)]
    ar=df[df.condition=='ar1_098'].set_index('route').loc[list(ROUTES)]
    drift=df[df.condition=='yaw_drift_5deg'].set_index('route').loc[list(ROUTES)]
    x=np.arange(len(iid));labels=['Straight','Rectangle','Rieul','Zigzag']
    fig,axes=plt.subplots(2,2,figsize=(11.8,8.0),layout='constrained')
    w=.25
    axes[0,0].bar(x-w,iid.rmse_2d_m,w,label='i.i.d. range')
    axes[0,0].bar(x,ar.rmse_2d_m,w,label='AR(1), rho=0.98')
    axes[0,0].bar(x+w,drift.rmse_2d_m,w,label='+5deg yaw drift')
    axes[0,0].set(title='Overall localization RMSE',ylabel='2D RMSE (m)');axes[0,0].legend(fontsize=8)
    axes[0,1].bar(x-w,iid.final_coverage_2d_95_pct,w,label='i.i.d.')
    axes[0,1].bar(x,ar.final_coverage_2d_95_pct,w,label='AR(1)')
    axes[0,1].bar(x+w,drift.final_coverage_2d_95_pct,w,label='+5deg drift')
    axes[0,1].axhline(95,c='gray',ls=':',lw=1,label='Nominal 95%')
    axes[0,1].set(title='Final 95% ellipse inclusion',ylabel='Coverage (%)',ylim=(0,103))
    axes[1,0].bar(x-w,iid.rmse_x_m,w,label='x')
    axes[1,0].bar(x,iid.rmse_y_m,w,label='y')
    axes[1,0].bar(x+w,iid.final_rmse_2d_m,w,label='Final 2D')
    axes[1,0].set(title='Direction-resolved RMSE (i.i.d.)',ylabel='RMSE (m)');axes[1,0].legend()
    axes[1,1].bar(x-w,iid.mean_nees_2d,w,label='i.i.d.')
    axes[1,1].bar(x,ar.mean_nees_2d,w,label='AR(1)')
    axes[1,1].bar(x+w,drift.mean_nees_2d,w,label='+5deg drift')
    axes[1,1].axhline(2,c='gray',ls=':',lw=1)
    axes[1,1].set(title='Mean position NEES (ideal mean 2)',ylabel='NEES')
    for ax in axes.flat:
        ax.set_xticks(x,labels);ax.grid(axis='y',alpha=.16)
    fig.savefig(filename,dpi=175,bbox_inches='tight');plt.close(fig)

def plot_coverage_geometry(cfg,results,name,filename):
    # For each independent run, map its final error into whitened / normalized coordinates.
    # Under calibrated P, these transformed points should lie inside a radius sqrt(5.991) about 95% of trials.
    r=results[name]['EKF'];e=r['error'][:,-1,:2];P=r['cov'][:,-1,:2,:2]; n=len(e)
    whiten=np.empty_like(e)
    for i in range(n):whiten[i]=np.linalg.solve(np.linalg.cholesky(P[i]),e[i])
    inside=(whiten**2).sum(axis=1)<=CHI95
    th=np.linspace(0,2*np.pi,360);rad=np.sqrt(CHI95)
    fig,ax=plt.subplots(figsize=(6.5,6.3),layout='constrained')
    ax.plot(rad*np.cos(th),rad*np.sin(th),'--',color='#444444',lw=2,label='95% threshold, chi2(2)=5.991')
    ax.scatter(whiten[inside,0],whiten[inside,1],s=7,alpha=.35,label=f'Inside: {inside.sum()}')
    ax.scatter(whiten[~inside,0],whiten[~inside,1],s=10,alpha=.7,label=f'Outside: {(~inside).sum()}')
    ax.axhline(0,c='gray',lw=.5);ax.axvline(0,c='gray',lw=.5)
    ax.set(xlabel='Whitened final x-error',ylabel='Whitened final y-error',
           title=f'Final 95% ellipse coverage: {ROUTES[name]["en"]}\n{100*inside.mean():.1f}% of {n} Monte Carlo final GTs')
    ax.set_aspect('equal');ax.grid(alpha=.14);ax.legend(loc='upper left')
    fig.savefig(filename,dpi=180,bbox_inches='tight');plt.close(fig)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runs',type=int,default=1000)
    ap.add_argument('--seed',type=int,default=20261012)
    ap.add_argument('--out',type=Path,default=ROOT);args=ap.parse_args()
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    cfg=base.Config(runs=args.runs,seed=args.seed)
    common=sample_common(cfg)
    colored_eps=colored(common['eps'],.98,cfg.range_std_m)
    rows=[];dr_rows=[];data={};pred={};drift_data={};runs0={}
    for name in ROUTES:
        d=generate(cfg,common,name);d_drift=generate(cfg,common,name,5.)
        data[name]=d;drift_data[name]=d_drift
        ekf=filter_ekf(cfg,d);dr=filter_ekf(cfg,d,False);pred[name]={'EKF':ekf,'DR':dr};runs0[name]=ekf
        rows.append(metrics(cfg,d,ekf,name,'iid'))
        dr_rows.append(dr_metrics(cfg,d,dr,name))
        rows.append(metrics(cfg,d_drift,filter_ekf(cfg,d_drift),name,'yaw_drift_5deg'))
        d_ar=generate(cfg,common,name,eps=colored_eps)
        rows.append(metrics(cfg,d_ar,filter_ekf(cfg,d_ar),name,'ar1_098'))
        plot_each(cfg,name,d,pred[name],out/f'route_{name}.png')
    # Machine-readable coordinates and per-run final-ellipse audits.
    reference_records=[];sample_records=[];coverage_records=[]
    for name in ROUTES:
        dd=data[name];ff=pred[name]['EKF'];dr=pred[name]['DR']
        for k in range(cfg.n_steps+1):
            ref=dd['reference'][k]
            reference_records.append(dict(route=name,step=k,distance_travelled_m=k*cfg.step_m,
                                          x_m=float(ref[0]),y_m=float(ref[1]),yaw_rad=float(ref[2])))
            tru=dd['gt'][0,k];ek=ff['estimate'][0,k];odom=dr['estimate'][0,k]
            sample_records.append(dict(route=name,run_id=0,step=k,time_s=k*cfg.dt_s,
                           gt_x_m=tru[0],gt_y_m=tru[1],gt_yaw_rad=tru[2],
                           dr_x_m=odom[0],dr_y_m=odom[1],dr_yaw_rad=odom[2],
                           ekf_x_m=ek[0],ekf_y_m=ek[1],ekf_yaw_rad=ek[2],
                           nees_xy=float(ff['nees_xy'][0,k])))
        for i in range(cfg.runs):
            P=ff['cov'][i,-1,:2,:2];tru=dd['gt'][i,-1,:2];ek=ff['estimate'][i,-1,:2]
            coverage_records.append(dict(route=name,run_id=i,gt_x_m=tru[0],gt_y_m=tru[1],
                ekf_x_m=ek[0],ekf_y_m=ek[1],cov_xx_m2=P[0,0],cov_xy_m2=P[0,1],cov_yy_m2=P[1,1],
                final_nees_xy=float(ff['nees_xy'][i,-1]),
                inside_95=bool(ff['nees_xy'][i,-1]<=CHI95)))
    pd.DataFrame(reference_records).to_csv(out/'reference_path_points.csv',index=False,float_format='%.12g')
    pd.DataFrame(sample_records).to_csv(out/'sample_trajectory_run0.csv',index=False,float_format='%.12g')
    pd.DataFrame(coverage_records).to_csv(out/'final_coverage_all_runs.csv',index=False,float_format='%.12g')
    df=pd.DataFrame(rows);df.to_csv(out/'route_metrics.csv',index=False,float_format='%.12g')
    pd.DataFrame(dr_rows).to_csv(out/'dr_only_metrics.csv',index=False,float_format='%.12g')
    plot_overview(cfg,data,pred,out/'01_all_route_shapes.png')
    plot_drift(cfg,data,drift_data,out/'02_yaw_drift_paths.png')
    plot_stats(df,out/'03_rmse_coverage_comparison.png')
    plot_coverage_geometry(cfg,pred,'straight',out/'04_final_95_coverage_demo.png')
    source_git=dict(repo='myoungsunk/sionna-resimulation',branch='codex/range-only-bias-consistency-20261011',
                    file='src/qclean_uwb/scenarios/corridor.py',blob_sha='eba1ab64d5e2117bfd519ceb5cac077b24caf3f8')
    manifest=dict(source=source_git,config=asdict(cfg),seed=args.seed,runs=args.runs,
                  methods=['DR only','3-state range-only EKF'],scenarios=['iid','yaw_drift_5deg','ar1_098'],
                  route_commands=ROUTES,limitations=['No dual-LP','No Sionna / physical RF','No wall collision response',
                    'Idealized instantaneous-like corner changes within one moving sample; not velocity/turn-rate constrained',
                    'Same 10m travelled, but routes have different end-to-end displacement and range geometries'],
                  all_raw_range_rmse_m=float(rmse(common['eps'])),
                  ar1_raw_range_rmse_m=float(rmse(colored_eps)),
                  source_baseline_sha256=hashlib.sha256((ROOT/'base_corridor_ekf.py').read_bytes()).hexdigest())
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=str),encoding='utf8')
    # numerical and geometry QA
    assert all(len(ctl(n)[0])==100 for n in ROUTES)
    assert df['nominal_within_corridor'].all(),df[['route','nominal_max_abs_y_m']]
    assert np.allclose(df['path_length_m'],10)
    assert np.allclose(df['raw_range_rmse_m'],.08,atol=1e-12)
    for key in ROUTES:
        e=pred[key]['EKF'];assert np.all(np.isfinite(e['estimate'])) and np.all(np.isfinite(e['cov']))
        assert np.linalg.eigvalsh(e['cov'][:,-1]).min()>0
        assert np.array_equal(e['nees_xy'][:,-1]<=CHI95,np.einsum('bi,bi->b',
            e['error'][:,-1,:2],np.linalg.solve(e['cov'][:,-1,:2,:2],e['error'][:,-1,:2,None])[:,:,0])<=CHI95)
    # unchanged straight run baseline: exact previous 2026-10-12 1000-run figures
    s=df[(df.route=='straight')&(df.condition=='iid')].iloc[0]
    assert abs(s.rmse_2d_m-0.340)<0.012 and abs(s.final_coverage_2d_95_pct-85.9)<1.,s.to_dict()
    (out/'QA_REPORT.json').write_text(json.dumps({'passed':True,'checks':['all segments total 100 steps and 10m',
      'nominal four trajectories inside allowed corridor','range RMSE identical 0.080m across all cases',
      'all filters finite, endpoint P positive definite','final ellipse flags recomputed from P',
      'straight baseline consistent with previous 2026-10-12 simulation'],
      'caveat':'GT trajectories can leave corridor; invalid_run_percentage disclosed in route_metrics.csv'},indent=2),encoding='utf8')
    print(df[['route','condition','rmse_x_m','rmse_y_m','rmse_2d_m','final_rmse_2d_m','mean_nis','mean_nees_2d','final_coverage_2d_95_pct','gt_out_of_legal_y_any_pct','final_coverage_on_valid_runs_pct','nominal_max_abs_y_m']].round(4).to_string(index=False))
    print('\nDR ONLY:')
    print(pd.DataFrame(dr_rows).round(4).to_string(index=False))
    print('All QA passed')

if __name__=='__main__':main()
