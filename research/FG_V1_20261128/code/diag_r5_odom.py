"""(a) truth-odom residuals vs modeled odom noise, (c) MAP with inflated odom noise, (d) s/range residual mean at truth in the excursion window."""
import json, numpy as np, gtsam
from functools import partial
from common import *
import ekf3, fg3, surrogate as S
cond, K = "B0", 156
an = env()["spec"]["anchor"]; p = packet(cond, 10, "R5"); T = truth("R5"); N = ekf3.GYRO_N[cond]
ek = ekf3.replay(p, S.sur_h, cond, nstate=3, anchor=an)
# (a) residual of truth under the odom model, in the body frame (along / lateral / yaw)
rows = []
for k in range(1, len(T)):
    ds, gy, dt = (float(p[q][k]) for q in ("ds", "gy", "dt"))
    y, F, G = ekf3.transition(T[k - 1], ds, gy, dt); e = T[k] - y; e[2] = fg3.wrap(e[2])
    c, s = np.cos(T[k - 1, 2]), np.sin(T[k - 1, 2]); along = c * e[0] + s * e[1]; lat = -s * e[0] + c * e[1]
    Q = ekf3.q_input(ds, dt, N, 3); rows.append((along, lat, e[2], np.sqrt(Q[0, 0]), np.sqrt(Q[1, 1]), ds))
R = np.array(rows)
def st(a): return dict(rms=float(np.sqrt(np.mean(a**2))), p95=float(np.percentile(abs(a), 95)))
res = {"truth_odom_residual_per_step": dict(along_m=st(R[:, 0]), lateral_m=st(R[:, 1]), yaw_deg=st(np.degrees(R[:, 2])),
       model_sigma_along_m_median=float(np.median(R[:, 3])), model_sigma_yaw_deg_median=float(np.degrees(np.median(R[:, 4]))),
       model_sigma_lateral_m=float(np.sqrt(fg3.EPS)), ds_median_m=float(np.median(R[:, 5])),
       ratio_along=float(np.sqrt(np.mean(R[:, 0]**2)) / np.median(R[:, 3])), ratio_yaw=float(np.sqrt(np.mean(R[:, 2]**2)) / np.median(R[:, 4])))}
print(json.dumps(res, indent=1))
# (d) measurement residuals at truth in windows
win = {}
for a, b in ((0, 100), (100, 160), (160, 260), (260, 500)):
    rr, ss = [], []
    for k in range(a, b):
        if not ek["mask"][k]: continue
        h, _ = S.sur_h(T[k]); r = p["z"][k] - h - p["muMB"][k]; rr.append(r[0] / np.sqrt(ek["Reff"][k][0, 0])); ss.append(r[1] / np.sqrt(ek["Reff"][k][1, 1]))
    win[f"k{a}-{b}"] = dict(range_whitened_mean=round(float(np.mean(rr)), 2), s_whitened_mean=round(float(np.mean(ss)), 2),
                            s_lag1_autocorr=round(float(np.corrcoef(ss[:-1], ss[1:])[0, 1]), 2), n=len(ss), truth_x=f"{T[a,0]:.1f}-{T[b-1,0]:.1f}")
res["meas_residual_at_truth"] = win; print(json.dumps(win, indent=1))
# (c) MAP of the graph up to K with odom noise as modeled vs inflated (empirical along/lateral/yaw from (a))
def solve(scale_along=1., lat_sigma=None, yaw_scale=1.):
    G = gtsam.NonlinearFactorGraph(); v = gtsam.Values(); x0 = p["x0"][:3].astype(float)
    G.add(gtsam.CustomFactor(fg3.gauss(p["P0"][:3, :3]), [fg3.X(0)], partial(fg3.prior_err, x0)))
    for k in range(K + 1):
        v.insert(fg3.X(k), ek["x"][k])
        if k:
            ds, gy, dt = (float(p[q][k]) for q in ("ds", "gy", "dt"))
            _, F, Gm = ekf3.transition(ek["x"][k - 1], ds, gy, dt); Q = ekf3.q_input(ds, dt, N, 3); Q = np.diag([Q[0, 0] * scale_along**2, Q[1, 1] * yaw_scale**2])
            C = Gm @ Q @ Gm.T
            if lat_sigma is not None:
                th = ek["x"][k - 1, 2]; nrm = np.array([-np.sin(th), np.cos(th), 0.]); C = C + lat_sigma**2 * np.outer(nrm, nrm)
            C = C + fg3.EPS * np.eye(3)
            G.add(gtsam.CustomFactor(fg3.gauss(C), [fg3.X(k - 1), fg3.X(k)], partial(fg3.odom_err, ds, gy, dt)))
        if ek["mask"][k]:
            G.add(gtsam.CustomFactor(fg3.gauss(ek["Reff"][k]), [fg3.X(k)], partial(fg3.meas_err, S.sur_h, p["z"][k], p["muMB"][k])))
    lm = gtsam.LevenbergMarquardtParams(); lm.setLinearSolverType("MULTIFRONTAL_QR"); lm.setMaxIterations(200)
    r = gtsam.LevenbergMarquardtOptimizer(G, v, lm).optimize(); a = np.array([r.atVector(fg3.X(k)) for k in range(K + 1)])
    e = a - T[:K + 1]; pe = np.linalg.norm(e[:, :2], axis=1); return dict(pos_err_at_K=round(float(pe[-1]), 3), pos_rmse_0K=round(float(np.sqrt(np.mean(pe**2))), 3))
ra, rl, ry = res["truth_odom_residual_per_step"]["ratio_along"], res["truth_odom_residual_per_step"]["lateral_m"]["rms"], res["truth_odom_residual_per_step"]["ratio_yaw"]
cases = {"as_modeled": solve(), "along_x_empirical": solve(scale_along=max(ra, 1.)), "lateral_empirical": solve(lat_sigma=rl),
         "yaw_x_empirical": solve(yaw_scale=max(ry, 1.)), "all_empirical": solve(scale_along=max(ra, 1.), lat_sigma=rl, yaw_scale=max(ry, 1.))}
res["MAP_vs_odom_noise_K156"] = cases; print(json.dumps(cases, indent=1))
json.dump(res, open(OUT + "/diag_r5_odom_B0.json", "w"), indent=1)
