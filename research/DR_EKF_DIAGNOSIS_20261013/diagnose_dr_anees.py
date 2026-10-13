"""D1: when does the DR EKF become inconsistent and how does it grow (Track B1).

Per cell (from the diagnose_dr_trace cache): ensemble ANEES_k (pre- and post-odometry-update), coverage, the
chi2(3N)/N band, the first persistent (>= 5 s) exceedance of the band and of 3.6 (including t < 30 s), the
motion context at that time, per-phase attribution of log-ANEES growth to prediction vs odometry update, and a
pooled cross-cell test of which clock (time, distance, rotation, filter heading sigma, actual heading error)
best orders the inconsistency.

usage: diagnose_dr_anees.py [--arm B0] [--seeds 6000:6300]
"""
import argparse
import csv
import json

import numpy as np

import dr_harness as H
import dr_io as IO
import dr_consistency as DC
import dr_plot as PL
from diagnose_dr_trace import load_cell, seed_range, seed_tag

OUT = H.HERE / 'out'
FIG = OUT / 'fig'


def ens(arr, key):
    return np.nanmean(arr[key].astype(float), axis=0)


def cell_timeseries(arr, route):
    m = H.MOT[route]
    E = arr['E_post'].astype(float)
    ts = dict(t=m['t'], phase=m['phase'], since_spin=m['since_spin'], cum_dist=m['cum_dist'], cum_rot=m['cum_rot'],
              anees_post=ens(arr, 'nees_pose_post'), anees_pre=ens(arr, 'nees_pose_pre'),
              coverage_post=np.nanmean(arr['nees_pose_post'] <= 7.8147, axis=0),
              anees_heading=ens(arr, 'nees_heading_post'), anees_cond_xy=ens(arr, 'nees_cond_xy_post'),
              anees_heading_pre=ens(arr, 'nees_heading_pre'), anees_cond_xy_pre=ens(arr, 'nees_cond_xy_pre'),
              anees_xy=ens(arr, 'nees_xy_post'), z2_long=ens(arr, 'z2_long_post'), z2_lat=ens(arr, 'z2_lat_post'),
              z2_long_cond=ens(arr, 'z2_long_cond_post'), z2_lat_cond=ens(arr, 'z2_lat_cond_post'),
              sigma_psi_deg=np.degrees(ens(arr, 'sigma_psi_post')),
              heading_rms_deg=np.degrees(np.sqrt(np.mean(E[:, :, 2] ** 2, axis=0))),
              pos_rms_m=np.sqrt(np.mean(E[:, :, 0] ** 2 + E[:, :, 1] ** 2, axis=0)),
              cond_min_sigma_cm=100 * ens(arr, 'cond_xy_min_sigma_post'))
    return ts


def departure(ts, N):
    lo, hi = DC.anees_band(N)
    out = {}
    for label, thr in (('band_upper', hi), ('criterion_3p6', 3.6)):
        t0, k = DC.first_persistent_exceedance(ts['anees_post'], ts['t'], thr)
        ctx = None
        if k >= 0:
            ctx = dict(t_s=t0, phase=str(ts['phase'][k]), since_last_spin_s=float(ts['since_spin'][k]),
                       cum_dist_m=float(ts['cum_dist'][k]), cum_abs_yaw_deg=float(np.degrees(ts['cum_rot'][k])),
                       filter_sigma_psi_deg=float(ts['sigma_psi_deg'][k]), actual_heading_rms_deg=float(ts['heading_rms_deg'][k]),
                       anees_heading=float(ts['anees_heading'][k]), anees_cond_xy=float(ts['anees_cond_xy'][k]))
        out[label] = dict(threshold=thr, first_persistent_t_s=t0, context=ctx)
    # which component departs first (heading > 1.5 vs conditional XY > 3 for 5 s)
    out['component_first'] = dict(
        heading_t_s=DC.first_persistent_exceedance(ts['anees_heading'], ts['t'], 1.5)[0],
        cond_xy_t_s=DC.first_persistent_exceedance(ts['anees_cond_xy'], ts['t'], 3.0)[0])
    return out


def phase_attribution(ts):
    """Sum of log-ANEES changes split into prediction (k-1 post -> k pre) and odometry update (k pre -> k post)."""
    out = {}
    for comp, post, pre in (('pose', 'anees_post', 'anees_pre'), ('heading', 'anees_heading', 'anees_heading_pre'),
                            ('cond_xy', 'anees_cond_xy', 'anees_cond_xy_pre')):
        a_post, a_pre = np.log(ts[post]), np.log(ts[pre])
        d_pred = a_pre[1:] - a_post[:-1]
        d_upd = a_post[1:] - a_pre[1:]
        ph = ts['phase'][1:]
        rows = {}
        for p in np.unique(ph):
            sel = ph == p
            rows[str(p)] = dict(n=int(sel.sum()), sum_dlog_predict=float(d_pred[sel].sum()), sum_dlog_update=float(d_upd[sel].sum()),
                                mean_dlog_predict_per_s=float(d_pred[sel].sum() / (0.2 * sel.sum())),
                                mean_dlog_update_per_s=float(d_upd[sel].sum() / (0.2 * sel.sum())))
        post_spin = (ts['since_spin'][1:] > 0) & (ts['since_spin'][1:] <= 5.0)
        rows['first_5s_after_spin'] = dict(n=int(post_spin.sum()), sum_dlog_predict=float(d_pred[post_spin].sum()),
                                           sum_dlog_update=float(d_upd[post_spin].sum()))
        rows['total'] = dict(sum_dlog_predict=float(d_pred.sum()), sum_dlog_update=float(d_upd.sum()),
                             net=float(a_post[-1] - a_post[0]))
        out[comp] = rows
    return out


def pooled_clock_test(series):
    """R^2 of log ANEES_k on log(clock) pooled over cells (t >= 10 s, 1 Hz). Within a cell all clocks are monotone;
    the pooled fit asks which clock puts the 9 cells on one curve."""
    clocks = ('t', 'cum_dist', 'cum_rot', 'sigma_psi_deg', 'heading_rms_deg')
    out = {}
    for target in ('anees_post', 'anees_cond_xy'):
        res = {}
        for c in clocks:
            xs, ys = [], []
            for ts in series.values():
                sel = (ts['t'] >= 10) & (np.arange(len(ts['t'])) % 5 == 0)
                xs.append(np.log(ts[c][sel]))
                ys.append(np.log(ts[target][sel]))
            x, y = np.concatenate(xs), np.concatenate(ys)
            A = np.c_[np.ones_like(x), x]
            coef, *_ = np.linalg.lstsq(A, y, rcond=None)
            r2 = 1 - np.sum((y - A @ coef) ** 2) / np.sum((y - y.mean()) ** 2)
            res[c] = dict(r2=float(r2), slope=float(coef[1]))
        out[target] = res
    return out


def write_timeseries_csv(series, path, every=5):
    keys = ['t', 'phase', 'since_spin', 'cum_dist', 'cum_rot', 'anees_post', 'anees_pre', 'coverage_post',
            'anees_heading', 'anees_cond_xy', 'anees_xy', 'z2_long', 'z2_lat', 'z2_long_cond', 'z2_lat_cond',
            'sigma_psi_deg', 'heading_rms_deg', 'pos_rms_m', 'cond_min_sigma_cm']
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['cell', 'k'] + keys)
        for cell, ts in series.items():
            for k in range(0, len(ts['t']), every):
                row = [cell, k] + [ts[key][k] for key in keys]
                w.writerow([f'{v:.6g}' if isinstance(v, (float, np.floating)) else v for v in row])


def figures(series, N, tag):
    import matplotlib.pyplot as plt
    PL.style()
    FIG.mkdir(parents=True, exist_ok=True)
    lo, hi = DC.anees_band(N)
    paths = []
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    for ax, route in zip(axes, H.ROUTES):
        ax.axhspan(lo, hi, color=PL.BAND, lw=0)
        ax.axhline(3.0, color=PL.TEXT2, lw=0.8, ls=':')
        for lv in H.LEVELS:
            ts = series[H.cell_name(route, lv)]
            ax.plot(ts['t'], ts['anees_post'], color=PL.SERIES[lv], label=f'drift {lv}')
        spin = H.MOT[route]['phase'] == 'spin'
        ax.fill_between(H.MOT[route]['t'], 0, 1, where=spin, transform=ax.get_xaxis_transform(), color=PL.GRID, lw=0)
        ax.set_yscale('log')
        ax.set_title(f'{route}: ensemble pose ANEES (N={N})')
        ax.set_xlabel('time [s]  (grey columns = in-place spins)')
    axes[0].set_ylabel('ANEES$_k$ (3 dof; band = $\\chi^2_{3N}/N$ 95%)')
    axes[0].legend(loc='upper left')
    paths.append(PL.save(fig, FIG / f'D1_anees_time_{tag}.png'))

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    for ax, route in zip(axes, H.ROUTES):
        for lv in H.LEVELS:
            ts = series[H.cell_name(route, lv)]
            ax.plot(ts['t'], ts['anees_cond_xy'] / 2, color=PL.SERIES[lv], label=f'drift {lv}: cond. XY / 2')
            ax.plot(ts['t'], ts['anees_heading'], color=PL.SERIES[lv], ls='--', lw=1.0, label=f'drift {lv}: heading')
        ax.axhline(1.0, color=PL.TEXT2, lw=0.8, ls=':')
        ax.set_yscale('log')
        ax.set_title(f'{route}: per-dof NEES contributions')
        ax.set_xlabel('time [s]')
    axes[0].set_ylabel('mean contribution per dof (consistent = 1)')
    axes[0].legend(loc='upper left', ncol=1)
    paths.append(PL.save(fig, FIG / f'D1_components_time_{tag}.png'))

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    for ax, clock, lab in ((axes[0], 'sigma_psi_deg', 'filter heading $\\sigma_\\psi$ [deg]'),
                           (axes[1], 't', 'time [s]')):
        for i, route in enumerate(H.ROUTES):
            for lv in H.LEVELS:
                ts = series[H.cell_name(route, lv)]
                sel = ts['t'] >= 10
                ax.plot(ts[clock][sel], ts['anees_cond_xy'][sel] / 2, color=PL.SERIES[i], lw=1.0,
                        label=route if lv == 0 else None)
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel(lab)
    axes[0].set_ylabel('cond. XY NEES / 2')
    axes[0].set_title('all 9 cells vs filter heading sigma')
    axes[1].set_title('all 9 cells vs time')
    axes[0].legend(loc='upper left')
    paths.append(PL.save(fig, FIG / f'D1_clock_collapse_{tag}.png'))
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', default='B0')
    ap.add_argument('--seeds', default='6000:6300')
    a = ap.parse_args()
    started = H.utc_now()
    seeds = seed_range(a.seeds)
    tag = f'{a.arm}_{seed_tag(seeds)}'
    series, cells = {}, {}
    for route, lv in H.CELLS:
        arr = load_cell(a.arm, seeds, route, lv)
        ts = cell_timeseries(arr, route)
        name = H.cell_name(route, lv)
        series[name] = ts
        keep = ts['t'] >= 30
        cells[name] = dict(
            departure=departure(ts, len(seeds)), attribution=phase_attribution(ts),
            mean_t30=dict(anees=float(np.mean(ts['anees_post'][keep])), heading=float(np.mean(ts['anees_heading'][keep])),
                          cond_xy=float(np.mean(ts['anees_cond_xy'][keep])), xy_marginal=float(np.mean(ts['anees_xy'][keep])),
                          z2_long=float(np.mean(ts['z2_long'][keep])), z2_lat=float(np.mean(ts['z2_lat'][keep])),
                          z2_long_cond=float(np.mean(ts['z2_long_cond'][keep])), z2_lat_cond=float(np.mean(ts['z2_lat_cond'][keep]))),
            first_30s=dict(anees=float(np.mean(ts['anees_post'][~keep][1:])), heading=float(np.mean(ts['anees_heading'][~keep][1:])),
                           cond_xy=float(np.mean(ts['anees_cond_xy'][~keep][1:]))),
            end=dict(anees=float(ts['anees_post'][-1]), sigma_psi_deg=float(ts['sigma_psi_deg'][-1]),
                     heading_rms_deg=float(ts['heading_rms_deg'][-1]), pos_rms_m=float(ts['pos_rms_m'][-1]),
                     cond_min_sigma_cm=float(ts['cond_min_sigma_cm'][-1])))
    doc = dict(arm=a.arm, seeds=[seeds[0], seeds[-1]], n=len(seeds), band=DC.anees_band(len(seeds)), cells=cells,
               pooled_clock_test=pooled_clock_test(series))
    OUT.mkdir(exist_ok=True)
    js = OUT / f'D1_ANEES_{tag}.json'
    js.write_text(IO.json_text(doc))
    csv_path = OUT / f'D1_ANEES_TIMESERIES_{tag}.csv'
    write_timeseries_csv(series, csv_path)
    figs = figures(series, len(seeds), tag)
    H.write_manifest(OUT, f'D1_ANEES_{tag}', dict(arm=a.arm, seeds=a.seeds), [js, csv_path] + figs, started)
    for name, c in cells.items():
        d = c['departure']
        print(f"{name}: depart(band) {d['band_upper']['first_persistent_t_s']:.1f}s depart(3.6) {d['criterion_3p6']['first_persistent_t_s']:.1f}s "
              f"head-first {d['component_first']['heading_t_s']:.1f} condXY-first {d['component_first']['cond_xy_t_s']:.1f} | "
              f"t>=30 head {c['mean_t30']['heading']:.2f} condXY {c['mean_t30']['cond_xy']:.2f} z2long|psi {c['mean_t30']['z2_long_cond']:.2f} "
              f"z2lat|psi {c['mean_t30']['z2_lat_cond']:.2f} | end sigpsi {c['end']['sigma_psi_deg']:.1f} headRMS {c['end']['heading_rms_deg']:.1f}")
    print(json.dumps(doc['pooled_clock_test'], indent=1))


if __name__ == '__main__':
    main()
