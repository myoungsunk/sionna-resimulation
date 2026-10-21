#!/usr/bin/env python3
"""Aggregate trade-off path analysis."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd

IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
PREV = Path(os.environ['PJ_PREV'])
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
A, G, S, Q = cat('*_TP_ATTR.csv'), cat('*_TP_GAIN.csv'), cat('*_TP_SCORES.csv'), cat('*_TP_QA.csv')
for nm, df in [('TP_ATTR', A), ('TP_GAIN', G), ('TP_SCORES', S), ('TP_QA', Q)]:
    df.to_csv(OUT / f'{nm}.csv', index=False)
key = ['case', 'bias']
# QA: reproduce previous run
P = pd.read_csv(PREV / 'V_SCORES.csv'); P = P[P.channel == 'full']
mm = S.merge(P, on=['case', 'bias', 'arm'], suffixes=['', '_prev'])
qa = {'n_matched_rows': len(mm), 'max_abs_d_heading_rmse_vs_prev': float((mm.heading_rmse_deg - mm.heading_rmse_deg_prev).abs().max()),
      'max_abs_d_range_rmse_vs_prev': float((mm.range_err_rmse_cm - mm.range_err_rmse_cm_prev).abs().max()), 'max_decomp_closure': float(Q.decomp_closure.max())}
# scores incl. MIX
b = S[S.arm == 'BASE'].set_index(key)
S2 = S.join(b[['heading_rmse_deg', 'range_err_rmse_cm', 'radial_rmse_cm', 'tangential_rmse_cm']].add_suffix('_b'), on=key)
S2['h'] = S2.heading_rmse_deg / S2.heading_rmse_deg_b; S2['r'] = S2.range_err_rmse_cm / S2.range_err_rmse_cm_b
summ = []
for arm, g in S2.groupby('arm', sort=False):
    summ.append({'arm': arm, 'heading_ratio_med': g.h.median(), 'h_better': int((g.h < 1).sum()), 'h_worse10': int((g.h > 1.1).sum()), 'h_worst': g.h.max(),
                 'range_ratio_med': g.r.median(), 'r_better': int((g.r < 1).sum()), 'r_worse10': int((g.r > 1.1).sum()), 'r_worst': g.r.max(),
                 'both_better': int(((g.h < 1) & (g.r < 1)).sum()), 'radial_ratio_med': (g.radial_rmse_cm / g.radial_rmse_cm_b).median(),
                 'tangential_ratio_med': (g.tangential_rmse_cm / g.tangential_rmse_cm_b).median(), 'median_nees': g.heading_nees.median(), 'median_h95': g.heading95.median()})
SUM = pd.DataFrame(summ); SUM.to_csv(OUT / 'TP_ARM_SUMMARY.csv', index=False)
S2[['case', 'bias', 'arm', 'h', 'r', 'heading_rmse_deg', 'range_err_rmse_cm', 'radial_rmse_cm', 'tangential_rmse_cm']].to_csv(OUT / 'TP_PER_CASE_RATIOS.csv', index=False)
# path attribution: delta contribution vs BASE, normalized by BASE total MSE of that quantity
base = A[A.arm == 'BASE'].set_index(['case', 'bias', 'split', 'quantity', 'component']).contrib
tot_b = A[(A.arm == 'BASE') & (A.component == 'TOTAL')].set_index(['case', 'bias', 'split', 'quantity']).contrib
A2 = A[A.arm != 'BASE'].copy()
A2['d_contrib'] = A2.contrib.to_numpy() - base.reindex(pd.MultiIndex.from_frame(A2[['case', 'bias', 'split', 'quantity', 'component']])).to_numpy()
A2['d_norm'] = A2.d_contrib.to_numpy() / tot_b.reindex(pd.MultiIndex.from_frame(A2[['case', 'bias', 'split', 'quantity']])).to_numpy()
A2.to_csv(OUT / 'TP_DELTA_ATTR.csv', index=False)
path = A2.groupby(['arm', 'split', 'quantity', 'component']).d_norm.agg(['median', 'mean', lambda v: int((v < 0).sum())]).rename(columns={'<lambda_0>': 'n_reduced'}).reset_index()
path.to_csv(OUT / 'TP_PATH_SUMMARY.csv', index=False)
# gains
gb = G[G.arm == 'BASE'].set_index(key)
gcols = [c for c in G.columns if c not in ('case', 'bias', 'arm')]
GR = []
for arm, g in G.groupby('arm', sort=False):
    gg = g.set_index(key)
    r = {'arm': arm}
    for c in gcols:
        r[c + '_med'] = float(gg[c].median())
        if c != 'prior_rho_rad_psi': r[c + '_ratio_med'] = float((gg[c] / gb[c].reindex(gg.index)).median())
    GR.append(r)
GR = pd.DataFrame(GR); GR.to_csv(OUT / 'TP_GAIN_SUMMARY.csv', index=False)
J = {'QA': qa}
(OUT / 'TP_JUDGEMENT.json').write_text(json.dumps(J, indent=2))
md = ['# Trade-off path (machine summary)', '```json\n' + json.dumps(J, indent=2) + '\n```', SUM.round(3).to_markdown(index=False),
      path[path.split == 'gate'].round(3).to_markdown(index=False), path[path.split == 'time'].round(3).to_markdown(index=False), GR.round(3).T.to_markdown()]
(OUT / 'TP_RESULTS.md').write_text('\n\n'.join(md) + '\n')
print('::notice title=TP::' + json.dumps(qa)); print('TP_SUMMARY_DONE')
