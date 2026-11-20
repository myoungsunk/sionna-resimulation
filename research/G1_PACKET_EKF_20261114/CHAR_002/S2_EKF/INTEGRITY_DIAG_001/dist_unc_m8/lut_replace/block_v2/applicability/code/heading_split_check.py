"""After heading removal, does E[eps^2 | rho, a] ~ a^2 sigma_theta^2(rho) + sigma_res^2(rho) hold? (RT Corridor stations; LoS truth = FFD stands for
nadir + relative LoS model, whose error was 0.12 deg constant in nadir_ref_check.)
near/mid (rho < 6): per-station heading shift d_st from the 2-psi phase vs LoS (nadir-referenced). Smooth part dbar(rho, side): distance-weighted
local mean (Gaussian kernel in rho, 0.75 m). Scatter d_st - dbar -> sigma_theta^2. Station-to-station correlation of the scatter checked.
far (rho >= 6): block = same-psi average over +-3 columns x 5 lines, centre column excluded; residual vs that block.
Model check: eps = s_full - m, m = s_LoS(psi - dbar) (near/mid) or block (far); fit c1 a^2 + c0 per bin; compare predicted and empirical E[eps^2] in |a| quintiles."""
import numpy as np, pandas as pd
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); SW["sL"] = SW.s_fp - ES0
xs = np.sort(SW.x_eval.round(3).unique()); ys = np.sort(SW.y_eval.round(2).unique()); ps = np.sort(SW.yaw_deg.unique())
ix = np.searchsorted(xs, SW.x_eval.round(3)); iy = np.searchsorted(ys, SW.y_eval.round(2)); ip = np.searchsorted(ps, SW.yaw_deg)
def cube(v): C = np.full((len(xs), len(ys), 36), np.nan); C[ix, iy, ip] = v; return C
F, L, A = cube(SW.s_fp.values), cube(SW.sL.values), cube(SW.a.values); RHO = np.full((len(xs), len(ys)), np.nan); RHO[ix, iy] = SW.rho.values
psi = np.radians(ps); side = np.sign(xs - 10.0); k2 = np.fft.rfftfreq(36, 1 / 36)
def chi(s): c = 2 * np.mean(s * np.cos(2 * psi)); d = 2 * np.mean(s * np.sin(2 * psi)); return 0.5 * np.arctan2(c, -d)
def rot(s, d):  # s(psi - d) by Fourier shift (d in rad)
    return np.fft.irfft(np.fft.rfft(s) * np.exp(-1j * k2 * d), n=36)
w = lambda a: (a + np.pi / 2) % np.pi - np.pi / 2
st = [(i, j) for i in range(len(xs)) for j in range(len(ys))]
d = {(i, j): w(chi(F[i, j]) - chi(L[i, j])) for (i, j) in st}
near = [(i, j) for (i, j) in st if RHO[i, j] < 6]
def dbar(i, j, bw=0.75):
    q = [(a, b) for (a, b) in near if side[a] == side[i] and (a, b) != (i, j)]; r = np.array([RHO[a, b] for a, b in q]); v = np.array([d[a, b] for a, b in q])
    wt = np.exp(-0.5 * ((r - RHO[i, j]) / bw)**2); return np.sum(wt * v) / np.sum(wt)
rows, eps_rows = [], []
for (i, j) in st:
    r = RHO[i, j]
    if r < 6:
        db = dbar(i, j); m = rot(L[i, j], db); am = rot(A[i, j], db); rows.append(dict(i=i, j=j, rho=r, d=np.degrees(d[i, j]), dbar=np.degrees(db), scat=np.degrees(w(d[i, j] - db))))
        m0 = L[i, j]; a0 = A[i, j]
    else:
        cols = [c for c in range(i - 3, i + 4) if 0 <= c < len(xs) and side[c] == side[i] and c != i]
        m = np.nanmean(np.stack([F[c, b] for c in cols for b in range(len(ys))]), axis=0); am = np.fft.irfft(1j * k2 * np.fft.rfft(m), n=36); m0 = L[i, j]; a0 = A[i, j]
    for kk in range(36): eps_rows.append(dict(rho=r, a=am[kk], eps=F[i, j, kk] - m[kk], a0=a0[kk], eps0=F[i, j, kk] - m0[kk]))
R = pd.DataFrame(rows); E = pd.DataFrame(eps_rows)
R["bin"] = pd.cut(R.rho, [0, 1.5, 3, 4.5, 6]); 
print(R.groupby("bin", observed=True).agg(n=("d", "size"), d_mean=("d", "mean"), d_sd=("d", "std"), dbar_mean=("dbar", "mean"), scatter_sd=("scat", "std")).round(2).to_string())
# station-to-station correlation of the scatter (next column, same line)
S = R.set_index(["i", "j"]).scat; pr = [(S[(i, j)], S[(i + 1, j)]) for (i, j) in S.index if (i + 1, j) in S.index and side[i] == side[i + 1]]
pr = np.array(pr); print("lag-1 (0.45 m) corr of heading scatter:", round(np.corrcoef(pr.T)[0, 1], 2), "  raw d:", round(np.corrcoef(np.array([(d[(i, j)], d[(i + 1, j)]) for (i, j) in S.index if (i + 1, j) in S.index and side[i] == side[i + 1]]).T)[0, 1], 2))
E["bin"] = pd.cut(E.rho, [0, 3, 6, 10], labels=["<3 m", "3-6 m", ">=6 m"]); out = []
for b, g in E.groupby("bin", observed=True):
    for lab, ee, aa in (("before (s_full - s_LoS)", g.eps0, g.a0), ("after heading removal", g.eps, g.a)):
        lo = np.abs(aa) < .3; c0 = np.mean(ee[lo]**2); c1 = max(np.sum(aa**2 * (ee**2 - c0)) / np.sum(aa**4), 0)
        q = pd.qcut(np.abs(aa), 5, labels=False); emp = (ee**2).groupby(q).mean().values; mod = (c1 * aa**2 + c0).groupby(q).mean().values
        out.append(dict(bin=b, case=lab, mean_eps=round(ee.mean(), 4), sigma_theta_deg=round(np.degrees(np.sqrt(c1)), 2), sigma_res=round(np.sqrt(c0), 4),
                        rms_eps=round(np.sqrt(np.mean(ee**2)), 4), quintile_ratio_emp_over_model=np.round(emp / mod, 2).tolist()))
pd.set_option("display.width", 250); print(pd.DataFrame(out).to_string(index=False))
