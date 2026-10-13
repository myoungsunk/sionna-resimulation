"""D6: independent confirmation on seeds frozen in D6_SPEC.json (8100-8399), criteria frozen in D6_PREREG_KO.md.

The spec (arms, seeds, criteria, thresholds) must be committed before this script is run; the script refuses to run
if D6_SPEC.json has uncommitted changes. Each criterion is evaluated mechanically and reported PASS/FAIL; nothing is
tuned after the run.

Two separate modes (evaluation never computes):
  --run-arms ARM ...   compute the missing cells of these spec arms; valid cached cells are reused and never
                       overwritten, an invalid cache aborts the run
  --evaluate           load-only: every spec arm/cell must exist and pass the content check (seed list, route length,
                       finite errors); then the criteria are evaluated and the verdict is derived with the decision
                       rules of D6_PREREG_KO.md (C1-C7 primary, S1 secondary and never part of the cause verdict)

usage: confirm_dr_independent.py --run-arms B0 ... [--procs 4] | --evaluate
"""
import argparse
import json
import subprocess
import sys

import numpy as np

import dr_harness as H
import dr_io as IO
from ablate_dr_calibration import ensure, load_rows, arm_summary
from compare_dr_nonlinear import posterior_agreement
from diagnose_dr_trace import load_cell, cell_status, seed_range, seed_tag, write_rows

OUT = H.HERE / 'out'
SPEC = H.HERE / 'D6_SPEC.json'


def spec_committed():
    r = subprocess.run(['git', '-C', str(H.ROOT), 'status', '--porcelain', '--', str(SPEC)], capture_output=True, text=True)
    tracked = subprocess.run(['git', '-C', str(H.ROOT), 'ls-files', '--error-unmatch', str(SPEC)], capture_output=True, text=True)
    return tracked.returncode == 0 and not r.stdout.strip()


def cells_of(rows):
    return {r['cell']: r for r in rows}


def validity_region(arm, seeds, max_sigma_deg, min_sigma_deg):
    """Per-time ensemble ANEES_k (t >= 10 s) binned by the ensemble-mean filter heading sigma."""
    inside, outside = [], []
    for route, lv in H.CELLS:
        a = load_cell(arm, seeds, route, lv)
        t = H.MOT[route]['t']
        k = t >= 10
        sig = np.degrees(np.nanmean(a['sigma_psi_post'].astype(float), 0))[k]
        an = np.nanmean(a['nees_pose_post'].astype(float), 0)[k]
        inside.append(an[sig <= max_sigma_deg])
        outside.append(an[sig >= min_sigma_deg])
    inside, outside = np.concatenate(inside), np.concatenate(outside)
    return dict(n_inside=int(len(inside)), frac_inside_le_3p6=float(np.mean(inside <= 3.6)) if len(inside) else float('nan'),
                median_inside=float(np.median(inside)) if len(inside) else float('nan'),
                n_outside=int(len(outside)), frac_outside_gt_3p6=float(np.mean(outside > 3.6)) if len(outside) else float('nan'),
                median_outside=float(np.median(outside)) if len(outside) else float('nan'))


def evaluate(spec, rows, seeds):
    res = {}
    for c in spec['criteria']:
        cid, kind = c['id'], c['kind']
        if kind == 'condxy_dominates':
            cells = cells_of(rows[c['arm']])
            per = {k: dict(cond_per_dof=v['mean_nees_cond_xy'] / 2, heading=v['mean_nees_heading']) for k, v in cells.items()}
            ok = all(p['cond_per_dof'] > c['min_cond_per_dof'] and p['cond_per_dof'] > p['heading'] for p in per.values())
            res[cid] = dict(status='PASS' if ok else 'FAIL', per_cell=per)
        elif kind == 'not_overconfident_all_cells':
            cells = cells_of(rows[c['arm']])
            per = {k: dict(anees=v['anees'], late=v['anees_late25'], coverage=v['coverage95']) for k, v in cells.items()}
            ok = all(p['anees'] <= 3.6 and p['late'] <= 3.6 and p['coverage'] >= 0.92 for p in per.values())
            res[cid] = dict(status='PASS' if ok else 'FAIL', per_cell=per)
        elif kind == 'overconfident_cells':
            cells = cells_of(rows[c['arm']])
            per = {k: dict(anees=cells[k]['anees'], heading=cells[k]['mean_nees_heading'],
                           cond_per_dof=cells[k]['mean_nees_cond_xy'] / 2) for k in c['cells']}
            ok = all(v['anees'] > 3.6 and v['heading'] <= c['max_heading'] for v in per.values())
            res[cid] = dict(status='PASS' if ok else 'FAIL', per_cell=per)
        elif kind == 'paired_no_effect':
            x, y = cells_of(rows[c['arm']]), cells_of(rows[c['reference']])
            per = {k: float(np.log(x[k]['anees'] / y[k]['anees'])) for k in x}
            ok = all(abs(v) <= c['max_abs_log_ratio'] for v in per.values())
            res[cid] = dict(status='PASS' if ok else 'FAIL', log_anees_ratio=per)
        elif kind == 'consistent_count':
            cells = cells_of(rows[c['arm']])
            n = sum(bool(v['consistent']) for v in cells.values())
            ok = c['min'] <= n <= c['max']
            res[cid] = dict(status='PASS' if ok else 'FAIL', n_consistent=n,
                            per_cell={k: dict(anees=v['anees'], late=v['anees_late25'], coverage=v['coverage95'], consistent=v['consistent'])
                                      for k, v in cells.items()})
        elif kind == 'reference_beats_ekf':
            e, p = cells_of(rows[c['ekf_arm']]), cells_of(rows[c['ref_arm']])
            per = {k: dict(ekf=e[k]['anees'], ref=p[k]['anees']) for k in c['cells']}
            ok = all(abs(np.log(v['ref'] / 3)) < abs(np.log(v['ekf'] / 3)) and v['ref'] <= c['ref_max_anees'] for v in per.values())
            res[cid] = dict(status='PASS' if ok else 'FAIL', per_cell=per)
        elif kind == 'posterior_agreement':
            per = {}
            for route, lv in H.CELLS:
                name = H.cell_name(route, lv)
                ag, _ = posterior_agreement(load_cell(c['ekf_arm'], seeds, route, lv), load_cell(c['ref_arm'], seeds, route, lv), route)
                per[name] = ag
            lo, hi = c['heading_var_ratio_range']
            ok = (all(per[k]['enees_t30'] > c['enees_min'] for k in c['cells_disagree'])
                  and all(per[k]['enees_t30'] <= c['enees_max_agree'] for k in c['cells_agree'])
                  and all(lo <= v['heading_var_ratio_t30'] <= hi for v in per.values()))
            res[cid] = dict(status='PASS' if ok else 'FAIL', per_cell=per)
        elif kind == 'validity_region':
            vr = validity_region(c['arm'], seeds, c['max_sigma_deg'], c['min_sigma_deg'])
            ok = vr['frac_inside_le_3p6'] >= c['min_frac_inside'] and vr['frac_outside_gt_3p6'] >= c['min_frac_outside']
            res[cid] = dict(status='PASS' if ok else 'FAIL', **vr)
        else:
            raise ValueError(kind)
        res[cid]['claim'] = c['claim']
    return res


PRIMARY = ('C1_PHENOMENON', 'C2_CALIBRATION_NECESSARY', 'C3_MISMATCH_NOT_NECESSARY', 'C4_EXACT_POSTERIOR_FIXES',
           'C5_EKF_POSTERIOR_ERROR', 'C6_C_TERM_IRRELEVANT', 'C7_VALIDITY_REGION')
CAUSE_CRITICAL = ('C2_CALIBRATION_NECESSARY', 'C3_MISMATCH_NOT_NECESSARY', 'C4_EXACT_POSTERIOR_FIXES', 'C5_EKF_POSTERIOR_ERROR')
STATEMENT_ONLY = {'C1_PHENOMENON': 'phenomenon scope (cond-XY dominance in every B0 cell)',
                  'C6_C_TERM_IRRELEVANT': 'irrelevance of the C term', 'C7_VALIDITY_REGION': 'validity-region threshold'}


def verdict(res):
    """Decision rules of D6_PREREG_KO.md section 'Pan-jeong-eo'. S1 is reported separately."""
    failed = [c for c in PRIMARY if res[c]['status'] != 'PASS']
    if not failed:
        cause = 'CAUSE_CONFIRMED: EKF_LINEARISATION_UNDER_CALIBRATION_DRIVEN_HEADING_UNCERTAINTY'
        withdrawn = []
    elif any(c in CAUSE_CRITICAL for c in failed):
        cause = 'UNRESOLVED'
        withdrawn = []
    else:
        cause = 'CAUSE_RETAINED_WITH_WITHDRAWN_STATEMENTS: EKF_LINEARISATION_UNDER_CALIBRATION_DRIVEN_HEADING_UNCERTAINTY'
        withdrawn = [STATEMENT_ONLY[c] for c in failed]
    return dict(cause_verdict=cause, primary_failed=failed, withdrawn_statements=withdrawn,
                secondary=dict(S1_PF_STRICT_GATE=res['S1_PF_STRICT_GATE']['status']))


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--run-arms', nargs='+', default=None)
    mode.add_argument('--evaluate', action='store_true')
    ap.add_argument('--procs', type=int, default=4)
    a = ap.parse_args()
    if not spec_committed():
        raise SystemExit('D6_SPEC.json must be committed (unchanged) before the confirmation run')
    spec = json.loads(SPEC.read_text())
    seeds = seed_range(spec['seeds'])
    if a.run_arms:
        unknown = [x for x in a.run_arms if x not in spec['arms']]
        if unknown:
            raise SystemExit(f'not spec arms: {unknown}')
        ensure(a.run_arms, seeds, a.procs, reuse=True)
        print('computed/verified arms', a.run_arms)
        return
    started = H.utc_now()
    status = {f'{arm}/{H.cell_name(r, lv)}': cell_status(arm, seeds, r, lv) for arm in spec['arms'] for r, lv in H.CELLS}
    bad = {k: v for k, v in status.items() if v != 'valid'}
    if bad:
        print('EVALUATION REFUSED - incomplete or invalid caches (nothing was computed):', file=sys.stderr)
        for k, v in bad.items():
            print(f'  {k}: {v}', file=sys.stderr)
        raise SystemExit(2)
    rows = load_rows(spec['arms'], seeds)
    res = evaluate(spec, rows, seeds)
    tag = seed_tag(seeds)
    doc = dict(spec=spec, spec_sha256=H.sha256(SPEC), seeds=[seeds[0], seeds[-1]], n=len(seeds),
               cache_check='all spec cells present and valid', verdict=verdict(res),
               arms={k: dict(summary=arm_summary(v), cells=v) for k, v in rows.items()}, criteria=res,
               notes=['A2_3D_GAUSS_DEFAULT does not depend on the drift level: its 9 cells are 3 distinct routes in triplicate '
                      '(C7 fractions are unaffected; sample counts are 3x the distinct counts).'])
    js = OUT / f'D6_CONFIRMATION_{tag}.json'
    js.write_text(IO.json_text(doc))
    csv_path = OUT / f'D6_CONFIRMATION_{tag}_CELLS.csv'
    write_rows([r for arm in spec['arms'] for r in rows[arm]], csv_path)
    H.write_manifest(OUT, f'D6_CONFIRMATION_{tag}', spec, [js, csv_path], started, extra_inputs=[SPEC])
    for cid, r in res.items():
        print(cid, r['status'], '-', r['claim'])
    print('verdict', json.dumps(doc['verdict'], indent=1))


if __name__ == '__main__':
    main()
