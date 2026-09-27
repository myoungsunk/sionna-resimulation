"""Validate the S1 local engine smoke outputs (no RF calls).

    python scripts/g2_completion/check_sionna_full_smoke.py \
        --campaign-root results/SIONNA_FULL_RESIM_20260925_01a0d86d --inputs-dir 00_inputs_R3

Scope (decision 2026-09-27): connection check only. 3 bins cannot judge
full-band CIR or detection; that is S2.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_finish import finish_target  # noqa: E402
from rt_cp_uwb_py.g2_full_panels import occluder_conductivity  # noqa: E402
from rt_cp_uwb_py.g2_full_runner import atomic_write_json, attempts, file_sha, verified_receipt  # noqa: E402
from rt_cp_uwb_py.g2_native_channel import sum_native_paths  # noqa: E402
from rt_cp_uwb_py.g2_scoped_channel import ARMS  # noqa: E402

SMOKE = '01_local_checks/rf_smoke'
BUDGET = 20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', required=True)
    a = ap.parse_args()
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    inputs = root/a.inputs_dir
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    panels = json.loads((inputs/'PANELS.json').read_text(encoding='utf8'))
    batch = json.loads((root/SMOKE/'SMOKE_BATCH.jsonl').read_text(encoding='utf8'))
    bdir = root/SMOKE/'runs'/batch['batch_id']
    targets = {}
    with (inputs/'TARGETS.jsonl').open(encoding='utf8') as f:
        for line in f:
            t = json.loads(line)
            if t['target_id'] in batch['target_ids']:
                targets[t['target_id']] = t
    checks, cases, total_calls = [], [], 0
    att = attempts(bdir)
    for tid in batch['target_ids']:
        rp = None
        for at in att:
            if (at/'raw'/f'{tid}.json').is_file():
                rp = at/'raw'/f'{tid}.json'
        receipt = json.loads(rp.read_text(encoding='utf8'))
        ok_receipt = verified_receipt(rp.parent, tid, receipt['run_key']) is not None
        total_calls += receipt['rf_calls']
        meta, t = receipt['meta'], targets[tid]
        with np.load(rp.parent/f'{tid}.npz') as z:
            raw = {k: z[k] for k in z.files}
        bins = raw['bins'].tolist()
        # H re-summed from native a/tau equals the producer sum (complex128 both sides).
        resum = max(float(np.max(np.abs(sum_native_paths(raw[f'{arm}_a_{fi:03d}'], raw[f'{arm}_tau_{fi:03d}'],
                                                          raw['frequencies_hz'][k]) - raw['H_arms'][k, ai])))
                    for k, fi in enumerate(bins) for ai, arm in enumerate(ARMS))
        spec = panels[t['panel_id']]['spec']
        rb = meta['panel_material_readback']
        if spec['kind'] == 'dielectric':
            mat_ok = all(math.isclose(r['relative_permittivity'], 12., rel_tol=1e-6)
                         and math.isclose(r['thickness_m'], .02, rel_tol=1e-6)
                         and math.isclose(r['conductivity_s_m'], occluder_conductivity(r['frequency_hz']), rel_tol=1e-6)
                         for r in rb) and rb[0]['conductivity_s_m'] < rb[-1]['conductivity_s_m']
        else:
            mat_ok = all(r['type'] == 'ITURadioMaterial' and math.isclose(r['thickness_m'], .001, rel_tol=1e-6)
                         for r in rb)
        binding = [b for b in meta['bindings'] if b['object'] == 'dynamic_panel'][0]
        ply_ok = binding['ply_sha256'] == file_sha(inputs/panels[t['panel_id']]['ply'])
        try:
            finish_target(raw, t, config['noise'], config['detector'])
            finish_guard = 'NOT_REJECTED'
        except ValueError as exc:
            finish_guard = str(exc)
        inter = {arm: np.asarray(raw[f'{arm}_interactions_128']).reshape(3, -1) for arm in ARMS}
        valid = {arm: np.asarray(raw[f'{arm}_valid_128']).reshape(-1).astype(bool) for arm in ARMS}
        info = {arm: dict(valid_paths=int(valid[arm].sum()),
                          los=bool(np.any(np.all(inter[arm] == 0, axis=0) & valid[arm])),
                          transmission_paths=int(np.sum(np.any((inter[arm] & 4) != 0, axis=0) & valid[arm])),
                          panel_object_hits=int(np.sum(np.any(
                              np.asarray(raw[f'{arm}_objects_128']).reshape(3, -1) ==
                              int([k for k, v in meta['object_indices'].items() if v == 'dynamic_panel'][0]),
                              axis=0) & valid[arm])))
                for arm in ARMS}
        case = dict(target_id=tid, condition=t['condition'], panel_kind=spec['kind'], bins=bins,
                    receipt_verified=ok_receipt, rf_calls=receipt['rf_calls'], material_readback=rb,
                    material_ok=mat_ok, ply_sha_ok=ply_ok, h_resum_max_abs_diff=resum,
                    finish_rejects_3_bins=finish_guard, path_counts=meta['path_counts'],
                    midband_path_info_not_a_judgement=info, elapsed_s=meta['elapsed_s'])
        cases.append(case)
        checks.append(ok_receipt and mat_ok and ply_ok and resum <= 1e-15 and finish_guard == 'FULL_BAND_REQUIRED'
                      and bins == [0, 128, 256] and receipt['rf_calls'] == 9)
    runtime = json.loads((att[0]/'RUNTIME.json').read_text(encoding='utf8'))
    versions_ok = runtime['versions'] == {'sionna-rt': '2.0.1', 'mitsuba': '3.8.0', 'drjit': '1.3.1'}
    reuse = sorted((bdir/'reuse_checks').glob('*.json')) if (bdir/'reuse_checks').is_dir() else []
    status = 'PASS' if all(checks) and versions_ok and total_calls <= BUDGET else 'FAIL'
    receipt = dict(
        status=status, scope='S1 engine connection smoke; not a full-band CIR/detection judgement (S2)',
        rf_calls_total=total_calls, rf_budget=BUDGET, versions=runtime['versions'], variant=runtime['variant'],
        bank_sha256_config=config['bank_sha256'], runtime_code_sha256=runtime['code_sha256'],
        pathsolver_sha256=runtime['pathsolver_sha256'], cases=cases,
        reuse_check=dict(evidence='second identical invocation: reused=2, computed=0, rf_calls=0, same attempt_001 '
                                  '(stdout recorded in the plan log)',
                         note='that run used the runner before the reuse-only STATUS fix; it overwrote '
                              'attempt_001/STATUS.json and RUNTIME.json with the reuse status (per-target receipts '
                              'intact, rf_calls 9+9). Fixed so reuse-only runs write reuse_checks/<utc>.json; a rerun '
                              'under the fixed code would recompute because the code SHA is part of the run key, '
                              'so it was not repeated (budget).',
                         later_reuse_receipts=[str(p.relative_to(bdir)) for p in reuse]))
    atomic_write_json(root/SMOKE/'SMOKE_RECEIPT.json', receipt)
    for c in cases:
        print(c['condition'], c['panel_kind'], 'material', c['material_ok'], 'ply', c['ply_sha_ok'],
              'resum', c['h_resum_max_abs_diff'], 'finish', c['finish_rejects_3_bins'], 'calls', c['rf_calls'])
        print('   paths per bin/arm', c['path_counts'], 'midband', json.dumps(c['midband_path_info_not_a_judgement']))
    print(json.dumps(dict(status=status, rf_calls_total=total_calls, versions_ok=versions_ok)))


if __name__ == '__main__':
    main()
