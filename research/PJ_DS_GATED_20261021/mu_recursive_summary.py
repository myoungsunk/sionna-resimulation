#!/usr/bin/env python3
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True); PREV = Path(os.environ['PJ_PREV'])
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
S, M, SE = cat('*_MR_SCORES.csv'), cat('*_MR_MEAS.csv'), cat('*_MR_SERIES.csv.gz')
S.to_csv(OUT / 'MR_SCORES.csv', index=False); M.to_csv(OUT / 'MR_MEAS.csv', index=False); SE.to_csv(OUT / 'MR_SERIES.csv.gz', index=False, compression='gzip')
P = pd.read_csv(PREV / 'TP_SCORES.csv'); mm = S[S.channel == 'full'].merge(P, on=['case', 'bias', 'arm'], suffixes=['', '_prev'])
qa = {'matched': len(mm), 'max_abs_d_heading_vs_prev': float((mm.heading_rmse_deg - mm.heading_rmse_deg_prev).abs().max())}
key = ['case', 'bias', 'channel']; rows = []
for ref in ['BASE', 'INFL_R']:
    b = S[S.arm == ref].set_index(key); mb = M[M.arm == ref].set_index(key)
    for arm, g in S.groupby('arm', sort=False):
        for chn in ['full', 'los']:
            gg = g[g.channel == chn].set_index(key); h = gg.heading_rmse_deg / b.heading_rmse_deg.reindex(gg.index); r = gg.range_err_rmse_cm / b.range_err_rmse_cm.reindex(gg.index)
            rd = gg.radial_rmse_cm / b.radial_rmse_cm.reindex(gg.index); mg = M[(M.arm == arm) & (M.channel == chn)].set_index(key)
            rows.append({'ref': ref, 'arm': arm, 'channel': chn, 'heading_med': h.median(), 'h_better': int((h < 1).sum()), 'h_worse10': int((h > 1.1).sum()), 'h_worst': h.max(),
                         'range_med': r.median(), 'r_better': int((r < 1).sum()), 'r_worse10': int((r > 1.1).sum()), 'r_worst': r.max(), 'radial_med': rd.median(), 'nees_med': gg.heading_nees.median(),
                         'meas_r_ratio_med': (mg.meas_r_rms_cm / mb.meas_r_rms_cm.reindex(mg.index)).median(), 'meas_s_ratio_med': (mg.meas_s_rms / mb.meas_s_rms.reindex(mg.index)).median()})
A = pd.DataFrame(rows); A.to_csv(OUT / 'MR_SUMMARY.csv', index=False)
(OUT / 'MR_QA.json').write_text(json.dumps(qa, indent=2))
(OUT / 'MR_RESULTS.md').write_text('# Measurement-to-recursive check\n\n```json\n' + json.dumps(qa, indent=2) + '\n```\n\n' + A.round(3).to_markdown(index=False) + '\n')
print('::notice title=MR::' + json.dumps(qa)); print('MR_SUMMARY_DONE')
