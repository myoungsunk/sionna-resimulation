"""LoS-free reference for the mid range (3-6 m): per anchor side and y line, fit chi(rho) by a polynomial (degree 1, 2) to
   1-3 m stations (measured s_full, small multipath) and >=6 m stations after same-line +-3 column averaging (heading part averages out);
predict chi_LoS at 3-6 m, then estimated multipath shift = chi_full - prediction. LoS truth used only for evaluation.
Outputs: LOSFREE_CHI_INTERP.csv (per mid station and degree), LOSFREE_CHI_INTERP_SUMMARY.csv."""
import numpy as np, pandas as pd
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); SW["sL"] = SW.s_fp - ES0
xs = np.sort(SW.x_eval.round(3).unique()); ys = np.sort(SW.y_eval.round(2).unique()); ps = np.sort(SW.yaw_deg.unique())
ix = np.searchsorted(xs, SW.x_eval.round(3)); iy = np.searchsorted(ys, SW.y_eval.round(2)); ip = np.searchsorted(ps, SW.yaw_deg)
def cube(v): C = np.full((len(xs), len(ys), 36), np.nan); C[ix, iy, ip] = v; return C
F, L = cube(SW.s_fp.values), cube(SW.sL.values); RHO = np.full((len(xs), len(ys)), np.nan); RHO[ix, iy] = SW.rho.values
psi = np.radians(ps); side = np.sign(xs - 10.0)
def chi(s): c = 2 * np.mean(s * np.cos(2 * psi)); d = 2 * np.mean(s * np.sin(2 * psi)); return np.degrees(0.5 * np.arctan2(c, -d))
w = lambda a: (a + 90) % 180 - 90; rows = []
for j in range(len(ys)):
    for sd in (-1, 1):
        cols = [i for i in range(len(xs)) if side[i] == sd]; Xr, Cr = [], []
        for i in cols:
            r = RHO[i, j]
            if 1 <= r < 3: Xr.append(r); Cr.append(chi(F[i, j]))
            elif r >= 6:
                q = [c for c in range(i - 3, i + 4) if c in cols]; Xr.append(r); Cr.append(chi(np.nanmean(F[q, j], axis=0)))
        Xr, Cr = np.array(Xr), np.unwrap(np.radians(np.array(Cr)) * 2) / 2
        for deg in (1, 2):
            b = np.polyfit(Xr, np.degrees(Cr), deg)
            for i in cols:
                r = RHO[i, j]
                if 3 <= r < 6:
                    pred = np.polyval(b, r); cl = chi(L[i, j]); cf = chi(F[i, j])
                    rows.append(dict(deg=deg, x=xs[i], y=ys[j], side=sd, rho=r, los_pred_err=w(pred - cl), dchi_true=w(cf - cl), dchi_est=w(cf - pred)))
D = pd.DataFrame(rows); D.to_csv("LOSFREE_CHI_INTERP.csv", index=False); out = []
for deg, g in D.groupby("deg"):
    out.append(dict(deg=deg, n=len(g), los_pred_err_mean=g.los_pred_err.mean(), los_pred_err_sd=g.los_pred_err.std(), dchi_true_mean=g.dchi_true.mean(), dchi_true_sd=g.dchi_true.std(),
                    dchi_est_mean=g.dchi_est.mean(), dchi_est_sd=g.dchi_est.std(), corr_est_true=np.corrcoef(g.dchi_est, g.dchi_true)[0, 1]))
S = pd.DataFrame(out); S.to_csv("LOSFREE_CHI_INTERP_SUMMARY.csv", index=False); print(S.round(3).to_string(index=False))
