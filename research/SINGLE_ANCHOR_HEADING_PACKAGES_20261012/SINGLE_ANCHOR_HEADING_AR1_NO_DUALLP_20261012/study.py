#!/usr/bin/env python3
"""Range-only + DR EKF, GitHub corridor geometry, no dual-LP, no RF heading-bias proxy.

Includes paired Monte Carlo sensitivities and AR(1) measurement covariance control.
No physical RF solver, maps, wall collisions, or data-driven antenna pattern.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base_corridor_ekf as base

ROOT=Path(__file__).resolve().parent
SIGMA=0.08


def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x)**2)))


def normalized_white(e, sigma=SIGMA):
    return e * (sigma / rms(e))


def ar1_noise(white:np.ndarray, rho:float):
    """Stationary initialization + innovations with marginal var sigma**2.
       Globally normalize realized RMS to 0.08m, rather than per-run normalization.
    """
    a=np.empty_like(white)
    a[:,0]=white[:,0]
    v=np.sqrt(1-rho*rho)
    for t in range(1,white.shape[1]):
        a[:,t]=rho*a[:,t-1]+v*white[:,t]
    return normalized_white(a)


def acf_pooled(arr:np.ndarray, lag:int):
    mu=np.mean(arr)
    centered=arr-mu
    return float(np.mean(centered[:,lag:]*centered[:,:-lag]) / np.mean(centered**2))


def neff_finite(n, rho):
    return float(n*n/(n+2*sum((n-k)*rho**k for k in range(1,n))))


def prior_innovations(c, z, result):
    n,steps=z.shape
    nn=np.zeros((n,steps))
    d_var=np.diag([c.dr_step_std_m**2,np.deg2rad(c.dr_yaw_step_std_deg)**2])
    for j in range(steps):
        x_prev=result['estimate'][:,j,:3]
        P_prev=result['cov'][:,j,:,:]
        F,G=base.f_F_G(x_prev,c.step_m,0.0,3)
        p_pred=F@P_prev@np.swapaxes(F,1,2) + (G@d_var)@np.swapaxes(G,1,2)
        m_pred=base.f_motion(x_prev,np.full(n,c.step_m),np.zeros(n))
        H=base.range_jacobian(c,m_pred)
        PH=(p_pred @ H[:,:,None])[:,:,0]
        S=(H*PH).sum(1)+c.range_std_m**2
        nn[:,j]=(z[:,j]-base.true_3d_range(c,m_pred[:,:2]))/np.sqrt(S)
    assert np.max(np.abs(nn**2-result['nis'][:,1:]))<1e-8
    return nn


def process_metrics(c, d, z, label, family, **args):
    data={**d,'z_ideal':z}
    out=base.apply_filter(c,data,'EKF_IDEAL')
    mm=base.filter_metrics(out)
    noise=z-d['r_true'][:,1:]
    ni=prior_innovations(c,z,out)
    row={
       'family':family, 'case':label,
       'raw_range_bias_m':float(noise.mean()), 'raw_range_rmse_m':rms(noise),
       'raw_range_acf1':acf_pooled(noise,1), 'raw_range_acf5':acf_pooled(noise,5),
       'rmse_x_m':mm['rmse_x_m'], 'rmse_y_m':mm['rmse_y_m'], 'rmse_2d_m':mm['rmse_2d_m'],
       'final_rmse_x_m':rms(out['error'][:,-1,0]),
       'final_rmse_y_m':rms(out['error'][:,-1,1]),
       'final_rmse_2d_m':mm['final_rmse_2d_m'],
       'final_heading_rmse_deg':mm['final_rmse_yaw_deg'],
       'mean_nis':mm['nis_mean'], 'nis_below_3p84_pct':mm['nis_below_95_pct'],
       'nis_innov_acf1':acf_pooled(ni,1),
       'mean_nees_xy':mm['nees_xy_mean'],
       'mean_nees_pose':mm['nees_pose_mean'],
       'coverage_xy_95_pct':mm['coverage_xy_95_pct'],
       'final_coverage_xy_95_pct':mm['final_coverage_xy_95_pct'],
       'final_mean_nees_xy':float(out['nees_xy'][:,-1].mean()),
       'p95_2d_m':mm['p95_2d_m'],
       'gt_wall_violation_traj_pct':float(100*np.any(np.abs(d['true'][:,:,1])>c.robot_y_limit_m,axis=1).mean()),
       **args
    }
    return row,out,ni


def run_ar1_aware(c,d,z,rho,sigma=SIGMA):
    """Correctly augmented EKF: 4th state is AR(1) colored range error.

    b(t)=rho*b(t-1)+u; Var(u)=sigma^2*(1-rho^2), Var(b0)=sigma^2.
    In this strictly synthetic experiment, all measurement error is represented by b:
    Rwhite=0. For a real system an extra independent sensor-noise term is needed.
    """
    n,k=z.shape
    x=np.zeros((n,4)); x[:,:3]=d['initial_est']
    P=np.zeros((n,4,4))
    for ix,v in enumerate(d['p0_diag']): P[:,ix,ix]=v
    P[:,3,3]=sigma*sigma
    M=np.diag([c.dr_step_std_m**2,np.deg2rad(c.dr_yaw_step_std_deg)**2])
    I=np.eye(4)[None]
    err=np.zeros((n,k+1,3)); nees_xy=np.zeros((n,k+1)); nees_pose=np.zeros((n,k+1)); nis=np.full((n,k+1),np.nan)
    ni=np.zeros((n,k))
    def store(t):
        err[:,t,:]=x[:,:3]-d['true'][:,t,:3]
        err[:,t,2]=base.wrap(err[:,t,2])
        nees_xy[:,t]=np.einsum('ni,ni->n',err[:,t,:2],np.linalg.solve(P[:,:2,:2],err[:,t,:2,None])[:,:,0])
        nees_pose[:,t]=np.einsum('ni,ni->n',err[:,t,:3],np.linalg.solve(P[:,:3,:3],err[:,t,:3,None])[:,:,0])
    store(0)
    for j in range(k):
        F,G=base.f_F_G(x[:,:3],c.step_m,0,4)
        F[:,3,3]=rho
        Q=(G@M)@np.swapaxes(G,1,2)
        Q[:,3,3]+=sigma*sigma*(1-rho*rho)
        P=F@P@np.swapaxes(F,1,2)+Q
        x[:,:3]=base.f_motion(x[:,:3],np.full(n,c.step_m),np.zeros(n))
        x[:,3]*=rho
        hh=base.true_3d_range(c,x[:,:2])
        H=np.zeros((n,4));H[:,:3]=base.range_jacobian(c,x[:,:3]);H[:,3]=1
        PH=(P@H[:,:,None])[:,:,0]
        S=np.einsum('ni,ni->n',H,PH)
        nu=z[:,j]-hh-x[:,3]
        ni[:,j]=nu/np.sqrt(S)
        nis[:,j+1]=nu**2/S
        K=PH/S[:,None]
        x+=K*nu[:,None];x[:,2]=base.wrap(x[:,2])
        A=I-K[:,:,None]*H[:,None,:]
        P=A@P@np.swapaxes(A,1,2)
        P=(P+np.swapaxes(P,1,2))/2
        store(j+1)
    result={'error':err,'nis':nis,'nees_xy':nees_xy,'nees_pose':nees_pose}
    mm=base.filter_metrics(result)
    return {
      'rmse_2d_m':mm['rmse_2d_m'],'rmse_x_m':mm['rmse_x_m'],'rmse_y_m':mm['rmse_y_m'],
      'final_rmse_2d_m':mm['final_rmse_2d_m'], 'mean_nis':mm['nis_mean'],
      'mean_nees_xy':mm['nees_xy_mean'],'coverage_xy_95_pct':mm['coverage_xy_95_pct'],
      'final_coverage_xy_95_pct':mm['final_coverage_xy_95_pct'],
      'nis_innov_acf1':acf_pooled(ni,1), 'final_mean_nees_xy':float(nees_xy[:,-1].mean())
    }


def bias_drift_data(c,base_data,accumulated_deg,noise):
    bb=np.deg2rad(accumulated_deg/c.n_steps)
    previous=base_data['true'];n,t,_=previous.shape
    true=np.zeros_like(previous);true[:,0]=previous[:,0]
    ds=np.linalg.norm(np.diff(previous[:,:,:2],axis=1),axis=-1)
    dpsi=base.wrap(np.diff(previous[:,:,2],axis=1)) + bb
    for j in range(c.n_steps):
        true[:,j+1]=base.f_motion(true[:,j],ds[:,j],dpsi[:,j])
    geom=base.true_3d_range(c,true[:,:,:2]);d={**base_data,'true':true,'r_true':geom}
    z=geom[:,1:]+noise
    dist_delta=rms(np.linalg.norm(true[:,-1,:2]-previous[:,-1,:2],axis=1))
    range_delta=rms(geom[:,-1]-base_data['r_true'][:,-1])
    return d,z,dist_delta,range_delta


def plot_heading(rows, path):
    a=pd.DataFrame(rows);pr=a[a.family=='heading_prior'];bi=a[a.family=='heading_drift']
    fig,axs=plt.subplots(2,2,figsize=(11,7.7),constrained_layout=True)
    for key,title,xcol in [(pr,'Initial heading uncertainty','heading_sigma_deg'),(bi,'Unmodeled accumulated heading drift','heading_drift_deg')]:
        r=0 if title.startswith('Initial') else 1
        axs[r,0].plot(key[xcol],key.rmse_x_m,'o-',label='RMSE x')
        axs[r,0].plot(key[xcol],key.rmse_y_m,'o-',label='RMSE y')
        axs[r,0].plot(key[xcol],key.rmse_2d_m,'o-',label='RMSE 2D')
        axs[r,0].set(xlabel='Degrees',ylabel='Overall RMSE (m)',title=title);axs[r,0].legend()
        axs[r,1].plot(key[xcol],key.final_coverage_xy_95_pct,'o-',label='Final 95% coverage')
        axs[r,1].axhline(95,c='gray',ls=':',label='Ideal 95%');axs[r,1].set(xlabel='Degrees',ylabel='Final 2D coverage (%)',title='Consistency at final time');axs[r,1].legend()
    fig.savefig(path,dpi=150);plt.close(fig)


def plot_ar1(rows,aware,path):
    df=pd.DataFrame(rows);df=df[df.family=='range_temporal'].sort_values('rho')
    fig,axs=plt.subplots(2,2,figsize=(11.3,7.8),constrained_layout=True)
    x=df.rho.to_numpy()
    axs[0,0].plot(x,df.rmse_x_m,'o-',label='x RMSE')
    axs[0,0].plot(x,df.rmse_y_m,'o-',label='y RMSE')
    axs[0,0].plot(x,df.rmse_2d_m,'o-',label='2D RMSE')
    axs[0,0].set(title='Localization RMSE: same ranging RMSE=0.080m',ylabel='RMSE (m)');axs[0,0].legend()
    axs[0,1].plot(x,df.mean_nis,'o-',label='Mean NIS (ideal 1)')
    axs[0,1].plot(x,df.mean_nees_xy,'o-',label='Mean position NEES (ideal 2)')
    axs[0,1].set(title='Filter consistency',ylabel='NIS / NEES');axs[0,1].legend()
    axs[1,0].plot(x,df.final_coverage_xy_95_pct,'o-',label='Unaware EKF')
    aa=pd.DataFrame(aware).sort_values('rho')
    axs[1,0].plot(aa.rho,aa.final_coverage_xy_95_pct,'s--',label='AR1-aware EKF')
    axs[1,0].axhline(95,c='gray',ls=':');axs[1,0].set(title='Final 95% ellipse coverage',ylabel='Coverage (%)',xlabel='AR1 rho');axs[1,0].legend()
    axs[1,1].plot(x,df.raw_range_acf1,'o-',label='Range residual ACF(1)')
    axs[1,1].plot(x,df.nis_innov_acf1,'o-',label='Normalized innovation ACF(1)')
    axs[1,1].set(title='Time correlation appears in innovations',xlabel='AR1 rho',ylabel='Lag-1 correlation');axs[1,1].legend()
    for ax in axs.flat:ax.grid(alpha=.24)
    fig.savefig(path,dpi=150);plt.close(fig)


def plot_temporal_example(noises,path):
    fig,axs=plt.subplots(2,1,figsize=(11,7.2),constrained_layout=True)
    t=np.arange(noises[0][1].shape[1])*0.5
    for rho,n in noises:
        if rho in [0,0.90,0.98]:
            axs[0].plot(t,n[0],alpha=.82,label=f'rho={rho:g}')
            lags=np.arange(1,21)
            ac=[acf_pooled(n,int(l)) for l in lags]
            axs[1].plot(lags,ac,'o-',markersize=3,label=f'rho={rho:g}')
    axs[0].set(title='One paired synthetic ranging-error trajectory',xlabel='Time (s)',ylabel='Range error (m)')
    axs[1].set(title='Ensemble ranging-error autocorrelation',xlabel='Lag (measurements, 0.5s each)',ylabel='ACF')
    for ax in axs: ax.grid(alpha=.25);ax.legend()
    fig.savefig(path,dpi=150);plt.close(fig)



def plot_geometry(rows,c,path):
    sub=pd.DataFrame(rows)
    sub=sub[sub.family=='anchor_geometry'].sort_values('anchor_y_m')
    xx=np.linspace(c.start_x_m,c.start_x_m+c.step_m*c.n_steps,250)
    fig,ax=plt.subplots(1,2,figsize=(10.6,3.8),constrained_layout=True)
    for ay in sub.anchor_y_m:
        hh=np.sqrt((xx-c.anchor_x_m)**2+ay**2+(c.anchor_z_m-c.tag_z_m)**2)
        ax[0].plot(xx,np.abs(ay)/hh,label=f'Anchor y={ay:g} m')
    ax[0].set(title='Lateral range sensitivity along y=0',xlabel='Robot x (m)',ylabel='|dr/dy|')
    ax[0].legend()
    xx2=np.arange(len(sub));width=0.32
    ax[1].bar(xx2-width/2,sub.rmse_x_m,width,label='RMSE x')
    ax[1].bar(xx2+width/2,sub.rmse_y_m,width,label='RMSE y')
    ax[1].set(xticks=xx2,xticklabels=[f'Anchor y={a:g}m' for a in sub.anchor_y_m],title='Optional illustration from user sketch',ylabel='Position RMSE (m)')
    ax[1].legend()
    for a in ax: a.grid(alpha=.22)
    fig.savefig(path,dpi=150);plt.close(fig)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runs',type=int,default=1000)
    ap.add_argument('--seed',type=int,default=20261012)
    ap.add_argument('--output',type=Path,default=ROOT)
    opt=ap.parse_args();out=opt.output;out.mkdir(parents=True,exist_ok=True)
    c=base.Config(runs=opt.runs,seed=opt.seed)
    d=base.generate(c)
    base_e=d['z_ideal']-d['r_true'][:,1:]
    noise=normalized_white(base_e)
    baseline_z=d['r_true'][:,1:]+noise
    rows=[]; aware=[]; noises=[]; paired_stats={}
    dr=base.filter_metrics(base.apply_filter(c,d,'DR'))

    # Paired initial yaw-error magnitudes; trajectory, XY prior errors, RF errors unchanged.
    init_z=base.wrap(d['initial_est'][:,2]-d['true'][:,0,2])/np.deg2rad(c.initial_yaw_std_deg)
    for deg in [0.5,1.,3.,6.]:
        ci=replace(c,initial_yaw_std_deg=deg)
        di={**d,'initial_est':d['initial_est'].copy(),
            'p0_diag':np.array([c.initial_xy_std_m**2,c.initial_xy_std_m**2,np.deg2rad(deg)**2])}
        di['initial_est'][:,2]=base.wrap(di['true'][:,0,2]+init_z*np.deg2rad(deg))
        r,_,_=process_metrics(ci,di,baseline_z,f'initial_sigma_{deg:g}deg','heading_prior',heading_sigma_deg=deg)
        rows.append(r)

    # True heading increment contains an unmodeled systematic bias; DR prediction omits it.
    for deg in [0.,1.,3.,5.]:
        db,zb,delta_xy,delta_range=bias_drift_data(c,d,deg,noise)
        r,_,_=process_metrics(c,db,zb,f'drift_{deg:g}deg','heading_drift',heading_drift_deg=deg,
                              final_true_position_shift_m=delta_xy,final_true_range_shift_m=delta_range)
        rows.append(r)

    # Exactly equal *realized* raw range RMSE across all temporal conditions.
    for rho in [0.,0.50,0.90,0.98]:
        nn=ar1_noise(noise,rho)
        z=d['r_true'][:,1:]+nn
        r,est,norm_innov=process_metrics(c,d,z,f'ar1_{rho:g}','range_temporal',rho=rho,
                     theoretical_Neff_mean100=neff_finite(c.n_steps,rho))
        rows.append(r);noises.append((rho,nn))
        if rho in (0.,0.98):
            paired_stats[rho]={
              'run_mse2d':np.mean(np.sum(est['error'][:,1:,:2]**2,axis=2),axis=1),
              'run_mean_nees2d':np.mean(est['nees_xy'][:,1:],axis=1),
              'final_covered':(est['nees_xy'][:,-1]<=base.CHI2_95_2).astype(float),
            }
        ar=run_ar1_aware(c,d,z,rho)
        aware.append({'rho':rho,'case':f'ar1_{rho:g}','method':'AR1-aware augmented EKF',**ar})

    # Optional alternative from user's drawing: anchor near the +y wall, same trajectory.
    # NOT the original GitHub corridor anchor; just a single-factor geometry control.
    for ay in [0.,1.0]:
        cg=replace(c,anchor_y_m=ay)
        dg={**d,'r_true':base.true_3d_range(cg,d['true'][:,:,:2])}
        zg=dg['r_true'][:,1:]+noise
        r,_,_=process_metrics(cg,dg,zg,f'anchor_y_{ay:g}m','anchor_geometry',anchor_y_m=ay)
        rows.append(r)

    rng=np.random.default_rng(opt.seed+208)
    boot_ids=rng.integers(0,opt.runs,size=(2000,opt.runs))
    a,b=paired_stats[0.],paired_stats[0.98]
    drmses=np.sqrt(b['run_mse2d'][boot_ids].mean(axis=1))-np.sqrt(a['run_mse2d'][boot_ids].mean(axis=1))
    dcov=100*(b['final_covered'][boot_ids].mean(axis=1)-a['final_covered'][boot_ids].mean(axis=1))
    dnees=b['run_mean_nees2d'][boot_ids].mean(axis=1)-a['run_mean_nees2d'][boot_ids].mean(axis=1)
    boot={
      'comparison':'AR1 rho=0.98 minus rho=0.00 (paired by Monte Carlo run)',
      'n_runs':opt.runs,'n_bootstrap':2000,
      'overall_rmse_2d_diff_m':{'estimate':float(np.sqrt(b['run_mse2d'].mean())-np.sqrt(a['run_mse2d'].mean())), 'bootstrap_95ci':np.quantile(drmses,[.025,.975]).tolist()},
      'final_coverage_diff_percentage_points':{'estimate':float(100*(b['final_covered'].mean()-a['final_covered'].mean())), 'bootstrap_95ci':np.quantile(dcov,[.025,.975]).tolist()},
      'overall_mean_nees_2d_diff':{'estimate':float(np.mean(b['run_mean_nees2d']-a['run_mean_nees2d'])), 'bootstrap_95ci':np.quantile(dnees,[.025,.975]).tolist()}
    }
    (out/'PAIRED_BOOTSTRAP.json').write_text(json.dumps(boot,indent=2),encoding='utf-8')
    df=pd.DataFrame(rows)
    for fam,name in [('heading_prior','heading_initial.csv'),('heading_drift','heading_drift.csv'),
                     ('range_temporal','ranging_temporal_correlation.csv'),('anchor_geometry','geometry_comparison.csv')]:
        df[df.family==fam].to_csv(out/name,index=False,float_format='%.10g')
    df.to_csv(out/'all_scenarios.csv',index=False,float_format='%.10g')
    pd.DataFrame(aware).to_csv(out/'ar1_aware_vs_unaware.csv',index=False,float_format='%.10g')
    # QA: all marginal RMSEs identical exactly within roundoff; same GT, motion, initialization for AR1.
    ar_df=df[df.family=='range_temporal'].sort_values('rho')
    assert np.max(np.abs(ar_df.raw_range_rmse_m-0.08))<1e-12
    assert abs(ar_df.iloc[0].rho)<1e-12
    assert all(abs(df[(df.family=='heading_prior')].raw_range_rmse_m-0.08)<1e-12)
    assert all(np.isfinite(ar_df.mean_nees_xy)) and all(np.isfinite(ar_df.mean_nis))
    assert np.all(np.diff(ar_df.raw_range_acf1)>0)
    for rho in [0.,.5,.9,.98]:
        v=ar_df[ar_df.rho==rho].iloc[0]
        assert abs(v.raw_range_acf1-rho)<0.04,(rho,v.raw_range_acf1)
    plot_heading(rows,out/'01_heading_error_vs_localization.png')
    plot_ar1(rows,aware,out/'02_ar1_same_ranging_rmse.png')
    plot_temporal_example(noises,out/'03_ar1_time_series_acf.png')
    plot_geometry(rows,c,out/'04_geometry_effect.png')
    hashbase=hashlib.sha256((ROOT/'base_corridor_ekf.py').read_bytes()).hexdigest()
    manifest={'model':'range-only + relative DR + 3-state EKF; optional AR(1) state-augmented 4-state EKF',
       'no_dual_lp':True,'no_yaw_rf_bias_proxy':True,'synthetic_no_sionna':True,
       'source_github_repo':'myoungsunk/sionna-resimulation',
       'source_branch':'codex/range-only-bias-consistency-20261011',
       'source_file':'src/qclean_uwb/scenarios/corridor.py',
       'source_blob_sha':'eba1ab64d5e2117bfd519ceb5cac077b24caf3f8',
       'config':asdict(c),'seed':opt.seed,'runs':opt.runs,'base_engine_sha256':hashbase,
       'scenarios':df[['family','case']].to_dict(orient='records'),
       'qa_equal_marginal_range_rmse':True,
       'notes':'GT and initial XY and motion noises are identical across temporal conditions; global realized ranging RMS standardized to 0.08 m. Walls are not enforced. H_y zero on centerline only for central-anchor layout.'}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('BOOTSTRAP',json.dumps(boot,ensure_ascii=False))
    print('DR baseline',dr['rmse_2d_m'],dr['final_rmse_2d_m'])
    print('\nHEADING (initial prior)\n',df[df.family=='heading_prior'][['case','raw_range_rmse_m','rmse_x_m','rmse_y_m','rmse_2d_m','final_rmse_2d_m','mean_nis','mean_nees_xy','final_coverage_xy_95_pct']].round(4).to_string(index=False))
    print('\nHEADING (drift)\n',df[df.family=='heading_drift'][['case','final_true_position_shift_m','final_true_range_shift_m','rmse_y_m','rmse_2d_m','mean_nees_xy','final_coverage_xy_95_pct','gt_wall_violation_traj_pct']].round(4).to_string(index=False))
    print('\nTEMPORAL\n',ar_df[['case','raw_range_rmse_m','raw_range_acf1','theoretical_Neff_mean100','rmse_x_m','rmse_y_m','rmse_2d_m','final_rmse_2d_m','mean_nis','nis_innov_acf1','mean_nees_xy','coverage_xy_95_pct','final_coverage_xy_95_pct']].round(4).to_string(index=False))
    print('\nAR1 aware\n',pd.DataFrame(aware).round(4).to_string(index=False))
    print('\nGEOMETRY\n',df[df.family=='anchor_geometry'][['case','rmse_x_m','rmse_y_m','rmse_2d_m','mean_nees_xy','final_coverage_xy_95_pct']].round(4).to_string(index=False))

if __name__=='__main__':main()
