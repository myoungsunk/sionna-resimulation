#!/usr/bin/env python3
"""E6 full pilot aggregate: route is experimental cluster; all cases retained."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();src=Path(a.input);dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
score_files=sorted(src.rglob('*_E6_SCORES.csv'))
qa_files=sorted(src.rglob('*_E6_QA.json'))
assert len(score_files)==len(qa_files)==7,([str(q) for q in score_files], [str(q) for q in qa_files])
S=pd.concat([pd.read_csv(f) for f in score_files],ignore_index=True)
qas=[json.loads(q.read_text()) for q in qa_files]
arms=['BASE','PWIDE_ALL','SEL_VS_Q80','SEL_SHAPE_Q80','SEL_DETECTOR_Q80','SEL_HALFSHRINK','ORACLE_Ds_DIAG']
assert len(S)==7*2*len(arms) and set(S.arm)==set(arms)
assert set(S.route)=={'R2','R4','R5'} and set(S.bias)=={'B0','L2'}
assert all(k['case'] in set(S.case) and k['all_online_candidates_have_no_GT_features'] for k in qas)
S.to_csv(dst/'E6_RECURSIVE_SCORES.csv',index=False)
m=S.set_index(['case','bias','arm'])
base=S[S.arm=='BASE'].set_index(['case','bias'])
cir=S[S.arm=='PWIDE_ALL'].set_index(['case','bias'])
routeRows=[]
for (route,bias,arm),grp in S.groupby(['route','bias','arm']):
    refs=base.loc[list(zip(grp.case,grp.bias))]
    vals=grp.heading_rmse_deg.to_numpy()
    ratios=vals/refs.heading_rmse_deg.to_numpy()
    routeRows.append({'route':route,'bias':bias,'arm':arm,
        'n_case':len(grp),'heading_rmse_route_median_deg':float(np.median(vals)),
        'ratio_to_BASE_median':float(np.median(ratios)),
        'n_case_better_BASE':int(np.sum(ratios<1)),
        'heading_nees_route_median':float(grp.heading_nees_1d.median()),
        'heading_coverage95_median':float(grp.heading_cov95.median()),
        'xy_rmse_route_median_cm':float(grp.xy_rmse_cm.median()),
        'xy_ratio_BASE_median':float(np.median(grp.xy_rmse_cm.to_numpy()/refs.xy_rmse_cm.to_numpy())),
        'alpha_frac_t30_median':float(grp.alpha_frac_t30.median()),
        'accept_t30_median':float(grp.accept_t30.median())})
R=pd.DataFrame(routeRows).sort_values(['route','bias','arm'])
R.to_csv(dst/'E6_ROUTE.csv',index=False)
a=[]
for f in sorted(src.rglob('*_E6_TRACE.csv.gz')):
    tr=pd.read_csv(f)
    assert tr.arm.nunique()==len(arms),str(f)
    tr=tr[(tr.t_s>=30)&(tr.arm!='ORACLE_Ds_DIAG')].copy()
    for (route,bias,arm),gg in tr.groupby(['route','bias','arm']):
        harmful=gg.d_s_truth<0
        small=np.abs(gg.rb_gt)<.05
        sel=gg.alpha>0
        a.append({'case':gg.case.iloc[0],'route':route,'bias':bias,'arm':arm,
          'n':len(gg),'alpha_mean':float(gg.alpha.mean()),
          'apply_when_harm_frac':float(np.mean(sel&harmful)),
          'apply_given_harm_rate':float(np.mean(sel[harmful])) if harmful.any() else np.nan,
          'apply_given_clean_rate':float(np.mean(sel[small])) if small.any() else np.nan,
          'residual_rms_after':float(np.sqrt(np.mean(gg.rp_gt**2))),
          'residual_signed_mean_after':float(gg.rp_gt.mean())})
pd.DataFrame(a).to_csv(dst/'E6_OFFLINE_HARM_DIAG.csv',index=False)
meta={'case_count':7,'rows':len(S),'base_equals_frozen_ladder3_for_all_cases':True,
      'selection_rule':'unlabelled train-route q80, applied to observed Full RF only',
      'oracle_is_diagnostic_only':True,'models_trained_on_held_route':False,
      'E5_same_prior_not_claimed':True,'E7_cov_calibration_not_claimed':True,
      'new_scene_independence':False,'n_outer_routes':3,
      'source_version':'original P2 ladder 3 PWIDE'}
(dst/'E6_QA.json').write_text(json.dumps(meta,indent=2))
print('E6 ROUTE SUMMARY\n'+R[['route','bias','arm','heading_rmse_route_median_deg','ratio_to_BASE_median','n_case_better_BASE','xy_ratio_BASE_median','heading_nees_route_median','heading_coverage95_median','alpha_frac_t30_median']].round(4).to_string(index=False),flush=True)
print('E6_PILOT_PASS '+json.dumps(meta),flush=True)
