#!/usr/bin/env python3
"""d0 rejection rules: false rejection by window, and heading RMSE / NEES(1D) / 95% coverage vs no-rejection (same eta)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

import os, glob
R = Path(__file__).resolve().parent / 'results_d0reject'; R.mkdir(exist_ok=True)
SRC = os.environ.get('PJ_REJ_IN')
if SRC:
    metas = [json.load(open(f)) for f in sorted(glob.glob(SRC + '/**/*_REJ_META.json', recursive=True))]; json.dump(metas, open(R / 'REJ_META.json', 'w'), indent=2)
    FILES = sorted(glob.glob(SRC + '/**/*_REJ.csv.gz', recursive=True))
else:
    metas = json.load(open(R / 'REJ_META.json')); FILES = [str(R / 'REJ.csv.gz')]
META = {m['case']: m for m in metas}
RULES = ['NONE', 'RJ_D0', 'RJ_STATE', 'RJ_SHAPE', 'RJ_ORACLE']; ETAS = ['1', '3']
rows = []
for fpath in FILES:
  E = pd.read_csv(fpath)
  E['win'] = pd.cut(E.t_s, [-1e-9, 2, 10, 30, 1e9], right=False, labels=['0-2s', '2-10s', '10-30s', '>=30s'])
  E['fam'] = E.init.str.replace(r'E[+-]', 'E', regex=True)
  E['q95'] = E.case.map({c: m['q95_es_train'] for c, m in META.items()})
  for (c, ch, bias, init), g in E.groupby(['case', 'channel', 'bias', 'init']):
      clean = (g.e_s.abs() < 0.5 * g.q95) if ch == 'full' else pd.Series(True, index=g.index); mp = (g.e_s.abs() >= g.q95) if ch == 'full' else pd.Series(False, index=g.index)
      for e in ETAS:
          for r in RULES:
              he = g[f'{r}_e{e}__herr']; hs = g[f'{r}_e{e}__hsig']; fl = g[f'{r}_e{e}__flag'].astype(bool)
              row = {'case': c, 'channel': ch, 'bias': bias, 'init': init, 'fam': g.fam.iloc[0], 'eta': e, 'rule': r}
              for w, gw in g.groupby('win', observed=True):
                  ix = gw.index
                  row[f'rmse_{w}'] = float(np.sqrt(np.mean(he[ix] ** 2))); row[f'nees_{w}'] = float(np.mean(he[ix] ** 2 / hs[ix] ** 2)); row[f'cov_{w}'] = float(np.mean(he[ix] ** 2 / hs[ix] ** 2 <= 3.841))
                  row[f'FR_{w}'] = float(fl[ix][clean[ix]].mean()) if clean[ix].any() else np.nan; row[f'TPR_{w}'] = float(fl[ix][mp[ix]].mean()) if mp[ix].any() else np.nan
                  row[f'rej_{w}'] = float(fl[ix].mean())
              rows.append(row)
A = pd.DataFrame(rows); A.to_csv(R / 'RJ_CASES.csv', index=False)
key = ['case', 'channel', 'bias', 'init', 'eta']; base = A[A.rule == 'NONE'].set_index(key); base1 = A[(A.rule == 'NONE') & (A.eta == '1')].set_index(['case', 'channel', 'bias', 'init'])
out = []
for (fam, ch, e, r), g in A.groupby(['fam', 'channel', 'eta', 'rule']):
    gg = g.set_index(key); bb = base.loc[gg.index]; b1 = base1.loc[[k[:4] for k in gg.index]]
    row = {'fam': fam, 'channel': ch, 'eta': e, 'rule': r, 'n': len(gg)}
    for w in ['0-2s', '2-10s', '10-30s', '>=30s']:
        rr = gg[f'rmse_{w}'].to_numpy() / bb[f'rmse_{w}'].to_numpy(); r1 = gg[f'rmse_{w}'].to_numpy() / b1[f'rmse_{w}'].to_numpy()
        row[f'rmse_vs_same_eta_{w}'] = float(np.median(rr)); row[f'rmse_vs_base1_{w}'] = float(np.median(r1)); row[f'worse10_vs_base1_{w}'] = int((r1 > 1.1).sum())
        row[f'nees_{w}'] = float(gg[f'nees_{w}'].median()); row[f'cov_{w}'] = float(gg[f'cov_{w}'].median())
        row[f'FR_{w}'] = float(gg[f'FR_{w}'].median()); row[f'TPR_{w}'] = float(gg[f'TPR_{w}'].median()); row[f'rej_{w}'] = float(gg[f'rej_{w}'].median())
    out.append(row)
SM = pd.DataFrame(out); SM.to_csv(R / 'RJ_SUMMARY.csv', index=False)
pd.set_option('display.width', 300); pd.set_option('display.max_columns', 80)
for w in ['0-2s', '2-10s', '>=30s']:
    print('=== window', w)
    print(SM[SM.channel == 'full'][['fam', 'eta', 'rule', f'rmse_vs_base1_{w}', f'worse10_vs_base1_{w}', f'nees_{w}', f'cov_{w}', f'FR_{w}', f'TPR_{w}', f'rej_{w}']].round(3).to_string())
print('=== LoS >=30s and 0-2s'); print(SM[SM.channel == 'los'][['fam', 'eta', 'rule', 'rmse_vs_base1_0-2s', 'FR_0-2s', 'rmse_vs_base1_>=30s', 'cov_>=30s', 'FR_>=30s']].round(3).to_string())
