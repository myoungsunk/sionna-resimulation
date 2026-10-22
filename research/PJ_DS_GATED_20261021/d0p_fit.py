#!/usr/bin/env python3
"""Refit POWER (POWER_BIN_JOINT: Ridge on log_fp_power + tertile-binned residual covariance) per held route with
labels swapped: GT (all poses, original), GT (label-filter trace poses only), d0 from BASE prior, d0 from J4 prior (GT-free)."""
from __future__ import annotations
import json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import v_replay as V
import n4b_rf_errors as B
from features import GROUPS

LAB = Path(os.environ['PJ_LABELS'])


def main():
    data = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); oof = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    L = pd.concat([pd.read_csv(p) for p in sorted(LAB.rglob('*_D0P_LABELS.csv.gz'))], ignore_index=True)
    L = L.drop_duplicates(['case', 'label_filter', 'pose_id'], keep='last')
    full = data[data.channel == 'full'].copy(); rows, meas, info = [], [], []
    variants = {'P_GT_ALL': None, 'P_GT_SUB': ('BASE', 'gt'), 'P_D0_BASE': ('BASE', 'd'), 'P_D0_J4': ('J4', 'd')}
    for held in ('R2', 'R4', 'R5'):
        te = data[data.route == held].copy(); dist = cKDTree(te[['x_eval', 'y_eval']].to_numpy()).query(full[['x_eval', 'y_eval']].to_numpy())[0]
        tr0 = full[(full.route != held) & (dist > 1e-4)].copy()
        for vn, spec in variants.items():
            tr = tr0.copy()
            if spec is not None:
                lf, kind = spec; lab = L[L.label_filter == lf].set_index(['case', 'pose_id'])
                tr = tr.join(lab[['d_r', 'd_s', 'e_r', 'e_s']].add_prefix('L_'), on=['case', 'pose_id'], how='inner')
                if kind == 'd': tr['e_r'] = tr.L_d_r; tr['e_s'] = tr.L_d_s
                info.append({'held': held, 'variant': vn, 'n_train': len(tr), 'label_noise_r_rms_cm': float(np.sqrt(np.mean((tr.e_r - tr.L_e_r) ** 2)) * 100),
                             'label_noise_s_rms': float(np.sqrt(np.mean((tr.e_s - tr.L_e_s) ** 2))), 'gt_label_check': float(np.max(np.abs(tr.L_e_s - full.set_index(['case', 'pose_id']).loc[list(zip(tr.case, tr.pose_id))].e_s.to_numpy())))})
            else:
                info.append({'held': held, 'variant': vn, 'n_train': len(tr)})
            w = B.site_weights(np, pd, tr)
            mp, cp, ip = B.fit_model(np, tr, te, w, 'POWER_BIN_JOINT', GROUPS)
            for mname, C in [('POWER1', cp), ('POWER_DIAG', None)]:
                if C is None: C = cp.copy(); C[:, 0, 1] = C[:, 1, 0] = 0
                q = te[['case', 'route', 'channel', 'pose_id']].copy(); q['variant'] = vn; q['model'] = mname
                q['mu_r'] = mp[:, 0]; q['mu_s'] = mp[:, 1]; q['Vr'] = C[:, 0, 0]; q['Vs'] = C[:, 1, 1]; q['Crs'] = C[:, 0, 1]; rows.append(q)
                Y = te[['e_r', 'e_s']].to_numpy() - mp
                for (cs, ch), ix in te.groupby(['case', 'channel']).indices.items():
                    meas.append({'case': cs, 'channel': ch, 'variant': vn, 'model': mname, 'r_rmse_cm': float(np.sqrt(np.mean(Y[ix, 0] ** 2)) * 100), 's_rmse': float(np.sqrt(np.mean(Y[ix, 1] ** 2))),
                                 'bias_r_cm': float(Y[ix, 0].mean() * 100), 'bias_s': float(Y[ix, 1].mean()), 'r95': float(np.mean(Y[ix, 0] ** 2 / C[ix, 0, 0] <= 3.841)),
                                 's95': float(np.mean(Y[ix, 1] ** 2 / C[ix, 1, 1] <= 3.841)), 'mean_sig_r_cm': float(np.sqrt(C[ix, 0, 0]).mean() * 100), 'mean_sig_s': float(np.sqrt(C[ix, 1, 1]).mean())})
    P = pd.concat(rows, ignore_index=True)
    ref = oof[oof.model.isin(['POWER1', 'POWER_DIAG'])].merge(P[P.variant == 'P_GT_ALL'], on=['case', 'channel', 'pose_id', 'model'], suffixes=('_o', ''))
    qa = {'reproduce_max_abs_mu_s': float((ref.mu_s_o - ref.mu_s).abs().max()), 'reproduce_max_abs_Vs': float((ref.Vs_o - ref.Vs).abs().max()), 'reproduce_n': len(ref)}
    out = V.OUT; P.to_csv(out / 'D0P_PARAMS.csv.gz', index=False, compression='gzip'); pd.DataFrame(meas).to_csv(out / 'D0P_MEAS.csv', index=False)
    pd.DataFrame(info).to_csv(out / 'D0P_FITINFO.csv', index=False); (out / 'D0P_FIT_QA.json').write_text(json.dumps(qa, indent=2)); print('FIT_DONE', qa, flush=True)


if __name__ == '__main__':
    main()
