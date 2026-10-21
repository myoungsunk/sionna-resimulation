#!/usr/bin/env python3
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
S, QA, M = cat('*_V_SCORES.csv'), cat('*_V_QA.csv'), cat('*_V_MEAS.csv')
CAL = {p.name.split('_V_')[0]: json.loads(p.read_text()) for p in sorted(IN.rglob('*_V_CALIB.json'))}
S.to_csv(OUT / 'V_SCORES.csv', index=False); QA.to_csv(OUT / 'V_QA.csv', index=False); M.to_csv(OUT / 'V_MEAS.csv', index=False)
(OUT / 'V_CALIB.json').write_text(json.dumps(CAL, indent=2))
key = ['case', 'bias', 'channel']
b = S[S.arm == 'BASE'].set_index(key)[['heading_rmse_deg', 'heading_nees', 'bias_rmse_dps', 'xy_rmse_m']].add_suffix('_b')
S = S.join(b, on=key); S['r'] = S.heading_rmse_deg / S.heading_rmse_deg_b
rows = []
for arm, g in S.groupby('arm', sort=False):
    f = g[g.channel == 'full']; l = g[g.channel == 'los']; l2 = f[f.bias == 'L2']
    rows.append({'arm': arm, 'median_rmse_ratio': f.r.median(), 'better': int((f.r < 1).sum()), 'worse_gt10pct': int((f.r > 1.1).sum()), 'worst': f.r.max(), 'best': f.r.min(),
                 'median_nees': f.heading_nees.median(), 'median_h95': f.heading95.median(), 'nees_closer': int((np.abs(np.log(f.heading_nees)) < np.abs(np.log(f.heading_nees_b))).sum()),
                 'xy_ratio_median': (f.xy_rmse_m / f.xy_rmse_m_b).median(), 'xy_better': int((f.xy_rmse_m < f.xy_rmse_m_b).sum()),
                 'L2_bias_ratio_median': (l2.bias_rmse_dps / l2.bias_rmse_dps_b).median(), 'los_median_rmse_ratio': l.r.median()})
A = pd.DataFrame(rows).set_index('arm'); A.to_csv(OUT / 'ARM_SUMMARY.csv')
if 'range_err_rmse_cm' in S:
    rb = S[S.arm == 'BASE'].set_index(key)[['range_err_rmse_cm', 'radial_rmse_cm', 'tangential_rmse_cm']].add_suffix('_b'); SR = S.join(rb, on=key)
    rr = []
    for arm, g in SR.groupby('arm', sort=False):
        for chn in ['full', 'los']:
            f = g[g.channel == chn]; q1 = f.range_err_rmse_cm / f.range_err_rmse_cm_b
            rr.append({'arm': arm, 'channel': chn, 'range_err_rmse_cm_median': f.range_err_rmse_cm.median(), 'range_ratio_median': q1.median(), 'range_better': int((q1 < 1).sum()),
                       'range_worse_gt10pct': int((q1 > 1.1).sum()), 'range_ratio_worst': q1.max(), 'range_ratio_best': q1.min(),
                       'radial_ratio_median': (f.radial_rmse_cm / f.radial_rmse_cm_b).median(), 'tangential_ratio_median': (f.tangential_rmse_cm / f.tangential_rmse_cm_b).median(),
                       'radial_rmse_cm_median': f.radial_rmse_cm.median(), 'tangential_rmse_cm_median': f.tangential_rmse_cm.median(), 'n': len(f)})
    pd.DataFrame(rr).to_csv(OUT / 'RANGING_SUMMARY.csv', index=False)
mm = M[M.channel == 'full'].groupby(['arm', 'subset'])[['s95', 'r95', 's_nees_pkt', 'r_nees_pkt']].median()
J = {'QA_pass': bool((QA.d_rmse < 1e-9).all()), 'QA_max': float(QA.d_rmse.max()), 'arm_summary': A.round(4).to_dict('index')}
(OUT / 'JUDGEMENT.json').write_text(json.dumps(J, indent=2))
cols = ['case', 'bias', 'channel', 'arm', 'heading_rmse_deg', 'heading_rmse_deg_b', 'r', 'heading95', 'heading_nees', 'xy_rmse_m', 'xy_rmse_m_b', 'bias_rmse_dps']
(OUT / 'RESULTS.md').write_text('\n\n'.join(['# Delta-s variance quick test', '```json\n' + json.dumps(J, indent=2) + '\n```', A.round(3).to_markdown(),
                                             mm.round(3).to_markdown(), S[S.arm != 'BASE'][cols].round(3).to_markdown(index=False)]) + '\n')
print('::notice title=V::' + json.dumps({'QA_pass': J['QA_pass']})); print('V_SUMMARY_DONE')
