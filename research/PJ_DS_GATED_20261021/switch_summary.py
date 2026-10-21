#!/usr/bin/env python3
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True); PREV = Path(os.environ['PJ_PREV'])
S = pd.concat([pd.read_csv(p) for p in sorted(IN.rglob('*_SW_SCORES.csv'))], ignore_index=True); S.to_csv(OUT / 'SW_SCORES.csv', index=False)
P = pd.read_csv(PREV / 'TP_SCORES.csv'); mm = S.merge(P, on=['case', 'bias', 'arm'], suffixes=['', '_prev'])
qa = {'matched': len(mm), 'max_abs_d_heading_vs_tradeoff': float((mm.heading_rmse_deg - mm.heading_rmse_deg_prev).abs().max())}
key = ['case', 'bias']; rows = []
for ref in ['BASE', 'INFL_R']:
    b = S[S.arm == ref].set_index(key)
    for arm, g in S.groupby('arm', sort=False):
        g = g.set_index(key); h = g.heading_rmse_deg / b.heading_rmse_deg; r = g.range_err_rmse_cm / b.range_err_rmse_cm; rd = g.radial_rmse_cm / b.radial_rmse_cm
        rows.append({'ref': ref, 'arm': arm, 'switch_on_frac_med': g.switch_on_frac.median(), 'heading_med': h.median(), 'h_better': int((h < 1).sum()), 'h_worse10': int((h > 1.1).sum()), 'h_worst': h.max(),
                     'range_med': r.median(), 'r_better': int((r < 1).sum()), 'r_worse10': int((r > 1.1).sum()), 'radial_med': rd.median(), 'nees_med': g.heading_nees.median(), 'h95_med': g.heading95.median()})
A = pd.DataFrame(rows); A.to_csv(OUT / 'SW_SUMMARY.csv', index=False)
(OUT / 'SW_QA.json').write_text(json.dumps(qa, indent=2))
(OUT / 'SW_RESULTS.md').write_text('# Switching replay\n\n```json\n' + json.dumps(qa, indent=2) + '\n```\n\n' + A.round(3).to_markdown(index=False) + '\n')
print('::notice title=SW::' + json.dumps(qa)); print('SW_SUMMARY_DONE')
