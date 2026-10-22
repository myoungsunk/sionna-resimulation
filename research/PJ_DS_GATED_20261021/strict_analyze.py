#!/usr/bin/env python3
"""Analysis of results_strict per 17_STRICT_PLAN_KO.md (route-level judgement, block bootstrap, same-prior detector AUC)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

R = Path(__file__).resolve().parent / 'results_strict'
S = pd.read_csv(R / 'SB_SCORES.csv'); key = ['case', 'bias', 'channel']
prev = pd.read_csv(Path(__file__).resolve().parent / 'results_d0var/D0V_SCORES.csv')
q = S[S.arm.isin(['BASE', 'MU_R'])].replace({'arm': {'MU_R': 'MU_R_EXDS'}}).merge(prev, on=['case', 'bias', 'channel', 'arm'])
QA = {'heading_vs_prev_maxabs': float((q.heading_rmse_deg_x - q.heading_rmse_deg_y).abs().max()), 'calib': json.loads((R / 'SB_CALIB.json').read_text())}
b = S[S.arm == 'BASE'].set_index(key)
rows = []
for arm, g in S.groupby('arm', sort=False):
    g = g.set_index(key); bb = b.loc[g.index]
    d = pd.DataFrame({'route': g.route, 'h': g.heading_rmse_deg / bb.heading_rmse_deg, 'anchor': g.anchor_range_rmse_cm / bb.anchor_range_rmse_cm,
                      'xy': g.xy_rmse_cm / bb.xy_rmse_cm, 'tan': g.tangential_rmse_cm / bb.tangential_rmse_cm, 'nees': g.heading_nees_1d, 'nees_b': bb.heading_nees_1d,
                      'hcov': g.heading_cov95, 'cov_b': bb.heading_cov95, 'xynees': g.xy_nees_2d, 'xycov': g.xy_cov95, 'xycov_b': bb.xy_cov95})
    for chn in ['full', 'los']:
        dd = d.xs(chn, level='channel')
        r = {'arm': arm, 'channel': chn, 'heading_ratio_med': dd.h.median(), 'h_better': int((dd.h < 1).sum()), 'h_worse10': int((dd.h > 1.1).sum()), 'h_worst': dd.h.max(),
             'anchor_ratio_med': dd.anchor.median(), 'xy_ratio_med': dd.xy.median(), 'tan_ratio_med': dd.tan.median(),
             'heading_nees1d_med': dd.nees.median(), 'heading_cov95_med': dd.hcov.median(), 'xy_nees2d_med': dd.xynees.median(), 'xy_cov95_med': dd.xycov.median()}
        for rt, gr in dd.groupby('route'):
            r[f'{rt}_h'] = gr.h.median(); r[f'{rt}_anchor'] = gr.anchor.median(); r[f'{rt}_xy'] = gr.xy.median(); r[f'{rt}_cov'] = gr.hcov.median(); r[f'{rt}_covb'] = gr.cov_b.median()
            r[f'{rt}_nees'] = gr.nees.median(); r[f'{rt}_neesb'] = gr.nees_b.median()
        if chn == 'full':
            rts = sorted(dd.route.unique())
            r['Q1_anchor_all_routes_lt1'] = bool(all(r[f'{x}_anchor'] < 1 for x in rts))
            r['Q2_i_heading_all_routes_le1'] = bool(all(r[f'{x}_h'] <= 1 for x in rts))
            r['Q2_ii_cov_closer_all_routes'] = bool(all(abs(r[f'{x}_cov'] - .95) < abs(r[f'{x}_covb'] - .95) for x in rts))
            r['Q2_iii_nees_closer_all_routes'] = bool(all(abs(np.log(r[f'{x}_nees'])) < abs(np.log(r[f'{x}_neesb'])) for x in rts))
            r['Q2_iv_anchor_lt1'] = bool(dd.anchor.median() < 1)
            r['Q2_all'] = r['Q2_i_heading_all_routes_le1'] and r['Q2_ii_cov_closer_all_routes'] and r['Q2_iii_nees_closer_all_routes'] and r['Q2_iv_anchor_lt1']
        rows.append(r)
A = pd.DataFrame(rows); A.to_csv(R / 'ST_SUMMARY.csv', index=False)
# case table for key arms
ct = S[S.channel == 'full'].pivot_table(index=['route', 'case', 'bias'], columns='arm', values=['heading_rmse_deg', 'heading_cov95', 'heading_nees_1d', 'anchor_range_rmse_cm', 'xy_rmse_cm'])
ct.to_csv(R / 'ST_CASE_TABLE.csv')
# ---- paired time-block bootstrap (10 s blocks) per case-bias: heading MSE ratio and coverage difference vs BASE
SE = pd.read_csv(R / 'SB_SERIES.csv.gz'); rng = np.random.default_rng(0); bt = []
arms_bt = ['INFL_R_S', 'MU_R', 'MU_R+GRAW', 'MU_R+GRAW+RONLY', 'BASE_eta*', 'MU_R+GRAW_eta*', 'MU_R+GRAW+RONLY_eta*']
for (c, bias), g in SE.groupby(['case', 'bias']):
    g = g[g.t_s >= 30]; blk = ((g.t_s - g.t_s.min()) // 10).astype(int).to_numpy(); ub = np.unique(blk); idx = [np.where(blk == u)[0] for u in ub]
    hb = g['BASE__herr_deg'].to_numpy(); cb = (g['BASE__herr_deg'] ** 2 / g['BASE__hsig_deg'] ** 2 <= 3.841).to_numpy(); rb = g['BASE__rerr_cm'].to_numpy()
    for arm in arms_bt:
        ha = g[f'{arm}__herr_deg'].to_numpy(); ca = (g[f'{arm}__herr_deg'] ** 2 / g[f'{arm}__hsig_deg'] ** 2 <= 3.841).to_numpy(); ra = g[f'{arm}__rerr_cm'].to_numpy()
        st = []
        for _ in range(2000):
            sel = np.concatenate([idx[i] for i in rng.integers(0, len(idx), len(idx))])
            st.append((np.mean(ha[sel] ** 2) / np.mean(hb[sel] ** 2), np.mean(ca[sel]) - np.mean(cb[sel]), np.mean(ra[sel] ** 2) / np.mean(rb[sel] ** 2)))
        st = np.array(st)
        bt.append({'case': c, 'bias': bias, 'arm': arm, 'h_mse_ratio': float(np.mean(ha ** 2) / np.mean(hb ** 2)), 'h_mse_lo': float(np.quantile(st[:, 0], .025)), 'h_mse_hi': float(np.quantile(st[:, 0], .975)),
                   'cov_diff': float(np.mean(ca) - np.mean(cb)), 'cov_lo': float(np.quantile(st[:, 1], .025)), 'cov_hi': float(np.quantile(st[:, 1], .975)),
                   'anchor_mse_ratio': float(np.mean(ra ** 2) / np.mean(rb ** 2)), 'anchor_lo': float(np.quantile(st[:, 2], .025)), 'anchor_hi': float(np.quantile(st[:, 2], .975))})
BT = pd.DataFrame(bt); BT.to_csv(R / 'ST_BOOTSTRAP.csv', index=False)
BS = BT.groupby('arm').apply(lambda g: pd.Series({'h_ci_below1': int((g.h_mse_hi < 1).sum()), 'h_ci_above1': int((g.h_mse_lo > 1).sum()), 'cov_ci_pos': int((g.cov_lo > 0).sum()),
                                                  'cov_ci_neg': int((g.cov_hi < 0).sum()), 'anchor_ci_below1': int((g.anchor_hi < 1).sum()), 'anchor_ci_above1': int((g.anchor_lo > 1).sum())}), include_groups=False)
BS.to_csv(R / 'ST_BOOTSTRAP_COUNTS.csv')
# ---- same-prior detector comparison (held route, t>=30)
DT = pd.read_csv(R / 'SB_DET.csv.gz'); DT = DT[DT.t_s >= 30]; det = []
for (pa, bias), g in DT.groupby(['prior_arm', 'bias']):
    sc = {'|d0|': g.d0.abs(), '|nu_s|': g.nu_s.abs(), 'w_s^2 (POWER Vs)': g.nu_s ** 2 / (g.hph_ss + g.Vs), '|nu_s|/sqrt(HPH)': g.nu_s.abs() / np.sqrt(g.hph_ss),
          '|d0|/sqrt(HPH+Vs)': g.d0.abs() / np.sqrt(g.hph_ss + g.Vs)}
    for thr_name, qv in [('top10', .9), ('top5', .95)]:
        y = (g.e_s.abs() >= g.e_s.abs().quantile(qv)).to_numpy()
        for dn, s in sc.items():
            au = [roc_auc_score(y[(g.case == c).to_numpy()], s[g.case == c]) for c in g.case.unique()]
            det.append({'prior_arm': pa, 'bias': bias, 'extreme': thr_name, 'detector': dn, 'auc_pooled': roc_auc_score(y, s), 'auc_case_med': float(np.median(au)), 'auc_case_min': float(np.min(au))})
    det.append({'prior_arm': pa, 'bias': bias, 'extreme': 'state_part', 'detector': 'rms(d0-e_s)', 'auc_pooled': float(np.sqrt(np.mean((g.d0 - g.e_s) ** 2))), 'auc_case_med': float(g.prior_psi_err_deg.abs().median()), 'auc_case_min': np.nan})
DE = pd.DataFrame(det); DE.to_csv(R / 'ST_DETECTOR.csv', index=False)
(R / 'ST_QA.json').write_text(json.dumps(QA, indent=2, default=float))
pd.set_option('display.width', 250)
print(json.dumps(QA, indent=1, default=float)); print(A[A.channel == 'full'].round(3).T.to_string()); print(A[A.channel == 'los'][['arm', 'heading_ratio_med', 'h_worse10', 'anchor_ratio_med', 'heading_cov95_med']].round(3).to_string())
print(BS.to_string()); print(DE.round(3).to_string())
