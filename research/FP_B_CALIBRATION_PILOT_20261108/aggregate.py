#!/usr/bin/env python3
"""Report fixed, preregistered route-held-out B-only calibration comparisons."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
ARMS=("NATIVE_FROZEN", "B_FROZEN", "B_BIAS", "B_COV", "B_BIAS_COV", "B_BIAS_FULLCOV")
ROUTES=("R2","R4","R5")

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    records=[json.loads((a.input/r/'RESULTS.json').read_text()) for r in ROUTES]
    for route,rec in zip(ROUTES,records):
        assert rec['status']=='PASS_IMPLEMENTER_SELF_CHECK' and rec['heldout']==route
        assert rec['n']=={'R2':979,'R4':742,'R5':1415}[route]
        assert route not in rec['training_routes'] and set(rec['training_routes'])==set(ROUTES)-{route}
        assert list(rec['score'])==list(ARMS)
    n=sum(r['n'] for r in records)
    assert n==3136
    pooled={}
    for arm in ARMS:
        out={}
        for key in ('heading_mse_deg2','xy_mse_m2','mean_nees3','pose95_coverage','xy95_coverage','heading95_coverage'):
            out[key]=sum(r['n']*r['score'][arm][key] for r in records)/n
        out['heading_rmse_deg']=math.sqrt(out['heading_mse_deg2']);out['xy_rmse_cm']=100*math.sqrt(out['xy_mse_m2'])
        out['accepted']=sum(r['score'][arm]['accepted'] for r in records)
        out['gate_flips_vs_B']=sum(r['score'][arm]['gate_flip_vs_B'] for r in records)
        pooled[arm]=out
    comparisons={}
    b=pooled['B_FROZEN'];nat=pooled['NATIVE_FROZEN']
    for arm in ARMS[2:]:
        x=pooled[arm]
        byroute={r['heldout']:dict(heading_rmse_deg=r['score'][arm]['heading_rmse_deg'],
                                  xy_rmse_cm=100*r['score'][arm]['xy_rmse_cm']/100,
                                  heading_improved=r['score'][arm]['heading_mse_deg2']<r['score']['B_FROZEN']['heading_mse_deg2'],
                                  xy_improved=r['score'][arm]['xy_mse_m2']<r['score']['B_FROZEN']['xy_mse_m2']) for r in records}
        comparisons[arm]=dict(vs_B_heading_delta_deg=x['heading_rmse_deg']-b['heading_rmse_deg'],
          vs_B_xy_delta_cm=x['xy_rmse_cm']-b['xy_rmse_cm'],
          vs_B_heading_reduction_pct=100*(1-x['heading_rmse_deg']/b['heading_rmse_deg']),
          vs_B_xy_reduction_pct=100*(1-x['xy_rmse_cm']/b['xy_rmse_cm']),
          vs_native_heading_delta_deg=x['heading_rmse_deg']-nat['heading_rmse_deg'],
          vs_native_xy_delta_cm=x['xy_rmse_cm']-nat['xy_rmse_cm'],
          B_beaten_on_both_pooled=x['heading_mse_deg2']<b['heading_mse_deg2'] and x['xy_mse_m2']<b['xy_mse_m2'],
          B_beaten_on_both_every_route=all(y['heading_improved'] and y['xy_improved'] for y in byroute.values()),
          by_route=byroute)
    summary=dict(status='PASS_AGGREGATE',n=n,split='leave-one-route-out',training_never_contains_heldout=True,
      source='original R2/R4/R5 B0 Full seed10 with verified SourceFFD',pooled=pooled,comparisons=comparisons,
      route_reports=[dict(heldout=r['heldout'],n=r['n'],train=r['training_routes'],score=r['score'],fit=r['fit']) for r in records],
      caveats=['shared corridor and seed10, not new-scene validation',
        'archived native calibration and R inherited, so native prior training may intersect holdout',
        'uncertainty and single trajectory autocorrelation prevent generalization claims',
        'no winner is selected via heldout tuning; all prespecified arms displayed'])
    (a.out/'RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    with (a.out/'METRICS.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['arm','heading_RMSE_deg','XY_RMSE_cm','NEES3','XY95','pose95','accepted','delta_heading_pct_vs_B','delta_XY_pct_vs_B'])
        for arm in ARMS:
            m=pooled[arm];c=comparisons.get(arm,{});w.writerow([arm,m['heading_rmse_deg'],m['xy_rmse_cm'],m['mean_nees3'],m['xy95_coverage'],m['pose95_coverage'],m['accepted'],c.get('vs_B_heading_reduction_pct',''),c.get('vs_B_xy_reduction_pct','')])
    md=['# Route-held-out B-only observation calibration — exploratory','',
        '3 route folds (R2/R4/R5), B0 Full seed10, 3136 time steps. No K1/K2.','',
        '## Global pooled metrics (RMS over all samples)','',
        '| Arm | Heading RMSE deg | XY RMSE cm | NEES3 | XY95 | Heading reduction vs B | XY reduction vs B |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for arm in ARMS:
        m=pooled[arm];c=comparisons.get(arm,{})
        md.append(f"| {arm} | {m['heading_rmse_deg']:.4f} | {m['xy_rmse_cm']:.3f} | {m['mean_nees3']:.3f} | {m['xy95_coverage']:.1%} | {c.get('vs_B_heading_reduction_pct',0):+.2f}% | {c.get('vs_B_xy_reduction_pct',0):+.2f}% |")
    md += ['','## Route-held-out performance','', '| Route | Arm | Heading RMSE deg | XY RMSE cm | NEES3 | XY95 |','|---|---|---:|---:|---:|---:|']
    for rec in records:
        for arm in ARMS:
            s=rec['score'][arm];md.append(f"| {rec['heldout']} | {arm} | {s['heading_rmse_deg']:.4f} | {s['xy_rmse_cm']:.3f} | {s['mean_nees3']:.3f} | {s['xy95_coverage']:.1%} |")
    md+=['','**Interpretation:** Cross-route predictions use a fit from the other two routes. Original mu/R remain frozen base; only a B-specific delta and conservative PSD variance addition are estimated. Shared scene/seed limits extrapolation; evaluation is exploratory.','',
         'HOLDOUT selection of the best arm is prohibited; review all proposed arms and sensitivity.']
    (a.out/'REPORT.md').write_text('\n'.join(md)+'\n')
    (a.out/'SHA256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.out.iterdir() if p.is_file() and p.name!='SHA256.json'},indent=2)+'\n')
    print('CALIB_AGGREGATE_PASS')
    print('\n'.join(md[:13]))

if __name__=='__main__':main()