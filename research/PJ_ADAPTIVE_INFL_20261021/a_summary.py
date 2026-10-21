#!/usr/bin/env python3
"""Aggregate adaptive inflation replay; report magnitudes for every metric plus diagnostics."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
D1 = Path(os.environ['PJ_D1_RESULTS']); MRES = Path(os.environ['PJ_M_RESULTS'])
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
S = cat('*_A_SCORES.csv'); QA = cat('*_A_QA.csv'); TR = cat('*_A_TRAJ.csv.gz')
S.to_csv(OUT / 'A_SCORES.csv', index=False); QA.to_csv(OUT / 'A_QA.csv', index=False)
TR.to_csv(OUT / 'A_TRAJ.csv.gz', index=False, compression='gzip')
assert S.case.nunique() == 7
key = ['case', 'bias', 'channel']
base = S[S.arm == 'FIX_1'].set_index(key)[['heading_rmse_deg', 'heading95', 'heading_nees', 'bias_rmse_dps']].add_suffix('_b')
med = S[S.arm == 'FIX_MED'].set_index(key)[['heading_rmse_deg', 'heading_nees']].add_suffix('_med')
S = S.join(base, on=key).join(med, on=key)
S['abs_ln_nees'] = np.abs(np.log(S.heading_nees)); S['abs_ln_nees_b'] = np.abs(np.log(S.heading_nees_b)); S['abs_ln_nees_med'] = np.abs(np.log(S.heading_nees_med))
S['rmse_ratio'] = S.heading_rmse_deg / S.heading_rmse_deg_b

rows = []
for arm, g in S.groupby('arm'):
    f = g[g.channel == 'full']; l = g[g.channel == 'los']; l2 = f[f.bias == 'L2']
    rows.append({'arm': arm, 'full_median_nees': f.heading_nees.median(), 'full_median_h95': f.heading95.median(),
                 'nees_closer_than_FIX1': int((f.abs_ln_nees < f.abs_ln_nees_b).sum()),
                 'median_rmse_ratio': f.rmse_ratio.median(), 'rmse_better': int((f.rmse_ratio < 1).sum()), 'rmse_worse_gt10pct': int((f.rmse_ratio > 1.1).sum()),
                 'worst_rmse_ratio': f.rmse_ratio.max(), 'L2_bias_ratio_median': float((l2.bias_rmse_dps / l2.bias_rmse_dps_b).median()),
                 'los_ok_le_1.10': int((l.rmse_ratio <= 1.10).sum()), 'los_median_rmse_ratio': l.rmse_ratio.median(), 'los_median_h95': l.heading95.median(),
                 'beats_FIX_MED': int(((f.abs_ln_nees < f.abs_ln_nees_med) & (f.heading_rmse_deg <= 1.05 * f.heading_rmse_deg_med)).sum()),
                 'eta_mean_median': f.eta_mean.median(), 'frac_at_cap_median': f.frac_at_cap.median()})
SUMM = pd.DataFrame(rows).set_index('arm'); SUMM.to_csv(OUT / 'ARM_SUMMARY.csv')

# D-F feedback curve (open-loop statistic in fixed arms)
fx = S[(S.arm.isin(['FIX_1', 'FIX_2', 'FIX_3', 'FIX_4', 'FIX_6', 'FIX_8'])) & (S.channel == 'full')].copy()
fx['eta_fixed'] = fx.arm.str[4:].astype(float)
slopes = []
for (c, b), g in fx.groupby(['case', 'bias']):
    g = g.sort_values('eta_fixed')
    sl = np.polyfit(g.eta_fixed, g.openloop_eta_raw_rs_mean, 1)[0]
    lsl = np.polyfit(np.log(g.eta_fixed), np.log(g.openloop_eta_raw_rs_mean.clip(lower=1e-6)), 1)[0]
    slopes.append({'case': c, 'bias': b, 'slope': sl, 'loglog_slope': lsl, **{f'raw_at_{int(e)}': v for e, v in zip(g.eta_fixed, g.openloop_eta_raw_rs_mean)}})
DF = pd.DataFrame(slopes); DF.to_csv(OUT / 'DIAG_FEEDBACK_CURVE.csv', index=False)

# D-V estimator validity vs D1 ACT/SHUF
d1 = pd.read_csv(D1 / 'D1_SURROGATE.csv'); d1 = d1[(d1.channel == 'full') & (d1.bias == 'B0') & (d1.model == 'POWER_DIAG')].pivot_table(index='case', columns='kind', values='nees_u_mean')
d1r = (d1.ACTUAL / d1.SHUFFLE).rename('d1_act_shuf')
f1 = S[(S.arm == 'FIX_1') & (S.channel == 'full') & (S.bias == 'B0')].set_index('case').openloop_eta_raw_rs_mean
DV = pd.concat([d1r, f1.rename('online_raw_at_eta1')], axis=1); DV.to_csv(OUT / 'DIAG_ESTIMATOR_VALIDITY.csv')
dv_rho = float(spearmanr(DV.d1_act_shuf, DV.online_raw_at_eta1).statistic)

# D-T trajectories vs per-case "NEES~1" fixed eta from previous 92-arm grid (descriptive)
M = pd.read_csv(MRES / 'M_SCORES.csv'); M = M[(M.family == 'COMMON') & (M.kappa == 1.0)].copy(); M['a'] = np.abs(np.log(M.heading_nees))
orc = M.loc[M.groupby(key).a.idxmin()].set_index(key).eta_s.rename('eta_nees1_grid')
DT = S[S.arm.str.startswith('ADAPT')].pivot_table(index=key, columns='arm', values='eta_mean').join(orc)
DT.to_csv(OUT / 'DIAG_ETA_VS_GRID.csv')
dt_rho = {a: float(spearmanr(DT[a], DT.eta_nees1_grid).statistic) for a in DT.columns if a.startswith('ADAPT')}

J = {'QA_reproduction_pass': bool((QA.d_rmse < 1e-9).all()), 'QA_max_d_rmse': float(QA.d_rmse.max()),
     'arm_summary': SUMM.round(4).to_dict('index'),
     'D_F_median_slope': float(DF.slope.median()), 'D_F_median_loglog_slope': float(DF.loglog_slope.median()),
     'D_V_spearman_online_vs_D1': dv_rho, 'D_T_spearman_eta_mean_vs_grid_eta': dt_rho}
(OUT / 'JUDGEMENT.json').write_text(json.dumps(J, indent=2, default=str))
cols = ['case', 'bias', 'channel', 'arm', 'heading_rmse_deg', 'heading_rmse_deg_b', 'rmse_ratio', 'heading95', 'heading95_b', 'heading_nees', 'heading_nees_b',
        'bias_rmse_dps', 'bias_rmse_dps_b', 'eta_mean', 'eta_min', 'eta_max_reached', 'frac_at_cap', 'eta_max']
md = ['# Adaptive COMMON inflation (machine summary)', '', '```json', json.dumps(J, indent=2, default=str), '```', '',
      '## Arm summary', SUMM.round(3).to_markdown(), '', '## Per case (adaptive + FIX_MED + REF_POWER1)',
      S[S.arm.str.startswith('ADAPT') | S.arm.isin(['FIX_MED', 'REF_POWER1'])][cols].round(3).to_markdown(index=False),
      '', '## Feedback curve', DF.round(3).to_markdown(index=False), '', '## Estimator validity', DV.round(3).to_markdown(),
      '', '## Eta vs grid', DT.round(3).to_markdown()]
(OUT / 'RESULTS.md').write_text('\n'.join(md) + '\n')
print('::notice title=summary::' + json.dumps({k: J[k] for k in J if k != 'arm_summary'}, default=str)[:900])
print('A_SUMMARY_DONE', flush=True)
