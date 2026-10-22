#!/usr/bin/env python3
"""Window-wise d0 detection (passive BASE prior) and effect of active range-only rejection, by initial heading error condition."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

R = Path(__file__).resolve().parent / 'results_d0early'
E = pd.read_csv(R / 'EARLY.csv.gz'); META = {m['held']: m for m in json.load(open(R / 'EARLY_META.json'))}
E['q50'] = E.route.map(lambda r: META[r]['es_thresholds_from_train_routes']['q50']); E['q90'] = E.route.map(lambda r: META[r]['es_thresholds_from_train_routes']['q90'])
E['q95'] = E.route.map(lambda r: META[r]['es_thresholds_from_train_routes']['q95']); E['tau5'] = E.route.map(lambda r: META[r]['tau5_d0'])
E['win'] = pd.cut(E.t_s, [-1e-9, 2, 10, 30, 1e9], right=False, labels=['0-2s', '2-10s', '10-30s', '>=30s'])
E['fam'] = E.init.str.replace(r'E[+-]', 'E', regex=True)            # pool +/- sign: NOM, E10_P5, E10_PM, E20_P5, E20_PM
E['abs_d0'] = E['BASE__d0'].abs(); E['norm'] = E['BASE__d0'] ** 2 / (E['BASE__hph'] + E['Vs'])
E['state_part'] = E['BASE__d0'] - E['e_s']
rows = []
for (fam, ch, bias, win), g in E.groupby(['fam', 'channel', 'bias', 'win'], observed=True):
    r = {'fam': fam, 'channel': ch, 'bias': bias, 'win': win, 'n': len(g), 'state_part_rms': float(np.sqrt(np.mean(g.state_part ** 2))),
         'base_abs_herr_med_deg': float(g['BASE__herr'].abs().median()), 'base_hsig_med_deg': float(g['BASE__hsig'].median())}
    clean = g.e_s.abs() < g.q50 if ch == 'full' else pd.Series(True, index=g.index)
    r['FR_d0'] = float((g.abs_d0 > g.tau5)[clean].mean()); r['FR_norm'] = float((g.norm > 3.841)[clean].mean()); r['flag_rate_d0'] = float((g.abs_d0 > g.tau5).mean())
    if ch == 'full':
        for lab in ['q90', 'q95']:
            y = (g.e_s.abs() >= g[lab]).to_numpy()
            if 0 < y.sum() < len(y):
                r[f'AUC_d0_{lab}'] = roc_auc_score(y, g.abs_d0); r[f'AUC_norm_{lab}'] = roc_auc_score(y, g.norm)
                au = [roc_auc_score(y[(g.case == c).to_numpy()], g.abs_d0[g.case == c]) for c in g.case.unique() if 0 < y[(g.case == c).to_numpy()].sum() < (g.case == c).sum()]
                r[f'AUC_d0_{lab}_casemed'] = float(np.median(au)) if au else np.nan; r[f'AUC_d0_{lab}_casemin'] = float(np.min(au)) if au else np.nan
                r[f'TPR_d0_{lab}'] = float((g.abs_d0 > g.tau5)[y].mean()); r[f'TPR_norm_{lab}'] = float((g.norm > 3.841)[y].mean())
        r['state_dominated_flags'] = float(((g.state_part.abs() > g.e_s.abs()) & (g.abs_d0 > g.tau5)).sum() / max((g.abs_d0 > g.tau5).sum(), 1))
    rows.append(r)
W = pd.DataFrame(rows); W.to_csv(R / 'EA_WINDOWS.csv', index=False)
# active arms: heading RMSE/coverage per window and convergence
act = []
for (c, ch, bias, init), g in E.groupby(['case', 'channel', 'bias', 'init']):
    for arm in ['BASE', 'RONLY_D0', 'RONLY_NORM']:
        he = g[f'{arm}__herr'].to_numpy(); hs = g[f'{arm}__hsig'].to_numpy(); t = g.t_s.to_numpy()
        ok = np.abs(he) < 2.0; tc = np.nan
        for i in range(len(t)):
            if ok[i:].all() if t[-1] - t[i] < 10 else ok[i:i + int(np.searchsorted(t[i:], t[i] + 10))].all():
                tc = t[i]; break
        r = {'case': c, 'channel': ch, 'bias': bias, 'init': init, 'fam': g.fam.iloc[0], 'arm': arm, 't_conv_s': tc, 'frac_pol_rejected': float(g[f'{arm}__flag'].mean())}
        for w, gw in g.groupby('win', observed=True):
            m = gw.index; hw = gw[f'{arm}__herr']; sw = gw[f'{arm}__hsig']
            r[f'rmse_{w}'] = float(np.sqrt(np.mean(hw ** 2))); r[f'cov_{w}'] = float(np.mean(hw ** 2 / sw ** 2 <= 3.841)); r[f'rej_{w}'] = float(gw[f'{arm}__flag'].mean())
        act.append(r)
A = pd.DataFrame(act); A.to_csv(R / 'EA_ACTIVE.csv', index=False)
key = ['case', 'channel', 'bias', 'init']; b = A[A.arm == 'BASE'].set_index(key); sm = []
for (fam, arm), g in A.groupby(['fam', 'arm']):
    for ch in ['full', 'los']:
        gg = g[g.channel == ch].set_index(key); bb = b.loc[gg.index]; r = {'fam': fam, 'arm': arm, 'channel': ch, 'n': len(gg)}
        for w in ['0-2s', '2-10s', '10-30s', '>=30s']:
            r[f'rmse_ratio_{w}'] = float((gg[f'rmse_{w}'] / bb[f'rmse_{w}']).median()); r[f'cov_{w}'] = float(gg[f'cov_{w}'].median()); r[f'rej_{w}'] = float(gg[f'rej_{w}'].median())
        r['t_conv_med'] = float(gg.t_conv_s.median()); r['t_conv_nan'] = int(gg.t_conv_s.isna().sum()); r['worse10_>=30s'] = int(((gg['rmse_>=30s'] / bb['rmse_>=30s']) > 1.1).sum())
        sm.append(r)
SM = pd.DataFrame(sm); SM.to_csv(R / 'EA_ACTIVE_SUMMARY.csv', index=False)
pd.set_option('display.width', 260); pd.set_option('display.max_columns', 60)
print(W[W.channel == 'full'].round(3).to_string()); print(W[W.channel == 'los'][['fam', 'win', 'FR_d0', 'FR_norm', 'state_part_rms']].round(3).to_string())
print(SM.round(3).to_string())
