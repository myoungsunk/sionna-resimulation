"""Nadir-referenced polarization reading (near/mid only, rho < 6 m), RT Corridor stations.
chi estimators on each 36-yaw sweep: zero crossings (rising and falling averaged), peak/trough (parabolic), 2-psi Fourier phase.
Heading shift vs nadir: dchi_tot = chi(station) - chi(nadir). Split: LoS part from the FFD *difference* chi_FFD(st) - chi_FFD(nadir),
multipath part = remainder. Polarization ratio: L(st)/L(nadir) divided by the same FFD ratio.
FFD used only as a relative (antenna-level) change; robustness tested with FFD' errors P1 (+5 deg global), P2 (+1 dB), P4 (rotation error growing with
off-nadir angle, 0 at nadir to +3 deg at rho = 6 m)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut2")
import pert
from common import env
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); SW["sL"] = SW.s_fp - ES0
SW["pos"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str); SW = SW.sort_values(["pos", "yaw_deg"])
e0 = env(); base, spec = e0["model"], e0["spec"]
def ffd_variant(kind, X):
    st = np.c_[X, np.zeros(len(X))]
    if kind == "P4":
        rho = np.hypot(st[:, 0] - 10, st[:, 1]); st = st.copy(); st[:, 2] += np.radians(3.0 * np.clip(rho / 6, 0, 1)); return base.batch(st, spec)[0][:, 1]
    if kind == "FFD": return base.batch(st, spec)[0][:, 1]
    return pert.make(base, kind)(st, spec)[0]
psi_deg = np.arange(-180, 180, 10.); psi = np.radians(psi_deg)
w = lambda a: (a + 90) % 180 - 90
def chi_fourier(s):
    c = 2 * np.mean(s * np.cos(2 * psi)); d = 2 * np.mean(s * np.sin(2 * psi)); return np.degrees(0.5 * np.arctan2(c, -d)), np.hypot(c, d)
def chi_zc(s):
    """s ~ L sin2(chi - psi): falling crossings (ds/dpsi < 0 in psi) at psi = chi (+180), rising at chi +- 90. Average all four, mapped to chi."""
    ss = np.r_[s, s[0]]; pp = np.r_[psi_deg, 180.]; est = []
    for k in range(36):
        if ss[k] == 0 or ss[k] * ss[k + 1] < 0:
            p0 = pp[k] + 10 * ss[k] / (ss[k] - ss[k + 1]); falling = ss[k] > ss[k + 1]
            est.append(np.radians(2 * (p0 if falling else p0 - 90)))
    return np.degrees(0.5 * np.angle(np.mean(np.exp(1j * np.array(est))))) if est else np.nan
def chi_peak(s):
    """maxima at psi = chi - 45 (+180), minima at chi + 45; parabolic refinement."""
    est = []
    for sign, off in ((1, 45.), (-1, -45.)):
        v = sign * s
        for k in range(36):
            if v[k] > v[k - 1] and v[k] >= v[(k + 1) % 36]:
                y0, y1, y2 = v[k - 1], v[k], v[(k + 1) % 36]; dp = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) * 10
                est.append(np.radians(2 * (psi_deg[k] + dp + off)))
    return np.degrees(0.5 * np.angle(np.mean(np.exp(1j * np.array(est)))))
G = {p: g for p, g in SW.groupby("pos")}; pos = list(G); X = {p: np.c_[np.full(36, G[p].x_eval.iloc[0]), np.full(36, G[p].y_eval.iloc[0]), np.radians(G[p].yaw_deg.values)] for p in pos}
rho = {p: G[p].rho.iloc[0] for p in pos}; nadir = min(pos, key=lambda p: rho[p])
rows = []
for kind in ("FFD", "P1", "P2", "P4"):
    ref = {p: ffd_variant(kind, X[p]) for p in pos}
    for p in pos:
        if rho[p] >= 6 or p == nadir: continue
        F, Lt, R = G[p].s_fp.values, G[p].sL.values, ref[p]; Fn, Rn = G[nadir].s_fp.values, ref[nadir]
        for est_name, est in (("zero", chi_zc), ("peak", chi_peak), ("fourier", lambda s: chi_fourier(s)[0])):
            tot = w(est(F) - est(Fn)); los_rel = w(est(R) - est(Rn)); mp_est = w(tot - los_rel); mp_true = w(est(F) - est(Lt))
            rows.append(dict(ffd=kind, est=est_name, rho=rho[p], dchi_tot=tot, los_part=los_rel, mp_est=mp_est, mp_true=mp_true))
        Lm = chi_fourier(F)[1] / chi_fourier(Fn)[1] / (chi_fourier(R)[1] / chi_fourier(Rn)[1]); Ltrue = chi_fourier(F)[1] / chi_fourier(Lt)[1]
        rows.append(dict(ffd=kind, est="L_ratio", rho=rho[p], mp_est=Lm, mp_true=Ltrue))
D = pd.DataFrame(rows); D.to_csv("NADIR_REF_CHECK.csv", index=False); D["bin"] = pd.cut(D.rho, [0, 3, 6], labels=["<3 m", "3-6 m"]); out = []
for (e, f, b), g in D.groupby(["est", "ffd", "bin"], observed=True):
    d = g.mp_est - g.mp_true
    out.append(dict(est=e, ffd=f, bin=b, n=len(g), mp_true=f"{g.mp_true.mean():+.3f} ± {g.mp_true.std():.3f}", mp_est=f"{g.mp_est.mean():+.3f} ± {g.mp_est.std():.3f}",
                    err=f"{d.mean():+.3f} ± {d.std():.3f}", corr=round(np.corrcoef(g.mp_est, g.mp_true)[0, 1], 3),
                    tot_sd=(round(g.dchi_tot.std(), 2) if e != "L_ratio" else np.nan), los_part_sd=(round(g.los_part.std(), 2) if e != "L_ratio" else np.nan)))
pd.set_option("display.width", 250); print(pd.DataFrame(out).to_string(index=False))
