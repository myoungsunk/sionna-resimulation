#!/usr/bin/env python3
"""Post-hoc P2-A transparent outcome tables; no held-route tuning or arm selection.

Route is unit of primary comparison; case/bias rows are matched trajectories, not IID routes.
"""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
p=argparse.ArgumentParser()
p.add_argument('--scores',required=True);p.add_argument('--out',required=True)
a=p.parse_args();dest=Path(a.out);dest.mkdir(exist_ok=True,parents=True)
raw=pd.read_csv(a.scores)
arms=['BASE_POWER','CIR_ONLY_SHARED','WIDE_SHARED','WIDE_CAL','NARROW_CAL','ORACLE_SHARED','RAW_SHARED','RANGE_ONLY','DR_ONLY']
initials=['NOM','E+10_P5','E-10_P5','E+20_P5','E-20_P5','E+10_PM','E-10_PM','E+20_PM','E-20_PM']
cases=['R2_aA_m0','R2_aA_m45','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0']
assert len(raw)==1701,(len(raw),'EXPECTED 1701')
assert set(raw.case)==set(cases) and set(raw.arm)==set(arms) and set(raw.init)==set(initials)
m=raw[raw.channel.eq('full') & raw.bias.isin(['B0','L2'])].copy()
k=['case','bias','init']
root=m[m.arm=='BASE_POWER'].set_index(k)
cir=m[m.arm=='CIR_ONLY_SHARED'].set_index(k)
assert len(root)==126,len(root)
rows=[]
for arm in arms:
    c=m[m.arm==arm].set_index(k)
    assert c.index.equals(root.index),arm
    q=c.copy()
    for prop in ['heading_rmse_deg','xy_rmse_cm','heading_nees_1d','heading_cov95','anchor_range_rmse_cm',
                 'stable_30_plus_heading_q99_abs_deg','stable_30_plus_heading_rmse_deg']:
        if prop in q:
            q['reference_BASE_'+prop]=root[prop]
            q['reference_CIR_'+prop]=cir[prop]
            if 'rmse' in prop or 'q99' in prop:
                q['ratio_BASE_'+prop]=q[prop]/np.maximum(root[prop],1e-12)
                q['ratio_CIR_'+prop]=q[prop]/np.maximum(cir[prop],1e-12)
    rows.append(q.reset_index())
pair=pd.concat(rows,ignore_index=True)
pair.to_csv(dest/'P2_A_PAIRED_FULL.csv',index=False)
groups=[]
for (route,init,arm),q in pair.groupby(['route','init','arm'],sort=True):
    groups.append({'route':route,'init':init,'arm':arm,'n_case_bias':len(q),
        'heading_rmse_median_deg':float(q.heading_rmse_deg.median()),
        'heading_ratio_BASE_median':float(q.ratio_BASE_heading_rmse_deg.median()),
        'heading_ratio_CIR_median':float(q.ratio_CIR_heading_rmse_deg.median()),
        'heading_nees_median':float(q.heading_nees_1d.median()),
        'heading_coverage95_median':float(q.heading_cov95.median()),
        'xy_rmse_median_cm':float(q.xy_rmse_cm.median()),
        'xy_ratio_BASE_median':float(q.ratio_BASE_xy_rmse_cm.median()),
        'heading_q99_ratio_BASE_median':float(q.ratio_BASE_stable_30_plus_heading_q99_abs_deg.median()),
        'anchor_range_ratio_BASE_median':float(q.ratio_BASE_anchor_range_rmse_cm.median())})
route=pd.DataFrame(groups).sort_values(['route','init','arm'])
route.to_csv(dest/'P2_A_ROUTE_MEDIAN.csv',index=False)
for initial in initials:
    w=route[(route.init==initial)&route.arm.isin(['BASE_POWER','CIR_ONLY_SHARED','WIDE_SHARED','WIDE_CAL','ORACLE_SHARED'])]
    print('ROUTE_MEDIAN init='+initial+'\n'+w[['route','arm','heading_rmse_median_deg','heading_ratio_BASE_median','heading_ratio_CIR_median','heading_nees_median','heading_coverage95_median','xy_ratio_BASE_median']].round(4).to_string(index=False),flush=True)
summary=[]
for init in initials:
    q=route[route.init==init]
    for arm in arms:
        v=q[q.arm==arm]
        if len(v)!=3:raise AssertionError(('ROUTE_MISSING',init,arm))
        summary.append({'init':init,'arm':arm,
            'route_medians_heading_deg_mean':float(v.heading_rmse_median_deg.mean()),
            'route_medians_heading_ratio_BASE_median':float(v.heading_ratio_BASE_median.median()),
            'route_medians_heading_ratio_CIR_median':float(v.heading_ratio_CIR_median.median()),
            'n_routes_heading_improve_vs_BASE':int((v.heading_ratio_BASE_median<1).sum()),
            'n_routes_heading_improve_vs_CIR':int((v.heading_ratio_CIR_median<1).sum()),
            'route_medians_heading_NEES_mean':float(v.heading_nees_median.mean()),
            'route_medians_heading_cov95_mean':float(v.heading_coverage95_median.mean()),
            'route_medians_xy_ratio_BASE_median':float(v.xy_ratio_BASE_median.median())})
pd.DataFrame(summary).to_csv(dest/'P2_A_COMPARISON.csv',index=False)
qa={'rows':len(raw),'full_B0_L2_rows':len(m),'routes':sorted(raw.route.unique().tolist()),
    'case_count':len(cases),'conditions':['full/B0','full/L2','los/B0'],
    'initial_conditions':initials,'arms':arms,
    'statistical_unit':'3 held routes; case-by-condition and time samples not IID replicates',
    'selection':'no model selection based on outer held route results',
    'generalization':'Only previously used development R2/R4/R5 routes; no external routes',
    'phase':'P2-A baseline recursive; P2-B calibration and P2-C range combination excluded'}
(dest/'P2_A_ANALYSIS_QA.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False))
print('P2_ANALYSIS_OK '+json.dumps(qa),flush=True)
