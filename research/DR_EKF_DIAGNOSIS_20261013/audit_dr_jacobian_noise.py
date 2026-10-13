"""D3: single-step model audit of the frozen sensor-v2 EKF (A4, A3, A1-controlled, A5).

1. F, G (transition) and H, B (odometry) vs central finite differences on straight / curve / spin / ~zero-rotation /
   large-rotation inputs, zero and non-zero calibration, known wheelbase error 0 and 0.01.
2. Empirical noise check with the FROZEN generator: one-step draws at fixed true state/increments ->
   Cov(e^-), Cov(e^-, v), Var(v) vs the filter's G Q G^T, C = -G Q B, R = B Q B (Q from measured increments),
   and Q_EKF (measured) vs Q_true (true increments). Variants: wheel+gyro noise, + slip (unmodelled).
3. Controlled linearisation test (A1): prior N(m, P) pushed through K noise-free straight/turning steps; EKF
   covariance vs exact nonlinear Monte Carlo (whitened eigenvalues, mean shift, expected pose NEES).
4. Calibration observability (A5): information the odometry pseudo-measurement gives on (b_g, SF, eps) along each
   route (true increments), singular values / weakest combination, and the EKF prior->posterior correlation.

usage: audit_dr_jacobian_noise.py [--draws 200000]
"""
import argparse
import json
import math

import numpy as np

import dr_harness as H
import dr_io as IO
import dr_consistency as DC
from dr_harness import F, V

OUT = H.HERE / 'out'
DT = 0.2
B_NOM = 0.287


def fd_jacobians(x, d, g, dt, known):
    b = B_NOM / (1 + known)
    _, Fa, Ga = F.transition(x, d, g, dt, b)
    h, Ha, Ba = F.odometry_model(x, d, g, dt, B_NOM, known)
    steps = np.array([1e-6, 1e-6, 1e-7, 1e-8, 1e-7, 1e-7])
    Ff = np.zeros((6, 6))
    Hf = np.zeros(6)
    for j in range(6):
        xp, xm = x.copy(), x.copy()
        xp[j] += steps[j]
        xm[j] -= steps[j]
        fp, fm = F.transition(xp, d, g, dt, b)[0], F.transition(xm, d, g, dt, b)[0]
        diff = fp - fm
        diff[2] = DC.wrap(diff[2])
        Ff[:, j] = diff / (2 * steps[j])
        Hf[j] = (F.odometry_model(xp, d, g, dt, B_NOM, known)[0] - F.odometry_model(xm, d, g, dt, B_NOM, known)[0]) / (2 * steps[j])
    Gf = np.zeros((6, 3))
    Bf = np.zeros(3)
    u = np.array([d, g, 0.0])
    for j, hstep in enumerate((1e-8, 1e-9, 1e-9)):
        up, um = u.copy(), u.copy()
        up[j] += hstep
        um[j] -= hstep
        fp, fm = F.transition(x, up[0], up[1], dt, b)[0], F.transition(x, um[0], um[1], dt, b)[0]
        diff = fp - fm
        diff[2] = DC.wrap(diff[2])
        Gf[:, j] = diff / (2 * hstep)
        rp = up[2] - F.odometry_model(x, up[0], up[1], dt, B_NOM, known)[0]
        rm = um[2] - F.odometry_model(x, um[0], um[1], dt, B_NOM, known)[0]
        Bf[j] = (rp - rm) / (2 * hstep)

    def err(a, f):
        scale = np.maximum(np.abs(f), 1e-6)
        return float(np.max(np.abs(a - f))), float(np.max(np.abs(a - f) / scale))
    return dict(F=err(Fa, Ff), G=err(Ga, Gf), H=err(Ha, Hf), B=err(Ba, Bf))


def jacobian_audit():
    states = dict(cal_zero=np.array([2.0, 0.3, 0.4, 0., 0., 0.]),
                  cal_level2=np.array([2.0, 0.3, -2.9, math.radians(0.2), 0.015, 0.01]),
                  cal_neg=np.array([-1.0, 4.0, 3.1, -math.radians(0.2), -0.015, -0.01]))
    inputs = dict(straight=(0.04, 0.0), curve=(0.04, math.radians(0.4)), spin=(0.0, math.radians(5.0)),
                  near_zero_rotation=(0.04, 1e-7), large_rotation=(0.04, 0.5), stop=(0.0, 0.0))
    rows, worst = [], dict(F=0., G=0., H=0., B=0.)
    for sname, x in states.items():
        for iname, (d, g) in inputs.items():
            for known in (0.0, 0.01):
                gg = g + (x[3] * DT if iname == 'near_zero_rotation' else 0.0)    # makes the corrected rate ~0
                r = fd_jacobians(x, d, gg, DT, known)
                rows.append(dict(state=sname, input=iname, known_eb=known, **{k: v for k, v in r.items()}))
                for k in worst:
                    worst[k] = max(worst[k], r[k][0])
    status = 'PASS' if max(worst.values()) < 1e-6 else 'FAIL'
    return dict(status=status, max_abs_error=worst, cases=rows,
                note='central differences; absolute error tolerance 1e-6 (entries are O(1e-3..1))')


def noise_audit(draws):
    """One-step empirical noise statistics through the frozen generator (one long sequence of identical steps)."""
    cases = dict(drive_curve=(0.04, math.radians(0.3)), drive_straight=(0.04, 0.0), spin=(0.0, math.radians(5.0)),
                 stop=(0.0, 0.0))
    worlds = dict(noise_only=dict(condition='noise_pair', params=None),
                  noise_plus_slip=dict(condition='all', params=dict(gyro_bias=0., gyro_sf=0., wheel_asymmetry=0., wheelbase=0.)))
    cfg = H.make_cfg(H.ARMS['B0'], 0, dict(wheelbase=0.0))
    x_prev = np.array([2.0, 0.3, 0.7, 0., 0., 0.])
    out = {}
    for wname, w in worlds.items():
        for cname, (ds, dth) in cases.items():
            n = draws
            t = np.arange(n + 1) * DT
            dsv = np.r_[0., np.full(n, ds)]
            dthv = np.r_[0., np.full(n, dth)]
            inputs, ev = V.generate(t, dsv, dthv, V.SensorV2Config(level=2, condition=w['condition']), 424242, w['params'])
            d, g, o = inputs['ds_odom'][1:], inputs['dtheta_gyro'][1:], inputs['dtheta_odom'][1:]
            X = np.repeat(x_prev[None], n, axis=0)
            xtrue = H.transition_vec(x_prev[None], np.array([ds]), np.array([dth]), DT, B_NOM)[0]
            xpred = H.transition_vec(X, d, g, DT, B_NOM)
            e = xtrue - xpred
            e[:, 2] = DC.wrap(e[:, 2])
            v = o - H.odometry_h_vec(X, d, g, DT, B_NOM)
            # model quantities per draw (G, B depend on the measured inputs only through tiny terms; use frozen code)
            GQG = np.zeros((6, 6))
            Cm = np.zeros(6)
            Rm = 0.0
            Qm = np.zeros(3)
            sub = np.linspace(0, n - 1, min(n, 4000)).astype(int)
            for i in sub:
                _, Fm, G = F.transition(x_prev, d[i], g[i], DT, B_NOM)
                Q = np.diag([cfg.k_s * abs(d[i]), cfg.gyro_N_rad_sqrt_s ** 2 * DT, cfg.k_theta * abs(o[i]) + cfg.k_stheta * abs(d[i])])
                _, Hm, B = F.odometry_model(x_prev, d[i], g[i], DT, B_NOM)
                GQG += G @ Q @ G.T
                Cm += -G @ Q @ B
                Rm += float(B @ Q @ B)
                Qm += np.diag(Q)
            GQG /= len(sub)
            Cm /= len(sub)
            Rm /= len(sub)
            Qm /= len(sub)
            Qtrue = np.array([cfg.k_s * abs(ds), cfg.gyro_N_rad_sqrt_s ** 2 * DT, cfg.k_theta * abs(dth) + cfg.k_stheta * abs(ds)])
            emp_cov = np.cov(e.T)
            prod = (e - e.mean(0)) * (v - v.mean())[:, None]
            emp_c = prod.mean(0)
            se_c = prod.std(0) / math.sqrt(n)
            emp_r = float(np.var(v))
            se_r = float(np.std((v - v.mean()) ** 2) / math.sqrt(n))
            se_var = np.array([np.std((e[:, i] - e[:, i].mean()) ** 2) / math.sqrt(n) for i in range(3)])
            idx = [0, 1, 2]
            gate = v * v / Rm <= 10.8276 if Rm > 0 else np.ones(n, bool)
            k4 = float(np.mean((v - v.mean()) ** 4) / emp_r ** 2) if emp_r > 0 else float('nan')

            def ratio(a, b):
                return float(a / b) if abs(b) > 0 else (float('nan') if abs(a) > 0 else 1.0)
            def z(a, b, se):
                return float((a - b) / se) if se > 0 else (0.0 if a == b else float('inf'))
            out[f'{wname}|{cname}'] = dict(
                true_increments=dict(ds=ds, dtheta=dth), n_draws=n,
                var_ratio_empirical_over_model_pose=[ratio(emp_cov[i, i], GQG[i, i]) for i in idx],
                var_z_pose=[z(emp_cov[i, i], GQG[i, i], se_var[i]) for i in idx],
                C_empirical=[float(emp_c[i]) for i in idx], C_model=[float(Cm[i]) for i in idx],
                C_ratio=[ratio(emp_c[i], Cm[i]) for i in idx], C_z=[z(emp_c[i], Cm[i], se_c[i]) for i in idx],
                C_corr_empirical=[float(emp_c[i] / math.sqrt(emp_cov[i, i] * emp_r)) if emp_cov[i, i] * emp_r > 0 else 0.0 for i in idx],
                R_empirical=emp_r, R_model=Rm, R_ratio=ratio(emp_r, Rm), R_z=z(emp_r, Rm, se_r),
                R_ratio_after_gate=ratio(float(np.var(v[gate])), Rm), gate_reject_frac=float(1 - gate.mean()),
                innovation_kurtosis=k4,
                Q_ekf_mean=Qm.tolist(), Q_true=Qtrue.tolist(), Q_ratio_ekf_over_true=[ratio(Qm[i], Qtrue[i]) for i in range(3)],
                mean_e_pose=[float(e[:, i].mean()) for i in idx], mean_v=float(v.mean()))
    # verdict on the modelled (noise_only) cases: a significant empirical EXCESS over the model (z > 4) would make the
    # filter over-confident; a significant deficit is a conservative mismatch and is reported, not failed.
    nm = {k: v for k, v in out.items() if k.startswith('noise_only')}
    excess = {k: [z for z in v['var_z_pose'] + [v['R_z']] + [abs(c) for c in v['C_z']] if z > 4] for k, v in nm.items()}
    deficit = {k: v['R_ratio'] for k, v in nm.items() if v['R_z'] < -4}
    status = 'PASS' if not any(excess.values()) else 'FAIL'
    if status == 'PASS' and deficit:
        status = 'PASS_CONSERVATIVE_MISMATCH'
    return dict(status=status, overconfident_excess_z=excess, conservative_R_ratio=deficit, cases=out,
                note=('z = (empirical - model)/standard error; |C_z| > 4 counts as a mismatch in either direction. '
                      'noise_plus_slip adds the unmodelled heavy-tailed slip (spin only); the gate is chi2_1 99.9%.'))


def propagation_linearisation(n_mc=50000, seed=99):
    """EKF vs exact MC for a prior pushed through K steps with known inputs (isolates propagation linearisation).

    input_noise=False: noise-free inputs (prior propagation only; along-track variance is only the 3 cm prior, the
    most severe case). input_noise=True: the filter's own wheel/gyro input noise is added in both EKF (G Q G^T) and MC.
    """
    rng = np.random.default_rng([H.DIAG_NAMESPACE, seed, 3])
    rows = []
    cal_std = np.array(H.P0_CAL_DEFAULT)
    k_s, gN2 = 2e-5, math.radians(0.015) ** 2
    grid = [(noise, cal_on) for noise in (False, True) for cal_on in (False, True)]
    for path_name, (ds, dth, K) in dict(straight_20m=(0.04, 0.0, 500), straight_40m=(0.04, 0.0, 1000),
                                        out_and_back=(None, None, None)).items():
        for sig_psi_deg in (1, 3, 5, 10, 17, 25):
            for input_noise, cal_on in grid:
                P0 = np.diag(np.r_[0.03, 0.03, math.radians(sig_psi_deg), cal_std if cal_on else 1e-12 * cal_std] ** 2)
                m0 = np.array([0., 0., 0., 0., 0., 0.])
                if path_name == 'out_and_back':
                    seq = [(0.04, 0.0)] * 440 + [(0.0, math.radians(5.0))] * 36 + [(0.04, 0.0)] * 440
                else:
                    seq = [(ds, dth)] * K
                S = m0[:, None] + np.linalg.cholesky(P0) @ rng.standard_normal((6, n_mc))
                m, P = m0.copy(), P0.copy()
                for (d, g) in seq:
                    m, Fm, G = F.transition(m, d, g, DT, B_NOM)
                    P = Fm @ P @ Fm.T
                    if input_noise:
                        qd, qg = k_s * abs(d), gN2 * DT
                        P = P + G[:, :2] @ np.diag([qd, qg]) @ G[:, :2].T
                        nz = rng.standard_normal((2, n_mc))
                        S = H.ParticleFilter._transition_rows(S, d - math.sqrt(qd) * nz[0], g - math.sqrt(qg) * nz[1], DT, B_NOM)
                    else:
                        S = H.ParticleFilter._transition_rows(S, d, g, DT, B_NOM)
                e = (S[:3] - m[:3, None]).T
                e[:, 2] = DC.wrap(e[:, 2])
                P3 = P[:3, :3]
                nees = DC.nees(e, np.broadcast_to(P3, (n_mc, 3, 3)))
                split = DC.heading_conditional_split(e, np.broadcast_to(P3, (n_mc, 3, 3)))
                C = np.cov(e.T)
                Wi = DC.sym_inv_sqrt(P3)
                lam = np.sort(np.linalg.eigvalsh(Wi @ C @ Wi))[::-1]
                mshift = e.mean(0)
                rows.append(dict(path=path_name, sigma_psi0_deg=sig_psi_deg, cal_prior=cal_on, input_noise=input_noise,
                                 ekf_sigma_psi_deg=float(np.degrees(math.sqrt(P3[2, 2]))),
                                 expected_pose_nees=float(np.mean(nees)), coverage95=float(np.mean(nees <= 7.8147)),
                                 heading_term=float(np.mean(split['heading'])), cond_xy_term=float(np.mean(split['cond_xy'])),
                                 whitened_cov_eig=lam.tolist(),
                                 whitened_mean_shift=float(mshift @ np.linalg.solve(P3, mshift)),
                                 mc_mean_shift_m=[float(mshift[0]), float(mshift[1])]))
    return dict(rows=rows, note='consistent propagation <=> expected_pose_nees ~ 3, whitened eig ~ 1; no measurement update')


def observability():
    """Odometry pseudo-measurement information on (b_g, SF, eps) along each route at the true increments."""
    out = {}
    cfg = H.make_cfg(H.ARMS['B0'], 0, dict(wheelbase=0.0))
    for route in H.ROUTES:
        m = H.MOT[route]
        info = np.zeros((3, 3))
        x = np.zeros(6)
        for k in range(1, len(m['t'])):
            d, g, dt = m['ds'][k], m['dtheta'][k], m['dt'][k]
            _, Hm, B = F.odometry_model(x, d, g, dt, B_NOM)
            Q = np.diag([cfg.k_s * abs(d), cfg.gyro_N_rad_sqrt_s ** 2 * dt, cfg.k_theta * abs(g) + cfg.k_stheta * abs(d)])
            info += np.outer(Hm[3:], Hm[3:]) / float(B @ Q @ B)
        P0 = np.diag(np.array(H.P0_CAL_DEFAULT) ** 2)
        post = np.linalg.inv(np.linalg.inv(P0) + info)
        sd = np.sqrt(np.diag(post))
        corr = post / np.outer(sd, sd)
        # weakest combination in prior-whitened coordinates
        Lp = np.sqrt(np.diag(P0))
        Iw = info * np.outer(Lp, Lp)
        w, Vv = np.linalg.eigh(Iw)
        out[route] = dict(posterior_sd=dict(bg_deg_s=float(np.degrees(sd[0])), sf=float(sd[1]), eps=float(sd[2])),
                          prior_sd=dict(bg_deg_s=0.12, sf=0.0104, eps=0.0064),
                          posterior_corr=corr.round(4).tolist(),
                          prior_whitened_info_eig=w.tolist(), weakest_combination_prior_whitened=Vv[:, 0].round(4).tolist(),
                          heading_drift_sd_over_route_deg=float(np.degrees(sd[0] * m['t'][-1])))
    return dict(routes=out, note='linear information ignoring C (shared gyro noise): an optimistic bound on identifiability')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--draws', type=int, default=200000)
    a = ap.parse_args()
    started = H.utc_now()
    OUT.mkdir(exist_ok=True)
    doc = dict(jacobian=jacobian_audit(), noise=noise_audit(a.draws), linearisation=propagation_linearisation(),
               observability=observability())
    doc['status'] = dict(jacobian=doc['jacobian']['status'], noise=doc['noise']['status'])
    path = OUT / 'D3_MODEL_AUDIT.json'
    path.write_text(IO.json_text(doc))
    H.write_manifest(OUT, 'D3_MODEL_AUDIT', dict(draws=a.draws), [path], started)
    print(json.dumps(doc['status']))
    for r in doc['linearisation']['rows']:
        print(f"{r['path']:13s} sig0 {r['sigma_psi0_deg']:3d} cal {int(r['cal_prior'])} noise {int(r['input_noise'])} ekf_sig_end {r['ekf_sigma_psi_deg']:6.1f} "
              f"E[NEES] {r['expected_pose_nees']:8.2f} head {r['heading_term']:5.2f} condXY {r['cond_xy_term']:8.2f} "
              f"eig {np.round(r['whitened_cov_eig'], 2)} shift {r['whitened_mean_shift']:.2f}")


if __name__ == '__main__':
    main()
