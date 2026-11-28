"""Which measurement drives the K=156 MAP away from truth? Batch MAP (LM) of the graph up to K with real vs synthetic-white measurements."""
import json, numpy as np, gtsam
from functools import partial
from common import *
import ekf3, fg3, surrogate as S
cond, K = "B0", 156
an = env()["spec"]["anchor"]; p = packet(cond, 10, "R5"); T = truth("R5"); N = ekf3.GYRO_N[cond]
ek = ekf3.replay(p, S.sur_h, cond, nstate=3, anchor=an); rng = np.random.default_rng(0)
def solve(hfun, zfun, rs_scale=1., use=("r", "s")):
    G = gtsam.NonlinearFactorGraph(); v = gtsam.Values(); x0 = p["x0"][:3].astype(float)
    G.add(gtsam.CustomFactor(fg3.gauss(p["P0"][:3, :3]), [fg3.X(0)], partial(fg3.prior_err, x0)))
    for k in range(K + 1):
        v.insert(fg3.X(k), ek["x"][k])
        if k:
            ds, gy, dt = (float(p[q][k]) for q in ("ds", "gy", "dt"))
            G.add(gtsam.CustomFactor(fg3.gauss(fg3.odom_cov(ek["x"][k - 1], ds, gy, dt, N)), [fg3.X(k - 1), fg3.X(k)], partial(fg3.odom_err, ds, gy, dt)))
        if ek["mask"][k]:
            z = zfun(k); R = ek["Reff"][k].copy(); R[1, 1] *= rs_scale
            for j, nm in ((0, "r"), (1, "s")):
                if nm in use:
                    G.add(gtsam.CustomFactor(gtsam.noiseModel.Isotropic.Sigma(1, float(np.sqrt(R[j, j]))), [fg3.X(k)], partial(fg3.meas_err_row, hfun, j, z[j], p["muMB"][k][j])))
    lm = gtsam.LevenbergMarquardtParams(); lm.setLinearSolverType("MULTIFRONTAL_QR"); lm.setMaxIterations(200)
    r = gtsam.LevenbergMarquardtOptimizer(G, v, lm).optimize(); a = np.array([r.atVector(fg3.X(k)) for k in range(K + 1)])
    e = a - T[:K + 1]; e[:, 2] = fg3.wrap(e[:, 2]); pe = np.linalg.norm(e[:, :2], axis=1)
    return dict(pos_err_at_K=round(float(pe[-1]), 3), pos_rmse_0K=round(float(np.sqrt(np.mean(pe**2))), 3), yaw_err_at_K_deg=round(float(np.degrees(e[-1, 2])), 2))
noise = rng.standard_normal((K + 1, 2))
def z_real(k): return p["z"][k]
def z_syn(which, hfun):
    def f(k):
        h, _ = hfun(T[k]); zs = h + p["muMB"][k] + noise[k] * np.sqrt(np.diag(ek["Reff"][k])); z = p["z"][k].copy()
        for j in which: z[j] = zs[j]
        return z
    return f
cases = {
 "D0_real_surrogate": solve(S.sur_h, z_real),
 "D1_real_FFD_exact": solve(ffd_h, z_real),
 "D2_s_synthetic_white": solve(S.sur_h, z_syn([1], S.sur_h)),
 "D3_range_synthetic_white": solve(S.sur_h, z_syn([0], S.sur_h)),
 "D4_both_synthetic_white": solve(S.sur_h, z_syn([0, 1], S.sur_h)),
 "D5_range_only_real": solve(S.sur_h, z_real, use=("r",)),
 "D6_real_Rss_x5": solve(S.sur_h, z_real, rs_scale=5.),
 "D7_real_Rss_x20": solve(S.sur_h, z_real, rs_scale=20.),
}
for k, v in cases.items(): print(k, v)
json.dump(cases, open(OUT + "/diag_r5_meas_B0_K156.json", "w"), indent=1)
