#!/usr/bin/env python3
"""P2-A aggregate: store case-window metrics and never silently drop failed cases."""
from __future__ import annotations
import argparse, json, glob
from pathlib import Path
import numpy as np
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument('--input',required=True)
p.add_argument('--out',required=True)
p.add_argument('--mode',choices=['smoke','full'],required=True)
a=p.parse_args()
dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
files=sorted(Path(a.input).rglob('*_P2_SCORES.csv'))
expected=1 if a.mode=='smoke' else 7
assert len(files)==expected,(expected,[str(f) for f in files])
scores=pd.concat([pd.read_csv(f) for f in files],ignore_index=True)
required=['DR_ONLY','RANGE_ONLY','BASE_POWER','RAW_SHARED',
      'CIR_ONLY_SHARED','WIDE_SHARED','WIDE_CAL','NARROW_CAL','ORACLE_SHARED']
assert set(required)==set(scores.arm),sorted(set(scores.arm))
cases=sorted(scores.case.unique().tolist())
if a.mode=='full':
    assert len(cases)==7
    assert set(scores.route)=={'R2','R4','R5'}
    # All 3 conditions and all initial conditions for every case.
    assert set(scores.channel)=={'full','los'}
    for cm,grp in scores.groupby('case'):
        assert grp[(grp.bias=='B0')&(grp.channel=='full')].init.nunique()==9,cm
        assert grp[(grp.bias=='L2')&(grp.channel=='full')].init.nunique()==9,cm
        assert grp[(grp.bias=='B0')&(grp.channel=='los')].init.nunique()==9,cm
else:
    assert len(cases)==1
    assert set(scores.init)=={'NOM','E+10_P5','E-10_P5'}
scores.to_csv(dst/'P2_A_SCORES.csv',index=False)
notes=[]
for file in sorted(Path(a.input).rglob('*_P2_QA.json')):
    notes.append(json.loads(file.read_text()))
assert len(notes)==expected
assert all(q['baseline_parity'] and max(max(x.values()) for x in q['baseline_parity'].values())<1e-7 for q in notes)
K=['case','route','bias','channel','init']
b=scores[scores.arm=='BASE_POWER'].set_index(K)
c=scores[scores.arm=='CIR_ONLY_SHARED'].set_index(K)
wide=scores[scores.arm=='WIDE_SHARED'].set_index(K)
for arm,x in [('CIR_ONLY_SHARED',c),('WIDE_SHARED',wide)]:
    assert b.index.equals(x.index),arm
    z=x.copy()
    z['ratio_heading_base']=x['heading_rmse_deg']/b['heading_rmse_deg']
    z['ratio_xy_base']=x['xy_rmse_cm']/b['xy_rmse_cm']
    z['ratio_heading_CIR']=x['heading_rmse_deg']/c['heading_rmse_deg']
    z.reset_index().to_csv(dst/(arm+'_PAIRED.csv'),index=False)
# In smoke: do not claim route-level generalization or P2 success.
qa={'mode':a.mode,'n_case':len(cases),'cases':cases,'rows':len(scores),
    'baseline_parity_max':max(max(x.values()) for q in notes for x in q['baseline_parity'].values()),
    'all_cases_completed':True,'route_level_gate_available':a.mode=='full',
    'source':'P2_A_SCORES + raw per-step series artifacts'}
(dst/'P2_A_QA.json').write_text(json.dumps(qa,indent=2))
print('P2_AGGREGATE '+json.dumps(qa),flush=True)
if a.mode=='smoke':
    pv=scores.pivot_table(index=['bias','channel','init'],columns='arm',
         values=['heading_rmse_deg','heading_nees_1d','heading_cov95','xy_rmse_cm'])
    print('P2_SMOKE_METRICS\n'+pv.round(4).to_string())
