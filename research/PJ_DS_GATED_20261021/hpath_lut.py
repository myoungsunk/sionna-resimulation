#!/usr/bin/env python3
"""(A) Exact heading-error path decomposition for range/pol mean-correction arms (incl. oracle bounds).
(B) Per-packet multipath-only CIR (Full - LoS) excess delay / strength, LoS-model s-profile at GT, GT+-1 deg and at the BASE prior state.
No new fitting except the same route-held-out HGB mean models as mu_recursive.py."""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
import d1_core as D
from core import transition
import mu_recursive as MR
from series_dump import OFFS

# arm -> (range mean, pol mean): None=POWER mean, 'EX'/'EXDS'=HGB, 'ORACLE'=true error (diagnostic bound)
ARMS = {'BASE': (None, None), 'MU_R_EX': ('EX', None), 'MU_R_EXDS': ('EXDS', None), 'MU_R_ORACLE': ('ORACLE', None),
        'MU_S_EXDS': (None, 'EXDS'), 'MU_S_ORACLE': (None, 'ORACLE')}
CONDITIONS = [('B0', 'full'), ('L2', 'full')]
DEG = 180 / math.pi
O_ALL = [0] + OFFS


def cir_of(H):
    H = np.asarray(H, np.complex128); nf = H.shape[1]
    w = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    return np.fft.ifft(H * w[None, :, None], n=4 * nf, axis=1) * nf


def profile(c):
    """c (n,nt,2) complex CIR -> fp tap and s at fp+o (same detector as features.py)."""
    n, nt, _ = c.shape; ii = np.arange(n); amp = np.abs(c); pw = amp ** 2
    br = amp.max(axis=1).argmax(axis=1); strong = amp[ii, :, br]; fp = (strong >= .3 * strong.max(axis=1)[:, None]).argmax(axis=1)
    s = {}
    for o in O_ALL:
        idx = fp + o; ok = (idx >= 0) & (idx < nt); P = pw[ii, np.clip(idx, 0, nt - 1), :]; den = P.sum(axis=1)
        s[o] = np.where(ok & (den > 0), (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1), np.nan)
    return fp, s


def mp_metrics(cf, cl):
    """Multipath-only CIR = Full - LoS. Excess delay of MP peak vs LoS peak (taps), MP/LoS power at Full fp and LoS fp."""
    n, nt, _ = cf.shape; ii = np.arange(n); mp = cf - cl
    Pm = (np.abs(mp) ** 2).sum(axis=2); Pl = (np.abs(cl) ** 2).sum(axis=2)
    fpf, _ = profile(cf); fpl, _ = profile(cl)
    lo = np.clip(fpl - 4, 0, nt - 1); out = {k: np.empty(n) for k in ['mp_peak_excess_tap', 'mp_wmean_excess_tap', 'mlr_fp_full_db', 'mlr_fp_los_db', 'mlr_peak_db', 'mp_s_fp']}
    for i in range(n):
        a, b = lo[i], min(nt, fpl[i] + 41); tl = a + int(np.argmax(Pl[i, a:b])); tm = a + int(np.argmax(Pm[i, a:b]))
        w = Pm[i, a:min(nt, fpl[i] + 17)]; tt = np.arange(a, a + len(w))
        out['mp_peak_excess_tap'][i] = tm - tl; out['mp_wmean_excess_tap'][i] = float(np.sum((tt - tl) * w) / max(w.sum(), 1e-300))
        f = fpf[i]; out['mlr_fp_full_db'][i] = 10 * np.log10(max(Pm[i, f], 1e-300) / max(Pl[i, f], 1e-300))
        out['mlr_fp_los_db'][i] = 10 * np.log10(max(Pm[i, fpl[i]], 1e-300) / max(Pl[i, fpl[i]], 1e-300))
        out['mlr_peak_db'][i] = 10 * np.log10(max(Pm[i, a:b].max(), 1e-300) / max(Pl[i, a:b].max(), 1e-300))
        pm = np.abs(mp[i, f]) ** 2; out['mp_s_fp'][i] = (pm[0] - pm[1]) / max(pm.sum(), 1e-300)
    out['fp_full'] = fpf; out['fp_los'] = fpl; out['fp_shift_tap'] = fpf - fpl
    return out


def model_profile(model, states, case):
    rows = []
    for k in range(0, len(states), 128):
        h = model.spectrum(states[k:k + 128], case, gradient=False)[0]; fp, s = profile(cir_of(h)); rows.append((fp, s))
    fp = np.concatenate([r[0] for r in rows]); s = {o: np.concatenate([r[1][o] for r in rows]) for o in O_ALL}
    return fp, s


def decompose(F, K, H, a, w, u, em, ep):
    """Same exact recursion as d1_core.decompose; measurement injections split by channel (r/s) and by the state row
    they are injected into (POS = x,y ; PSI = psi,b). Components sum exactly to ep."""
    n, J = a.shape; Ka = np.where(a[..., None, None], K, 0.0); Aup = D.I4 - Ka @ H
    q = np.zeros((n, J, 4))
    for k in range(1, n): q[k] = em[k] - (np.einsum('jab,jb->ja', F[k], ep[k - 1]) - w[k][None])
    q[..., 2] = D.wrap(q[..., 2])
    ell = ep - (np.einsum('njab,njb->nja', Aup, em) + np.einsum('njab,njb->nja', Ka, u)); ell[..., 2] = D.wrap(ell[..., 2])
    z = np.zeros((n, J, 4)); rows_pos = np.array([1, 1, 0, 0.]); rows_psi = 1 - rows_pos
    inj = lambda ch, rows: Ka[..., :, ch] * u[..., ch][..., None] * rows
    specs = {'INIT': (z, z, em[0]), 'PROCESS': (-np.broadcast_to(w[:, None, :], (n, J, 4)), z, np.zeros((J, 4))), 'LIN': (q, ell, np.zeros((J, 4))),
             'U_R_POS': (z, inj(0, rows_pos), np.zeros((J, 4))), 'U_R_PSI': (z, inj(0, rows_psi), np.zeros((J, 4))),
             'U_S_POS': (z, inj(1, rows_pos), np.zeros((J, 4))), 'U_S_PSI': (z, inj(1, rows_psi), np.zeros((J, 4)))}
    out = {}
    for name, (im, ip, init) in specs.items():
        c = np.empty((n, J, 4)); prev = None
        for k in range(n):
            cm = init.copy() + im[0] if k == 0 else np.einsum('jab,jb->ja', F[k], prev) + im[k]
            c[k] = np.einsum('jab,jb->ja', Aup[k], cm) + ip[k]; prev = c[k]
        out[name] = c
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    FT = MR.feature_table(); tr = FT[(FT.channel == 'full') & (FT.route != held)]
    models = {(y, k): MR.hgb(tr, MR.EXIST if k == 'EX' else MR.EXIST + MR.DS, y) for y in ['e_r', 'e_s'] for k in ['EX', 'EXDS']}
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    model = V.SourceFFD(); names = list(ARMS); J = len(names)
    # ---------- (B) per-packet CIR / model profile table (all poses) ----------
    ids_all = pd.DataFrame(json.loads((V.ROOT / case['samples_path']).read_text()))
    Hf = np.load(V.ROOT / case['full_path'], mmap_mode='r', allow_pickle=False); Hl = np.load(V.ROOT / case['los_path'], mmap_mode='r', allow_pickle=False)
    blocks = []
    for k in range(0, len(Hf), 128):
        cf = cir_of(Hf[k:k + 128, :, :, 0]); cl = cir_of(Hl[k:k + 128, :, :, 0]); m = mp_metrics(cf, cl)
        _, sf = profile(cf); _, sl = profile(cl)
        for o in O_ALL: m[f'sF_{o:+d}'] = sf[o]; m[f'sL_{o:+d}'] = sl[o]
        blocks.append(pd.DataFrame(m))
    PK = pd.concat(blocks, ignore_index=True); PK['pose_id'] = ids_all.pose_id.to_numpy(int)
    gt = np.column_stack([ids_all.x, ids_all.y, np.radians(ids_all.yaw_body_deg)])
    for tag, dpsi in [('GT', 0.), ('GTp1', 1.), ('GTm1', -1.)]:
        st = gt.copy(); st[:, 2] += math.radians(dpsi); fp, s = model_profile(model, st, case)
        PK[f'fpM_{tag}'] = fp
        for o in O_ALL: PK[f'sM{tag}_{o:+d}'] = s[o]
    f = feat[(feat.case == a.case) & (feat.channel == 'full')].set_index('pose_id').loc[PK.pose_id]
    assert np.nanmax(np.abs(PK['sF_+0'].to_numpy() - f.s_fp.to_numpy())) < 1e-9
    for col in ['e_s', 'e_r', 'log_fp_power']: PK[col] = f[col].to_numpy()
    PK['case'] = a.case; PK['route'] = held
    # ---------- (A) recursive decomposition ----------
    rows_attr, rows_pair, rows_score, rows_gain, qa, prior_rows = [], [], [], [], [], []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n = len(t); b_true = math.radians(V.BIAS_LEVELS[bias])
        gi = pd.Series(np.arange(len(gt)), index=PK.pose_id.to_numpy()).loc[ids].to_numpy()
        yaw_qa = float(np.max(np.abs(D.wrap(gt[gi, 2] - truth[:, 2])))); xy_qa = float(np.max(np.abs(gt[gi, :2] - truth[:, :2]))); print('GT_QA', yaw_qa, xy_qa, flush=True)
        truth4 = np.column_stack([truth, np.full(n, b_true)])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float); e = d[['e_r', 'e_s']].to_numpy(float)
        fx = FT[(FT.case == a.case) & (FT.channel == ch)].set_index('pose_id').loc[ids]
        pred = {(y, k): m_.predict(fx[MR.EXIST if k == 'EX' else MR.EXIST + MR.DS]) for (y, k), m_ in models.items()}
        mu0, R0b = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        MU = np.repeat(mu0[:, None, :], J, axis=1).copy(); RR = np.repeat(R0b[:, None], J, axis=1).copy()
        for j, nm in enumerate(names):
            mr, ms = ARMS[nm]
            if mr: MU[:, j, 0] = e[:, 0] if mr == 'ORACLE' else pred[('e_r', mr)]
            if ms: MU[:, j, 1] = e[:, 1] if ms == 'ORACLE' else pred[('e_s', ms)]
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool); Xm = np.empty((n, J, 4))
        F = np.zeros((n, J, 4, 4)); K = np.zeros((n, J, 4, 2)); H = np.zeros((n, J, 2, 4)); w = np.zeros((n, 4)); em = np.zeros((n, J, 4)); Pm = np.zeros((n, J, 4, 4))
        for k in range(n):
            if k:
                ds_, gy, dt = float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k])
                for j in range(J):
                    F[k, j] = transition(x[j], ds_, gy, dt)[1]; x[j], P[j] = V.predict_one(x[j], P[j], ds_, gy, dt)
                wk = truth4[k] - transition(truth4[k - 1], ds_, gy, dt)[0]; wk[2] = D.wrap(wk[2]); w[k] = wk
            h, Hk = model.batch(x, case); em[k] = D.err(x, truth4[k]); Pm[k] = P; Xm[k] = x
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P; acc[k] = yes; K[k] = Kk; H[k] = Hk
        ep = D.err(X, truth4[:, None, :]); u = e[:, None, :] - MU; m = t >= 30
        comps = decompose(F, K, H, acc, w, u, em, ep); tot = sum(comps.values())
        closure = max(float(np.max(np.abs(D.wrap(tot[..., 2] - ep[..., 2])))), float(np.max(np.abs(tot[..., :2] - ep[..., :2]))))
        anc = np.asarray(case['anchor'], float)
        uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True)
        qf = {'heading_deg': lambda c: c[..., 2] * DEG, 'radial_cm': lambda c: (c[..., 0] * uh[:, None, 0] + c[..., 1] * uh[:, None, 1]) * 100}
        merged = {'INIT': comps['INIT'], 'PROCESS': comps['PROCESS'], 'LIN': comps['LIN'], 'U_R': comps['U_R_POS'] + comps['U_R_PSI'], 'U_S': comps['U_S_POS'] + comps['U_S_PSI']}
        for qn, fq in qf.items():
            Tq = fq(tot)[m]
            for cn, c in comps.items():
                Cq = fq(c)[m]
                for j, nm in enumerate(names):
                    rows_attr.append({'case': a.case, 'bias': bias, 'arm': nm, 'quantity': qn, 'component': cn, 'contrib': float(np.mean(Cq[:, j] * Tq[:, j])),
                                      'ms': float(np.mean(Cq[:, j] ** 2)), 'mean': float(np.mean(Cq[:, j])), 'total_ms': float(np.mean(Tq[:, j] ** 2))})
            for c1 in merged:
                for c2 in merged:
                    A1 = fq(merged[c1])[m]; A2 = fq(merged[c2])[m]
                    for j, nm in enumerate(names):
                        rows_pair.append({'case': a.case, 'bias': bias, 'arm': nm, 'quantity': qn, 'c1': c1, 'c2': c2, 'value': float(np.mean(A1[:, j] * A2[:, j]))})
        sc = V.MC.score(X, C, t, truth, b_true)
        for j, nm in enumerate(names):
            sel = m & acc[:, j]; sr = np.sqrt(RR[:, j, 0, 0]); ss = np.sqrt(RR[:, j, 1, 1])
            rows_score.append({'case': a.case, 'bias': bias, 'arm': nm, **sc[j], 'accepted_fraction': float(acc[m, j].mean()), 'closure': closure,
                               'u_r_rms_cm': float(np.sqrt(np.mean(u[m, j, 0] ** 2)) * 100), 'u_s_rms': float(np.sqrt(np.mean(u[m, j, 1] ** 2))),
                               'u_r_mean_cm': float(np.mean(u[m, j, 0]) * 100), 'u_s_mean': float(np.mean(u[m, j, 1])), 'corr_ur_us': float(np.corrcoef(u[m, j, 0], u[m, j, 1])[0, 1])})
            rows_gain.append({'case': a.case, 'bias': bias, 'arm': nm, 'Kpsi_r_deg_per_sig': float(np.median(np.abs(K[sel, j, 2, 0] * sr[sel])) * DEG),
                              'Kpsi_s_deg_per_sig': float(np.median(np.abs(K[sel, j, 2, 1] * ss[sel])) * DEG), 'Hs_psi_med': float(np.median(np.abs(H[sel, j, 1, 2]))),
                              'Hs_rad_med_per_m': float(np.median(np.abs(H[sel, j, 1, 0] * uh[sel, 0] + H[sel, j, 1, 1] * uh[sel, 1]))),
                              'prior_sig_psi_deg': float(np.median(np.sqrt(Pm[sel, j, 2, 2])) * DEG)})
        series = pd.DataFrame({'case': a.case, 'bias': bias, 'k': np.arange(n), 't_s': t, 'pose_id': ids})
        for j, nm in enumerate(names):
            series[f'{nm}__herr'] = ep[:, j, 2] * DEG; series[f'{nm}__u_r_cm'] = u[:, j, 0] * 100; series[f'{nm}__u_s'] = u[:, j, 1]
            for cn in ['U_R_POS', 'U_R_PSI', 'U_S_POS', 'U_S_PSI', 'LIN']: series[f'{nm}__{cn}_h'] = comps[cn][:, j, 2] * DEG
        # prior state of BASE (j=0): LoS-model profile at x^- for the LUT comparison
        fp, s = model_profile(model, Xm[:, 0, :3], case)
        series['fpM_prior'] = fp; series['prior_psi_err_deg'] = em[:, 0, 2] * DEG
        series['prior_rad_err_cm'] = (em[:, 0, 0] * uh[:, 0] + em[:, 0, 1] * uh[:, 1]) * 100
        for o in O_ALL: series[f'sMprior_{o:+d}'] = s[o]
        prior_rows.append(series); qa.append({'case': a.case, 'bias': bias, 'closure': closure, 'gt_yaw_qa_rad': yaw_qa, 'gt_xy_qa_m': xy_qa})
        print('HP_DONE', stem, 'closure', closure, flush=True)
    out = V.OUT
    PK.to_csv(out / f'{a.case}_HP_PACKETS.csv.gz', index=False, compression='gzip')
    pd.concat(prior_rows).to_csv(out / f'{a.case}_HP_SERIES.csv.gz', index=False, compression='gzip')
    for nm, rows in [('HP_ATTR', rows_attr), ('HP_PAIR', rows_pair), ('HP_SCORES', rows_score), ('HP_GAIN', rows_gain), ('HP_QA', qa)]:
        pd.DataFrame(rows).to_csv(out / f'{a.case}_{nm}.csv', index=False)
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
