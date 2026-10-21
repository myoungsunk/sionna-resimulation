#!/usr/bin/env python3
"""Local analysis of results_hpath (no new simulation). Writes HA_*.csv."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

R = Path(__file__).resolve().parent / 'results_hpath'
OFFS = [-8, -4, -2, -1, 1, 2, 4, 8]
PK = pd.read_csv(R / 'HP_PACKETS.csv.gz'); SE = pd.read_csv(R / 'HP_SERIES.csv.gz')
out = {}
for o in OFFS:
    PK[f'dF_{o:+d}'] = PK[f'sF_{o:+d}'] - PK['sF_+0']; PK[f'dL_{o:+d}'] = PK[f'sL_{o:+d}'] - PK['sL_+0']
    PK[f'dM_{o:+d}'] = PK[f'sMGT_{o:+d}'] - PK['sMGT_+0']
    PK[f'gD_{o:+d}'] = ((PK[f'sMGTp1_{o:+d}'] - PK['sMGTp1_+0']) - (PK[f'sMGTm1_{o:+d}'] - PK['sMGTm1_+0'])) / 2
    PK[f'dRes_{o:+d}'] = PK[f'dF_{o:+d}'] - PK[f'dM_{o:+d}']
PK['g0'] = (PK['sMGTp1_+0'] - PK['sMGTm1_+0']) / 2
PK['abs_es'] = PK.e_s.abs(); PK['a1'] = PK['dF_+1'].abs()

# ---- QA model vs measured LoS
qa = {'s0_absdiff_p50': float((PK['sMGT_+0'] - PK['sL_+0']).abs().median()), 's0_absdiff_p99': float((PK['sMGT_+0'] - PK['sL_+0']).abs().quantile(.99)),
      'ds1_absdiff_p50': float((PK['dM_+1'] - PK['dL_+1']).abs().median()), 'ds1_absdiff_p99': float((PK['dM_+1'] - PK['dL_+1']).abs().quantile(.99)),
      'fp_model_eq_los': float((PK.fpM_GT == PK.fp_los).mean())}
out['QA'] = qa


# ---- route-held-out ridge R2 of e_s from a feature set, evaluated per stratum
def heldout_pred(df, cols, y='e_s'):
    p = np.full(len(df), np.nan)
    for r in df.route.unique():
        tr = df.route != r; m = Ridge(alpha=1e-3).fit(df.loc[tr, cols].fillna(0), df.loc[tr, y]); p[~tr.to_numpy()] = m.predict(df.loc[~tr, cols].fillna(0))
    return p


def r2(y, p):
    return float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)) if len(y) > 5 else np.nan


DF = [f'dF_{o:+d}' for o in OFFS]; DR = [f'dRes_{o:+d}' for o in OFFS]
PK['pred_dF'] = heldout_pred(PK, DF); PK['pred_dRes'] = heldout_pred(PK, DR)

# ---- strata by multipath-only CIR
d = PK.mp_wmean_excess_tap
PK['stratum'] = np.select([PK.mlr_fp_full_db < -15, PK.fp_shift_tap != 0, d.abs() <= 1, d.abs() <= 3, d.abs() <= 6],
                          ['0_clean(MP<-15dB)', '5_fp_shifted', '1_coincident(|d|<=1tap)', '2_partial(1-3tap)', '3_partial(3-6tap)'], '4_offset(>6tap)')
tot = float(np.sum(PK.e_s ** 2)); q80 = PK.abs_es.quantile(.8); tau = 0.055
rows = []
for st, g in PK.groupby('stratum'):
    big = g[g.abs_es >= q80]
    rows.append({'stratum': st, 'n': len(g), 'share_n': len(g) / len(PK), 'share_es2': float(np.sum(g.e_s ** 2)) / tot, 'rms_es': float(np.sqrt(np.mean(g.e_s ** 2))),
                 'med_mlr_fp_db': float(g.mlr_fp_full_db.median()), 'med_abs_ds1': float(g.a1.median()), 'corr_ds1_es': float(np.corrcoef(g['dF_+1'], g.e_s)[0, 1]),
                 'R2_heldout_ds8': r2(g.e_s.to_numpy(), g.pred_dF.to_numpy()), 'R2_heldout_dsres8': r2(g.e_s.to_numpy(), g.pred_dRes.to_numpy()),
                 'n_big_es': len(big), 'big_es_frac_ds_small': float((big.a1 < tau).mean()) if len(big) else np.nan,
                 'med_fp_shift': float(g.fp_shift_tap.median()), 'med_mp_s_fp': float(g.mp_s_fp.median())})
ST = pd.DataFrame(rows); ST.to_csv(R / 'HA_STRATA.csv', index=False)
# per case/route breakdown of share
PK.groupby(['case', 'stratum']).apply(lambda g: pd.Series({'n': len(g), 'share_es2_case': np.sum(g.e_s ** 2)}), include_groups=False).reset_index().to_csv(R / 'HA_STRATA_CASE.csv', index=False)

# ---- heading sensitivity of s level vs delta-s shape (LoS model, per degree)
sens = {'med_abs_g0_per_deg': float(PK.g0.abs().median())}
for o in [1, 2, 4, -1]:
    sens[f'med_abs_gD{o:+d}_per_deg'] = float(PK[f'gD_{o:+d}'].abs().median()); sens[f'ratio_gD{o:+d}_over_g0_med'] = float((PK[f'gD_{o:+d}'].abs() / PK.g0.abs().clip(1e-9)).median())
sens['med_abs_dL1_los'] = float(PK['dL_+1'].abs().median()); sens['med_abs_dF1_full'] = float(PK['dF_+1'].abs().median())
sens['corr_dM1_g0'] = float(np.corrcoef(PK['dM_+1'], PK.g0)[0, 1])
out['SENS'] = sens

# ---- online LUT comparison along BASE prior (B0 and L2)
S = SE.merge(PK.drop(columns=['route']), on=['case', 'pose_id'], how='left'); S = S[S.t_s >= 30].copy()
for o in OFFS:
    S[f'dP_{o:+d}'] = S[f'sMprior_{o:+d}'] - S['sMprior_+0']; S[f'nuD_{o:+d}'] = S[f'dF_{o:+d}'] - S[f'dP_{o:+d}']
S['nu_s0'] = S['sF_+0'] - S['sMprior_+0']
S['route'] = S.case.map(PK.drop_duplicates('case').set_index('case').route)
lut = []
for bias, g in S.groupby('bias'):
    g = g.copy(); ND = [f'nuD_{o:+d}' for o in OFFS]
    g['p_nuD'] = heldout_pred(g, ND); g['p_dF'] = heldout_pred(g, DF)
    row = {'bias': bias, 'n': len(g), 'R2_es_from_dF': r2(g.e_s.to_numpy(), g.p_dF.to_numpy()), 'R2_es_from_nuD': r2(g.e_s.to_numpy(), g.p_nuD.to_numpy()),
           'corr_nuD1_prior_psi_err': float(np.corrcoef(g['nuD_+1'], g.prior_psi_err_deg)[0, 1]), 'corr_dF1_prior_psi_err': float(np.corrcoef(g['dF_+1'], g.prior_psi_err_deg)[0, 1]),
           'corr_nu_s0_prior_psi_err': float(np.corrcoef(g.nu_s0, g.prior_psi_err_deg)[0, 1]), 'corr_nu_s0_e_s': float(np.corrcoef(g.nu_s0, g.e_s)[0, 1]),
           'fp_prior_eq_gt': float((g.fpM_prior == g.fpM_GT).mean()), 'med_abs_dP1_minus_dM1': float((g['dP_+1'] - g['dM_+1']).abs().median()),
           'med_abs_prior_psi_err_deg': float(g.prior_psi_err_deg.abs().median())}
    # share of nu_s0 variance explained by heading-error part vs multipath part
    hpart = g['sMGT_+0'] - g['sMprior_+0']; row['var_share_heading_part'] = float(np.var(hpart) / np.var(g.nu_s0)); row['var_share_mp_part'] = float(np.var(g.e_s) / np.var(g.nu_s0))
    lut.append(row)
pd.DataFrame(lut).to_csv(R / 'HA_LUT.csv', index=False)
(R / 'HA_QA_SENS.json').write_text(json.dumps(out, indent=2))

# ---- Q4 heading path
A = pd.read_csv(R / 'HP_ATTR.csv'); SC = pd.read_csv(R / 'HP_SCORES.csv'); PR = pd.read_csv(R / 'HP_PAIR.csv'); G = pd.read_csv(R / 'HP_GAIN.csv')
key = ['case', 'bias']; b = SC[SC.arm == 'BASE'].set_index(key)
sc = []
for arm, g in SC.groupby('arm', sort=False):
    g = g.set_index(key); h = g.heading_rmse_deg / b.heading_rmse_deg
    sc.append({'arm': arm, 'heading_med': h.median(), 'h_better': int((h < 1).sum()), 'h_worse10': int((h > 1.1).sum()), 'h_worst': h.max(),
               'u_r_rms_cm_med': g.u_r_rms_cm.median(), 'u_s_rms_med': g.u_s_rms.median(), 'corr_ur_us_med': g.corr_ur_us.median(), 'acc_med': g.accepted_fraction.median()})
pd.DataFrame(sc).to_csv(R / 'HA_Q4_SCORES.csv', index=False)
H = A[A.quantity == 'heading_deg']; base = H[H.arm == 'BASE'].set_index(key + ['component']); bms = H[(H.arm == 'BASE')].groupby(key).total_ms.first()
dd = []
for (arm, comp), g in H.groupby(['arm', 'component']):
    g = g.set_index(key); dlt = (g.contrib - base.xs(comp, level='component').contrib) / bms
    dd.append({'arm': arm, 'component': comp, 'base_share_med': float((base.xs(comp, level='component').contrib / bms).median()), 'delta_med': float(dlt.median()),
               'n_up': int((dlt > 0).sum()), 'n_down': int((dlt < 0).sum())})
pd.DataFrame(dd).to_csv(R / 'HA_Q4_DELTA.csv', index=False)
P = PR[PR.quantity == 'heading_deg']; bP = P[P.arm == 'BASE']
pairs = []
for (arm, c1, c2), g in P.groupby(['arm', 'c1', 'c2']):
    if c1 > c2: continue
    g = g.set_index(key).value / bms
    pairs.append({'arm': arm, 'c1': c1, 'c2': c2, 'value_over_baseMSE_med': float(g.median()), 'n_neg': int((g < 0).sum()), 'n': len(g)})
pd.DataFrame(pairs).to_csv(R / 'HA_Q4_PAIR.csv', index=False)
# per case BASE cross term U_R x U_S and heading ratio of MU_R_EXDS
pc = P[(P.c1 == 'U_R') & (P.c2 == 'U_S')].pivot_table(index=key, columns='arm', values='value')
pc = pc.div(bms, axis=0).add_prefix('cross_RS_')
for arm in ['MU_R_EXDS', 'MU_R_ORACLE', 'MU_S_ORACLE']:
    pc[f'h_{arm}'] = SC[SC.arm == arm].set_index(key).heading_rmse_deg / b.heading_rmse_deg
pc['base_heading_deg'] = b.heading_rmse_deg
pc.reset_index().to_csv(R / 'HA_Q4_CASE.csv', index=False)
G.groupby('arm')[['Kpsi_r_deg_per_sig', 'Kpsi_s_deg_per_sig', 'Hs_psi_med', 'Hs_rad_med_per_m', 'prior_sig_psi_deg']].median().to_csv(R / 'HA_Q4_GAIN.csv')
print(json.dumps(out, indent=1)); print(ST.round(3).to_string()); print(pd.DataFrame(lut).round(3).T.to_string())
print(pd.DataFrame(sc).round(3).to_string()); print(pd.DataFrame(dd).round(3).to_string()); print(pd.DataFrame(pairs).round(3).to_string()); print(pc.round(3).to_string())
