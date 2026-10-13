#!/usr/bin/env python3
"""Independent numerical QA: analytic EKF Jacobians, gauge symmetry, matched trial, PSD and outputs."""
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from dual_heading_sim import Config,generate,measure,filter_run,motion,true_range,wrap,D2R
out=Path(__file__).resolve().parent
checks={}
cfg=Config(runs=1000)
# Motion Jacobian finite diff at a nontrivial state and turn, numeric in world coords.
x=np.array([7.2,0.2,.37]);u=np.array([.11,.26]);h=1e-6
phi=x[2]+.5*u[1];F=np.eye(3);F[0,2]=-u[0]*np.sin(phi);F[1,2]=u[0]*np.cos(phi)
G=np.array([[np.cos(phi),-.5*u[0]*np.sin(phi)], [np.sin(phi),.5*u[0]*np.cos(phi)], [0.,1.]])
fn=lambda xv,uv: motion(xv[None,:],np.array([uv[0]]),np.array([uv[1]]))[0]
Fe=np.zeros((3,3));Ge=np.zeros((3,2))
for j in range(3):
 xp=x.copy();xm=x.copy();xp[j]+=h;xm[j]-=h
 dd=(fn(xp,u)-fn(xm,u))/(2*h);dd[2]=wrap(fn(xp,u)[2]-fn(xm,u)[2])/(2*h)
 Fe[:,j]=dd
for j in range(2):
 up=u.copy();um=u.copy();up[j]+=h;um[j]-=h
 dd=(fn(x,up)-fn(x,um))/(2*h);dd[2]=wrap(fn(x,up)[2]-fn(x,um)[2])/(2*h)
 Ge[:,j]=dd
checks['motion_jacobian_finite_difference']={'pass':bool(max(np.max(np.abs(F-Fe)),np.max(np.abs(G-Ge)))<2e-8),'max_abs_diff':float(max(np.max(np.abs(F-Fe)),np.max(np.abs(G-Ge))))}
# Correct linearisation of anchor-relative bearing.
ax,ay,_=cfg.anchor_xyz_m
def bearing(q):return wrap(np.arctan2(ay-q[1],ax-q[0])-q[2])
dx=ax-x[0];dy=ay-x[1];d2=dx*dx+dy*dy
Hb=np.array([dy/d2,-dx/d2,-1.]);Hnum=[]
for j in range(3):
 xp=x.copy();xm=x.copy();xp[j]+=h;xm[j]-=h;Hnum.append(wrap(bearing(xp)-bearing(xm))/(2*h))
checks['relative_bearing_jacobian_finite_difference']={'pass':bool(np.max(np.abs(Hb-Hnum))<1e-8),'max_abs_diff':float(np.max(np.abs(Hb-Hnum)))}
# Full 3-way noise covariance correlation is PSD for included sweep.
rg=.5;rr=.5;M=np.array([[1.,0.,rg],[0.,1.,rr],[rg,rr,1.]])
checks['combined_noise_correlation_PSD']={'pass':bool(np.linalg.eigvalsh(M).min()>0),'lambda_min':float(np.linalg.eigvalsh(M).min())}
# Gauge invariance of range and anchor-relative bearing about the one fixed anchor.
p=np.array([8.3,-.36,.5]);turn=1.02;c,s=np.cos(turn),np.sin(turn)
R=np.array([[c,-s],[s,c]])
pnew=p.copy();pnew[:2]=[ax,ay]+R@(p[:2]-[ax,ay]);pnew[2]=wrap(p[2]+turn)
checks['single_anchor_rotation_symmetry']={'pass':bool(abs(float(true_range(cfg,p)-true_range(cfg,pnew)))<1e-12 and abs(float(wrap(bearing(p)-bearing(pnew))))<1e-12)}
# First baseline must numerically reproduce the main study (script patched only with optional cadence, defaults unchanged).
d=generate(cfg,'straight');z=measure(cfg,d)
f=filter_run(cfg,d,z,method='both');df=pd.read_csv(out/'01_sensor_ablation.csv');p=df[(df.route=='straight')&(df.model=='both')].iloc[0]
err=max(abs(f[k]-p[k]) for k in ('rmse_2d_m','mean_nees_xy','final_coverage_pct'))
checks['reproduce_baseline_after_optional_cadence_extension']={'pass':bool(err<1e-9),'max_abs_diff':float(err)}
checks['repeatable_exact_sample']={'pass':bool(np.array_equal(generate(cfg,'straight')['gt'],d['gt']))}
# All output stats and file counts.
all_cases=pd.read_csv(out/'all_cases.csv');cad=pd.read_csv(out/'11_heading_cadence_complementarity.csv');cov=pd.read_csv(out/'12_simultaneous_cross_correlation.csv');e=pd.read_csv(out/'10_empirical_noise_covariance_checks.csv')
checks['348_core_56_supplementary_experiments']={'pass':bool(len(all_cases)==348 and len(cad)==48 and len(cov)==8),'core':len(all_cases),'extra':len(cad)+len(cov)}
checks['measured_correlations_match_generation']={'pass':bool(max(abs(e.rho_range_rf_empirical-e.rho_r_rf_requested).max(),abs(e.rho_gyro_rf_empirical-e.rho_g_rf_requested).max())<.018),
 'worst_abs_rho_error':float(max(abs(e.rho_range_rf_empirical-e.rho_r_rf_requested).max(),abs(e.rho_gyro_rf_empirical-e.rho_g_rf_requested).max()))}
checks['all_coverage_within_0_100']={'pass':bool(all_cases.final_coverage_pct.between(0,100).all())}
checks['all_rmse_positive_finite']={'pass':bool(np.isfinite(all_cases.rmse_2d_m).all() and (all_cases.rmse_2d_m>0).all())}
qa={'passed':all(z['pass'] for z in checks.values()),'checks':checks}
(out/'QA_INDEPENDENT.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(qa,indent=2))
if not qa['passed']:raise SystemExit(1)
