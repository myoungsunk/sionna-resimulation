#!/usr/bin/env python3
"""Aggregate method A (delta-s conditioned mu_s) with magnitudes for every metric."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd

IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
S = cat('*_MA_SCORES.csv'); QA = cat('*_MA_QA.csv'); MEAS = cat('*_MA_MEAS.csv')
S.to_csv(OUT / 'MA_SCORES.csv', index=False); QA.to_csv(OUT / 'MA_QA.csv', index=False); MEAS.to_csv(OUT / 'MA_MEAS.csv', index=False)
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
    mf = MEAS[(MEAS.arm == arm) & (MEAS.channel == 'full')]; ml = MEAS[(MEAS.arm == arm) & (MEAS.channel == 'los')]
    r.update({'meas_R2_pose_median': mf.R2_nc_pose.median(), 'meas_R2_pose_min': mf.R2_nc_pose.min(), 'meas_R2_LF_median': mf.R2_nc_LF.median(), 'meas_R2_LF_min': mf.R2_nc_LF.min(),
              's95_packet_median': mf.s95_packet.median(), 'mean_Vs_median': mf.mean_Vs.median(), 'los_resid_rms_median': ml.rms_resid.median()})
    rows.append(r)
A = pd.DataFrame(rows).set_index('arm'); A.to_csv(OUT / 'ARM_SUMMARY.csv')
J = {'QA_reproduction_pass': bool((QA.d_rmse < 1e-9).all()), 'QA_max_d_rmse': float(QA.d_rmse.max()), 'arm_summary': A.round(4).to_dict('index')}
(OUT / 'JUDGEMENT.json').write_text(json.dumps(J, indent=2, default=str))
cols = ['case', 'bias', 'channel', 'arm', 'heading_rmse_deg', 'heading_rmse_deg_b', 'rmse_ratio', 'heading95', 'heading95_b', 'heading_nees', 'heading_nees_b', 'bias_rmse_dps', 'bias_rmse_dps_b']
extra = []
md = ['# Method A (machine summary)', '', '```json', json.dumps(J, indent=2, default=str), '```', '', '## Arm summary', A.round(3).to_markdown(), '',
      '## Per case', S[S.arm != 'BASE'][cols + extra].round(3).to_markdown(index=False), '', '## Measurement', MEAS.round(3).to_markdown(index=False)]
(OUT / 'RESULTS.md').write_text('\n'.join(md) + '\n')
print('::notice title=MA::' + json.dumps({k: J[k] for k in ['QA_reproduction_pass', 'QA_max_d_rmse']}))
print('MA_SUMMARY_DONE', flush=True)
