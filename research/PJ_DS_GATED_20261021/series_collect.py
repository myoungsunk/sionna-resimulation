#!/usr/bin/env python3
"""Collect per-case series and QA against the trade-off run (heading RMSE reproduction)."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
PREV = Path(os.environ['PJ_PREV'])
S = pd.concat([pd.read_csv(p) for p in sorted(IN.rglob('*_SERIES.csv.gz'))], ignore_index=True)
S.to_csv(OUT / 'ALL_SERIES.csv.gz', index=False, compression='gzip')
P = pd.read_csv(PREV / 'TP_SCORES.csv'); qa = []
for (c, b), g in S.groupby(['case', 'bias']):
    m = g.t_s >= 30
    for arm in ['BASE', 'INFL_R', 'DEFL_S', 'MIX_IR_DS']:
        r = float(np.sqrt(np.mean(g.loc[m, f'{arm}__herr_deg'] ** 2)))
        ref = float(P[(P.case == c) & (P.bias == b) & (P.arm == arm)].heading_rmse_deg.iloc[0])
        qa.append({'case': c, 'bias': b, 'arm': arm, 'heading_rmse': r, 'prev': ref, 'abs_diff': abs(r - ref)})
Q = pd.DataFrame(qa); Q.to_csv(OUT / 'SERIES_QA.csv', index=False)
J = {'rows': len(S), 'max_abs_diff_heading_rmse_vs_tradeoff': float(Q.abs_diff.max())}
(OUT / 'SERIES_QA.json').write_text(json.dumps(J, indent=2)); print('::notice title=SERIES::' + json.dumps(J)); print('SERIES_SUMMARY_DONE')
