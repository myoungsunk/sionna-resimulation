#!/usr/bin/env python3
"""CTRL-TRAJ-07 — candidate variables / indicators for a slowly varying reflection-offset EKF state (EXPLORATORY,
label-free w.r.t. POL-XCORR-001; controlled channel only, no corpus labels).

Channel: CTRL-TRAJ-02/06 construction (sha-verified FFD banks, slab Fresnel, 1 bounce). Straight routes along x
4.2..19.8 m at y in {0.0, 0.3, 0.6}, z 0.45; mount {0, 45}; body yaw {0, 180}; scenarios LOS, LOS+C, LOS+F, LOS+W, ALL.
All offsets are defined against the LoS model at the SAME (true) pose, so they are what an EKF with an LoS h() would see
as persistent measurement bias.

Offset decomposition on the Stokes sphere (FP tap and 7-tap window):
  t = dS_LoS/dpsi (heading direction), n = S_LoS x t_hat (the only tangent direction orthogonal to heading).
  b_par = (S - S_LoS).t_hat   -> confounded with heading (same as the scalar b_s = s_fp - s_fp,LoS)
  b_n   = (S - S_LoS).n_hat   -> heading-invariant to first order (needs S2/S3 = two-port correlation)
Heading-equivalent bias of an LoS-model EKF observing: s_fp -> b_s/g_s ; Stokes FP tap -> b_par/|g_S|.
Indicators (heading-invariant candidates), all as residual vs LoS model:
  correlation-based: b_n (FP, window), dq (depolarisation q_W), offset-tap Stokes shape dS_o projected on (t, n)
  power-only      : ds_o = s(fp+o)-s(fp) (LUT-subtracted, = 'Delta s' of PJ_STEP1/USAGE_MAP), pulse-shape log P_o/P_0, dlogP_fp
Reported: magnitude vs range; along-track and yaw decorrelation; direction stability of (b_par, b_n); heading
invariance under a 2 deg prior error; tap-noise std at sigma_s = 0.03; leave-one-config-out linear R^2 for b_par / b_s.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('c6', HERE.parent / 'CTRL_TRAJ_06' / 'ctrl_traj_06.py')
C6 = importlib.util.module_from_spec(spec); spec.loader.exec_module(C6)
C2 = C6.C2
OFFS = [-2, -1, 1, 2, 3, 4]
SCEN = ['LOS', 'LOS+C', 'LOS+F', 'LOS+W', 'ALL']
YAW_D = [2, 5, 10, 20, 45]


def raw(W):
    """W (n,7,2) -> dict of raw per-pose features."""
    P = abs(W) ** 2; Pt = P.sum(-1)
    s_tap = (P[..., 0] - P[..., 1]) / Pt
    c = W[..., 0] * np.conj(W[..., 1])
    St = np.stack([P[..., 0] - P[..., 1], 2 * c.real, -2 * c.imag], -1); St = St / np.linalg.norm(St, axis=-1, keepdims=True)
    j11 = P[..., 0].sum(1); j22 = P[..., 1].sum(1); j12 = c.sum(1)
    Sw = np.stack([j11 - j22, 2 * j12.real, -2 * j12.imag], -1); Sw = Sw / np.linalg.norm(Sw, axis=-1, keepdims=True)
    q = 4 * (j11 * j22 - abs(j12) ** 2) / (j11 + j22) ** 2
    return dict(sfp=s_tap[:, 2], s_tap=s_tap, Sfp=St[:, 2], St=St, Sw=Sw, q=q, sW=(j11 - j22) / (j11 + j22),
                lpshape=np.log10(Pt / Pt[:, 2:3]), lPfp=np.log10(Pt[:, 2]))


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-15)


def frame(Lm, L0, Lp, key):
    """tangent (per deg) and normal of the LoS Stokes state at psi from psi -/+ 0.5 deg."""
    t = (Lp[key] - Lm[key]) / 1.0; S = L0[key]
    t = t - np.sum(t * S, -1, keepdims=True) * S; g = np.linalg.norm(t, axis=-1); th = unit(t); nh = unit(np.cross(S, th))
    return th, nh, g


def indicators(F, L0, th_fp, nh_fp, th_w, nh_w):
    """residuals of a scenario feature set F vs LoS L0 (same pose / heading)."""
    d = {}
    dSf = F['Sfp'] - L0['Sfp']; dSw = F['Sw'] - L0['Sw']
    d['b_s'] = F['sfp'] - L0['sfp']
    d['b_par_fp'] = np.sum(dSf * th_fp, -1); d['b_n_fp'] = np.sum(dSf * nh_fp, -1)
    d['b_par_w'] = np.sum(dSw * th_w, -1); d['b_n_w'] = np.sum(dSw * nh_w, -1)
    d['dq'] = F['q'] - L0['q']; d['dsW'] = F['sW'] - L0['sW']; d['dlPfp'] = F['lPfp'] - L0['lPfp']
    for o in OFFS:
        d[f'ds_{o:+d}'] = (F['s_tap'][:, 2 + o] - F['sfp']) - (L0['s_tap'][:, 2 + o] - L0['sfp'])
        d[f'dp_{o:+d}'] = F['lpshape'][:, 2 + o] - L0['lpshape'][:, 2 + o]
        dS_o = (F['St'][:, 2 + o] - F['Sfp']) - (L0['St'][:, 2 + o] - L0['Sfp'])
        d[f'dSt_{o:+d}'] = np.sum(dS_o * th_fp, -1); d[f'dSn_{o:+d}'] = np.sum(dS_o * nh_fp, -1)
    return d


TARGETS = ['b_s', 'b_par_fp', 'b_par_w']
SETS = {
    'CORR_bn': ['b_n_fp', 'b_n_w'],
    'CORR_all': ['b_n_fp', 'b_n_w', 'dq'] + [f'dSt_{o:+d}' for o in OFFS] + [f'dSn_{o:+d}' for o in OFFS],
    'POWER_ds': [f'ds_{o:+d}' for o in OFFS],
    'POWER_all': [f'ds_{o:+d}' for o in OFFS] + [f'dp_{o:+d}' for o in OFFS] + ['dlPfp'],
}
SETS['ALL_INV'] = SETS['CORR_all'] + SETS['POWER_all']


def loco_r2(D, target, cols, lam=1e-3):
    y_all, yh_all = [], []
    for cfg in D.cfg.unique():
        tr = D[D.cfg != cfg]; te = D[D.cfg == cfg]
        X = tr[cols].to_numpy(); mu = X.mean(0); sd = X.std(0) + 1e-12; Xs = (X - mu) / sd
        A = np.c_[Xs, np.ones(len(Xs))]; w = np.linalg.solve(A.T @ A + lam * len(A) * np.eye(A.shape[1]), A.T @ tr[target].to_numpy())
        Xt = (te[cols].to_numpy() - mu) / sd; yh_all.append(np.c_[Xt, np.ones(len(Xt))] @ w); y_all.append(te[target].to_numpy())
    y = np.concatenate(y_all); yh = np.concatenate(yh_all)
    return float(1 - np.sum((y - yh) ** 2) / np.sum(y ** 2)), float(1 - np.sum((y - yh) ** 2) / np.sum((y - y.mean()) ** 2))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--bank-dir', required=True); ap.add_argument('--out', required=True); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    ant = C2.Antennas(C6.REPO, a.bank_dir); A = C6.ANCHOR
    xs = np.round(np.arange(4.2, 19.8001, 0.04), 4); n = len(xs); L = C6.noise_chol(); SIG00 = float(np.real((L @ L.conj().T)[0, 0]))
    rows, yrows, nrows, QA = [], [], [], {}
    for mount in (0, 45):
        for yb in (0, 180):
            for yr in (0.0, 0.3, 0.6):
                cfg = f'm{mount}_yb{yb}_y{yr}'
                xyz = np.column_stack([xs, np.full(n, yr), np.full(n, C6.ZR)]); rho = np.hypot(xs - A[0], yr - A[1])
                def F(dpsi, sc):
                    return raw(C6.channel_feats(ant, xyz, np.full(n, yb + mount + dpsi), C2.SCEN[sc]))
                Lm, L0, Lp, L2 = F(-0.5, 'LOS'), F(0.0, 'LOS'), F(0.5, 'LOS'), F(2.0, 'LOS')
                th_fp, nh_fp, g_fp = frame(Lm, L0, Lp, 'Sfp'); th_w, nh_w, g_w = frame(Lm, L0, Lp, 'Sw')
                g_s = (Lp['sfp'] - Lm['sfp']) / 1.0
                for sc in SCEN:
                    Fs = L0 if sc == 'LOS' else F(0.0, sc)
                    d = indicators(Fs, L0, th_fp, nh_fp, th_w, nh_w)
                    df = pd.DataFrame(d); df['cfg'] = cfg; df['mount'] = mount; df['yaw_body'] = yb; df['y'] = yr; df['scen'] = sc
                    df['x'] = xs; df['rho'] = rho; df['g_s'] = g_s; df['g_Sfp'] = g_fp; df['g_Sw'] = g_w
                    df['ehead_s_deg'] = d['b_s'] / np.where(abs(g_s) > 1e-9, g_s, np.nan)
                    df['ehead_Sfp_deg'] = d['b_par_fp'] / np.where(g_fp > 1e-9, g_fp, np.nan)
                    df['ehead_Sw_deg'] = d['b_par_w'] / np.where(g_w > 1e-9, g_w, np.nan)
                    rows.append(df)
                # heading-invariance probe: LoS truth observed with a 2 deg prior error (residual vs LoS model at psi+2)
                L15, L25 = F(1.5, 'LOS'), F(2.5, 'LOS')
                th2, nh2, _ = frame(L15, L2, L25, 'Sfp'); th2w, nh2w, _ = frame(L15, L2, L25, 'Sw')
                dh = pd.DataFrame(indicators(L0, L2, th2, nh2, th2w, nh2w)); dh['cfg'] = cfg; dh['scen'] = 'LOS_err2deg'; dh['x'] = xs; dh['rho'] = rho
                dh['mount'] = mount; dh['yaw_body'] = yb; dh['y'] = yr; rows.append(dh)
                # yaw decorrelation of the offsets (C and ALL)
                if yr == 0.3:
                    for D_ in YAW_D:
                        Lm_, L0_, Lp_ = F(D_ - 0.5, 'LOS'), F(D_, 'LOS'), F(D_ + 0.5, 'LOS')
                        a1, b1, _ = frame(Lm_, L0_, Lp_, 'Sfp'); a2, b2, _ = frame(Lm_, L0_, Lp_, 'Sw')
                        for sc in ('LOS+C', 'ALL'):
                            dd = pd.DataFrame(indicators(F(D_, sc), L0_, a1, b1, a2, b2))
                            dd['cfg'] = cfg; dd['scen'] = sc; dd['dyaw'] = D_; dd['x'] = xs; dd['rho'] = rho; yrows.append(dd)
                    # tap-noise std of each indicator at sigma_s = 0.03 (debiased taps), 30 far poses x 200 draws
                    Wl = C6.channel_feats(ant, xyz, np.full(n, yb + mount), [])
                    fr = np.where(rho > 6)[0][::8][:30]; rr = np.random.default_rng(7)
                    w0 = (rr.standard_normal((200, len(fr), 2, 7)) + 1j * rr.standard_normal((200, len(fr), 2, 7))) / np.sqrt(2)
                    Z = np.swapaxes(np.einsum('ij,...pj->...pi', L, w0), -1, -2)
                    def sstd(sn):
                        P_ = abs(Wl[fr][None] + sn * Z) ** 2; den = P_[..., 2, :].sum(-1) - 2 * sn ** 2 * SIG00
                        return float(np.median(np.std((P_[..., 2, 0] - P_[..., 2, 1]) / den, axis=0)))
                    lo, hi = 1e-10, 1e3
                    for _ in range(60):
                        mid = math.sqrt(lo * hi); lo, hi = (mid, hi) if sstd(mid) < 0.03 else (lo, mid)
                    sn = math.sqrt(lo * hi); QA[f'{cfg}_sigma_n'] = sn
                    Ln = {k: v[fr] if isinstance(v, np.ndarray) else v for k, v in L0.items()}
                    vals = []
                    for b in range(200):
                        Fn = raw(Wl[fr] + sn * Z[b])
                        vals.append(pd.DataFrame(indicators(Fn, Ln, th_fp[fr], nh_fp[fr], th_w[fr], nh_w[fr])))
                    st = pd.concat(vals).groupby(level=0).std().median()
                    st = st.to_frame('noise_std').reset_index().rename(columns={'index': 'ind'}); st['cfg'] = cfg; nrows.append(st)
                print('cfg done', cfg, flush=True)
    D = pd.concat(rows, ignore_index=True); D.to_csv(out / 'CT7_POSES.csv.gz', index=False)
    Y = pd.concat(yrows, ignore_index=True); Y.to_csv(out / 'CT7_YAW.csv.gz', index=False)
    NZ = pd.concat(nrows, ignore_index=True); NZ.to_csv(out / 'CT7_NOISE.csv', index=False)
    far = D.rho > 6
    inds = [c for c in D.columns if c.startswith(('b_', 'dq', 'dsW', 'dlPfp', 'ds_', 'dp_', 'dSt_', 'dSn_'))]
    # 1. magnitude vs range
    D['rbin'] = pd.cut(D.rho, [0, 3, 6, 10, 16.1])
    mag = D[D.scen != 'LOS'].groupby(['scen', 'rbin'], observed=True)[['b_s', 'b_par_fp', 'b_n_fp', 'b_par_w', 'b_n_w', 'dq', 'ds_+1']].agg(lambda v: float(np.sqrt(np.mean(v ** 2)))).reset_index()
    mag.to_csv(out / 'CT7_MAG_BY_RANGE.csv', index=False)
    # 2. heading-equivalent bias: s observation vs Stokes observation (window 1 m means, far)
    eh = []
    for (cfg, sc), g in D[far & D.scen.isin(['LOS+C', 'LOS+F', 'LOS+W', 'ALL'])].groupby(['cfg', 'scen']):
        k = np.arange(len(g)) // 25
        m = g.groupby(k)[['b_s', 'b_par_fp', 'b_par_w', 'g_s', 'g_Sfp', 'g_Sw']].mean()
        eh.append({'cfg': cfg, 'scen': sc, 'mount': g.mount.iloc[0],
                   'rms_ehead_s': float(np.sqrt(np.mean((m.b_s / m.g_s) ** 2))),
                   'rms_ehead_Sfp': float(np.sqrt(np.mean((m.b_par_fp / m.g_Sfp) ** 2))),
                   'rms_ehead_Sw': float(np.sqrt(np.mean((m.b_par_w / m.g_Sw) ** 2))),
                   'med_abs_g_s': float(np.median(abs(g.g_s))), 'med_g_Sfp': float(np.median(g.g_Sfp)), 'med_g_Sw': float(np.median(g.g_Sw))})
    EH = pd.DataFrame(eh); EH.to_csv(out / 'CT7_HEADING_EQUIV.csv', index=False)
    # 3. along-track decorrelation (corr of b(x) and b(x+dx), non-centred and centred), far
    dec = []
    for (cfg, sc), g in D[far & D.scen.isin(['LOS+C', 'ALL', 'LOS+F', 'LOS+W'])].groupby(['cfg', 'scen']):
        for col in ('b_s', 'b_par_fp', 'b_n_fp', 'b_par_w', 'b_n_w'):
            v = g[col].to_numpy()
            for dx in (0.2, 0.5, 1.0, 2.0, 4.0):
                k = int(round(dx / 0.04)); a_, b_ = v[:-k], v[k:]
                dec.append({'cfg': cfg, 'scen': sc, 'var': col, 'dx_m': dx, 'corr_nc': float(np.sum(a_ * b_) / np.sqrt(np.sum(a_ ** 2) * np.sum(b_ ** 2))),
                            'corr_c': float(np.corrcoef(a_, b_)[0, 1])})
            vc = v - v.mean(); ac = np.correlate(vc, vc, 'full')[len(vc) - 1:]; ac = ac / ac[0]; z = np.where(ac < np.exp(-1))[0]
            dec.append({'cfg': cfg, 'scen': sc, 'var': col, 'dx_m': -1, 'acf_1e_m': float((z[0] if len(z) else len(v)) * 0.04),
                        'mean': float(v.mean()), 'rms': float(np.sqrt(np.mean(v ** 2)))})
    DEC = pd.DataFrame(dec); DEC.to_csv(out / 'CT7_ALONG_TRACK.csv', index=False)
    # 4. yaw decorrelation (non-centred corr between offset at yaw and yaw+dyaw, same positions), far
    base = D[(D.y == 0.3) & D.scen.isin(['LOS+C', 'ALL'])]
    yd = []
    for (cfg, sc, dy), g in Y[Y.rho > 6].groupby(['cfg', 'scen', 'dyaw']):
        b0 = base[(base.cfg == cfg) & (base.scen == sc) & (base.rho > 6)]
        for col in ('b_s', 'b_par_fp', 'b_n_fp', 'b_par_w', 'b_n_w'):
            u, v = b0[col].to_numpy(), g[col].to_numpy()
            yd.append({'cfg': cfg, 'scen': sc, 'dyaw': dy, 'var': col, 'corr_nc': float(np.sum(u * v) / np.sqrt(np.sum(u ** 2) * np.sum(v ** 2))),
                       'rms_ratio': float(np.sqrt(np.mean(v ** 2) / np.mean(u ** 2)))})
    YD = pd.DataFrame(yd); YD.to_csv(out / 'CT7_YAW_DECORR.csv', index=False)
    # 5. direction stability of (b_par, b_n) on the sphere, far
    ds_ = []
    for (cfg, sc), g in D[far & D.scen.isin(['LOS+C', 'LOS+F', 'LOS+W', 'ALL'])].groupby(['cfg', 'scen']):
        for lvl in ('fp', 'w'):
            bp, bn = g[f'b_par_{lvl}'].to_numpy(), g[f'b_n_{lvl}'].to_numpy(); k = np.arange(len(bp)) // 25
            mp_, mn_ = pd.Series(bp).groupby(k).mean().to_numpy(), pd.Series(bn).groupby(k).mean().to_numpy()
            phi = np.arctan2(mn_, mp_); R_ = abs(np.mean(np.exp(1j * phi)))
            ds_.append({'cfg': cfg, 'scen': sc, 'level': lvl, 'corr_par_n': float(np.corrcoef(bp, bn)[0, 1]),
                        'frac_energy_n': float(np.sum(bn ** 2) / np.sum(bp ** 2 + bn ** 2)),
                        'phi_mean_deg': float(np.degrees(np.angle(np.mean(np.exp(1j * phi))))), 'phi_circ_std_deg': float(np.degrees(np.sqrt(-2 * np.log(max(R_, 1e-12)))))})
    DS = pd.DataFrame(ds_); DS.to_csv(out / 'CT7_DIRECTION.csv', index=False)
    # 6. indicator table: contamination rms (far), heading-error leakage at 2 deg (LoS), noise std, invariance ratio, window SNR
    it = []
    nz = NZ.groupby('ind').noise_std.median()
    for col in inds:
        r = {'ind': col, 'leak_2deg_rms': float(np.sqrt(np.mean(D[far & (D.scen == 'LOS_err2deg')][col] ** 2))), 'noise_std_s003': float(nz.get(col, np.nan))}
        for sc in ('LOS+C', 'LOS+F', 'LOS+W', 'ALL'):
            r[f'rms_{sc}'] = float(np.sqrt(np.mean(D[far & (D.scen == sc)][col] ** 2)))
        r['leak_over_C'] = r['leak_2deg_rms'] / max(r['rms_LOS+C'], 1e-15)
        r['snr_C_win25'] = r['rms_LOS+C'] / max(r['noise_std_s003'] / 5.0, 1e-15)
        it.append(r)
    IT = pd.DataFrame(it); IT.to_csv(out / 'CT7_INDICATORS.csv', index=False)
    # 7. LOCO linear prediction of the heading-confounded offsets from heading-invariant indicator sets
    pr = []
    for sc_set, scs in (('C', ['LOS+C']), ('ALL', ['ALL']), ('POOLED', ['LOS+C', 'LOS+F', 'LOS+W', 'ALL'])):
        sub = D[far & D.scen.isin(scs)].copy()
        k = sub.groupby(['cfg', 'scen']).cumcount() // 25
        win = sub.assign(k=k).groupby(['cfg', 'scen', 'k'])[TARGETS + SETS['ALL_INV']].mean().reset_index()
        for level, data in (('pose', sub), ('win1m', win)):
            for tg in TARGETS:
                for sn, cols in SETS.items():
                    r2nc, r2c = loco_r2(data, tg, cols)
                    pr.append({'scen': sc_set, 'level': level, 'target': tg, 'set': sn, 'n_feat': len(cols), 'R2_noncentred': r2nc, 'R2_centred': r2c})
    PR = pd.DataFrame(pr); PR.to_csv(out / 'CT7_PREDICT_LOCO.csv', index=False)
    meta = {'status': 'EXPLORATORY', 'banks': ant.receipts, 'QA': QA, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    meta['outputs'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
    (out / 'CT7_MANIFEST.json').write_text(json.dumps(meta, indent=1))
    pd.set_option('display.width', 250); pd.set_option('display.max_rows', 400); pd.set_option('display.max_columns', 30)
    print(mag.round(4).to_string(index=False))
    print(EH.groupby(['scen', 'mount'])[['rms_ehead_s', 'rms_ehead_Sfp', 'rms_ehead_Sw', 'med_abs_g_s', 'med_g_Sfp']].median().round(3).to_string())
    print(DEC[DEC.dx_m > 0].groupby(['scen', 'var', 'dx_m']).corr_nc.median().unstack().round(2).to_string())
    print(DEC[DEC.dx_m < 0].groupby(['scen', 'var'])[['acf_1e_m', 'mean', 'rms']].median().round(4).to_string())
    print(YD.groupby(['scen', 'var', 'dyaw']).corr_nc.median().unstack().round(2).to_string())
    print(DS.groupby(['scen', 'level'])[['corr_par_n', 'frac_energy_n', 'phi_circ_std_deg']].median().round(2).to_string())
    print(IT.round(4).to_string(index=False))
    print(PR.pivot_table(index=['scen', 'level', 'target'], columns='set', values='R2_noncentred').round(3).to_string())


if __name__ == '__main__':
    main()
