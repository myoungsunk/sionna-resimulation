"""Shared helpers for the pre-diagnostics: synthetic-white observations and run metrics."""
import numpy as np
from common import *
import ekf3, fg3, surrogate as S
SIGMA_B = 0.005
def make_white(pkt, T, seed, rows=(0, 1), hfun=None):
    """Replace z[:, rows] by h(truth) + muMB + N(0, Reff) with Reff = R + diag(0, sigma_b^2) (sigma_b constant, so Reff is filter-independent)."""
    hfun = hfun or S.sur_h; rng = np.random.default_rng(10007 * seed + 17); q = dict(pkt); z = pkt["z"].copy()
    for k in range(len(z)):
        R = pkt["R"][k].copy(); R[1, 1] += SIGMA_B ** 2; h, _ = hfun(T[k]); zz = h + pkt["muMB"][k] + rng.standard_normal(2) * np.sqrt(np.diag(R))
        for j in rows: z[k, j] = zz[j]
    q["z"] = z; return q
def metrics(x, P, T):
    e = x - T[:len(x)]; e[:, 2] = fg3.wrap(e[:, 2]); nees = np.array([e[i] @ np.linalg.solve(P[i], e[i]) for i in range(len(e))])
    pe = np.linalg.norm(e[:, :2], axis=1)
    return dict(anees=float(nees.mean()), log_anees=float(np.log(nees.mean())), cover95=float(np.mean(nees <= 7.815)),
                pos_rmse=float(np.sqrt(np.mean(pe ** 2))), yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[:, 2] ** 2)))), pos_max=float(pe.max()))
