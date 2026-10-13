"""D6-1: controlled nonlinear covariance-vs-MC audit (USER-RUN ONLY).

This experiment does NOT load RF or inject gyro bias.  It isolates the
nonlinear mapping of an uncertain *initial heading* to travelled position.
All trajectories are propagated with the identical SE(2) arc model.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from d6_d9_common import (EKF3, arc, eval_covariance, finish, make_out,
                          ut_propagate, wrap, write_csv, THRESHOLD_3D_95, THRESHOLD_2D_95)


def commands(path: str, distance: float, count: int = 40) -> list[tuple[float, float]]:
    if distance <= 0 or count < 2:
        raise ValueError('Invalid distance/step count')
    if path == 'straight':
        return [(distance/count, 0.)]*count
    if path == 'arc90':
        return [(distance/count, (math.pi/2)/count)]*count
    if path == 'outback':
        return ([(distance/count, 0.)]*count + [(0., math.pi)] +
                [(distance/count, 0.)]*count)
    raise ValueError('Unknown path')


def batch_arc(x: np.ndarray, ds: float, a: float) -> None:
    phi = x[:, 2] + .5*a
    sc = np.sinc((.5*a)/np.pi)
    x[:, 0] += ds*sc*np.cos(phi)
    x[:, 1] += ds*sc*np.sin(phi)
    x[:, 2] = (x[:, 2]+a+np.pi)%(2*np.pi)-np.pi


def one_grid(path: str, distance: float, sigma_deg: float, draws: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    sigma = math.radians(sigma_deg)
    P0 = np.diag([.1**2, .1**2, sigma**2])
    samples = rng.normal(size=(draws, 3)) @ np.linalg.cholesky(P0).T
    f = EKF3(np.zeros(3), P0)
    u_x = np.zeros(3)
    u_P = P0.copy()
    truth = np.zeros(3)
    for ds, da in commands(path, distance):
        batch_arc(samples, ds, da)
        truth = arc(truth, ds, da)
        # Strictly zero process noise: isolate nonlinear initial-P propagation.
        f.predict(ds, da, 1., Q_input=np.zeros((2, 2)))
        # UT is applied with numerically zero increment noise by taking its
        # full deterministic augmented formulation with zero Q, analytically
        # here via a 3-state sigma-point transform (see below).
    # Recompute full-route UT from the initial Gaussian, not a statewise Q hack.
    n = 3
    lam = 1.
    L = np.linalg.cholesky(P0*(n+lam))
    sp = np.array([np.zeros(3), *[L[:, j] for j in range(n)],
                   *[-L[:, j] for j in range(n)]])
    wm = np.full(2*n+1, 1/(2*(n+lam)))
    wm[0] = lam/(n+lam)
    wc = wm.copy()
    wc[0] += 2.
    for ds, da in commands(path, distance):
        sp = np.asarray([arc(v, ds, da) for v in sp])
    u_x = np.einsum('i,ij->j', wm, sp)
    u_x[2] = math.atan2(float(wm@np.sin(sp[:, 2])), float(wm@np.cos(sp[:, 2])))
    residual = sp-u_x
    residual[:, 2] = np.arctan2(np.sin(residual[:, 2]), np.cos(residual[:, 2]))
    u_P = np.einsum('i,ij,ik->jk', wc, residual, residual)
    actual = samples-truth
    actual[:, 2] = np.arctan2(np.sin(actual[:, 2]), np.cos(actual[:, 2]))
    mu_e = np.mean(actual, axis=0)
    measured_cov = np.cov(actual.T, ddof=1)
    # Exact nonlinear mean/covariance of R(delta-yaw)*nominal displacement
    # with independent initial x/y Gaussian noise and zero process noise.
    D = truth[:2].copy()
    turn = np.array([-D[1], D[0]])
    q = math.exp(-sigma**2)
    exact_mean_xy = math.exp(-sigma**2/2)*D
    exact_cov_xy = (.01*np.eye(2) +
                    (.5*(1+q*q)-q)*np.outer(D,D) +
                    (.5*(1-q*q))*np.outer(turn,turn))
    exact_estimate = np.r_[exact_mean_xy,truth[2]]
    # Second-order Taylor moment propagation; NOT a Gaussian truth label.
    second_estimate = np.r_[D*(1-.5*sigma**2),truth[2]]
    second_cov = P0.copy()
    second_cov[:2,:2] = (.01*np.eye(2) + sigma**2*np.outer(turn,turn) +
                          .5*sigma**4*np.outer(D,D))
    second_cov[:2,2] = sigma**2*turn
    second_cov[2,:2] = second_cov[:2,2]
    def pos_coverage(estimate, cov):
        diff=samples[:,:2]-np.asarray(estimate)[:2]
        P=np.asarray(cov)[:2,:2]
        nees=np.einsum('ni,ni->n',diff,np.linalg.solve(P,diff.T).T)
        return float(np.mean(nees<=THRESHOLD_2D_95))
    def skew(arr):
        centered=arr-np.mean(arr)
        sd=np.std(centered)
        return float(np.mean((centered/sd)**3)) if sd>1e-14 else 0.
    mc_forward=np.asarray(actual[:,:2]@np.array([math.cos(truth[2]),math.sin(truth[2])]))
    mc_lateral=np.asarray(actual[:,:2]@np.array([-math.sin(truth[2]),math.cos(truth[2])]))
    axes = {'forward': np.array([math.cos(truth[2]), math.sin(truth[2])]),
            'lateral': np.array([-math.sin(truth[2]), math.cos(truth[2])])}
    def project(P, a):
        return float(a@P[:2, :2]@a)
    err_ekf = samples - f.x
    err_ut = samples - u_x
    err_ekf[:, 2] = np.arctan2(np.sin(err_ekf[:, 2]), np.cos(err_ekf[:, 2]))
    err_ut[:, 2] = np.arctan2(np.sin(err_ut[:, 2]), np.cos(err_ut[:, 2]))
    cov_ekf = np.linalg.solve(f.P, err_ekf.T).T
    cov_ut = np.linalg.solve(u_P, err_ut.T).T
    cover_ekf = np.mean(np.einsum('ij,ij->i',err_ekf,cov_ekf) <= THRESHOLD_3D_95)
    cover_ut = np.mean(np.einsum('ij,ij->i',err_ut,cov_ut) <= THRESHOLD_3D_95)
    output = dict(path=path, travel_distance_m=distance, sigma_heading_deg=sigma_deg,
                  draws=draws, seed=seed,
                  true_final_yaw_deg=math.degrees(truth[2]),
                  mc_forward_mean_m=float(mu_e[:2]@axes['forward']),
                  mc_lateral_mean_m=float(mu_e[:2]@axes['lateral']),
                  ekf_forward_mean_m=float((f.x-truth)[:2]@axes['forward']),
                  ut_forward_mean_m=float((u_x-truth)[:2]@axes['forward']),
                  mc_pose95_under_ekf=float(cover_ekf),
                  mc_pose95_under_ut=float(cover_ut),
                  mc_position95_under_ekf=pos_coverage(f.x,f.P),
                  mc_position95_under_ut=pos_coverage(u_x,u_P),
                  mc_position95_under_second_order=pos_coverage(second_estimate,second_cov),
                  mc_position95_under_analytic=pos_coverage(exact_estimate,exact_cov_xy),
                  mc_forward_skewness=skew(mc_forward),
                  mc_lateral_skewness=skew(mc_lateral),
                  mc_forward_second_order_mean_m=float((second_estimate-truth)[:2]@axes['forward']),
                  analytic_forward_mean_m=float((exact_estimate-truth)[:2]@axes['forward']))
    for axis_name, a in axes.items():
        for label, C in [('mc', measured_cov), ('ekf', f.P), ('ut', u_P),
                         ('second_order', second_cov), ('analytical', exact_cov_xy)]:
            output[f'{label}_{axis_name}_variance_m2'] = project(C, a)
    output['mc_over_ekf_forward_var'] = (
        output['mc_forward_variance_m2']/max(output['ekf_forward_variance_m2'], 1e-20))
    # Analytic exact mean in the straight path is a model-consistency check.
    output['straight_exact_expected_forward_mean_m'] = (
        distance*(math.exp(-sigma**2/2)-1) if path=='straight' else None)
    return output


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--out', type=Path, required=True)
    a.add_argument('--draws', type=int, default=5000)
    a.add_argument('--seed', type=int, default=20261013)
    a.add_argument('--paths', nargs='+', choices=['straight','arc90','outback'],
                   default=['straight','arc90','outback'])
    a.add_argument('--distances', type=float, nargs='+', default=[1., 5., 10., 20.])
    a.add_argument('--heading-std-deg', type=float, nargs='+', default=[5.,10.,17.,20.,30.])
    args = a.parse_args()
    if args.draws < 100 or any(v <= 0 for v in args.distances+args.heading_std_deg):
        raise ValueError('Invalid MC grid')
    rows = [one_grid(p, d, s, args.draws, args.seed)
            for p in args.paths for d in args.distances for s in args.heading_std_deg]
    out = make_out(args.out)
    file = out/'D6_MC_MOMENT_COMPARISON.csv'
    write_csv(file, rows)
    finish(out, 'D6_MC', vars(args)|{'out':str(out)}, [file], caveats=[
        'Pure model-consistent initial-heading experiment, no RF or gyro bias',
        'Includes 2D position-ellipse coverage, analytical and Taylor second-order moments',
        'Individual Monte Carlo particles are NOT independent RF environments'])
    print('D6_MC_EXPLORATORY_DONE', str(file))


if __name__ == '__main__':
    main()
