#!/usr/bin/env python3
"""Measurement-level (pre-recursion) evaluation of d0 = s_Full(fp) - s_LUT(fp; x^-) as a polarization-extreme detector / gate,
in the setting where type-1 delta-s is used for range mean correction (MU_R_EXDS). No new simulation: uses saved series."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

R = Path(__file__).resolve().parent; OUT = R / 'results_d0gate'; OUT.mkdir(exist_ok=True)
key = ['case', 'bias', 'k']
A = pd.read_csv(R / 'results_series/ALL_SERIES.csv.gz', usecols=key + ['route', 't_s', 'pose_id', 'e_s', 'e_r', 'mu_s', 'Vs', 'abs_ds1', 'BASE__nu_s_w', 'BASE__H_spsi', 'BASE__acc'])
HG = pd.read_csv(R / 'results_hgate/HG_SERIES.csv.gz', usecols=key + ['BASE__nu_s', 'BASE__nis', 'MU_R_EXDS__acc', 'MU_R_EXDS__nu_s', 'MU_R_EXDS__nis', 'MU_R_EXDS__nu_r'])
HP = pd.read_csv(R / 'results_hpath/HP_SERIES.csv.gz', usecols=key + ['sMprior_+0', 'prior_psi_err_deg'])
MRS = pd.read_csv(R / 'results_murec/MR_SERIES.csv.gz', usecols=key + ['MU_R_EXDS__meas_r_cm'])
PK = pd.read_csv(R / 'results_hpath/HP_PACKETS.csv.gz', usecols=['case', 'pose_id', 'sF_+0', 'sMGT_+0', 'fp_shift_tap', 'mlr_fp_full_db'])
D = A.merge(HG, on=key).merge(HP, on=key).merge(MRS, on=key).merge(PK, on=['case', 'pose_id'])
D['d0_base'] = D['sF_+0'] - D['sMprior_+0']                     # BASE prior LUT
D['d0'] = D['MU_R_EXDS__nu_s'] + D['mu_s']                       # = s - h_s(x^- of the range-corrected filter)
D['state_part'] = D['d0'] - D['e_s']                            # s_LUT(GT) - s_LUT(x^-)
D['S_ss'] = (D['BASE__nu_s'] / D['BASE__nu_s_w']) ** 2; D['ws2'] = D['BASE__nu_s_w'] ** 2
D['HPH_ss'] = (D['S_ss'] - D['Vs']).clip(lower=1e-12)
D['d0_z_state'] = D['d0'].abs() / np.sqrt(D['HPH_ss'])             # d0 normalised by state uncertainty only (no V_s)
D['mu_r_hat_cm'] = (D['e_r'] * 100 - D['MU_R_EXDS__meas_r_cm']).abs()
qa = {'d0_base_vs_nu_plus_mu_maxabs': float((D['d0_base'] - (D['BASE__nu_s'] + D['mu_s'])).abs().max()), 'n_rows': len(D)}
M = D[D.t_s >= 30].copy()
q90, q95 = M.e_s.abs().quantile([.9, .95]); qa.update({'abs_es_q90': float(q90), 'abs_es_q95': float(q95)})
# ---------- detector quality ----------
DET = {'|d0|': M.d0.abs(), '|d0|/sqrt(HPH)': M.d0_z_state, 'w_s^2 (POWER, in chi2)': M.ws2, '|ds1| (type1)': M.abs_ds1, '|mu_r_hat|': M.mu_r_hat_cm}
rows = []
for bias, g in M.groupby('bias'):
    for thr_name, thr in [('top10', q90), ('top5', q95)]:
        y = (g.e_s.abs() >= thr).to_numpy()
        for dn, sc in DET.items():
            s = sc.loc[g.index].to_numpy(); aucs = [roc_auc_score(y[g.case == c], s[g.case == c]) for c in g.case.unique() if 0 < y[g.case == c].sum() < (g.case == c).sum()]
            rows.append({'bias': bias, 'extreme': thr_name, 'detector': dn, 'auc_pooled': roc_auc_score(y, s), 'auc_case_median': float(np.median(aucs)), 'auc_case_min': float(np.min(aucs))})
pd.DataFrame(rows).to_csv(OUT / 'D0_DETECTOR_AUC.csv', index=False)


# ---------- gate on top of MU_R_EXDS acceptance (pol channel only) ----------
def lf_bias(df, es):
    """RMS of 10 s rolling mean of the accepted e_s stream (persistent bias that enters the filter), per case-bias."""
    v = []
    for _, g in df.groupby(['case', 'bias']):
        x = pd.Series(es.loc[g.index].to_numpy()).rolling(51, center=True, min_periods=1).mean().to_numpy(); v.append(np.sqrt(np.mean(x ** 2)))
    return float(np.median(v))


base_acc = M['BASE__acc'].astype(bool); mur_acc = M['MU_R_EXDS__acc'].astype(bool)
newly = mur_acc & ~base_acc; clean = M.e_s.abs() < 0.1
heq = (M.e_s / M.BASE__H_spsi.where(M.BASE__H_spsi.abs() > 0.05)).abs() * 180 / np.pi   # heading-equivalent pol error (deg), |H|>0.05 only


def stats(name, use, rate=np.nan, flag=None):
    es = M.e_s.where(use, 0.0)
    r = {'set': name, 'flag_rate': rate, 'n_pol_used': int(use.sum()), 'es_rms_used': float(np.sqrt(np.mean(M.e_s[use] ** 2))), 'es_absmean_used': float(M.e_s[use].abs().mean()),
         'es2_mass_rel_BASE': float(np.sum(M.e_s[use] ** 2) / np.sum(M.e_s[base_acc] ** 2)), 'lf10s_bias_rms_med': lf_bias(M, es),
         'heq_deg_rms_used': float(np.sqrt(np.nanmean(heq[use] ** 2))), 'n_top5_used': int((use & (M.e_s.abs() >= q95)).sum())}
    if flag is not None:
        r.update({'newly_caught_frac': float((flag & newly).sum() / max(newly.sum(), 1)), 'clean_flagged_frac': float((flag & clean & mur_acc).sum() / max((clean & mur_acc).sum(), 1)),
                  'flag_state_dominated_frac': float(((M.state_part.abs() > M.e_s.abs()) & flag & mur_acc).sum() / max((flag & mur_acc).sum(), 1))})
    return r


G = [stats('BASE joint gate', base_acc), stats('MU_R_EXDS joint gate', mur_acc)]
for dn, sc in DET.items():
    for rate in [0.02, 0.03, 0.05, 0.10]:
        flag = pd.Series(False, index=M.index)
        for r_ in M.route.unique():  # threshold calibrated on the other two routes
            tr = M.route != r_; thr = sc[tr].quantile(1 - rate); flag |= (~tr) & (sc > thr)
        G.append(stats(f'MU_R_EXDS + pol gate {dn}', mur_acc & ~flag, rate, flag))
GT = pd.DataFrame(G); GT.to_csv(OUT / 'D0_GATE_MEAS.csv', index=False)
# per bias split for d0 gate at 3% and 5%, and heading-error dominated flags in L2
pb = []
for bias in ['B0', 'L2']:
    mb = M.bias == bias; sc = M.d0.abs()
    for rate in [0.03, 0.05]:
        flag = pd.Series(False, index=M.index)
        for r_ in M.route.unique():
            tr = (M.route != r_); thr = sc[tr & mb].quantile(1 - rate); flag |= (~tr) & mb & (sc > thr)
        f = flag & mur_acc & mb
        pb.append({'bias': bias, 'rate': rate, 'n_flag': int(f.sum()), 'flag_state_dominated_frac': float((M.state_part.abs() > M.e_s.abs())[f].mean()),
                   'flag_med_abs_es': float(M.e_s.abs()[f].median()), 'flag_med_abs_state_part': float(M.state_part.abs()[f].median()),
                   'flag_med_abs_prior_psi_err_deg': float(M.prior_psi_err_deg.abs()[f].median()), 'all_med_abs_prior_psi_err_deg': float(M.prior_psi_err_deg.abs()[mb].median())})
pd.DataFrame(pb).to_csv(OUT / 'D0_FLAG_BY_BIAS.csv', index=False)
# per case for d0 gate 3%
pc = []
for c, g in M.groupby('case'):
    sc = M.d0.abs(); i = g.index; tr = M.route != g.route.iloc[0]; thr = sc[tr].quantile(0.97); flag = (sc.loc[i] > thr)
    use_mur = mur_acc.loc[i]; use_g = use_mur & ~flag; ub = base_acc.loc[i]
    pc.append({'case': c, 'es_rms_BASE': float(np.sqrt(np.mean(g.e_s[ub] ** 2))), 'es_rms_MUR': float(np.sqrt(np.mean(g.e_s[use_mur] ** 2))), 'es_rms_MUR_d0gate': float(np.sqrt(np.mean(g.e_s[use_g] ** 2))),
               'n_newly': int((newly.loc[i]).sum()), 'newly_caught': int((newly.loc[i] & flag).sum()), 'n_flag': int((flag & use_mur).sum())})
pd.DataFrame(pc).to_csv(OUT / 'D0_GATE_CASE.csv', index=False)
# stratum view: where do d0 flags fall
M['st'] = np.select([(M.fp_shift_tap == 0) & (M.mlr_fp_full_db < -15), M.fp_shift_tap == 0, M.fp_shift_tap.abs() == 1, M.fp_shift_tap.abs() <= 3], ['A_clean', 'B_overlap_fp0', 'C_fp_pm1', 'D_fp_2to3'], 'E_fp_ge4')
thr = M.d0.abs().quantile(0.97)
M.assign(flag=M.d0.abs() > thr).groupby('st').agg(n=('flag', 'size'), flag_rate=('flag', 'mean'), es_rms=('e_s', lambda x: np.sqrt(np.mean(x ** 2)))).to_csv(OUT / 'D0_FLAG_STRATA.csv')
(OUT / 'D0_QA.json').write_text(json.dumps(qa, indent=2))
print(json.dumps(qa, indent=1)); print(pd.DataFrame(rows).round(3).to_string()); print(GT.round(4).to_string()); print(pd.DataFrame(pb).round(3).to_string()); print(pd.DataFrame(pc).round(3).to_string())
print(pd.read_csv(OUT / 'D0_FLAG_STRATA.csv').round(3).to_string())
