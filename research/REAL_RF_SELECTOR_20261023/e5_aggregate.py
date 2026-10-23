#!/usr/bin/env python3
"""E5 same-prior, same-R/gate offline one-update paired packet outcomes."""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True)
a=ap.parse_args();inp=Path(a.input);out=Path(a.out);out.mkdir(exist_ok=True,parents=True)
fs=sorted(inp.rglob('*_E5_SAMEPRIOR.csv'))
qa=sorted(inp.rglob('*_E5_QA.json'))
assert len(fs)==len(qa)==7,([str(x) for x in fs],[str(x) for x in qa])
S=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
assert len(S)==7*2*7,S.shape
assert set(S.route)=={'R2','R4','R5'}
check=[json.loads(p.read_text()) for p in qa]
assert all(max(q.values())<1e-7 for z in check for q in z['parity'].values())
S.to_csv(out/'E5_SINGLE_PRIOR_ALL.csv',index=False)
rows=[]
for (rt,bias,arm),g in S.groupby(['route','bias','arm']):
    rows.append({'route':rt,'bias':bias,'arm':arm,'n_case':len(g),
        'heading_rmse_case_median_deg':float(g.heading_rmse_after_deg.median()),
        'mean_Dpsi_deg2_median':float(g.mean_Dpsi_deg2.median()),
        'q99_abs_case_median_deg':float(g.heading_q99_abs_deg.median()),
        'fraction_positive_Dpsi_median':float(g.fraction_Dpsi_positive.median()),
        'alpha_selected_fraction_median':float(g.fraction_alpha_positive.median())})
R=pd.DataFrame(rows)
R.to_csv(out/'E5_ROUTE_MEDIAN.csv',index=False)
(out/'E5_QA.json').write_text(json.dumps({'n_case':7,'full_coverage':True,
 'all_same_prior_GATE_RH':True,'baseline_parity':max(max(q.values()) for z in check for q in z['parity'].values()),
 'n_scores':len(S),'model_source':'Frozen P2 ladder 3 PWIDE',
 'oracle_Ds_only_diagnostic':True,'no_filter_recursion_per_candidate':True},indent=2))
print('E5 RESULTS\n'+R.round(4).to_string(index=False),flush=True)
print('E5_ALL_PASS',flush=True)
