"""Absorption of the injected P1 error ALONG THE ROUTES (truth poses), not at station poses.
Kriging is linear, so (mean correction 2b) - (mean correction S0-id) = kriging of d = e_P1 - e_S0id = h_FFD - h'_P1 at stations.
Compare that kriged d with the analytic d at the route truth poses; the leftover is what the filter sees as unabsorbed model error.
Far bin: POWER cannot represent d at all (leftover = d); kriging leftover shown as the D1 alternative.
Also reported: same leftover at station positions with psi shifted by 5 deg (off the 10 deg yaw grid)."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut2")
import stage2_static as S2, pert
from common import TRUTH, env
e0 = env(); base, spec = e0["model"], e0["spec"]; fP = pert.make(base, "P1")
d_st = np.load("ES_P1.npy") - S2.ES0; prm = {k: S2.KP[f"e_s|{k}"]["params"] for k in range(3)}; EDG = np.array([0., 3., 6., 10.]); A = np.array([10., 0.])
BI = {k: (S2.X3[S2.BIN == k], d_st[S2.BIN == k], d_st[S2.BIN == k].mean()) for k in range(3)}
def analytic(X):
    st = np.c_[X, np.zeros(len(X))]; h0, J0 = base.batch(st, spec)[:2]; h1, _ = fP(st, spec); return h0[:, 1] - h1, J0[:, 1, 2]
rows = []
def evaluate(name, X):
    rho = np.hypot(X[:, 0] - A[0], X[:, 1] - A[1]); b = np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2)
    d, a = analytic(X); kd = np.array([S2.kr_one(BI[k][0], BI[k][1], BI[k][2], q, prm[k]) for q, k in zip(X, b)])
    for k in range(3):
        m = b == k
        if not m.any(): continue
        left = (d - kd)[m]; rms = lambda v: float(np.sqrt(np.mean(v**2)))
        rows.append(dict(where=name, bin=["<3 m", "3-6 m", ">=6 m"][k], n=int(m.sum()), injected_rms=rms(d[m]), leftover_krige_rms=rms(left),
                         leftover_krige_mean=float(left.mean()), heading_equiv_mean_deg=float(np.degrees(np.mean(left * a[m]) / np.mean(a[m]**2))),
                         absorbed_frac=1 - rms(left)**2 / rms(d[m])**2))
for r in ("R2", "R4", "R5"):
    T = TRUTH[r]["truth"]; evaluate(r, T[:, :3].astype(float))
Xs = S2.X3.copy(); Xs[:, 2] += np.radians(5.); evaluate("stations_psi+5deg", Xs)
D = pd.DataFrame(rows); D.to_csv("ROUTE_ABSORB_P1.csv", index=False); pd.set_option("display.width", 250); print(D.round(4).to_string(index=False))
