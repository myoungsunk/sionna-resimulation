"""3-state FG (no gyro-bias node): Vector3 pose (x, y, psi) per packet; odom between consecutive poses; one joint [r, s] factor per accepted packet.

Model = ekf3 with nstate=3: same transition, same Q, same frozen R (EKF Reff) and the EKF accept mask.
g0()        : lag=1, one GN step at the EKF prior  -> must equal EKF (equivalence gate)
run_isam()  : lag=inf causal (iSAM2, no marginalization); records latest-node estimate and marginal covariance
"""
import math, time
from functools import partial
import numpy as np
import gtsam
import ekf3

EPS = 1e-10  # odom covariance is rank 2 (no lateral noise); regularize for an invertible noise model


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def X(k):
    return gtsam.symbol('x', k)


def odom_cov(x, ds, gy, dt, N, lateral=0.):
    _, F, G = ekf3.transition(x, ds, gy, dt)
    C = G @ ekf3.q_input(ds, dt, N, 3) @ G.T
    if lateral:
        nv = np.array([-math.sin(x[2]), math.cos(x[2]), 0.]); return C + lateral ** 2 * np.outer(nv, nv) + 1e-14 * np.eye(3)
    return C + EPS * np.eye(3)


def odom_err(ds, gy, dt, this, v, H):
    xp = v.atVector(this.keys()[0]); xn = v.atVector(this.keys()[1])
    y, F, _ = ekf3.transition(xp, ds, gy, dt)
    e = xn - y; e[2] = wrap(e[2])
    if H is not None:
        H[0] = -F; H[1] = np.eye(3)
    return e


def meas_err(hfun, z, mu, this, v, H):
    x = v.atVector(this.keys()[0]); h, J = hfun(x)
    if H is not None:
        H[0] = J
    return h + mu - z


def meas_err_row(hfun, j, z, mu, this, v, H):
    x = v.atVector(this.keys()[0]); h, J = hfun(x)
    if H is not None:
        H[0] = J[j:j + 1]
    return np.array([h[j] + mu - z])


def prior_err(x0, this, v, H):
    e = v.atVector(this.keys()[0]) - x0; e[2] = wrap(e[2])
    if H is not None:
        H[0] = np.eye(3)
    return e


def gauss(C):
    return gtsam.noiseModel.Gaussian.Covariance(np.asarray(C, float))


def g0(pkt, ek, hfun, N, lateral=0.):
    """lag=1, one GN step linearized at the EKF prior. Returns x, P per packet."""
    x, P = pkt["x0"][:3].astype(float).copy(), pkt["P0"][:3, :3].astype(float).copy()
    A, C = gtsam.symbol('a', 0), gtsam.symbol('c', 0)
    xs, Ps = [], []
    for k in range(len(pkt["t"])):
        g = gtsam.NonlinearFactorGraph(); v = gtsam.Values()
        if k == 0:
            g.add(gtsam.CustomFactor(gauss(P), [C], partial(prior_err, x))); v.insert(C, x); keys = [C]
        else:
            ds, gy, dt = (float(pkt[q][k]) for q in ("ds", "gy", "dt"))
            g.add(gtsam.CustomFactor(gauss(P), [A], partial(prior_err, x)))
            g.add(gtsam.CustomFactor(gauss(odom_cov(x, ds, gy, dt, N, lateral)), [A, C], partial(odom_err, ds, gy, dt)))
            v.insert(A, x); v.insert(C, ekf3.transition(x, ds, gy, dt)[0]); keys = [A, C]
        if ek["mask"][k]:
            g.add(gtsam.CustomFactor(gauss(ek["Reff"][k]), [C], partial(meas_err, hfun, pkt["z"][k], pkt["muMB"][k])))
        lin = g.linearize(v); info, eta = lin.hessian(gtsam.Ordering(keys))
        dl = np.linalg.solve(info, eta); cov = np.linalg.inv(info)
        sl = slice(0, 3) if len(keys) == 1 else slice(3, 6)
        x = v.atVector(C) + dl[sl]; x[2] = wrap(x[2]); P = cov[sl, sl]; P = (P + P.T) / 2
        xs.append(x.copy()); Ps.append(P.copy())
    return np.array(xs), np.array(Ps)


def run_isam(pkt, ek, hfun, N, thr=1e-3, nmax=None, budget_s=None, counter=None, split=False, lateral=0.):
    """lag=inf causal: iSAM2 with QR, relinearizeSkip=1. Returns latest-node x, P, per-step update time, relin/reelim counts."""
    p = gtsam.ISAM2Params(); p.setFactorization("QR"); p.setRelinearizeThreshold(thr); p.relinearizeSkip = 1
    isam = gtsam.ISAM2(p)
    n = len(pkt["t"]) if nmax is None else min(nmax, len(pkt["t"]))
    xs, Ps, tu, relin, reelim = [], [], [], [], []
    t0 = time.time(); prev = None
    for k in range(n):
        g = gtsam.NonlinearFactorGraph(); init = gtsam.Values()
        if k == 0:
            x0 = pkt["x0"][:3].astype(float)
            g.add(gtsam.CustomFactor(gauss(pkt["P0"][:3, :3]), [X(0)], partial(prior_err, x0))); init.insert(X(0), x0)
        else:
            ds, gy, dt = (float(pkt[q][k]) for q in ("ds", "gy", "dt"))
            g.add(gtsam.CustomFactor(gauss(odom_cov(prev, ds, gy, dt, N, lateral)), [X(k - 1), X(k)], partial(odom_err, ds, gy, dt)))
            init.insert(X(k), ekf3.transition(prev, ds, gy, dt)[0])
        if ek["mask"][k] and not split:
            g.add(gtsam.CustomFactor(gauss(ek["Reff"][k]), [X(k)], partial(meas_err, hfun, pkt["z"][k], pkt["muMB"][k])))
        if ek["mask"][k] and split:   # range and s as two 1D factors; same joint-NIS accept mask
            for j in (0, 1):
                g.add(gtsam.CustomFactor(gtsam.noiseModel.Isotropic.Sigma(1, float(np.sqrt(ek["Reff"][k][j, j]))), [X(k)], partial(meas_err_row, hfun, j, pkt["z"][k][j], pkt["muMB"][k][j])))
        s = time.time(); r = isam.update(g, init); tu.append(time.time() - s)
        relin.append(r.getVariablesRelinearized()); reelim.append(r.getVariablesReeliminated())
        xk = isam.calculateEstimateVector(X(k)) if hasattr(isam, "calculateEstimateVector") else isam.calculateEstimate().atVector(X(k))
        Pk = isam.marginalCovariance(X(k))
        xs.append(np.array(xk)); Ps.append(np.array(Pk)); prev = np.array(xk)
        if budget_s is not None and time.time() - t0 > budget_s:
            break
    return dict(x=np.array(xs), P=np.array(Ps), t_update=np.array(tu), relin=np.array(relin), reelim=np.array(reelim), wall=time.time() - t0)
