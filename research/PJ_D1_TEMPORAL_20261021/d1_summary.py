#!/usr/bin/env python3
"""Aggregate D1 outputs and apply the preregistered judgements verbatim."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
cat = lambda key: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(f'*_D1_{key}.csv'))], ignore_index=True)
comp, sur, acf, sca, cov = (cat(k) for k in ['COMPONENTS', 'SURROGATE', 'ACF', 'SCALAR', 'COVATTR'])
qa = [q for p in sorted(IN.rglob('*_D1_QA.json')) for q in json.loads(p.read_text())]
assert len(qa) == 21, len(qa)
for name, df in [('COMPONENTS', comp), ('SURROGATE', sur), ('ACF', acf), ('SCALAR', sca), ('COVATTR', cov)]:
    df.to_csv(OUT / f'D1_{name}.csv', index=False)
(OUT / 'D1_QA.json').write_text(json.dumps(qa, indent=2))
qa_df = pd.DataFrame(qa)
fb = lambda d: d[(d.channel == 'full') & (d.bias == 'B0')]

# QA0 / QA1
qa0_fail = qa_df[~qa_df.QA0_pass][['case', 'bias', 'channel', 'reconstruct_max_dx', 'reconstruct_max_dP']]
lin = comp[comp.component == 'LIN'][['case', 'bias', 'channel', 'model', 'share_of_total_heading_rms']]
lin_flag = lin[lin.share_of_total_heading_rms > 0.30]
trace_mismatch = float(sca.heading95_trace_check_absdiff.max())

# H1
a = fb(acf[acf.whitened_channel == 's'])
h1 = {m: int((a[a.model == m].lag1_noncentred > 0.5).sum()) for m in ['POWER1', 'SEP_BIN']}
H1 = all(v >= 5 for v in h1.values())

# H2 / H2b
s = fb(sur).pivot_table(index=['case', 'model'], columns='kind', values='nees_u_mean')
cond = s.SHUFFLE.between(0.5, 2) & (s.ACTUAL > 3)
H2_n = int(cond.sum()); H2 = H2_n > len(s) / 2
ratio = (s.PHASE / s.ACTUAL)[cond]
n_spec = int(ratio.between(0.5, 2).sum()); n_det = int((ratio < 0.5).sum())
H2b = 'spectrum' if n_spec > len(ratio) / 2 else ('deterministic_alignment' if n_det > len(ratio) / 2 else 'mixed_or_undetermined')

# H3
c = fb(cov); r5 = c[(c.case == 'R5_aA_m0') & (c.model == 'SEP_BIN')].iloc[0]
H3_share = float(r5.sigma_effect / r5.total_change) if r5.total_change != 0 else float('nan')
H3 = bool(H3_share >= 0.7)

# H4
cc = fb(comp)
def mse(case, model, component):
    return float(cc[(cc.case == case) & (cc.model == model) & (cc.component == component)].heading_mse_deg2.iloc[0])
us = lambda m: mse('R2_aB_m0', m, 'U_S_LF') + mse('R2_aB_m0', m, 'U_S_HF')
tot = lambda m: float(fb(sca)[(fb(sca).case == 'R2_aB_m0') & (fb(sca).model == m)].heading_rmse_trace_deg.iloc[0]) ** 2
H4_share = (us('PWR_MU_SEP_COV') - us('POWER1')) / (tot('PWR_MU_SEP_COV') - tot('POWER1'))
H4 = bool(H4_share >= 0.5)

# auxiliary scalar formula
sc = fb(sca).set_index(['case', 'model'])
emp_gamma = (s.ACTUAL / s.SHUFFLE)
j = sc.join(emp_gamma.rename('emp_gamma'))
rho_aux = spearmanr(j.gamma_scalar, j.emp_gamma, nan_policy='omit')

judge = {'QA0_failed_conditions': qa0_fail.to_dict('records'), 'QA1_LIN_over_30pct_rows': len(lin_flag),
         'trace_heading95_max_absdiff': trace_mismatch,
         'H1_cases_lag1_gt_0.5': h1, 'H1_pass': H1,
         'H2_rows_meeting': H2_n, 'H2_rows_total': int(len(s)), 'H2_pass': H2,
         'H2b_rows_ratio_in_0.5_2': n_spec, 'H2b_rows_ratio_lt_0.5': n_det, 'H2b_verdict': H2b,
         'H3_sigma_effect_share': H3_share, 'H3_sigma_effect': float(r5.sigma_effect), 'H3_delta_effect': float(r5.delta_effect), 'H3_pass': H3,
         'H4_US_share_of_MSE_increase': float(H4_share), 'H4_pass': H4,
         'aux_spearman_gamma_scalar_vs_empirical': float(rho_aux.statistic)}
(OUT / 'D1_JUDGEMENT.json').write_text(json.dumps(judge, indent=2, default=str))

# compact table
arms = ['JOINT4', 'POWER1', 'POWER_DIAG', 'SEP_DIAG', 'SEP_BIN', 'SEP_MU_PWR_COV', 'PWR_MU_SEP_COV', 'SEP_BIN_BOX_GATE']
rows = []
for (case, model), g in fb(sca).groupby(['case', 'model']):
    if model not in arms: continue
    gc = cc[(cc.case == case) & (cc.model == model)].set_index('component')
    ga = fb(acf)[(fb(acf).case == case) & (fb(acf).model == model)].set_index('whitened_channel')
    rows.append({'case': case, 'model': model, 'heading_rmse_deg': g.heading_rmse_trace_deg.iloc[0], 'heading95': g.heading95_trace.iloc[0],
                 'nees_u_ACT': s.loc[(case, model), 'ACTUAL'], 'nees_u_SHUF': s.loc[(case, model), 'SHUFFLE'], 'nees_u_PHASE': s.loc[(case, model), 'PHASE'],
                 'rms_U_S_LF': gc.loc['U_S_LF', 'heading_rms_deg'], 'rms_U_S_HF': gc.loc['U_S_HF', 'heading_rms_deg'],
                 'rms_U_R_LF': gc.loc['U_R_LF', 'heading_rms_deg'], 'rms_U_R_HF': gc.loc['U_R_HF', 'heading_rms_deg'],
                 'rms_PROCESS': gc.loc['PROCESS', 'heading_rms_deg'], 'rms_INIT': gc.loc['INIT', 'heading_rms_deg'], 'rms_LIN': gc.loc['LIN', 'heading_rms_deg'],
                 'tau_s_sec': ga.loc['s', 'tau_int_s'], 'lag1_s': ga.loc['s', 'lag1_noncentred'], 'tau_r_sec': ga.loc['r', 'tau_int_s'], 'mean_ut_s': ga.loc['s', 'mean'], 'mean_ut_r': ga.loc['r', 'mean']})
tab = pd.DataFrame(rows); tab.to_csv(OUT / 'D1_FULL_B0_TABLE.csv', index=False)
md = ['# D1 results (machine summary)', '', '```json', json.dumps(judge, indent=2, default=str), '```', '',
      '## Full B0', tab.round(3).to_markdown(index=False), '',
      '## Coverage attribution vs POWER1 (Full B0)', fb(cov).round(4).to_markdown(index=False), '',
      '## Surrogate (all conditions)', sur.round(3).to_markdown(index=False)]
(OUT / 'D1_RESULTS.md').write_text('\n'.join(md) + '\n')
for k, v in judge.items():
    print(f'::notice title=D1 {k}::{json.dumps(v, default=str)[:900]}')
print('D1_SUMMARY_DONE', flush=True)
