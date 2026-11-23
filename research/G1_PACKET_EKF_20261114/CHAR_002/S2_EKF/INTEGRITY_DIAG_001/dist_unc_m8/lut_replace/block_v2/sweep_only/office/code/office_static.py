"""Office applicability of the sweep block (RT, static, LoS route poses of O01 / O02 / O03; DIAGNOSTIC).
Office stations: 25 LoS stations on a 2-D layout (1.5 m spacing), anchor (5, 2.2). Block = per-station 36-yaw curve, all 19 psi harmonics,
coefficients interpolated in (x, y) by Delaunay-linear interpolation (nearest station outside the hull); psi analytic.
  interp limit : block from LoS curves (s_fp - e_s)  vs  s_LoS at route poses    -> can this station density reproduce LoS between stations?
  SWB-office   : block from s_full curves             vs  s_full
  FFD only     : s_LoS                                vs  s_full
  FFD + krige  : s_LoS + kriging of station labels e_s (office hyperparameters from O3_INFO)  vs  s_full
Reported per distance bin: RMS, heading-equivalent mean (deg, using a = d s_LoS / d psi from the route table), share outside the hull."""
import json, numpy as np, pandas as pd
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
O = "/home/claude/office"; A = np.array([5., 2.2]); K = 19; kk = np.arange(K)
S = pd.read_csv(f"{O}/OFFICE_SWEEP_FEATURES.csv.gz"); S = S[S.los].sort_values(["station", "yaw_deg"])
R = pd.read_csv(f"{O}/OFFICE_ROUTE_FEATURES.csv.gz"); R = R[R.los].reset_index(drop=True)
info = json.load(open(f"{O}/O3_INFO.json")); KP = {int(k): v["params"] for k, v in info["krige_office"].items()}
st = S.groupby("station").agg(x=("x_eval", "first"), y=("y_eval", "first"), rho=("rho", "first")).reset_index(); P = st[["x", "y"]].to_numpy()
def coefs(col):
    C = np.array([np.fft.rfft(g[col].to_numpy())[:K] for _, g in S.groupby("station")]); return np.c_[C.real, C.imag]
S["sL"] = S.s_fp - S.e_s
blocks = {}
for nm, col in (("interp limit", "sL"), ("SWB-office", "s_fp")):
    V = coefs(col); blocks[nm] = (LinearNDInterpolator(P, V), NearestNDInterpolator(P, V))
def evalb(nm, x, y, psi):
    lin, near = blocks[nm]; q = np.c_[x, y]; V = lin(q); bad = np.isnan(V[:, 0]); V[bad] = near(q[bad]); c = V[:, :K] + 1j * V[:, K:]
    w = np.r_[1., 2 * np.ones(K - 2), 1.] / 36; e = np.exp(1j * kk[None] * (psi[:, None] + np.pi)); return np.sum(w * np.real(c * e), 1), bad
wrap = lambda a: (a + np.pi) % (2 * np.pi) - np.pi
X3 = np.c_[S.x_eval, S.y_eval, np.radians(S.yaw_deg)]; ES = S.e_s.to_numpy(); EDG = np.array([0., 3., 6., 10.]); BS = np.clip(np.searchsorted(EDG, S.rho, side="right") - 1, 0, 2)
def krige(q, rho):
    b = int(np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2)); lx, ly, lp, nug = KP[b]; m = BS == b; Xt, yt = X3[m], ES[m]; mu0 = yt.mean()
    d = np.abs(Xt[:, 0] - q[0]) / lx + np.abs(Xt[:, 1] - q[1]) / ly + np.abs(wrap(Xt[:, 2] - q[2])) / lp; idx = np.argsort(d)[:150]; Xi = Xt[idx]
    Kc = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
    wv = np.linalg.solve((1 - nug) * Kc + nug * np.eye(len(idx)), (1 - nug) * np.exp(-d[idx])); return mu0 + wv @ (yt[idx] - mu0)
rows = []
for r, g in R.groupby("route"):
    x, y, psi = g.x_eval.to_numpy(), g.y_eval.to_numpy(), np.radians(g.yaw_deg.to_numpy()); s = g.s_fp.to_numpy(); sL = s - g.e_s.to_numpy(); a = g.a.to_numpy()
    rho = np.hypot(x - A[0], y - A[1]); b = np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2)
    mL, bad = evalb("interp limit", x, y, psi); mS, _ = evalb("SWB-office", x, y, psi); kr = np.array([krige(q, rr) for q, rr in zip(np.c_[x, y, psi], rho)])
    for nm, pred, ref in (("interp limit (vs LoS)", mL, sL), ("SWB-office", mS, s), ("FFD only", sL, s), ("FFD + krige", sL + kr, s)):
        e = ref - pred
        for q in range(3):
            m = b == q
            if m.any(): rows.append(dict(route=r, bin=["<3 m", "3-6 m", ">=6 m"][q], arm=nm, n=int(m.sum()), rms=np.sqrt(np.mean(e[m]**2)), head_eq=np.degrees(-np.mean(e[m] * a[m]) / np.mean(a[m]**2)), outside=bad[m].mean()))
D = pd.DataFrame(rows); D.to_csv("OFFICE_STATIC.csv", index=False)
A_ = D.groupby(["bin", "arm"], sort=False).apply(lambda q: pd.Series(dict(n=q.n.sum(), rms=np.sqrt(np.average(q.rms**2, weights=q.n)), head_eq=np.average(q.head_eq, weights=q.n), outside=np.average(q.outside, weights=q.n)))).reset_index()
pd.set_option("display.width", 200); print(A_.round(4).to_string(index=False))
print(D[D.arm.isin(["SWB-office", "FFD + krige"])].pivot_table(index=["route", "bin"], columns="arm", values="rms").round(4).to_string())
