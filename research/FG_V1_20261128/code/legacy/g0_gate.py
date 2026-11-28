"""G0 gate: FG with lag=1 (previous posterior as Gaussian prior), one GN step linearized at the EKF prior. Compare x and P with EKF H2."""
import sys, numpy as np, gtsam, time
sys.argv = ['x', '1']
exec(open('/home/claude/fgv1/scripts/fg_smoke.py').read().split("mask = ekf")[0])
mask = ekf["mask"]; Reff = ekf["Reff"]; n = len(pkt["t"])
def gauss_prior(mean, this, v, H):
    e = np.r_[v.atVector(this.keys()[0]), v.atVector(this.keys()[1])] - mean; e[2] = wrap(e[2])
    if H is not None: H[0] = np.eye(4)[:, :3]; H[1] = np.eye(4)[:, 3:4]
    return e
x, Pm = pkt["x0"].copy(), pkt["P0"].copy(); X, PP = [], []; t0 = time.time()
A, Bk = gtsam.symbol('a', 0), gtsam.symbol('b', 0); C = gtsam.symbol('c', 0)
for k in range(n):
    g = gtsam.NonlinearFactorGraph(); v = gtsam.Values()
    if k == 0:
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(Pm), [C, Bk], partial(gauss_prior, x))); v.insert(C, x[:3]); v.insert(Bk, x[3:4]); keys = [C, Bk]
    else:
        ds, gy, dt = (float(pkt[q][k]) for q in ("ds", "gy", "dt"))
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(Pm), [A, Bk], partial(gauss_prior, x)))
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(odom_cov(x[:3], x[3], ds, gy, dt)), [A, C, Bk], partial(odom_err, ds, gy, dt)))
        v.insert(A, x[:3]); v.insert(Bk, x[3:4]); v.insert(C, core.transition(x, ds, gy, dt)[0][:3]); keys = [A, C, Bk]
    if mask[k]:
        g.add(gtsam.CustomFactor(gtsam.noiseModel.Gaussian.Covariance(Reff[k]), [C, Bk], partial(meas_err, pkt["z"][k], pkt["muMB"][k])))
    lin = g.linearize(v)                                  # linearized at the EKF prior (one GN step)
    info, eta = lin.hessian(gtsam.Ordering(keys)); dl = np.linalg.solve(info, eta); cov = np.linalg.inv(info)
    idx = [0, 1, 2, 3] if len(keys) == 2 else [3, 4, 5, 6]
    xn = np.r_[v.atVector(C), v.atVector(Bk)] + dl[idx]; xn[2] = wrap(xn[2])
    x, Pm = xn, cov[np.ix_(idx, idx)]; Pm = (Pm + Pm.T) / 2; X.append(x.copy()); PP.append(Pm.copy())
X, PP = np.array(X), np.array(PP); d = X - ekf["x"]; d[:, 2] = wrap(d[:, 2])
print(f"n={n} {time.time()-t0:.1f}s  max|dx| pos {np.abs(d[:, :2]).max():.2e} m  yaw {np.abs(d[:, 2]).max():.2e} rad  b_g {np.abs(d[:, 3]).max():.2e}")
print(f"max|dP| {np.abs(PP - ekf['P']).max():.2e}  rel {np.max(np.abs(PP - ekf['P']) / (np.abs(ekf['P']) + 1e-12)):.2e}")
