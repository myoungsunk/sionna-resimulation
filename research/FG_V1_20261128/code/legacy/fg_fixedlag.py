"""Fixed-lag (sliding window) FG on R2/B0/seed10, H2 model, EKF accept mask. Report time/step, FFD calls/step, diff vs EKF."""
import sys, time, numpy as np, gtsam
W = float(sys.argv[1]); sys.argv = ['x', '1']
exec(open('/home/claude/fgv1/scripts/fg_smoke.py').read().split("mask = ekf")[0])
CNT = {'ffd': 0}; _m = meas_err
def meas_err(z, mu, this, v, H):
    CNT['ffd'] += 1; return _m(z, mu, this, v, H)
mask = ekf["mask"]; Reff = ekf["Reff"]; n = len(pkt["t"])
import os; NM = int(os.environ.get("NMAX", n))
lm = gtsam.LevenbergMarquardtParams(); lm.setMaxIterations(10); lm.setLinearSolverType("MULTIFRONTAL_QR")
sm = gtsam.BatchFixedLagSmoother(W, lm)
out, tst, fcalls = [], [], []; t0 = time.time()
for k in range(NM):
    g = gtsam.NonlinearFactorGraph(); init = gtsam.Values(); ts = {}
    if k == 0:
        x0 = pkt["x0"]; g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(pkt["P0"]), [Xk(0), BK], partial(prior_err, x0)))
        init.insert(Xk(0), x0[:3]); init.insert(BK, x0[3:4])
    else:
        est = sm.calculateEstimate(); xp = est.atVector(Xk(k - 1)); b = est.atVector(BK)[0]
        ds, gy, dt = (float(pkt[q][k]) for q in ("ds", "gy", "dt"))
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(odom_cov(xp, b, ds, gy, dt)), [Xk(k - 1), Xk(k), BK], partial(odom_err, ds, gy, dt)))
        init.insert(Xk(k), core.transition(np.r_[xp, b], ds, gy, dt)[0][:3])
    if mask[k]:
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(Reff[k]), [Xk(k), BK], partial(meas_err, pkt["z"][k], pkt["muMB"][k])))
    stamps = gtsam.FixedLagSmootherKeyTimestampMap()
    stamps.insert((Xk(k), float(k))); stamps.insert((BK, float(k)))   # b_g re-stamped every step so it never leaves the window
    c0 = CNT['ffd']; s = time.time(); sm.update(g, init, stamps); tst.append(time.time() - s); fcalls.append(CNT['ffd'] - c0)
    est = sm.calculateEstimate(); out.append(np.r_[est.atVector(Xk(k)), est.atVector(BK)])
X = np.array(out); n = NM; d = X - ekf["x"][:n]; d[:, 2] = wrap(d[:, 2])
T = np.load(M.replace("m7_final_model_stage1", "gm_theta_m6/inputs") + "/R2_evaluator.npz")["truth"][:n]
e = X[:, :3] - T; e[:, 2] = wrap(e[:, 2]); ee = ekf["x"][:n, :3] - T; ee[:, 2] = wrap(ee[:, 2])
print(f"W={W:.0f}: total {time.time()-t0:.0f}s  step ms mean {1e3*np.mean(tst):.1f} max {1e3*np.max(tst):.0f}  FFD calls/step mean {np.mean(fcalls):.1f} max {np.max(fcalls)}")
print(f"   vs EKF max|dpos| {np.abs(d[:, :2]).max():.3f} m  max|dyaw| {np.degrees(np.abs(d[:, 2]).max()):.2f} deg")
print(f"   pos RMSE FG {np.sqrt(np.mean(np.sum(e[:, :2]**2, 1))):.3f} / EKF {np.sqrt(np.mean(np.sum(ee[:, :2]**2, 1))):.3f} m   yaw RMSE FG {np.degrees(np.sqrt(np.mean(e[:, 2]**2))):.2f} / EKF {np.degrees(np.sqrt(np.mean(ee[:, 2]**2))):.2f} deg")
