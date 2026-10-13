"""D5 supplement (POST-HOC, added after the interim review): how far can the particle filter stand in for the exact posterior?

V1 single step: locally-optimal proposal + marginal likelihood vs an independent bootstrap importance sampler
   (prior draw of state and input noise, weight by the odometry-noise density only). Exaggerated input noise and
   wheel-asymmetry prior make the input-noise conditioning dominate, so sign or scale errors in B1/B2 would show.
V2 short horizon: the full PF (20k, systematic resampling + Liu-West a=0.98) vs sequential importance sampling with
   the same exact proposal, 1M particles, no resampling/jitter -> isolates the resampling/rejuvenation error.
V3 particle count: 20k vs 80k on development seeds 8000-8007 in R2_d2, R5_d2, R4_d1 (model-matched world).
V4 gate: PF with the EKF's chi2_1 99.9% odometry gate (mixture predictive moments) vs the ungated PF_A2_3, dev seeds.
The D6 arm PF_A2_3 is NOT changed by this file (frozen in dr_harness.py).

usage: validate_dr_pf.py [--parts V1 V2 V3 V4] [--procs 4]
"""
import argparse
import dataclasses
import math

import numpy as np

import dr_harness as H
import dr_consistency as DC
import dr_io as IO
from dr_harness import F, CHI2_1_999

OUT = H.HERE / 'out'


class NoResamplePF(H.ParticleFilter):
    def _maybe_resample(self):
        w = np.exp(self.lw)
        self.stats['ess_min'] = min(self.stats['ess_min'], float(1.0 / np.sum(w * w)))


def moments(X, w):
    w = w / w.sum()
    m = X @ w
    ref = m[2]
    d = X - m[:, None]
    d[2] = DC.wrap(X[2] - ref)
    return m, (d * w) @ d.T


def compare(m_a, C_a, m_ref, C_ref):
    d = m_a - m_ref
    d[2] = DC.wrap(d[2])
    Wi = DC.sym_inv_sqrt(C_ref)
    eig = np.linalg.eigvalsh(Wi @ C_a @ Wi)
    return dict(whitened_mean_diff_sq=float(d @ np.linalg.solve(C_ref, d)), cov_eig_min=float(eig.min()), cov_eig_max=float(eig.max()))


def v1_single_step(n_pf=400_000, n_ref=4_000_000, seed=1):
    cfg = dataclasses.replace(H.make_cfg(H.ARMS['A2_3_GAUSS_LEVEL'], 2, dict(wheelbase=0.0)),
                              k_s=0.05, gyro_N_rad_sqrt_s=0.01, known_wheelbase_error=0.01)
    m = np.array([1.0, 0.5, 0.3, math.radians(0.2), 0.015, 0.05])
    P = np.diag(np.array([0.03, 0.03, math.radians(10), math.radians(0.2), 0.015, 0.05]) ** 2)
    out = {}
    for name, (d, g) in dict(drive=(0.04, 0.01), spin=(0.0, math.radians(5.0))).items():
        dt = 0.2
        Qd, Qg = cfg.k_s * abs(d), cfg.gyro_N_rad_sqrt_s ** 2 * dt
        h_m = H.odometry_h_vec(m[None], d, g, dt, cfg.wheel_base, cfg.known_wheelbase_error)[0]
        o = h_m + 2.0 * math.sqrt(max(cfg.k_theta * abs(h_m) + cfg.k_stheta * abs(d), 1e-12) + 1e-5)
        Qo = cfg.k_theta * abs(o) + cfg.k_stheta * abs(d)
        rng = np.random.default_rng([H.DIAG_NAMESPACE, seed, 41])
        X = m[:, None] + np.linalg.cholesky(P) @ rng.standard_normal((6, n_ref))
        nd = rng.standard_normal(n_ref) * math.sqrt(Qd)
        ng = rng.standard_normal(n_ref) * math.sqrt(Qg)
        xn = H.ParticleFilter._transition_rows(X, d - nd, g - ng, dt, cfg.wheel_base / (1 + cfg.known_wheelbase_error))
        z = H.odometry_h_vec(X.T, d - nd, g - ng, dt, cfg.wheel_base, cfg.known_wheelbase_error)
        lw = -0.5 * (o - z) ** 2 / Qo
        w = np.exp(lw - lw.max())
        m_ref, C_ref = moments(xn, w)
        pf = NoResamplePF(cfg, m, P, n_pf, np.random.default_rng([H.DIAG_NAMESPACE, seed, 42]))
        pf.step(d, g, o, dt)
        m_pf, C_pf = pf.mean_cov()
        # what an error in the input-noise conditioning would look like: same PF, conditioning switched off
        rng2 = np.random.default_rng([H.DIAG_NAMESPACE, seed, 43])
        X2 = m[:, None] + np.linalg.cholesky(P) @ rng2.standard_normal((6, n_pf))
        xn2 = H.ParticleFilter._transition_rows(X2, d - rng2.standard_normal(n_pf) * math.sqrt(Qd),
                                                g - rng2.standard_normal(n_pf) * math.sqrt(Qg), dt,
                                                cfg.wheel_base / (1 + cfg.known_wheelbase_error))
        h2 = H.odometry_h_vec(X2.T, d, g, dt, cfg.wheel_base, cfg.known_wheelbase_error)
        D = 1 + X2[4]
        L = 1 - X2[5] ** 2 / 4
        S2 = (X2[5] / cfg.wheel_base) ** 2 * Qd + (L / D / (1 + cfg.known_wheelbase_error)) ** 2 * Qg + Qo
        lw2 = -0.5 * (o - h2) ** 2 / S2 - 0.5 * np.log(S2)
        m_wr, C_wr = moments(xn2, np.exp(lw2 - lw2.max()))
        ess_ref = float(w.sum() ** 2 / (w * w).sum())
        out[name] = dict(pf_vs_reference=compare(m_pf, C_pf, m_ref, C_ref),
                         unconditioned_noise_vs_reference=compare(m_wr, C_wr, m_ref, C_ref),
                         reference_ess=ess_ref, n_pf=n_pf, n_ref=n_ref)
    return out


def v2_short_horizon(K=120, n_pf=20_000, n_sis=1_000_000, seeds=(8000, 8001, 8002)):
    arm = H.ARMS['A2_3_GAUSS_LEVEL']
    out = {}
    for route in ('R4', 'R2'):
        for seed in seeds:
            inputs, ev, p, truth = H.make_world(arm, route, 2, seed)
            cfg = H.make_cfg(arm, 2, p)
            p0 = np.asarray(cfg.p0_std)
            x0 = H.initial_state(arm, route, seed, p, p0)
            pf = H.ParticleFilter(cfg, x0, np.diag(p0 ** 2), n_pf, np.random.default_rng([H.DIAG_NAMESPACE, seed, 51]))
            sis = NoResamplePF(cfg, x0, np.diag(p0 ** 2), n_sis, np.random.default_rng([H.DIAG_NAMESPACE, seed, 52]))
            for k in range(1, K + 1):
                args = (inputs['ds_odom'][k], inputs['dtheta_gyro'][k], inputs['dtheta_odom'][k], inputs['dt_s'][k])
                pf.step(*args)
                sis.step(*args)
            m_pf, C_pf = pf.mean_cov()
            m_s, C_s = sis.mean_cov()
            out[f'{route}_d2_s{seed}'] = dict(pose=compare(m_pf[:3], C_pf[:3, :3], m_s[:3], C_s[:3, :3]),
                                             full=compare(m_pf, C_pf, m_s, C_s), pf_resamples=pf.stats['resamples'],
                                             sis_ess_min=sis.stats['ess_min'], steps=K)
    return out


def v3_particle_count(procs):
    from diagnose_dr_trace import run_arm, load_cell, seed_range
    from compare_dr_nonlinear import posterior_agreement
    seeds = seed_range('8000:8008')
    cells = (('R2', 2), ('R5', 2), ('R4', 1))
    run_arm('PF_A2_3_N80K', seeds, procs, cells=cells, reuse=True)
    full = seed_range('8000:8032')
    out = {}
    for route, lv in cells:
        a80 = load_cell('PF_A2_3_N80K', seeds, route, lv)
        a20 = load_cell('PF_A2_3', full, route, lv, validate=False)
        sub = {k: (v[:8] if isinstance(v, np.ndarray) and v.ndim >= 1 and v.shape[0] == 32 else v) for k, v in a20.items()}
        ag, _ = posterior_agreement(sub, a80, route)
        t = H.MOT[route]['t']
        keep = t >= 30
        out[H.cell_name(route, lv)] = dict(
            anees_20k=float(np.nanmean(np.nanmean(sub['nees_pose_post'][:, keep].astype(float), 0))),
            anees_80k=float(np.nanmean(np.nanmean(a80['nees_pose_post'][:, keep].astype(float), 0))),
            enees_80k_posterior_under_20k=ag['enees_t30'], heading_var_ratio_80k_over_20k=ag['heading_var_ratio_t30'],
            cond_xy_cov_ratio_80k_over_20k=ag['cond_xy_cov_ratio_t30'], n_seeds=8)
    return out


class GatedPF(H.ParticleFilter):
    """PF with the EKF's odometry gate: reject when ybar^2 / S_mix > chi2_1(0.999), S_mix = mixture predictive variance;
    a rejected sample is propagated with the prior input-noise proposal (as the EKF predicts without updating)."""

    def step(self, d, g, o, dt):
        c = self.cfg
        X = self.X
        ke = 1 + c.known_wheelbase_error
        Qd = c.k_s * abs(d)
        Qg = c.gyro_N_rad_sqrt_s ** 2 * dt
        Qo = c.k_theta * abs(o) + c.k_stheta * abs(d)
        D = 1 + X[4]
        eps = X[5]
        L = 1 - eps ** 2 / 4
        h0 = (L * (g - X[3] * dt) / D + eps * d * ke / self.b_nom) / ke
        S = (eps / self.b_nom) ** 2 * Qd + (L / D / ke) ** 2 * Qg + Qo
        w = np.exp(self.lw)
        y = o - h0
        ybar = float(w @ y)
        smix = float(w @ (S + (y - ybar) ** 2))
        if ybar * ybar / smix > CHI2_1_999:
            self.stats['o_rejected'] += 1
            z = self.rng.standard_normal((2, self.n))
            self.X = self._transition_rows(X, d - z[0] * math.sqrt(Qd), g - z[1] * math.sqrt(Qg), dt, self.b)
            return dict(status='rejected')
        return super().step(d, g, o, dt)


def v4_gate(procs):
    from diagnose_dr_trace import run_arm, load_cell, seed_range
    seeds = seed_range('8000:8032')
    name = 'PF_A2_3_GATED_POSTHOC'
    H.ARMS[name] = dataclasses.replace(H.ARMS['PF_A2_3'], name=name, role='POST-HOC: PF_A2_3 + EKF-equivalent odometry gate')
    H.STATUS_CODE.setdefault('rejected', 2)
    H.ParticleFilter = GatedPF            # forked workers inherit the patched class; dr_harness.py on disk is unchanged
    rows = run_arm(name, seeds, procs, reuse=True)
    out = {}
    for r in rows:
        route, lv = r['cell'].split('_d')[0], int(r['cell'].split('_d')[1])
        base = H.cell_summary(load_cell('PF_A2_3', seeds, route, lv), route)
        g = load_cell(name, seeds, route, lv)
        out[r['cell']] = dict(anees_gated=r['anees'], anees_ungated=base['anees'], late_gated=r['anees_late25'],
                              late_ungated=base['anees_late25'], coverage_gated=r['coverage95'], coverage_ungated=base['coverage95'],
                              consistent_gated=r['consistent'], consistent_ungated=base['consistent'],
                              gate_reject_frac=float(np.mean(g['status'][:, 1:] == 2)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', nargs='*', default=['V1', 'V2', 'V3', 'V4'])
    ap.add_argument('--procs', type=int, default=4)
    a = ap.parse_args()
    started = H.utc_now()
    path = OUT / 'D5_PF_VALIDATION.json'
    doc = IO.load_json(path) if path.exists() else dict(status='POST-HOC supplement to D5; does not alter D6 arms or criteria')
    funcs = dict(V1=lambda: v1_single_step(), V2=lambda: v2_short_horizon(), V3=lambda: v3_particle_count(a.procs), V4=lambda: v4_gate(a.procs))
    for part in a.parts:
        doc[part] = funcs[part]()
        path.write_text(IO.json_text(doc))
        print(part, IO.json_text(doc[part])[:3000])
    H.write_manifest(OUT, 'D5_PF_VALIDATION', dict(parts=a.parts), [path], started)


if __name__ == '__main__':
    main()
