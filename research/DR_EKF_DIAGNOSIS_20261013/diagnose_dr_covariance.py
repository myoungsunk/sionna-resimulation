"""D2: actual error second moments vs EKF covariance (Track B2-B4).

* B2: M_k = mean e e^T vs Pbar_k = mean P (pose, path frame long/lat/psi), bias vs variance split,
  unit-free whitened eigenvalues of Pbar^-1/2 M Pbar^-1/2, predicted (pre-update) vs updated (post-update).
* B3: heading-conditional XY: e~ = e_xy - P_xy,psi/P_psipsi e_psi vs P_xy|psi (pure metres): thinnest predicted
  direction, its orientation to the path, actual RMS along it, conditional mean (bias) along it.
* B4: error-distribution shape at 0/30/60/100/150 s/end: skewness, kurtosis, bimodality, standardized error along
  the most over-confident whitened direction, and a split by the sign of each generated calibration parameter.

usage: diagnose_dr_covariance.py [--arm B0] [--seeds 6000:6300] [--figure-cells R2_d2 R5_d0]
"""
import argparse
import json

import numpy as np

import dr_harness as H
import dr_consistency as DC
import dr_plot as PL
from diagnose_dr_trace import load_cell, seed_range, seed_tag

OUT = H.HERE / 'out'
FIG = OUT / 'fig'
CHECK_T = (30.0, 60.0, 100.0, 150.0, 'end')


def check_indices(t):
    idx = {}
    for c in CHECK_T:
        if c == 'end':
            idx['end'] = len(t) - 1
        elif c <= t[-1]:
            idx[f't{int(c)}'] = int(np.searchsorted(t, c))
    return idx


def path_frame_T(psi):
    T = np.zeros(psi.shape + (3, 3))
    T[..., :2, :2] = DC.rotation_to_path(psi)
    T[..., 2, 2] = 1.0
    return T


def pose_moments(arr, phase, psi, N):
    T = path_frame_T(psi)
    se = np.einsum('kij,kj->ki', T, arr[f'sum_e_{phase}'][:, :3])
    see = T @ arr[f'sum_ee_{phase}'][:, :3, :3] @ np.swapaxes(T, -1, -2)
    sP = T @ arr[f'sum_P_{phase}'][:, :3, :3] @ np.swapaxes(T, -1, -2)
    return DC.mse_vs_predicted(se, see, sP, N)


def conditional_moments(arr, phase, psi):
    E = arr[f'E_{phase}'].astype(float)[:, :, :3]
    P3 = arr[f'P3_{phase}']
    split = DC.heading_conditional_split(E, P3)
    R = DC.rotation_to_path(psi)
    et = np.einsum('kij,nkj->nki', R, split['e_tilde'])
    Pc = np.einsum('kij,nkjl,kml->nkim', R, split['P_cond'], R)
    N = E.shape[0]
    Mt = np.einsum('nki,nkj->kij', et, et) / N
    Pcb = Pc.mean(0)
    w, Vv = np.linalg.eigh(Pcb)                       # ascending: column 0 = thinnest predicted direction
    thin = Vv[:, :, 0]
    sig_pred = np.sqrt(w[:, 0])
    rms_act = np.sqrt(np.einsum('ki,kij,kj->k', thin, Mt, thin))
    mean_along = np.einsum('ki,nki->k', thin, et) / N
    angle = np.degrees(np.arctan2(np.abs(thin[:, 1]), np.abs(thin[:, 0])))   # 0 = longitudinal, 90 = lateral
    Wi = DC.sym_inv_sqrt(Pcb)
    lam = np.linalg.eigvalsh(Wi @ Mt @ Wi)[:, ::-1]
    # per-run (heterogeneous P) conditional NEES split into longitudinal-thin and its orthogonal part
    return dict(sig_pred_thin_m=sig_pred, rms_actual_thin_m=rms_act, mean_actual_thin_m=mean_along,
                thin_angle_from_long_deg=angle, whitened_eig=lam, Mt=Mt, Pc=Pcb,
                sig_pred_wide_m=np.sqrt(w[:, 1]))


def shape_stats(arr, k, psi_k, mom):
    """Distribution shape at sample k (path frame), standardized along the most over-confident whitened axis."""
    E = arr['E_post'].astype(float)[:, k, :3]
    R = DC.rotation_to_path(psi_k)
    ell = np.c_[E[:, :2] @ R.T, E[:, 2]]
    sk, ku = DC.skew_kurt(ell)
    Wi = DC.sym_inv_sqrt(mom['Pbar'][k])
    lam, Vv = np.linalg.eigh(Wi @ mom['M'][k] @ Wi)
    v = Vv[:, -1]
    z = (ell @ Wi.T) @ v
    zs = z / np.sqrt(lam[-1])
    names = ('long', 'lat', 'psi')
    return dict(mean=dict(zip(names, ell.mean(0).tolist())), rms=dict(zip(names, np.sqrt((ell ** 2).mean(0)).tolist())),
                skew=dict(zip(names, sk.tolist())), kurtosis=dict(zip(names, ku.tolist())),
                bimodality=dict(zip(names, [DC.bimodality_coefficient(ell[:, i]) for i in range(3)])),
                top_whitened=dict(lambda_=float(lam[-1]), mean_z=float(z.mean() / np.sqrt(lam[-1])),
                                  kurtosis=float(DC.skew_kurt(zs)[1]),
                                  abs_q99=float(np.quantile(np.abs(zs - zs.mean()), 0.99))))


def sign_split(arr, route):
    t = H.MOT[route]['t']
    keep = t >= 30
    per_run = np.nanmean(arr['nees_pose_post'][:, keep].astype(float), axis=1)
    cond = np.nanmean(arr['nees_cond_xy_post'][:, keep].astype(float), axis=1)
    psi_end = H.MOT[route]['pose'][-1, 2]
    E_end = arr['E_post'].astype(float)[:, -1, :3]
    ll = E_end[:, :2] @ DC.rotation_to_path(psi_end).T
    out = {}
    names = [str(n) for n in arr['param_names']]
    for j, name in enumerate(names):
        if name == 'common_scale':
            continue
        sgn = np.sign(arr['params'][:, j])
        groups = {}
        for s, lab in ((1, 'pos'), (-1, 'neg'), (0, 'zero')):
            sel = sgn == s
            if sel.sum() == 0:
                continue
            groups[lab] = dict(n=int(sel.sum()), mean_time_avg_nees=float(per_run[sel].mean()),
                               median_time_avg_nees=float(np.median(per_run[sel])), mean_cond_xy=float(cond[sel].mean()),
                               end_mean_long_m=float(ll[sel, 0].mean()), end_mean_lat_m=float(ll[sel, 1].mean()),
                               end_mean_psi_deg=float(np.degrees(E_end[sel, 2].mean())))
        out[name] = groups
    return out


def summarise(arr, route, N):
    t = H.MOT[route]['t']
    psi = H.MOT[route]['pose'][:, 2]
    mom = {ph: pose_moments(arr, ph, psi, N) for ph in ('pre', 'post')}
    cm = {ph: conditional_moments(arr, ph, psi) for ph in ('pre', 'post')}
    anees = np.nanmean(arr['nees_pose_post'].astype(float), axis=0)
    idx = check_indices(t)
    pts = {}
    for lab, k in idx.items():
        p, q = mom['post'], mom['pre']
        c = cm['post']
        pts[lab] = dict(
            t_s=float(t[k]), anees=float(anees[k]), tr_Pbar_inv_M=float(p['bias_term'][k] + p['var_term'][k]),
            bias_term=float(p['bias_term'][k]), var_term=float(p['var_term'][k]),
            whitened_eig_post=p['whitened_eig'][k].tolist(), whitened_eig_pre=q['whitened_eig'][k].tolist(),
            top_dir_scaled_long_lat_psi=p['top_dir_scaled'][k].tolist(),
            mean_error_long_lat_m=p['ebar'][k][:2].tolist(), mean_error_psi_deg=float(np.degrees(p['ebar'][k][2])),
            rms_long_lat_m=np.sqrt(np.diag(p['M'][k])[:2]).tolist(), pred_sd_long_lat_m=np.sqrt(np.diag(p['Pbar'][k])[:2]).tolist(),
            rms_psi_deg=float(np.degrees(np.sqrt(p['M'][k][2, 2]))), pred_sd_psi_deg=float(np.degrees(np.sqrt(p['Pbar'][k][2, 2]))),
            corr_pred_lat_psi=float(p['Pbar'][k][1, 2] / np.sqrt(p['Pbar'][k][1, 1] * p['Pbar'][k][2, 2])),
            corr_actual_lat_psi=float(p['M'][k][1, 2] / np.sqrt(p['M'][k][1, 1] * p['M'][k][2, 2])),
            corr_pred_long_psi=float(p['Pbar'][k][0, 2] / np.sqrt(p['Pbar'][k][0, 0] * p['Pbar'][k][2, 2])),
            corr_actual_long_psi=float(p['M'][k][0, 2] / np.sqrt(p['M'][k][0, 0] * p['M'][k][2, 2])),
            cond=dict(sig_pred_thin_cm=float(100 * c['sig_pred_thin_m'][k]), rms_actual_thin_cm=float(100 * c['rms_actual_thin_m'][k]),
                      mean_actual_thin_cm=float(100 * c['mean_actual_thin_m'][k]), thin_angle_from_long_deg=float(c['thin_angle_from_long_deg'][k]),
                      sig_pred_wide_cm=float(100 * c['sig_pred_wide_m'][k]),
                      whitened_eig_post=c['whitened_eig'][k].tolist(), whitened_eig_pre=cm['pre']['whitened_eig'][k].tolist()),
            shape=shape_stats(arr, k, psi[k], p))
    keep = t >= 30
    # fraction of over-confidence created in prediction vs update, conditional-XY metres view
    pre_t, post_t = cm['pre']['whitened_eig'][:, 0], cm['post']['whitened_eig'][:, 0]
    return dict(checkpoints=pts, sign_split=sign_split(arr, route),
                heterogeneity_mean_ratio_anees_over_trPinvM=float(np.mean(anees[keep] / (mom['post']['bias_term'][keep] + mom['post']['var_term'][keep]))),
                bias_fraction_t30=float(np.mean(mom['post']['bias_term'][keep] / (mom['post']['bias_term'][keep] + mom['post']['var_term'][keep]))),
                cond_top_whitened_eig_mean_t30=dict(pre=float(np.mean(pre_t[keep])), post=float(np.mean(post_t[keep])))), mom, cm


def figures(results, tag, figure_cells, cache):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse
    PL.style()
    FIG.mkdir(parents=True, exist_ok=True)
    paths = []
    fig, axes = plt.subplots(3, 3, figsize=(12, 8), sharex='col', sharey=True)
    for i, route in enumerate(H.ROUTES):
        t = H.MOT[route]['t']
        for lv in H.LEVELS:
            ax = axes[lv, i]
            mom = results[H.cell_name(route, lv)][1]['post']
            for j, lab in enumerate(('largest', 'middle', 'smallest')):
                ax.plot(t[1:], mom['whitened_eig'][1:, j], color=PL.SERIES[j], label=lab)
            ax.axhline(1.0, color=PL.TEXT2, lw=0.8, ls=':')
            ax.set_yscale('log')
            ax.set_title(f'{route} drift {lv}', fontsize=9)
            if lv == 2:
                ax.set_xlabel('time [s]')
        axes[1, 0].set_ylabel('whitened eigenvalue of $\\bar P^{-1/2} M \\bar P^{-1/2}$ (1 = matched)')
    axes[0, 0].legend(loc='upper left')
    paths.append(PL.save(fig, FIG / f'D2_whitened_eig_{tag}.png'))

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    for ax, route in zip(axes, H.ROUTES):
        t = H.MOT[route]['t']
        for lv in H.LEVELS:
            c = results[H.cell_name(route, lv)][2]['post']
            ax.plot(t[1:], 100 * c['rms_actual_thin_m'][1:], color=PL.SERIES[lv], label=f'drift {lv}: actual RMS')
            ax.plot(t[1:], 100 * c['sig_pred_thin_m'][1:], color=PL.SERIES[lv], ls='--', lw=1.0, label=f'drift {lv}: EKF sigma')
        ax.set_yscale('log')
        ax.set_title(f'{route}: thinnest heading-conditional XY direction')
        ax.set_xlabel('time [s]')
    axes[0].set_ylabel('[cm]')
    axes[0].legend(loc='upper left')
    paths.append(PL.save(fig, FIG / f'D2_cond_thin_direction_{tag}.png'))

    for cell in figure_cells:
        route, lv = cell.split('_d')[0], int(cell.split('_d')[1])
        arr = cache[cell]
        t = H.MOT[route]['t']
        psi = H.MOT[route]['pose'][:, 2]
        mom = results[cell][1]['post']
        idx = check_indices(t)
        fig, axes = plt.subplots(2, len(idx), figsize=(3.0 * len(idx), 5.6))
        bg = np.sign(arr['params'][:, list(arr['param_names']).index('gyro_bias')])
        for col, (lab, k) in enumerate(idx.items()):
            E = arr['E_post'].astype(float)[:, k, :3]
            ll = E[:, :2] @ DC.rotation_to_path(psi[k]).T
            ax = axes[0, col]
            for s, color, name in ((1, PL.SERIES[0], 'gyro bias +'), (-1, PL.SERIES[1], 'gyro bias -'), (0, PL.SERIES[2], 'gyro bias 0')):
                sel = bg == s
                if sel.any():
                    ax.scatter(ll[sel, 0], ll[sel, 1], s=8, color=color, alpha=0.7, lw=0, label=name)
            P2 = mom['Pbar'][k][:2, :2]
            w, Vv = np.linalg.eigh(P2)
            ang = np.degrees(np.arctan2(Vv[1, 1], Vv[0, 1]))
            r = np.sqrt(5.991 * w)
            ax.add_patch(Ellipse((0, 0), 2 * r[1], 2 * r[0], angle=ang, fill=False, ec=PL.TEXT, lw=1.0))
            ax.set_title(f'{cell} t={t[k]:.0f}s', fontsize=9)
            ax.set_xlabel('longitudinal error [m]')
            if col == 0:
                ax.set_ylabel('lateral error [m]')
            ax.axis('equal')
            ax2 = axes[1, col]
            ax2.hist(np.degrees(E[:, 2]), bins=30, density=True, color=PL.SERIES[0], alpha=0.8)
            sd = np.degrees(np.sqrt(mom['Pbar'][k][2, 2]))
            xs = np.linspace(-4 * sd, 4 * sd, 200)
            ax2.plot(xs, np.exp(-0.5 * (xs / sd) ** 2) / (sd * np.sqrt(2 * np.pi)), color=PL.TEXT, lw=1.0)
            ax2.set_xlabel('heading error [deg]')
        axes[0, 0].legend(loc='upper left', fontsize=7)
        axes[1, 0].set_ylabel('density (line: EKF mean-P Gaussian)')
        fig.suptitle(f'{cell}: path-frame XY error (ellipse: 95% of mean EKF P) and heading error', fontsize=10)
        paths.append(PL.save(fig, FIG / f'D2_snapshots_{cell}_{tag}.png'))
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', default='B0')
    ap.add_argument('--seeds', default='6000:6300')
    ap.add_argument('--figure-cells', nargs='*', default=['R2_d2', 'R5_d0', 'R4_d0'])
    ap.add_argument('--no-figures', action='store_true')
    a = ap.parse_args()
    started = H.utc_now()
    seeds = seed_range(a.seeds)
    tag = f'{a.arm}_{seed_tag(seeds)}'
    results, cache, doc = {}, {}, {}
    for route, lv in H.CELLS:
        name = H.cell_name(route, lv)
        arr = load_cell(a.arm, seeds, route, lv)
        if name in a.figure_cells:
            cache[name] = arr
        results[name] = summarise(arr, route, len(seeds))
        doc[name] = results[name][0]
        cp = doc[name]['checkpoints']['end']
        print(f"{name}: end ANEES {cp['anees']:.1f} bias/var {cp['bias_term']:.1f}/{cp['var_term']:.1f} "
              f"W_eig {np.round(cp['whitened_eig_post'], 2)} topdir(l,l,psi) {np.round(cp['top_dir_scaled_long_lat_psi'], 2)} | "
              f"thin sig {cp['cond']['sig_pred_thin_cm']:.2f}cm act {cp['cond']['rms_actual_thin_cm']:.2f}cm mean {cp['cond']['mean_actual_thin_cm']:.2f}cm "
              f"angle {cp['cond']['thin_angle_from_long_deg']:.0f}deg | corr lat-psi pred {cp['corr_pred_lat_psi']:.3f} act {cp['corr_actual_lat_psi']:.3f}")
    OUT.mkdir(exist_ok=True)
    js = OUT / f'D2_COVARIANCE_{tag}.json'
    js.write_text(json.dumps(dict(arm=a.arm, seeds=[seeds[0], seeds[-1]], cells=doc), indent=1, default=float))
    figs = [] if a.no_figures else figures(results, tag, a.figure_cells, cache)
    H.write_manifest(OUT, f'D2_COVARIANCE_{tag}', dict(arm=a.arm, seeds=a.seeds), [js] + figs, started)


if __name__ == '__main__':
    main()
