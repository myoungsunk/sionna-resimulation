#!/usr/bin/env python3
"""Checks model algebra, simulated statistics and output provenance.
Does NOT validate any real-world RF model or real corridor measurements.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import base_corridor_ekf as base

D=Path(__file__).resolve().parent
C=base.Config(runs=30)
r=np.array([[8.12,0.35,0.3],[11.,-0.2,-0.4]],dtype=float)
a=base.range_jacobian(C,r)
assert np.all(a[:,2] == 0)
for index in (0,1):
    rp=r.copy();rm=r.copy();eps=1e-6
    rp[:,index]+=eps;rm[:,index]-=eps
    fd=(base.true_3d_range(C,rp[:,:2])-base.true_3d_range(C,rm[:,:2]))/(2*eps)
    assert np.allclose(fd,a[:,index],atol=1e-8)
assert np.allclose(base.true_3d_range(C,r[:,:2]),base.true_3d_range(C,np.column_stack([r[:,:2]])))

manifest=json.loads((D/'MANIFEST.json').read_text())
scen=pd.read_csv(D/'all_scenarios.csv')
aware=pd.read_csv(D/'ar1_aware_vs_unaware.csv')
boot=json.loads((D/'PAIRED_BOOTSTRAP.json').read_text())
ar=scen[scen.family=='range_temporal'].sort_values('rho')
assert len(ar)==4 and len(aware)==4
assert np.allclose(ar.raw_range_rmse_m.to_numpy(),0.08,atol=1e-10)
assert np.all(np.abs(ar.raw_range_acf1.to_numpy()-ar.rho.to_numpy())<0.04)
assert scen[['rmse_x_m','rmse_y_m','rmse_2d_m','mean_nis','mean_nees_xy']].notna().all().all()
assert np.allclose(scen.rmse_2d_m, np.hypot(scen.rmse_x_m,scen.rmse_y_m),atol=1e-8)
assert np.all(scen.rmse_2d_m>0)
assert scen[scen.family=='heading_prior'].raw_range_rmse_m.max()-scen[scen.family=='heading_prior'].raw_range_rmse_m.min()<1e-10
assert ar.iloc[-1].mean_nees_xy>ar.iloc[0].mean_nees_xy
assert ar.iloc[-1].final_coverage_xy_95_pct<ar.iloc[0].final_coverage_xy_95_pct
assert aware.loc[aware.rho==0.98,'mean_nees_xy'].iloc[0]<ar.iloc[-1].mean_nees_xy
assert abs(boot['overall_rmse_2d_diff_m']['estimate']-(ar.iloc[-1].rmse_2d_m-ar.iloc[0].rmse_2d_m))<1e-7
assert manifest['no_dual_lp'] and manifest['no_yaw_rf_bias_proxy']

# Check covariance PSD and positive chi-square statistics in a fresh small run.
c=base.Config(runs=30,n_steps=30)
d=base.generate(c)
out=base.apply_filter(c,d,'EKF_IDEAL')
eig=np.linalg.eigvalsh(out['cov'].reshape(-1,3,3))
assert float(eig.min())>-1e-12
assert np.all(np.isfinite(out['nees_xy'])) and np.all(out['nis'][:,1:]>0)

for name in ('01_heading_error_vs_localization.png','02_ar1_same_ranging_rmse.png',
             '03_ar1_time_series_acf.png','04_geometry_effect.png','MANIFEST.json','all_scenarios.csv','EXECUTION_LOG.txt'):
    assert (D/name).stat().st_size>100

info={
  'model_yaw_jacobian_zero':'PASS',
  'range_position_jacobian_central_difference':'PASS',
  'same_realized_marginal_ranging_RMSE_for_all_temporal_cases':'PASS',
  'empirical_AR1_autocorrelation_matches_rho':'PASS',
  'rmse2d_identity':'PASS',
  'finite_NIS_NEES_and_positive_metrics':'PASS',
  'covariance_PSD_sample':'PASS',
  'no_dual_LP_no_yaw_RF_bias_proxy':'PASS',
  'AR1_aware_vs_naive_directional_sanity':'PASS',
  'figures_and_tables_exist':'PASS',
  'full_replay_determinism':('PASS_EXTERNAL_REPLAY' if (D/'REPRODUCIBILITY_CHECK.json').exists() and
      json.loads((D/'REPRODUCIBILITY_CHECK.json').read_text()).get('study_code_sha256')==__import__('hashlib').sha256((D/'study.py').read_bytes()).hexdigest() and
      all(__import__('hashlib').sha256((D/k['path']).read_bytes()).hexdigest()==k['sha256'] for k in json.loads((D/'REPRODUCIBILITY_CHECK.json').read_text())['compared'])
      else 'NOT_CHECKED'),
  'actual_Sionna_or_measured_RF_validation':'NOT_RUN',
  'wall_collision_enforced':'NO',
}
(D/'QA_REPORT.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(info,ensure_ascii=False,indent=2))
