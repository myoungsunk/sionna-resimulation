#!/usr/bin/env python3
"""Independent postprocessing: show trajectory coupling, sensor disagreement, empirical covariance.

Run after main dual_heading_sim.py. Uses exactly the same synthetic seed streams.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dual_heading_sim import Config,ROUTES,generate,measure,filter_run,wrap,D2R,true_range


def rmse(x):return float(np.sqrt(np.mean(np.asarray(x)**2)))
def corr(x,y):
    x=np.asarray(x).reshape(-1);y=np.asarray(y).reshape(-1)
    return float(np.corrcoef(x,y)[0,1])


def main(runs=1000,out=Path(__file__).resolve().parent):
    cfg=Config(runs=runs)
    rows=[];samples={}
    for route in ROUTES:
        data=generate(cfg,route);obs=measure(cfg,data)
        dr=filter_run(cfg,data,obs,method='dr',retain_trace=True)
        ro=filter_run(cfg,data,obs,method='range',retain_trace=True)
        fy=filter_run(cfg,data,obs,method='both',retain_trace=True)
        # Integrate only heading1 and its initial yaw; also compare raw heading2.
        psi1=wrap(data['initial'][:,2,None]+np.cumsum(obs['dpsi'],axis=1))
        gt_psi=data['gt'][:,1:,2]
        err_1=wrap(psi1-gt_psi)/D2R
        err_2=wrap(obs['zheading']-gt_psi)/D2R
        f_err=wrap(fy['trajectory'][:,1:,2]-gt_psi)/D2R
        fin_b1=err_1[:,-1]; fin_RF=err_2[:,-1];fin_f=f_err[:,-1]
        yd=dr['trajectory'][:,-1,1]-data['gt'][:,-1,1]
        yr=ro['trajectory'][:,-1,1]-data['gt'][:,-1,1]
        yf=fy['trajectory'][:,-1,1]-data['gt'][:,-1,1]
        one=dict(route=route,runs=runs,heading1_final_rmse_deg=rmse(fin_b1),heading2_raw_final_rmse_deg=rmse(fin_RF),
          heading_fused_final_rmse_deg=rmse(fin_f),
          heading1_vs_heading2_final_disagreement_rmse_deg=rmse(wrap((psi1[:,-1]-obs['zheading'][:,-1]))/D2R),
          corr_final_y_vs_heading1_DR=corr(yd,fin_b1),
          corr_final_y_vs_heading1_rangeEKF=corr(yr,fin_b1),
          corr_final_y_vs_fused_heading_fusion=corr(yf,fin_f),
          heading1_step_bias_deg=float(np.mean(obs['yaw1_error_deg'])),heading1_step_sigma_deg=float(np.std(obs['yaw1_error_deg'])),
          heading2_obs_bias_deg=float(np.mean(err_2)),heading2_obs_sigma_deg=float(np.std(err_2)),
          range_std_m=float(np.std(obs['range_error_m'])),
          empirical_rho_range_rfheading=corr(obs['range_error_m'],err_2),
          empirical_rho_gyro_rfheading=corr(obs['yaw1_error_deg'],err_2))
        rows.append(one)
        samples[route]=dict(e1=fin_b1,e2=fin_RF,ef=fin_f,yd=yd,yr=yr,yf=yf)
    f=out/'09_sensor_error_trajectory_relationships.csv'
    pd.DataFrame(rows).to_csv(f,index=False,float_format='%.12g')
    # Explicitly simulate two correlated noises to verify that the covariance
    # entries in R and C are sourced from the intended sharing mechanisms.
    crows=[]
    for rc,gc in [(0,0),(.8,0),(-.8,0),(0,.6),(0,-.6),(.5,.5)]:
        x=generate(cfg,'straight')
        ob=measure(cfg,x,corr_range_rf=rc,corr_gyro_rf=gc)
        etar=ob['range_error_m']/cfg.range_std_m
        etag=ob['yaw1_error_deg']/cfg.dr_yaw_std_deg
        etah=ob['yaw2_error_deg']/cfg.rf_heading_std_deg
        crows.append(dict(rho_r_rf_requested=rc,rho_g_rf_requested=gc,
            rho_range_rf_empirical=corr(etar,etah),rho_gyro_rf_empirical=corr(etag,etah),
            rho_range_gyro_empirical=corr(etar,etag)))
    pd.DataFrame(crows).to_csv(out/'10_empirical_noise_covariance_checks.csv',index=False,float_format='%.12g')

    fig,axes=plt.subplots(2,2,figsize=(12.3,8.9),layout='constrained')
    colors=['#176da7','#c07f30','#539a71','#8a64b1']
    for (route,col) in zip(ROUTES,colors):
        d=samples[route]
        a=axes[0,0]
        a.scatter(d['e1'],d['yd'],s=6,alpha=.15,color=col,label=f'{ROUTES[route]["name"]} (rho={corr(d["e1"],d["yd"]):.2f})')
        a=axes[0,1]
        a.scatter(d['ef'],d['yf'],s=6,alpha=.15,color=col,label=f'{ROUTES[route]["name"]} (rho={corr(d["ef"],d["yf"]):.2f})')
    axes[0,0].set(title='DR heading-1 final error vs DR lateral position error',xlabel='Integrated heading1 error (deg)',ylabel='Final lateral error y (m)')
    axes[0,1].set(title='Fused heading error vs fused lateral position error',xlabel='Fused heading error (deg)',ylabel='Final lateral error y (m)')
    axes[0,0].legend(fontsize=7,ncol=1);axes[0,1].legend(fontsize=7,ncol=1)
    data=pd.DataFrame(rows); xx=np.arange(len(data));w=.24
    axes[1,0].bar(xx-w,data.heading1_final_rmse_deg,w,label='Heading1 integrated DR')
    axes[1,0].bar(xx,data.heading2_raw_final_rmse_deg,w,label='Heading2 RF observation')
    axes[1,0].bar(xx+w,data.heading_fused_final_rmse_deg,w,label='Fused EKF')
    axes[1,0].set(title='Two heading channels & estimated yaw error',ylabel='Final heading RMSE (deg)')
    axes[1,0].set_xticks(xx,['Straight','Rectangle','Rieul','Zigzag'])
    axes[1,0].legend(fontsize=8)
    cdf=pd.DataFrame(crows)
    inds=np.arange(len(cdf));w=.3
    axes[1,1].bar(inds-w/2,cdf.rho_range_rf_empirical,width=w,label='measured corr(range, RF yaw)')
    axes[1,1].bar(inds+w/2,cdf.rho_gyro_rf_empirical,width=w,label='measured corr(gyro, RF yaw)')
    axes[1,1].set_xticks(inds,[f'({r:+.1f},{g:+.1f})' for r,g in zip(cdf.rho_r_rf_requested,cdf.rho_g_rf_requested)],rotation=20)
    axes[1,1].set(title='Empirical same-epoch noise correlation QA',xlabel='Requested (rho_range, rho_gyro)',ylabel='Pearson correlation',ylim=(-1,1))
    axes[1,1].legend(fontsize=7)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('Two heading sensors, range and trajectory error: distinct statistical relationships',fontsize=13)
    fig.savefig(out/'07_sensor_trajectory_error_coupling.png',dpi=175,bbox_inches='tight')
    plt.close(fig)
    print('RELATIONSHIP_AUDIT');print(pd.DataFrame(rows).round(4).to_string(index=False))
    print('COV_AUDIT');print(pd.DataFrame(crows).round(4).to_string(index=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs',type=int,default=1000);p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent)
    a=p.parse_args();main(a.runs,a.out)
