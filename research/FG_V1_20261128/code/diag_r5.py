"""Diagnose the early R5 excursion: compare graph cost at iSAM2 / EKF / truth / batch-converged solutions."""
import sys, json, numpy as np, gtsam, time
from functools import partial
from common import *
import ekf3, fg3, surrogate as S
cond = sys.argv[1] if len(sys.argv) > 1 else "B0"; K = int(sys.argv[2]) if len(sys.argv) > 2 else 156
model = sys.argv[3] if len(sys.argv) > 3 else "sur"
hfun = S.sur_h if model == "sur" else ffd_h
an = env()["spec"]["anchor"]; p = packet(cond, 10, "R5"); T = truth("R5"); N = ekf3.GYRO_N[cond]
ek = ekf3.replay(p, hfun, cond, nstate=3, anchor=an)
X = fg3.X; gauss = fg3.gauss
prm = gtsam.ISAM2Params(); prm.setFactorization("QR"); prm.setRelinearizeThreshold(1e-3); prm.relinearizeSkip = 1
isam = gtsam.ISAM2(prm); G = gtsam.NonlinearFactorGraph(); tags = []; prev = None; causal = []
for k in range(K + 1):
    g = gtsam.NonlinearFactorGraph(); init = gtsam.Values()
    if k == 0:
        x0 = p["x0"][:3].astype(float); f = gtsam.CustomFactor(gauss(p["P0"][:3, :3]), [X(0)], partial(fg3.prior_err, x0)); g.add(f); tags.append(("prior", 0)); init.insert(X(0), x0)
    else:
        ds, gy, dt = (float(p[q][k]) for q in ("ds", "gy", "dt"))
        f = gtsam.CustomFactor(gauss(fg3.odom_cov(prev, ds, gy, dt, N)), [X(k - 1), X(k)], partial(fg3.odom_err, ds, gy, dt)); g.add(f); tags.append(("odom", k))
        init.insert(X(k), ekf3.transition(prev, ds, gy, dt)[0])
    if ek["mask"][k]:
        f = gtsam.CustomFactor(gauss(ek["Reff"][k]), [X(k)], partial(fg3.meas_err, hfun, p["z"][k], p["muMB"][k])); g.add(f); tags.append(("meas", k))
    for i in range(g.size()): G.add(g.at(i))
    isam.update(g, init); prev = np.array(isam.calculateEstimate().atVector(X(k))); causal.append(prev)
causal = np.array(causal)
def vals(arr):
    v = gtsam.Values()
    for k in range(K + 1): v.insert(X(k), np.asarray(arr[k], float))
    return v
def arr(v): return np.array([v.atVector(X(k)) for k in range(K + 1)])
def breakdown(v):
    out = {"prior": 0., "odom": 0., "meas_r": 0., "meas_s": 0.}
    for i, (t, k) in enumerate(tags):
        e = G.at(i).error(v)
        if t == "meas":
            x = v.atVector(X(k)); h, _ = hfun(x); res = h + p["muMB"][k] - p["z"][k]; R = ek["Reff"][k]
            out["meas_r"] += .5 * res[0]**2 / R[0, 0]; out["meas_s"] += .5 * res[1]**2 / R[1, 1]
        else: out[t] += e
    out["total"] = G.error(v); return {a: round(float(b), 2) for a, b in out.items()}
def traj(a):
    e = a - T[:K + 1]; e[:, 2] = fg3.wrap(e[:, 2]); pe = np.linalg.norm(e[:, :2], axis=1)
    return dict(pos_err_at_K=round(float(pe[-1]), 3), pos_rmse_0K=round(float(np.sqrt(np.mean(pe**2))), 3), yaw_err_at_K_deg=round(float(np.degrees(e[-1, 2])), 2))
lm = gtsam.LevenbergMarquardtParams(); lm.setLinearSolverType("MULTIFRONTAL_QR"); lm.setMaxIterations(200); lm.setRelativeErrorTol(1e-10); lm.setAbsoluteErrorTol(1e-10)
cands = {"isam2_full_estimate_at_K": arr(isam.calculateEstimate()), "ekf_filtered": ek["x"][:K + 1], "truth": T[:K + 1]}
for name in list(cands):
    r = gtsam.LevenbergMarquardtOptimizer(G, vals(cands[name]), lm).optimize(); cands["batchLM_from_" + name] = arr(r)
res = {"cond": cond, "K": K, "model": model, "n_meas_factors": sum(t == "meas" for t, _ in tags)}
for name, a in cands.items():
    res[name] = dict(cost=breakdown(vals(a)), **traj(a)); print(name, res[name])
res["isam2_causal_latest"] = traj(causal)
json.dump(res, open(f"{OUT}/diag_r5_{cond}_K{K}_{model}.json", "w"), indent=1)
