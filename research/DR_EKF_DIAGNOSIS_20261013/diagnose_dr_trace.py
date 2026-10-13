"""D0 + trace engine: run arms over the 9 route x drift cells, cache per-run/per-time traces, summarise.

The frozen code is never modified (see dr_harness). For arm B0 with seeds 6000..6299 the summary is checked
against the stored R2-2 cells (research/LOS_RANGE_RECAL_20261012/out_R2/R22_ADR_CELLS.csv) and a bitwise
check against r22_adr_decomposition.one() is run on sample tasks.

usage: diagnose_dr_trace.py --arms B0 [--seeds 6000:6300] [--procs 4] [--check-r22] [--dump R2:2:6000]
Outputs: out/TRACE_<arm>_<seedtag>_CELLS.csv, out/TRACE_<arm>_<seedtag>.json, cache/<arm>_<seedtag>/<cell>.npz (gitignored)
"""
import argparse
import csv
import gzip
import json
import sys
import time
from pathlib import Path

import numpy as np

import dr_harness as H
import dr_io as IO

OUT = H.HERE / 'out'
CACHE = H.HERE / 'cache'


def seed_range(text):
    a, b = (int(x) for x in text.split(':'))
    return list(range(a, b))


def seed_tag(seeds):
    return f's{seeds[0]}-{seeds[-1]}'


def cache_path(arm, seeds, route, level):
    return CACHE / f'{arm}_{seed_tag(seeds)}' / f'{H.cell_name(route, level)}.npz'


def load_cell(arm, seeds, route, level, validate=True):
    """Load a cached cell; with validate=True the content must match the requested seeds and route length."""
    arr = IO.load_cache(cache_path(arm, seeds, route, level))
    if validate:
        problems = IO.validate_cell(arr, seeds, len(H.MOT[route]['t']))
        if problems:
            raise RuntimeError(f'invalid cache {arm} {H.cell_name(route, level)}: {problems}')
    return arr


def cell_status(arm, seeds, route, level):
    """'missing' | 'valid' | 'invalid: ...' (never modifies the file)."""
    p = cache_path(arm, seeds, route, level)
    if not p.exists():
        return 'missing'
    try:
        problems = IO.validate_cell(IO.load_cache(p), seeds, len(H.MOT[route]['t']))
    except Exception as exc:  # unreadable / partially written legacy file
        return f'invalid: {exc}'
    return 'valid' if not problems else 'invalid: ' + '; '.join(problems)


def provenance():
    return dict(harness_sha256=H.sha256(H.HERE / 'dr_harness.py'), runner_sha256=H.sha256(Path(__file__)),
                git_head=H.git_state()['head'], written_utc=H.utc_now())


def run_arm(arm, seeds, procs, cells=H.CELLS, verbose=True, reuse=False):
    """Run an arm cell by cell. reuse=True: a valid cached cell is loaded, never recomputed or overwritten; an
    invalid one aborts (it must be inspected, not silently replaced). reuse=False: every cell is recomputed."""
    rows = []
    for route, level in cells:
        t0 = time.time()
        p = cache_path(arm, seeds, route, level)
        status = cell_status(arm, seeds, route, level) if reuse else 'missing'
        if status.startswith('invalid'):
            raise RuntimeError(f'refusing to overwrite {p}: {status}')
        if status == 'valid':
            arr = load_cell(arm, seeds, route, level)
            how = 'cached'
        else:
            acc, runs = H.run_cell(arm, route, level, seeds, procs=procs)
            arr = H.cell_arrays(runs, acc)
            IO.save_cache(p, arr, provenance())
            how = f'{time.time() - t0:.0f}s'
        m = H.cell_summary(arr, route)
        rows.append(dict(arm=arm, cell=H.cell_name(route, level), n=len(seeds), **m))
        if verbose:
            print(f"{arm:22s} {H.cell_name(route, level)} ANEES {m['anees']:8.2f} late {m['anees_late25']:8.2f} "
                  f"cov {m['coverage95']:.3f} head {m['mean_nees_heading']:.2f} condXY {m['mean_nees_cond_xy']:.2f} "
                  f"({how})", flush=True)
    return rows


def write_rows(rows, path):
    keys = list(rows[0])
    for r in rows[1:]:
        keys += [k for k in r if k not in keys]
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


R22_KEYS = ('anees', 'anees_late25', 'coverage95', 'frac_k_inside_chi2_interval', 'per_run_mean_nees_median',
            'per_run_mean_nees_mean', 'pos_rmse_m', 'heading_rmse_deg')


def check_r22(rows):
    ref = {}
    with open(H.R22_DIR / 'out_R2/R22_ADR_CELLS.csv') as fh:
        for r in csv.DictReader(fh):
            if r['config'] == 'B0':
                ref[r['cell']] = r
    out, worst = {}, 0.0
    for r in rows:
        diffs = {}
        for k in R22_KEYS:
            a, b = float(r[k]), float(ref[r['cell']][k])
            diffs[k] = abs(a - b) / max(abs(b), 1e-12)
        diffs['consistent_equal'] = str(r['consistent']) == ref[r['cell']]['consistent']
        diffs['direction_equal'] = r['direction'] == ref[r['cell']]['direction']
        worst = max(worst, max(v for k, v in diffs.items() if k in R22_KEYS))
        out[r['cell']] = diffs
    sys.path.insert(0, str(H.R22_DIR))
    import r22_adr_decomposition as R22
    bitwise = {}
    for route, level, seed in (('R2', 2, 6000), ('R4', 0, 6150), ('R5', 1, 6299)):
        _, nees, pe, he = R22.one(('B0', route, level, seed))
        mine = H.run_one('B0', route, level, seed)
        E = mine['E_post']
        bitwise[f'{route}_d{level}_s{seed}'] = bool(
            np.array_equal(mine['diag_post']['nees_pose'].astype(np.float32), nees, equal_nan=True)
            and np.array_equal(np.hypot(E[:, 0], E[:, 1]).astype(np.float32), pe)
            and np.array_equal(E[:, 2].astype(np.float32), he))
    status = 'PASS' if worst <= 1e-9 and all(bitwise.values()) and all(
        d['consistent_equal'] and d['direction_equal'] for d in out.values()) else 'FAIL'
    return dict(status=status, max_relative_difference=worst, per_cell=out, bitwise_series_vs_r22_one=bitwise,
                reference='research/LOS_RANGE_RECAL_20261012/out_R2/R22_ADR_CELLS.csv (config B0)')


def dump_full_trace(route, level, seed, arm='B0'):
    """Every logged quantity of one run (state, truth, P pre/post, F, G, Q, H, R, C, S, K, NIS, status) as CSV.gz."""
    r = H.run_one(arm, route, level, seed, full_trace=True)
    m = H.MOT[route]
    inputs, ev, params, truth6 = H.make_world(H.ARMS[arm], route, level, seed)
    path = OUT / f'TRACE_FULL_{arm}_{H.cell_name(route, level)}_s{seed}.csv.gz'
    names = ['x', 'y', 'psi', 'bg', 'sf', 'eps']
    header = ['k', 't', 'phase', 'cum_dist_m', 'cum_abs_yaw_rad', 'ds_true', 'dtheta_true', 'ds_odom', 'dtheta_gyro', 'dtheta_odom']
    header += [f'true_{n}' for n in names] + [f'est_pre_{n}' for n in names] + [f'est_post_{n}' for n in names]
    header += [f'Ppre_{i}{j}' for i in range(6) for j in range(i, 6)] + [f'Ppost_{i}{j}' for i in range(6) for j in range(i, 6)]
    header += [f'F_{i}{j}' for i in range(6) for j in range(6)] + [f'G_{i}{j}' for i in range(6) for j in range(3)]
    header += ['Q_d', 'Q_g', 'Q_o'] + [f'H_{i}' for i in range(6)] + [f'C_{i}' for i in range(6)] + [f'K_{i}' for i in range(6)]
    header += ['R', 'S', 'innovation', 'nis', 'status', 'true_wheelbase_err']
    iu = np.triu_indices(6)
    with gzip.open(path, 'wt', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for k in range(len(m['t'])):
            pre_x = truth6[k] - r['E_pre'][k]
            post_x = truth6[k] - r['E_post'][k]
            row = [k, m['t'][k], m['phase'][k], m['cum_dist'][k], m['cum_rot'][k], m['ds'][k], m['dtheta'][k],
                   inputs['ds_odom'][k], inputs['dtheta_gyro'][k], inputs['dtheta_odom'][k]]
            row += list(truth6[k]) + list(pre_x) + list(post_x) + list(r['P_pre'][k][iu]) + list(r['P_post'][k][iu])
            if k:
                tr = r['trace'][k - 1]
                row += list(tr['F'].ravel()) + list(tr['G'].ravel()) + list(np.diag(tr['Q'])) + list(tr['H']) + list(tr['C'])
                row += list(tr['K']) + [tr['R'], tr['S'], tr['innovation'], tr['innovation'] ** 2 / tr['S'], tr['status']]
            else:
                row += [''] * (36 + 18 + 3 + 6 + 6 + 6 + 4) + ['initial']
            row += [params['wheelbase']]
            w.writerow([f'{v:.17g}' if isinstance(v, (float, np.floating)) else v for v in row])
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arms', nargs='+', default=['B0'])
    ap.add_argument('--seeds', default='6000:6300')
    ap.add_argument('--procs', type=int, default=4)
    ap.add_argument('--cells', nargs='*', default=None, help='subset like R2_d2')
    ap.add_argument('--check-r22', action='store_true')
    ap.add_argument('--dump', nargs='*', default=[], help='route:level:seed full traces (B0)')
    a = ap.parse_args()
    started = H.utc_now()
    seeds = seed_range(a.seeds)
    cells = H.CELLS if not a.cells else tuple((c.split('_d')[0], int(c.split('_d')[1])) for c in a.cells)
    OUT.mkdir(exist_ok=True)
    outputs = []
    for arm in a.arms:
        t0 = time.time()
        rows = run_arm(arm, seeds, a.procs, cells)
        csv_path = OUT / f'TRACE_{arm}_{seed_tag(seeds)}_CELLS.csv'
        write_rows(rows, csv_path)
        doc = dict(arm=H.ARMS[arm].describe(), seeds=[seeds[0], seeds[-1]], n=len(seeds), seconds=time.time() - t0,
                   all_cells_consistent=all(r['consistent'] for r in rows),
                   n_consistent=sum(bool(r['consistent']) for r in rows),
                   n_overconfident=sum(r['direction'] == 'OVERCONFIDENT' for r in rows),
                   n_conservative=sum(r['direction'] == 'CONSERVATIVE' for r in rows),
                   anees_median_over_cells=float(np.median([r['anees'] for r in rows])), cells=rows)
        if a.check_r22 and arm == 'B0' and seeds == list(range(6000, 6300)):
            doc['r22_reproduction'] = check_r22(rows)
            print('R2-2 reproduction:', doc['r22_reproduction']['status'], doc['r22_reproduction']['max_relative_difference'])
        js = OUT / f'TRACE_{arm}_{seed_tag(seeds)}.json'
        js.write_text(IO.json_text(doc))
        outputs += [csv_path, js]
    for spec in a.dump:
        route, level, seed = spec.split(':')
        outputs.append(dump_full_trace(route, int(level), int(seed)))
    H.write_manifest(OUT, f'TRACE_{"_".join(a.arms)}_{seed_tag(seeds)}',
                     dict(arms={k: H.ARMS[k].describe() for k in a.arms}, seeds=a.seeds, cells=[H.cell_name(*c) for c in cells]),
                     outputs, started)


if __name__ == '__main__':
    main()
