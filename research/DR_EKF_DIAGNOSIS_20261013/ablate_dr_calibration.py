"""D4: single-variable interventions on calibration prior, calibration knowledge, odometry update and C (Track A2/A3/A4).

Every arm changes one thing relative to its reference (see dr_harness.ARMS roles). Runs through the trace engine
(same seeds -> paired), writes an arm x cell table and a paired log-ANEES comparison against the reference arm.

usage: ablate_dr_calibration.py [--seeds 8000:8032] [--arms ...] [--reuse]
"""
import argparse
import csv
import json

import numpy as np

import dr_harness as H
import dr_io as IO
import dr_plot as PL
from diagnose_dr_trace import run_arm, cache_path, load_cell, seed_range, seed_tag, write_rows

OUT = H.HERE / 'out'
FIG = OUT / 'fig'
D4_ARMS = ('B0', 'A2_2_PRIOR_MATCHED', 'A2_2C_MATCHED_CLEAN', 'A2_3_GAUSS_LEVEL', 'A2_3D_GAUSS_DEFAULT', 'ORACLE_CAL',
           'ODOM_OFF', 'ORACLE_CAL_ODOM_OFF', 'A2_3_ODOM_OFF', 'A2_3D_ODOM_OFF', 'NO_C', 'Q_TRUE', 'WN_ONLY', 'WN_ONLY_ORACLE')
REFERENCE = {'A2_2_PRIOR_MATCHED': 'B0', 'A2_2C_MATCHED_CLEAN': 'A2_2_PRIOR_MATCHED', 'A2_3_GAUSS_LEVEL': 'A2_2C_MATCHED_CLEAN',
             'A2_3D_GAUSS_DEFAULT': 'B0', 'ORACLE_CAL': 'B0', 'ODOM_OFF': 'B0', 'ORACLE_CAL_ODOM_OFF': 'ORACLE_CAL',
             'A2_3_ODOM_OFF': 'A2_3_GAUSS_LEVEL', 'A2_3D_ODOM_OFF': 'A2_3D_GAUSS_DEFAULT', 'NO_C': 'B0', 'Q_TRUE': 'B0',
             'WN_ONLY': 'B0', 'WN_ONLY_ORACLE': 'WN_ONLY'}


def ensure(arms, seeds, procs, reuse):
    """reuse=True: per-cell reuse of validated caches; only missing cells are computed, nothing is overwritten."""
    return {arm: run_arm(arm, seeds, procs, reuse=reuse) for arm in arms}


def load_rows(arms, seeds):
    """Load-only: summaries from validated caches; raises if any cell is missing or invalid (never computes)."""
    rows = {}
    for arm in arms:
        rr = []
        for r, lv in H.CELLS:
            arr = load_cell(arm, seeds, r, lv)
            rr.append(dict(arm=arm, cell=H.cell_name(r, lv), n=len(seeds), **H.cell_summary(arr, r)))
        rows[arm] = rr
    return rows


def arm_summary(rr):
    def med(k):
        return float(np.median([r[k] for r in rr]))
    return dict(n_consistent=int(sum(bool(r['consistent']) for r in rr)), n_overconfident=int(sum(r['direction'] == 'OVERCONFIDENT' for r in rr)),
                n_conservative=int(sum(r['direction'] == 'CONSERVATIVE' for r in rr)),
                anees_median=med('anees'), anees_min=float(min(r['anees'] for r in rr)), anees_max=float(max(r['anees'] for r in rr)),
                anees_late_median=med('anees_late25'), coverage_median=med('coverage95'), heading_median=med('mean_nees_heading'),
                cond_xy_median=med('mean_nees_cond_xy'), sigma_psi_end_median_deg=med('mean_sigma_psi_end_deg'),
                heading_rms_end_median_deg=med('heading_rms_end_deg'), pos_rmse_median_m=med('pos_rmse_m'),
                odom_z_var_median=med('odom_z_var') if 'odom_z_var' in rr[0] else None)


def paired(rows, arm, ref):
    a = {r['cell']: r for r in rows[arm]}
    b = {r['cell']: r for r in rows[ref]}
    d = {c: float(np.log(a[c]['anees'] / b[c]['anees'])) for c in a}
    return dict(reference=ref, log_anees_ratio=d, median_ratio=float(np.exp(np.median(list(d.values())))),
                cells_improved=int(sum(abs(np.log(a[c]['anees'] / 3)) < abs(np.log(b[c]['anees'] / 3)) for c in a)))


def strip_figure(rows, arms, path, title):
    import matplotlib.pyplot as plt
    PL.style()
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(arms) + 1.2))
    ax.axvspan(2.4, 3.6, color=PL.BAND, lw=0)
    for i, arm in enumerate(arms):
        for r in rows[arm]:
            route = r['cell'].split('_')[0]
            j = H.ROUTES.index(route)
            ax.scatter(r['anees'], len(arms) - 1 - i + (j - 1) * 0.15, color=PL.SERIES[j], s=18, lw=0,
                       label=route if i == 0 and r['cell'].endswith('d0') else None)
    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels(arms[::-1], fontsize=8)
    ax.set_xscale('log')
    ax.set_xlabel('time-mean ensemble pose ANEES, t >= 30 s (band = consistency criterion 2.4-3.6)')
    ax.set_title(title)
    ax.legend(loc='lower right')
    return PL.save(fig, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='8000:8032')
    ap.add_argument('--arms', nargs='*', default=list(D4_ARMS))
    ap.add_argument('--procs', type=int, default=4)
    ap.add_argument('--reuse', action='store_true')
    a = ap.parse_args()
    started = H.utc_now()
    seeds = seed_range(a.seeds)
    tag = seed_tag(seeds)
    rows = ensure(a.arms, seeds, a.procs, a.reuse)
    doc = dict(seeds=[seeds[0], seeds[-1]], n=len(seeds), arms={})
    for arm in a.arms:
        doc['arms'][arm] = dict(definition=H.ARMS[arm].describe(), summary=arm_summary(rows[arm]), cells=rows[arm])
        ref = REFERENCE.get(arm)
        if ref in rows:
            doc['arms'][arm]['paired_vs_reference'] = paired(rows, arm, ref)
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    js = OUT / f'D4_ABLATION_{tag}.json'
    js.write_text(IO.json_text(doc))
    csv_path = OUT / f'D4_ABLATION_{tag}_CELLS.csv'
    write_rows([r for arm in a.arms for r in rows[arm]], csv_path)
    fig = strip_figure(rows, list(a.arms), FIG / f'D4_ablation_{tag}.png', f'D4 interventions (seeds {seeds[0]}-{seeds[-1]})')
    H.write_manifest(OUT, f'D4_ABLATION_{tag}', dict(arms={k: H.ARMS[k].describe() for k in a.arms}, seeds=a.seeds), [js, csv_path, fig], started)
    print(f"{'arm':22s} cons over cons-  ANEESmed (min-max)        late  cov   head  condXY  sigpsi_end headRMS_end")
    for arm in a.arms:
        s = doc['arms'][arm]['summary']
        print(f"{arm:22s} {s['n_consistent']:3d} {s['n_overconfident']:4d} {s['n_conservative']:4d}  {s['anees_median']:7.2f} ({s['anees_min']:.2f}-{s['anees_max']:.1f})"
              f"  {s['anees_late_median']:6.2f} {s['coverage_median']:.3f} {s['heading_median']:5.2f} {s['cond_xy_median']:7.2f} "
              f"{s['sigma_psi_end_median_deg']:8.1f} {s['heading_rms_end_median_deg']:8.1f}")


if __name__ == '__main__':
    main()
