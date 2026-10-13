"""INTERIM snapshot of every arm/cell cached so far (D5 and D6 still running when written).

Reads cache/<arm>_<seedtag>/<cell>.npz, skips files still being written (modified < 30 s ago or unreadable), and writes
per-cell summaries plus EKF/CKF-vs-PF posterior agreement for complete development pairs. It does NOT evaluate the
D6 criteria: those are evaluated only by confirm_dr_independent.py after all D6 arms finish.

usage: snapshot_interim.py
"""
import json
import time

import numpy as np

import dr_harness as H
from compare_dr_nonlinear import posterior_agreement
from diagnose_dr_trace import CACHE, write_rows

OUT = H.HERE / 'out'
PAIRS = (('A2_3_GAUSS_LEVEL', 'PF_A2_3'), ('CKF_A2_3', 'PF_A2_3'), ('A2_3D_GAUSS_DEFAULT', 'PF_A2_3D'),
         ('CKF_A2_3D', 'PF_A2_3D'), ('B0', 'PF_B0'), ('CKF_B0', 'PF_B0'))


def load_ready(path):
    if time.time() - path.stat().st_mtime < 30:
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            return {k: z[k] for k in z.files}
    except Exception:
        return None


def main():
    started = H.utc_now()
    rows, arms = [], {}
    cache = {}
    for d in sorted(CACHE.iterdir()):
        arm, tag = d.name.rsplit('_s', 1)
        role = {'6000-6299': 'development (R2-2 seeds)', '8000-8031': 'development', '8100-8399': 'D6 confirmation (INTERIM, criteria not evaluated)'}[tag]
        done = []
        for route, lv in H.CELLS:
            p = d / f'{H.cell_name(route, lv)}.npz'
            if not p.exists():
                continue
            arr = load_ready(p)
            if arr is None:
                continue
            cache[(arm, tag, H.cell_name(route, lv))] = arr
            m = H.cell_summary(arr, route)
            rows.append(dict(arm=arm, seeds=tag, role=role, cell=H.cell_name(route, lv), n=len(arr['seeds']), **m))
            done.append(H.cell_name(route, lv))
        sub = [r for r in rows if r['arm'] == arm and r['seeds'] == tag]
        arms[f'{arm}|{tag}'] = dict(role=role, cells_complete=len(done), cells=done,
                                    n_consistent=int(sum(bool(r['consistent']) for r in sub)),
                                    anees_median=float(np.median([r['anees'] for r in sub])) if sub else None,
                                    heading_median=float(np.median([r['mean_nees_heading'] for r in sub])) if sub else None,
                                    cond_xy_median=float(np.median([r['mean_nees_cond_xy'] for r in sub])) if sub else None)
    agreement = {}
    for a, ref in PAIRS:
        per = {}
        for route, lv in H.CELLS:
            c = H.cell_name(route, lv)
            if (a, '8000-8031', c) in cache and (ref, '8000-8031', c) in cache:
                per[c], _ = posterior_agreement(cache[(a, '8000-8031', c)], cache[(ref, '8000-8031', c)], route)
        if per:
            agreement[f'{a}_vs_{ref}'] = per
    OUT.mkdir(exist_ok=True)
    csv_path = OUT / 'INTERIM_SNAPSHOT_CELLS.csv'
    write_rows(rows, csv_path)
    js = OUT / 'INTERIM_SNAPSHOT.json'
    js.write_text(json.dumps(dict(status='INTERIM', written_utc=H.utc_now(),
                                  note='D5 and D6 runs in progress; D6 criteria are NOT evaluated here',
                                  arms=arms, posterior_agreement_dev=agreement), indent=1, default=float))
    H.write_manifest(OUT, 'INTERIM_SNAPSHOT', dict(note='interim snapshot of cached arms'), [csv_path, js], started)
    for k, v in arms.items():
        print(f"{k:40s} cells {v['cells_complete']} consistent {v['n_consistent']} ANEESmed {v['anees_median']:.2f} "
              f"head {v['heading_median']:.2f} condXY {v['cond_xy_median']:.2f}")
    for k, v in agreement.items():
        print(k, {c: round(x['enees_t30'], 2) for c, x in v.items()})


if __name__ == '__main__':
    main()
