#!/usr/bin/env python3
"""Standalone verification of archived heading fusion outputs (no simulation rerun)."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
checks={}
for f in ['heading_fusion.py','base_corridor_ekf.py','simulate_routes.py','previous_route_metrics_20261012.csv',
          'method_ablation.csv','heading_precision_sweep.csv','heading_update_cadence.csv',
          'heading_persistent_bias.csv','unmodelled_heading_drift.csv','paired_bootstrap_summary.csv',
          'final_coverage_per_run.csv','illustrative_run_selection.csv','illustrative_selected_paths.csv',
          'MANIFEST.json','QA_REPORT.json','README_KO.md','REPORT_KO.md']:
    assert (ROOT/f).is_file(),f
checks['required_sources_and_results_exist']=True
for i in range(1,8):
    assert len(list(ROOT.glob(f'{i:02d}_*.png')))==1,i
checks['seven_png_figures_exist']=True
A=pd.read_csv(ROOT/'method_ablation.csv')
old=pd.read_csv(ROOT/'previous_route_metrics_20261012.csv')
for n in ['straight','rectangle','rieul','zigzag']:
    ar=A[(A.route==n)&(A.method=='range_only')].iloc[0]
    ro=old[(old.route==n)&(old.condition=='iid')].iloc[0]
    assert abs(ar.rmse_2d_m-ro.rmse_2d_m)<1e-10,(n,ar.rmse_2d_m,ro.rmse_2d_m)
    assert abs(ar.final_coverage_xy_95_pct-ro.final_coverage_2d_95_pct)<1e-10
checks['published_20261012_baseline_reproduced']=True
S=pd.read_csv(ROOT/'heading_precision_sweep.csv')
F=S[S.method=='range_plus_heading']
assert len(F)==24
assert set(np.round(F.heading_sigma_deg,4))=={.5,1,2,3,5,10}
assert np.allclose(F.raw_ranging_rmse_m,.08,atol=1e-12)
assert np.isfinite(F[['rmse_2d_m','heading_rmse_deg','mean_nees_xy']].to_numpy()).all()
assert all(F[F.route==n].rmse_2d_m.max()<float(A[(A.route==n)&(A.method=='range_only')].rmse_2d_m.iloc[0]) for n in ('straight','rectangle','rieul','zigzag'))
checks['sigma_sweep_complete_and_better_than_baseline_in_studied_cases']=True
B=pd.read_csv(ROOT/'paired_bootstrap_summary.csv')
assert len(B)==4
assert np.all(B.bootstrap_improvement_pct_ci_low>0)
assert np.all(B.bootstrap_improvement_pct_ci_low<=B.rmse_improvement_pct)
assert np.all(B.rmse_improvement_pct<=B.bootstrap_improvement_pct_ci_high)
checks['paired_bootstrap_intervals_valid']=True
C=pd.read_csv(ROOT/'final_coverage_per_run.csv')
assert len(C)==8000
assert np.array_equal(C.inside_95.astype(bool).to_numpy(),(C.final_nees_xy.to_numpy()<=5.991464547107979))
for n in ['straight','rectangle','rieul','zigzag']:
    for method in ['range_only','range_plus_heading']:
        subset=C[(C.route==n)&(C.method==method)]
        assert len(subset)==1000
        ar=A[(A.route==n)&(A.method==method)]
        assert abs(100*subset.inside_95.mean()-float(ar.final_coverage_xy_95_pct.iloc[0]))<1e-9
checks['individual_final_coverage_flags_recomputed']=True
N=pd.read_csv(ROOT/'illustrative_run_selection.csv')
assert len(N)==4 and N.run_id.between(0,999).all()
I=pd.read_csv(ROOT/'illustrative_selected_paths.csv')
assert len(I)==4*101
for n in N.route:
    assert (I[I.route==n].selected_run_id==int(N[N.route==n].run_id.iloc[0])).all()
checks['illustrative_selection_disclosed_and_coordinates_exist']=True
Q=json.loads((ROOT/'QA_REPORT.json').read_text()); assert Q['all_passed']
checks['source_simulation_QA_passed']=True
print(json.dumps({'status':'PASS','checks':checks,'total':len(checks)},indent=2,ensure_ascii=False))
