"""D5: EKF vs sigma-point (cubature) vs particle filter / nonlinear Monte Carlo on the SAME worlds, priors and inputs.

Families pair arms that differ only in the estimator (dr_harness.ARMS). Besides each arm's own consistency
statistics, the EKF posterior is compared directly with the (approximately exact) particle posterior computed from the
same data under the same model:

    ENEES_k = mean_runs[ tr(P_EKF^-1 P_PF) + d^T P_EKF^-1 d ],  d = m_PF - m_EKF     (pose, 3 dof)

i.e. the pose NEES the EKF would show if the truth were distributed as the exact posterior. With the odometry update
off the "PF" has uniform weights (pure nonlinear Monte Carlo propagation) and ENEES isolates propagation
linearisation; with it on, ENEES measures EKF posterior approximation error irrespective of how realistic the world is.

usage: compare_dr_nonlinear.py [--seeds 8000:8032] [--families ...] [--reuse]
"""
import argparse
import json

import numpy as np

import dr_harness as H
import dr_io as IO
import dr_consistency as DC
import dr_plot as PL
from ablate_dr_calibration import ensure, arm_summary, strip_figure
from diagnose_dr_trace import load_cell, seed_range, seed_tag, write_rows

OUT = H.HERE / 'out'
FIG = OUT / 'fig'
FAMILIES = {
    'MATCHED_LEVEL': ('A2_3_GAUSS_LEVEL', 'CKF_A2_3', 'PF_A2_3'),
    'MATCHED_DEFAULT': ('A2_3D_GAUSS_DEFAULT', 'CKF_A2_3D', 'PF_A2_3D'),
    'B0': ('B0', 'CKF_B0', 'PF_B0'),
    'WHEEL_NOISE_ONLY': ('WN_ONLY', 'CKF_WN_ONLY', 'PF_WN_ONLY'),
    'PROP_MATCHED_LEVEL': ('A2_3_ODOM_OFF', 'MC_A2_3_ODOM_OFF'),
    'PROP_MATCHED_DEFAULT': ('A2_3D_ODOM_OFF', 'MC_A2_3D_ODOM_OFF'),
    'PROP_B0': ('ODOM_OFF', 'MC_ODOM_OFF'),
}


def posterior_agreement(a_ref, a_cmp, route):
    """ENEES of the comparison posterior under the reference Gaussian (pose), per time, ensemble mean."""
    E_r, E_c = a_ref['E_post'].astype(float)[:, :, :3], a_cmp['E_post'].astype(float)[:, :, :3]
    P_r, P_c = a_ref['P3_post'], a_cmp['P3_post']
    d = E_r - E_c                                   # m_cmp - m_ref = (truth - E_cmp) - (truth - E_ref)
    d[:, :, 2] = DC.wrap(d[:, :, 2])
    tr = np.trace(np.linalg.solve(P_r, P_c), axis1=-2, axis2=-1)
    q = np.einsum('nki,nki->nk', d, np.linalg.solve(P_r, d[..., None])[..., 0])
    split = DC.heading_conditional_split(d, P_r)
    # covariance-only conditional part: tr(Pc_ref^-1 Pc_cmp) for the heading-conditional XY blocks
    sc = DC.heading_conditional_split(np.zeros_like(d), P_c)['P_cond']
    sr = split['P_cond']
    tr_c = np.trace(np.linalg.solve(sr, sc), axis1=-2, axis2=-1)
    t = H.MOT[route]['t']
    keep = t >= 30
    enees = np.mean(tr + q, axis=0)
    return dict(enees_t30=float(np.mean(enees[keep])), enees_end=float(enees[-1]),
                trace_part_t30=float(np.mean(np.mean(tr, 0)[keep])), mean_part_t30=float(np.mean(np.mean(q, 0)[keep])),
                cond_xy_cov_ratio_t30=float(np.mean(np.mean(tr_c, 0)[keep]) / 2),
                heading_var_ratio_t30=float(np.mean(np.mean(P_c[:, :, 2, 2] / P_r[:, :, 2, 2], 0)[keep]))), enees


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='8000:8032')
    ap.add_argument('--families', nargs='*', default=list(FAMILIES))
    ap.add_argument('--procs', type=int, default=4)
    ap.add_argument('--reuse', action='store_true')
    a = ap.parse_args()
    started = H.utc_now()
    seeds = seed_range(a.seeds)
    tag = seed_tag(seeds)
    arms = [arm for f in a.families for arm in FAMILIES[f]]
    rows = ensure(arms, seeds, a.procs, a.reuse)
    doc = dict(seeds=[seeds[0], seeds[-1]], n=len(seeds), families={})
    curves = {}
    for fam in a.families:
        members = FAMILIES[fam]
        ref = members[-1]                            # PF / MC = reference posterior
        fd = dict(arms={m: dict(definition=H.ARMS[m].describe(), summary=arm_summary(rows[m]), cells=rows[m]) for m in members},
                  agreement_vs_reference={})
        for m in members[:-1]:
            per_cell = {}
            for route, lv in H.CELLS:
                res, curve = posterior_agreement(load_cell(m, seeds, route, lv), load_cell(ref, seeds, route, lv), route)
                per_cell[H.cell_name(route, lv)] = res
                curves[(fam, m, H.cell_name(route, lv))] = curve
            fd['agreement_vs_reference'][m] = dict(reference=ref, cells=per_cell,
                                                   enees_t30_median=float(np.median([c['enees_t30'] for c in per_cell.values()])))
        doc['families'][fam] = fd
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    js = OUT / f'D5_NONLINEAR_{tag}.json'
    js.write_text(IO.json_text(doc))
    csv_path = OUT / f'D5_NONLINEAR_{tag}_CELLS.csv'
    write_rows([r for arm in arms for r in rows[arm]], csv_path)
    fig1 = strip_figure(rows, arms, FIG / f'D5_estimators_{tag}.png', f'D5 estimator comparison (seeds {seeds[0]}-{seeds[-1]})')
    figs = [fig1, agreement_figure(curves, a.families, FIG / f'D5_ekf_vs_reference_posterior_{tag}.png')]
    H.write_manifest(OUT, f'D5_NONLINEAR_{tag}', dict(families={f: FAMILIES[f] for f in a.families}, seeds=a.seeds), [js, csv_path] + figs, started)
    for fam in a.families:
        print(f'== {fam}')
        for m in FAMILIES[fam]:
            s = doc['families'][fam]['arms'][m]['summary']
            extra = ''
            if m in doc['families'][fam]['agreement_vs_reference']:
                ag = doc['families'][fam]['agreement_vs_reference'][m]
                extra = f" | ENEES vs {ag['reference']} median {ag['enees_t30_median']:.2f}"
            print(f"  {m:22s} cons {s['n_consistent']} over {s['n_overconfident']} cons- {s['n_conservative']} ANEESmed {s['anees_median']:7.2f} "
                  f"({s['anees_min']:.2f}-{s['anees_max']:.1f}) cov {s['coverage_median']:.3f} head {s['heading_median']:.2f} "
                  f"condXY {s['cond_xy_median']:.2f} posRMSE {s['pos_rmse_median_m']:.2f}{extra}")


def agreement_figure(curves, families, path):
    import matplotlib.pyplot as plt
    PL.style()
    fams = [f for f in families if any(k[0] == f for k in curves)]
    fig, axes = plt.subplots(1, len(fams), figsize=(3.3 * len(fams), 3.3), sharey=True, squeeze=False)
    for ax, fam in zip(axes[0], fams):
        for (f, m, cell), c in curves.items():
            if f != fam:
                continue
            route = cell.split('_')[0]
            lv = int(cell[-1])
            t = H.MOT[route]['t']
            ls = '-' if H.ARMS[m].estimator == 'ekf' else '--'
            ax.plot(t, c, color=PL.SERIES[H.ROUTES.index(route)], lw=0.6 + 0.5 * lv, ls=ls,
                    label=(f'{route}' if lv == 2 and ls == '-' else None))
        ax.axhline(3.0, color=PL.TEXT2, lw=0.8, ls=':')
        ax.set_yscale('log')
        ax.set_title(fam, fontsize=9)
        ax.set_xlabel('time [s]')
    axes[0, 0].set_ylabel('ENEES of reference posterior under EKF (3 = agree)\nsolid EKF, dashed CKF; width = drift level')
    axes[0, 0].legend(loc='upper left')
    return PL.save(fig, path)


if __name__ == '__main__':
    main()
