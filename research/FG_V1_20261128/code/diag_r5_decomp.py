import json, numpy as np, gtsam
from functools import partial
from common import *
import ekf3, fg3, surrogate as S
K = 156; an = np.array(env()["spec"]["anchor"][:2]); p = packet("B0", 10, "R5"); T = truth("R5"); N = ekf3.GYRO_N["B0"]
def mapsol(hfun):
    ek = ekf3.replay(p, hfun, "B0", nstate=3, anchor=env()["spec"]["anchor"])
    G = gtsam.NonlinearFactorGraph(); v = gtsam.Values(); x0 = p["x0"][:3].astype(float)
    G.add(gtsam.CustomFactor(fg3.gauss(p["P0"][:3, :3]), [fg3.X(0)], partial(fg3.prior_err, x0)))
    for k in range(K + 1):
        v.insert(fg3.X(k), ek["x"][k])
        if k:
            ds, gy, dt = (float(p[q][k]) for q in ("ds", "gy", "dt"))
            G.add(gtsam.CustomFactor(fg3.gauss(fg3.odom_cov(ek["x"][k - 1], ds, gy, dt, N)), [fg3.X(k - 1), fg3.X(k)], partial(fg3.odom_err, ds, gy, dt)))
        if ek["mask"][k]:
            G.add(gtsam.CustomFactor(fg3.gauss(ek["Reff"][k]), [fg3.X(k)], partial(fg3.meas_err, hfun, p["z"][k], p["muMB"][k])))
    lm = gtsam.LevenbergMarquardtParams(); lm.setLinearSolverType("MULTIFRONTAL_QR"); lm.setMaxIterations(200)
    r = gtsam.LevenbergMarquardtOptimizer(G, v, lm).optimize(); return np.array([r.atVector(fg3.X(k)) for k in range(K + 1)])
out = {}
for name, hf in (("surrogate", S.sur_h), ("FFD_exact", ffd_h)):
    A = mapsol(hf); Tw = T[:K + 1]
    ths = np.radians(np.linspace(-30, 30, 6001)); best = None
    for th in ths:
        c, s = np.cos(th), np.sin(th); d = Tw[:, :2] - an; Rt = an + np.c_[c * d[:, 0] - s * d[:, 1], s * d[:, 0] + c * d[:, 1]]
        res = np.linalg.norm(A[:, :2] - Rt, axis=1); sc = np.sqrt(np.mean(res**2))
        if best is None or sc < best[1]: best = (th, sc, res)
    th, sc, res = best; yaw_err = np.degrees(fg3.wrap(A[:, 2] - Tw[:, 2]))
    out[name] = dict(MAP_pos_rmse_0K=round(float(np.sqrt(np.mean(np.sum((A[:, :2] - Tw[:, :2])**2, 1)))), 3),
                     best_fit_rigid_rotation_deg=round(float(np.degrees(th)), 2), pos_rmse_after_removing_rotation=round(float(sc), 3),
                     MAP_yaw_err_mean_deg=round(float(yaw_err.mean()), 2), MAP_yaw_err_at_K_deg=round(float(yaw_err[-1]), 2))
    print(name, out[name])
json.dump(out, open(OUT + "/diag_r5_rotation_decomposition.json", "w"), indent=1)
