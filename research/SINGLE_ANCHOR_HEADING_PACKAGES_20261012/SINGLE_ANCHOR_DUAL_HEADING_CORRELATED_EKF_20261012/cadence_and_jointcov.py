#!/usr/bin/env python3
"""Supplemental robustness study (sparser RF and simultaneously correlated error streams)."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dual_heading_sim import Config,generate,measure,filter_run

def main():
 out=Path(__file__).resolve().parent
 cfg=Config(runs=1000);rows=[]
 for route in ('straight','zigzag'):
  d=generate(cfg,route)
  for period in (1,10,20):
   for rfstd in (1.,5.):
    for gstd in (.08,.60):
     for gbias in (0.,5.):
      obs=measure(cfg,d,gyro_std_deg=gstd,gyro_accum_bias_deg=gbias,rf_std_deg=rfstd)
      f=filter_run(cfg,d,obs,method='both',dr_std_deg=gstd,rf_std_deg=rfstd,heading_period_steps=period)
      rows.append(dict(route=route,rf_step_period=period,rf_period_s=.5*period,
         rf_sigma_deg=rfstd,gyro_step_sigma_deg=gstd,gyro_accum_bias_deg=gbias,
         rmse_2d_m=f['rmse_2d_m'],rmse_heading_deg=f['rmse_heading_deg'],mean_nees_xy=f['mean_nees_xy'],final_95_coverage_pct=f['final_coverage_pct']))
 x=pd.DataFrame(rows);x.to_csv(out/'11_heading_cadence_complementarity.csv',index=False,float_format='%.12g')
 cor=[]
 for route in ('straight','rectangle','rieul','zigzag'):
  d=generate(cfg,route)
  obs=measure(cfg,d,corr_range_rf=.5,corr_gyro_rf=.5)
  for flag in (True,False):
   f=filter_run(cfg,d,obs,method='both',rho_range_rf=.5,rho_gyro_rf=.5,use_correct_cov=flag)
   cor.append(dict(route=route,requested_rho_range_rf=.5,requested_rho_gyro_rf=.5,
       covariance_model='correct_full' if flag else 'ignored_all',
       rmse_2d_m=f['rmse_2d_m'],mean_nees_xy=f['mean_nees_xy'],final_95_coverage_pct=f['final_coverage_pct'],mean_nis=f['mean_nis']))
 co=pd.DataFrame(cor);co.to_csv(out/'12_simultaneous_cross_correlation.csv',index=False,float_format='%.12g')
 fig,axs=plt.subplots(2,2,figsize=(12.5,8.7),layout='constrained')
 for rr,row in enumerate(('straight','zigzag')):
  for cc,rfstd in enumerate((1.,5.)):
   ax=axs[rr,cc];d=x[(x.route==row)&(x.rf_sigma_deg==rfstd)]
   for gstd in (.08,.60):
    for bias in (0.,5.):
     q=d[(d.gyro_step_sigma_deg==gstd)&(d.gyro_accum_bias_deg==bias)].sort_values('rf_step_period')
     ax.plot(q.rf_period_s,q.rmse_2d_m,'-o' if bias==0 else '--s',label=f'gyro σ={gstd:g}°, biasΣ={bias:g}°')
   ax.set(title=f'{row} | RF heading sigma {rfstd:g}°',xlabel='RF heading update interval (s)',ylabel='2D position RMSE (m)')
   ax.grid(alpha=.2);ax.legend(fontsize=8)
 fig.suptitle('When gyro heading matters again: fewer and noisier RF heading updates',fontsize=13)
 fig.savefig(out/'08_heading_precision_vs_rf_rate.png',dpi=175,bbox_inches='tight');plt.close(fig)
 print('CADENCE ABLATION selected:')
 print(x[(x.route=='straight')&(x.rf_sigma_deg==5.)][['rf_period_s','gyro_step_sigma_deg','gyro_accum_bias_deg','rmse_2d_m','mean_nees_xy','final_95_coverage_pct']].round(4).to_string(index=False))
 print('SIMULTANEOUS CORRELATION:');print(co.round(4).to_string(index=False))

if __name__=='__main__':main()
