"""FG smoke test on R2 / B0 / seed10, model = EKF H2 (same h, R, mask). Vector3 pose (world frame) + one constant b_g node."""
import sys, time, math, json, numpy as np, gtsam
from functools import partial
M = "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1"
sys.path.insert(0, M); import m7_replay as R7
A2 = M + "/attempt_02"; P = json.load(open(A2 + "/replay/RUN_CONTRACT.json"))["parameters"]["R2"]
env = R7.load_environment("/home/claude/fgv1/base.json"); core, model, spec = env["core"], env["model"], env["spec"]
Z = np.load(A2 + "/input_generation/inputs/B0/seed10/R2_online.npz"); pkt = {k: Z[k] for k in Z.files}
ekf = R7.replay(pkt, env, "H2", sigma_b=P["sigma_b"], condition="B0", rref_policy="own")
N = int(sys.argv[1]) if len(sys.argv) > 1 else len(pkt["t"]); MODE = sys.argv[2] if len(sys.argv) > 2 else "isam2"
wrap = lambda a: (a + np.pi) % (2 * np.pi) - np.pi
Xk = lambda k: gtsam.symbol('x', k); BK = gtsam.symbol('b', 0)
GY = math.radians(.015); EPS = 1e-10
def odom_err(ds, gy, dt, this, v, H):
    xp = v.atVector(this.keys()[0]); xn = v.atVector(this.keys()[1]); b = v.atVector(this.keys()[2])[0]
    y, F, G = core.transition(np.r_[xp, b], ds, gy, dt); e = xn - y[:3]; e[2] = wrap(e[2])
    if H is not None: H[0] = -F[:3, :3]; H[1] = np.eye(3); H[2] = -F[:3, 3:4]
    return e
def meas_err(z, mu, this, v, H):
    x = v.atVector(this.keys()[0]); b = v.atVector(this.keys()[1])[0]
    h, J = (f[0] for f in model.batch(np.r_[x, b][None], spec)); e = h + mu - z
    if H is not None: H[0] = J[:, :3]; H[1] = J[:, 3:4]
    return e
def prior_err(x0, this, v, H):
    e = np.r_[v.atVector(this.keys()[0]), v.atVector(this.keys()[1])] - x0; e[2] = wrap(e[2])
    if H is not None: H[0] = np.eye(4)[:, :3]; H[1] = np.eye(4)[:, 3:4]
    return e
def odom_cov(x, b, ds, gy, dt):
    _, F, G = core.transition(np.r_[x, b], ds, gy, dt); Q = np.diag([2e-5 * abs(ds), GY**2 * dt, 0.])
    C = (G @ Q @ G.T)[:3, :3]; return C + EPS * np.eye(3)
mask = ekf["mask"]; Reff = ekf["Reff"]
p = gtsam.ISAM2Params(); p.setFactorization("QR"); p.setRelinearizeThreshold(1e-3); p.relinearizeSkip = 1
isam = gtsam.ISAM2(p); t0 = time.time(); out = []; tstep = []
for k in range(N):
    g = gtsam.NonlinearFactorGraph(); init = gtsam.Values()
    if k == 0:
        x0 = pkt["x0"]; g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(pkt["P0"]), [Xk(0), BK], partial(prior_err, x0)))
        init.insert(Xk(0), x0[:3]); init.insert(BK, x0[3:4])
    else:
        est = isam.calculateEstimate(); xp = est.atVector(Xk(k - 1)); b = est.atVector(BK)[0]
        ds, gy, dt = (float(pkt[q][k]) for q in ("ds", "gy", "dt"))
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(odom_cov(xp, b, ds, gy, dt)), [Xk(k - 1), Xk(k), BK], partial(odom_err, ds, gy, dt)))
        init.insert(Xk(k), core.transition(np.r_[xp, b], ds, gy, dt)[0][:3])
    if mask[k]:
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(Reff[k]), [Xk(k), BK], partial(meas_err, pkt["z"][k], pkt["muMB"][k])))
    s = time.time(); isam.update(g, init); est = isam.calculateEstimate()
    xk = np.r_[est.atVector(Xk(k)), est.atVector(BK)]
    out.append(xk); tstep.append(time.time() - s)
    if k % 100 == 99: print(f"k={k+1} elapsed {time.time()-t0:.0f}s last100 mean {1e3*np.mean(tstep[-100:]):.0f} ms", flush=True)
X = np.array(out); E = ekf["x"][:N]; T = np.load(M.replace("m7_final_model_stage1", "gm_theta_m6/inputs") + "/R2_evaluator.npz")["truth"][:N]
d = X - E; d[:, 2] = wrap(d[:, 2])
print(f"N={N} total {time.time()-t0:.1f}s  step ms mean {1e3*np.mean(tstep):.1f} p95 {1e3*np.percentile(tstep,95):.1f} max {1e3*np.max(tstep):.1f}")
print("FG-causal vs EKF  max|dpos| m", np.abs(d[:, :2]).max().round(4), " max|dyaw| deg", np.degrees(np.abs(d[:, 2]).max()).round(3))
for name, A in (("EKF", E), ("FG lag=inf causal", X)):
    e = A[:, :3] - T; e[:, 2] = wrap(e[:, 2])
    print(f"{name:18s} pos RMSE {np.sqrt(np.mean(np.sum(e[:,:2]**2,1))):.3f} m  yaw RMSE {np.degrees(np.sqrt(np.mean(e[:,2]**2))):.2f} deg")
