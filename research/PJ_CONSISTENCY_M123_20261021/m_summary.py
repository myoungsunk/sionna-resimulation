#!/usr/bin/env python3
"""Route-heldout selection (train routes only) and preregistered judgements."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

IN = Path(os.environ['PJ_IN']); OUT = Path(os.environ['PJ_RESULTS']); OUT.mkdir(parents=True, exist_ok=True)
D1 = Path(os.environ['PJ_D1_RESULTS'])
cat = lambda g: pd.concat([pd.read_csv(p) for p in sorted(IN.rglob(g))], ignore_index=True)
S = cat('*_M_SCORES.csv'); QA = cat('*_M_QA.csv')
HA, HE, HEF, HDB, HDC = cat('*_HA.csv'), cat('*_HE.csv'), cat('*_HE_FEATURES.csv'), cat('*_HD_BLOCKS.csv'), cat('*_HD_CASE.csv')
for name, df in [('M_SCORES', S), ('M_QA', QA), ('HA', HA), ('HE', HE), ('HE_FEATURES', HEF), ('HD_BLOCKS', HDB), ('HD_CASE', HDC)]:
    df.to_csv(OUT / f'{name}.csv', index=False)
assert S.case.nunique() == 7, S.case.unique()
PD = 'S_ONLY_e1_k1'
ETAS = sorted(S[S.family == 'S_ONLY'].eta_s.unique()); KAPPAS = sorted(S.kappa.unique(), reverse=True)
key = ['case', 'bias', 'channel']
S['abs_ln_nees'] = np.abs(np.log(S.heading_nees))
pdv = S[S.arm == PD].set_index(key)
S = S.join(pdv[['heading_rmse_deg', 'heading95', 'abs_ln_nees', 'bias_rmse_dps', 'heading_nees']].add_suffix('_pd'), on=key)
p1 = S[S.arm == 'REF_POWER1'].set_index(key)
S = S.join(p1[['heading_rmse_deg', 'heading95', 'abs_ln_nees']].add_suffix('_p1'), on=key)
S['rmse_ratio_pd'] = S.heading_rmse_deg / S.heading_rmse_deg_pd
S['rmse_ratio_p1'] = S.heading_rmse_deg / S.heading_rmse_deg_p1

qa_pass = bool((QA.d_rmse < 1e-9).all() and (QA.d_h95 < 1e-12).all())


def select(train, families):
    eta_star = {}
    for fam in families:
        for k in KAPPAS:
            g = train[(train.family == fam) & (train.kappa == k)].groupby('eta_s').abs_ln_nees.median()
            eta_star[(fam, k)] = float(g.idxmin())
    cand = []
    for (fam, k), e in eta_star.items():
        g = train[(train.family == fam) & (train.kappa == k) & (train.eta_s == e)]
        cand.append({'family': fam, 'kappa': k, 'eta': e, 'arm': g.arm.iloc[0], 'train_med_h95': float(g.heading95.median()),
                     'train_med_rmse_ratio': float(g.rmse_ratio_pd.median()), 'train_med_abs_ln_nees': float(g.abs_ln_nees.median())})
    cand = pd.DataFrame(cand)
    ok = cand[cand.train_med_h95.between(0.90, 0.99)]
    pick = ok.loc[ok.train_med_rmse_ratio.idxmin()] if len(ok) else cand.loc[cand.train_med_abs_ln_nees.idxmin()]
    return pick, cand


full = S[S.channel == 'full']
sel_rows, cand_rows, held_rows = [], [], []
for H in ['R2', 'R4', 'R5']:
    train = full[full.route != H]
    for label, fams in [('M', ['S_ONLY', 'COMMON']), ('M_E', ['MU_S0'])]:
        pick, cand = select(train, fams)
        cand['held_route'] = H; cand['selection'] = label; cand_rows.append(cand)
        sel_rows.append({'held_route': H, 'selection': label, **pick.to_dict()})
        held = S[(S.route == H) & (S.arm == pick.arm)].copy(); held['selection'] = label; held_rows.append(held)
SEL = pd.DataFrame(sel_rows); CAND = pd.concat(cand_rows); HELD = pd.concat(held_rows)
SEL.to_csv(OUT / 'SELECTION.csv', index=False); CAND.to_csv(OUT / 'SELECTION_CANDIDATES.csv', index=False); HELD.to_csv(OUT / 'HELD_SELECTED.csv', index=False)


def judge(label):
    h = HELD[HELD.selection == label]; f = h[h.channel == 'full']; l = h[(h.channel == 'los')]
    s1n = int((f.abs_ln_nees < f.abs_ln_nees_pd).sum()); med95 = float(f.heading95.median())
    S1 = s1n >= 10 and 0.85 <= med95 <= 0.99
    medr = float(f.rmse_ratio_pd.median()); worse = int((f.rmse_ratio_pd > 1.1).sum()); better = int((f.rmse_ratio_pd < 1).sum())
    S2 = medr <= 1.0 and worse <= 2
    S3 = S1 and S2 and better >= 8
    los_ok = int((l.rmse_ratio_pd <= 1.10).sum()); S4 = los_ok >= 6
    return {'n_full': len(f), 'S1_nees_closer_count': s1n, 'S1_median_heading95': med95, 'S1_pass': S1,
            'S2_median_rmse_ratio_vs_PD': medr, 'S2_worse_gt10pct': worse, 'S2_pass': S2,
            'S3_rmse_better_count': better, 'S3_pass': S3, 'S4_los_ok_count': los_ok, 'S4_pass': S4,
            'vs_POWER1_median_rmse_ratio': float(f.rmse_ratio_p1.median()),
            'vs_POWER1_nees_closer_count': int((f.abs_ln_nees < f.abs_ln_nees_p1).sum()),
            'PD_median_heading95': float(f.heading95_pd.median()), 'median_nees_selected': float(f.heading_nees.median()), 'median_nees_PD': float(f.heading_nees_pd.median()),
            'L2_bias_rmse_ratio_vs_PD_median': float((f[f.bias == 'L2'].bias_rmse_dps / f[f.bias == 'L2'].bias_rmse_dps_pd).median())}


J = {'QA_reproduction_pass': qa_pass, 'QA_max_d_rmse': float(QA.d_rmse.max()), 'QA_max_d_h95': float(QA.d_h95.max()),
     'M': judge('M'), 'M_E': judge('M_E'), 'selection': SEL[['held_route', 'selection', 'arm', 'eta', 'kappa', 'train_med_h95', 'train_med_rmse_ratio']].to_dict('records')}
# kappa effect at selected family/eta, held L2
kap = []
for r in SEL[SEL.selection == 'M'].itertuples():
    for k in KAPPAS:
        g = S[(S.route == r.held_route) & (S.family == r.family) & (S.eta_s == r.eta) & (S.kappa == k) & (S.channel == 'full')]
        kap.append({'held_route': r.held_route, 'kappa': k, 'L2_bias_rmse_med': float(g[g.bias == 'L2'].bias_rmse_dps.median()),
                    'heading_rmse_med': float(g.heading_rmse_deg.median()), 'heading95_med': float(g.heading95.median())})
pd.DataFrame(kap).to_csv(OUT / 'KAPPA_EFFECT.csv', index=False)

# H-A
ha = HA.pivot_table(index='case', columns='model', values='rho_A')
ha_i = int((ha.SEP_BIN > ha.POWER_DIAG).sum())
ha_ii = int(HA[HA.model == 'SEP_BIN'].lowV_has_max_absd.sum())
d1 = pd.read_csv(D1 / 'D1_SURROGATE.csv'); d1 = d1[(d1.channel == 'full') & (d1.bias == 'B0')].pivot_table(index=['case', 'model'], columns='kind', values='nees_u_mean')
lap = np.log(d1.ACTUAL / d1.PHASE).unstack('model')
dl = (lap.SEP_BIN - lap.POWER_DIAG).reindex(ha.index); drho = ha.SEP_BIN - ha.POWER_DIAG
J['H_A'] = {'rhoA_SEP_gt_PD_cases': ha_i, 'lowV_max_absd_cases_SEP': ha_ii, 'pass': ha_i >= 5 and ha_ii >= 5,
            'spearman_drho_vs_dlnACTPHASE': float(spearmanr(drho, dl).statistic)}
# H-D
b = HDB[HDB.v_mean > 0.02].dropna(subset=['tau_int_s'])
ratio = float(np.percentile(b.v_mean, 90) / np.percentile(b.v_mean, 10)) if len(b) > 5 else float('nan')
testable = bool(ratio >= 1.5)
rs = float(spearmanr(b.tau_int_s, 1 / b.v_mean).statistic) if len(b) > 5 else float('nan')
cv = lambda x: float(np.std(x) / np.mean(x))
J['H_D'] = {'n_blocks': int(len(b)), 'speed_p90_p10': ratio, 'testable': testable, 'spearman_tau_invv': rs,
            'cv_ell_c': cv(HDC.ell_c_m), 'cv_tau': cv(HDC.tau_int_s),
            'spearman_tau_omega': float(spearmanr(b.tau_int_s, b.omega_mean).statistic) if len(b) > 5 else float('nan'),
            'pass': bool(testable and rs >= 0.3 and cv(HDC.ell_c_m) < cv(HDC.tau_int_s)), 'verdict': 'not_testable' if not testable else None}
# H-E
he = HE.pivot_table(index='case', columns='model', values='R2_nc')
he_n = int(((he.POWER1 <= 0.10) & (he.SEP_BIN <= 0.10)).sum())
top = HEF.assign(a=HEF.spearman_with_elf.abs()).groupby('feature').a.median().sort_values(ascending=False).head(8)
J['H_E'] = {'cases_both_R2nc_le_0.10': he_n, 'pass': he_n >= 5, 'R2_nc_median': he.median().to_dict(), 'top_features_median_abs_spearman': top.to_dict()}
(OUT / 'JUDGEMENT.json').write_text(json.dumps(J, indent=2, default=str))

md = ['# M1–M3 replay + H-A/H-D/H-E (machine summary)', '', '```json', json.dumps(J, indent=2, default=str), '```', '',
      '## Held-route selected arms', HELD[['selection', 'case', 'bias', 'channel', 'arm', 'heading_rmse_deg', 'heading_rmse_deg_pd', 'heading_rmse_deg_p1',
                                           'heading95', 'heading95_pd', 'heading95_p1', 'heading_nees', 'bias_rmse_dps', 'bias_rmse_dps_pd']].round(4).to_markdown(index=False),
      '', '## Selection candidates', CAND.round(4).to_markdown(index=False), '', '## H-A', HA.round(4).to_markdown(index=False),
      '', '## H-E', HE.round(4).to_markdown(index=False), '', '## H-D case', HDC.round(4).to_markdown(index=False)]
(OUT / 'RESULTS.md').write_text('\n'.join(md) + '\n')
for k in ['QA_reproduction_pass', 'M', 'M_E', 'H_A', 'H_D', 'H_E']:
    print(f'::notice title={k}::{json.dumps(J[k], default=str)[:900]}')
print('M_SUMMARY_DONE', flush=True)
