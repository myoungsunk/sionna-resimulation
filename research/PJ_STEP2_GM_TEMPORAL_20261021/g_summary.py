#!/usr/bin/env python3
"""Aggregate Step 2 (Gauss-Markov consider/augment) with magnitudes for every metric."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd

IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
S = cat('*_G_SCORES.csv'); QA = cat('*_G_QA.csv'); TR = cat('*_G_TRAJ.csv.gz')
S.to_csv(OUT / 'G_SCORES.csv', index=False); QA.to_csv(OUT / 'G_QA.csv', index=False); TR.to_csv(OUT / 'G_TRAJ.csv.gz', index=False, compression='gzip')
assert S.case.nunique() == 7
key = ['case', 'bias', 'channel']
b = S[S.arm == 'BASE'].set_index(key)[['heading_rmse_deg', 'heading95', 'heading_nees', 'bias_rmse_dps', 'xy_rmse_m']].add_suffix('_b')
S = S.join(b, on=key); S['rmse_ratio'] = S.heading_rmse_deg / S.heading_rmse_deg_b
S['aln'] = np.abs(np.log(S.heading_nees)); S['aln_b'] = np.abs(np.log(S.heading_nees_b))
rows = []
for arm, g in S.groupby('arm', sort=False):
    f = g[g.channel == 'full']; l = g[g.channel == 'los']; l2 = f[f.bias == 'L2']
    r = {'arm': arm, 'full_median_nees': f.heading_nees.median(), 'full_median_h95': f.heading95.median(), 'nees_closer': int((f.aln < f.aln_b).sum()),
         'median_rmse_ratio': f.rmse_ratio.median(), 'rmse_better': int((f.rmse_ratio < 1).sum()), 'rmse_worse_gt10pct': int((f.rmse_ratio > 1.1).sum()),
         'worst_rmse_ratio': f.rmse_ratio.max(), 'best_rmse_ratio': f.rmse_ratio.min(),
         'L2_bias_ratio_median': float((l2.bias_rmse_dps / l2.bias_rmse_dps_b).median()), 'xy_ratio_median': float((f.xy_rmse_m / f.xy_rmse_m_b).median()),
         'los_median_rmse_ratio': l.rmse_ratio.median(), 'los_le_1.10': int((l.rmse_ratio <= 1.10).sum()), 'los_median_h95': l.heading95.median()}
    if 'beta_s_corr_with_us_LF' in g and g.beta_s_corr_with_us_LF.notna().any():
        r['beta_s_corr_median_full'] = f.beta_s_corr_with_us_LF.median(); r['beta_s_post_prior_var_median'] = f.beta_s_post_prior_var.median()
        r['us_LF_rms_median'] = f.us_LF_rms.median(); r['us_LF_minus_beta_rms_median'] = f.us_LF_minus_beta_rms.median()
    rows.append(r)
A = pd.DataFrame(rows).set_index('arm'); A.to_csv(OUT / 'ARM_SUMMARY.csv')
J = {'QA_reproduction_pass': bool((QA.d_rmse < 1e-9).all()), 'QA_max_d_rmse': float(QA.d_rmse.max()), 'arm_summary': A.round(4).to_dict('index')}
(OUT / 'JUDGEMENT.json').write_text(json.dumps(J, indent=2, default=str))
cols = ['case', 'bias', 'channel', 'arm', 'heading_rmse_deg', 'heading_rmse_deg_b', 'rmse_ratio', 'heading95', 'heading95_b', 'heading_nees', 'heading_nees_b', 'bias_rmse_dps', 'bias_rmse_dps_b']
extra = [c for c in ['beta_s_corr_with_us_LF', 'beta_s_post_prior_var', 'beta_r_corr_with_ur_LF', 'beta_r_post_prior_var'] if c in S]
md = ['# Step 2 Gauss-Markov (machine summary)', '', '```json', json.dumps(J, indent=2, default=str), '```', '', '## Arm summary', A.round(3).to_markdown(), '',
      '## Per case', S[S.arm != 'BASE'][cols + extra].round(3).to_markdown(index=False)]
(OUT / 'RESULTS.md').write_text('\n'.join(md) + '\n')
print('::notice title=G::' + json.dumps({k: J[k] for k in ['QA_reproduction_pass', 'QA_max_d_rmse']}))
print('G_SUMMARY_DONE', flush=True)
