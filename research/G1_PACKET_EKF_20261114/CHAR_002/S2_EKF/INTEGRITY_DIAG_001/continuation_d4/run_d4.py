"""G1-INT-DIAG-001/D4 on the frozen D0/D2 packet grid."""

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
D0 = PARENT / 'attempt_02' / 'd0'
D2 = PARENT / 'continuation_d2_d3' / 'd2'
STRUCTURE = PARENT / 'structure_sc_ki'
PUBLICATION = PARENT.parents[1] / 'g1_int_diag001_publication_20261115'
REVISION = '3405f0d5b397c3f06857bd81d1b3874ced40841e'
BASE_SHA = 'c5582baf48948a5a20a9c555c10ad708fd18326a27a5ad463f830f9c7b5333cc'
DIAG_SHA = '473aecc118a579c581333258cf06806db5dba0e0c9710f93e83d2ebf9cea9083'
B_STRUCT_SHA = 'c056347b9d8a20685442235d250415058c85073ec93535c947723c685d2d684b'
LOCK = HERE / 'RUN_CONTRACT.json'
QUESTION = 'G1-INT-DIAG-001/D4'
TOL = 1e-10

sys.path.insert(0, str(PARENT))
from d0_d5 import bind, identity, key_for, spec_for
from d1_shuffle import dump, now, sha, verify_file


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def item(path):
    return {'path': str(path), 'sha256': sha(path)}


def pinned(path, digest):
    return item(verify_file({'path': str(path), 'sha256': digest}))


def freeze(path=LOCK):
    from feature_d4 import feature_inputs
    from residual_d4 import D4_THRESHOLDS

    parent = pinned(PARENT / 'RUN_CONTRACT.json', BASE_SHA)
    diag = pinned(D2.parent / 'CONTINUATION_CONTRACT.json', DIAG_SHA)
    structure = pinned(STRUCTURE / 'RUN_CONTRACT.json', B_STRUCT_SHA)
    base = read(parent['path'])
    revision = subprocess.check_output(['git', '-C', str(PUBLICATION), 'rev-parse',
                                        'origin/research/g1-sweep-heading-floor-spec-20261113'], text=True).strip()
    if revision != REVISION:
        raise ValueError('Expected published plan and SC/KI evidence at pinned branch revision')
    d0_check_path, diag_check_path = D0.parent / 'VERIFICATION.json', D2.parent / 'VERIFICATION.json'
    struct_check_path = STRUCTURE / 'VERIFICATION.json'
    d0_check, diag_check, struct_check = map(read, (d0_check_path, diag_check_path, struct_check_path))
    for check, key, digest in [(d0_check, 'contract_sha256', BASE_SHA),
                               (diag_check, 'continuation_contract_sha256', DIAG_SHA),
                               (struct_check, 'contract_sha256', B_STRUCT_SHA)]:
        if check['status'] != 'PASS_REAGGREGATION' or check[key] != digest:
            raise ValueError('Prior research verification missing or mismatched')
    prerequisites = [parent, diag, structure, item(d0_check_path), item(diag_check_path), item(struct_check_path),
                     pinned(D0 / 'EXECUTION.json', d0_check['d0_d5_execution_sha256']['d0']),
                     pinned(D2 / 'EXECUTION.json', diag_check['output_checks']['d2']),
                     pinned(D2.parent / 'd3' / 'EXECUTION.json', diag_check['output_checks']['d3']),
                     pinned(STRUCTURE / 'run_01' / 'EXECUTION.json', struct_check['execution_sha256'])]
    for row in prerequisites[6:]:
        if read(row['path'])['exit_code'] != 0:
            raise ValueError(f"Prior run failed: {row['path']}")
    d0_receipt = read(D0 / 'EXECUTION.json')['outputs']
    d2_receipt = read(D2 / 'EXECUTION.json')['outputs']
    structure_receipt = read(STRUCTURE / 'run_01' / 'EXECUTION.json')['outputs']
    structure_scores = pinned(STRUCTURE / 'run_01' / 'RESULTS.json', structure_receipt['RESULTS.json'])
    prerequisites.append(structure_scores)
    prerequisites.append(pinned(D0 / 'RESULTS.json', d0_receipt['RESULTS.json']))
    prereq_assets = [base['provenance']['original_plan'], base['provenance']['amendment'], *base['governance'],
                     *base['provenance']['native_files'].values()]
    for asset in prereq_assets:
        verify_file(asset)
    cells = []
    for cell in base['cells']:
        name = f'{key_for(cell)}.npz'
        for key in ('online', 'evaluator'):
            verify_file(cell[key])
        if cell.get('archive_trace'):
            verify_file(cell['archive_trace'])
        cells.append(cell | {'d0_trace': pinned(D0 / name, d0_receipt[name]),
                             'd2_residual_check': pinned(D2 / name, d2_receipt[name])})
    d0_src = pinned(PARENT / 'd0_d5.py', read(D0.parent / 'RETRY_RECEIPT.json')['d0_d5_corrected_driver_sha256'])
    s2_sources = [entry for entry in base['provenance']['code'] if Path(entry['path']).parent == Path(base['s2'])]
    for entry in s2_sources:
        verify_file(entry)
    sources = [item(Path(__file__)), item(HERE / 'residual_d4.py'), item(HERE / 'feature_d4.py'), item(HERE / 'verify_d4.py'),
               d0_src, item(PARENT / 'd1_shuffle.py'), *s2_sources]
    features = feature_inputs()
    lock = {'question': QUESTION, 'classification': 'DIAGNOSTIC_ONLY', 'role': 'IMPLEMENTER', 'frozen_utc': now(),
            'publication': {'repository': 'myoungsunk/sionna-resimulation',
                            'branch': 'research/g1-sweep-heading-floor-spec-20261113', 'commit': revision},
            'scope': base['scope'], 'anchors': base['anchors'], 'cells': cells, 'thresholds': D4_THRESHOLDS,
            'residual': 'z - native SourceFFD h(truth) - frozen per-packet muMB, [r metres, s ratio]',
            'range_primary': 'true horizontal Euclidean distance between robot and anchor',
            'range_sensitivity': 'true 3D slant range using the native robot RF height',
            'R_eff': 'diagonal of authenticated D0 original E0 trace. Keep finite packets before gate.',
            'autocorrelation': 'Raw epsilon centered by route/bin/channel; D2-style initial positive lag pairs '
                               'with product support restricted to contiguous runs within the same bin.',
            'hypothesis_boundary': 'H3 mean-residual evidence only. A results are descriptive; no A confirmatory '
                                   'replay, candidate fitting, gate interventions, D6 or tuning. L2 is paired sensitivity.',
            'feature_assessment': features, 'inputs': prereq_assets,
            'prerequisites': prerequisites, 'sources': sources, 'native': base['native'], 's2': base['s2']}
    dump(path, lock)
    print(f'{QUESTION} contract SHA-256 {sha(path)}', flush=True)


def authenticate(path):
    lock = read(path)
    if lock['question'] != QUESTION:
        raise ValueError('Wrong D4 contract')
    for row in lock['sources'] + lock['inputs'] + lock['prerequisites']:
        verify_file(row)
    sys.path[:0] = [lock['s2'], str(Path(lock['native']) / 'src')]
    return lock


def load_cases(lock, model):
    from qclean_uwb.fp_sc.e0_baseline import SPEC
    from replay_s2 import parity, read_npz, validate_trace

    d0_scores = read(D0 / 'RESULTS.json')['by_cell']
    cases, parity_records = [], {}
    for cell in lock['cells']:
        key = key_for(cell)
        packet, truth = bind(cell)
        d0 = read_npz(verify_file(cell['d0_trace']))
        d2 = read_npz(verify_file(cell['d2_residual_check']))
        identity(packet, d0, ('t', 'pose_id'))
        identity(packet, d2, ('t', 'pose_id'))
        validate_trace(d0)
        spec = spec_for(cell['anchor'], SPEC)
        if list(spec['anchor']) != lock['anchors'][cell['anchor']]:
            raise ValueError(f'Anchor geometry mismatch: {key}')
        nominal, _ = model.batch(np.column_stack((truth, np.zeros(len(truth)))), spec, gradient=False)
        eps = packet['z'] - nominal - packet['muMB']
        parity_records[key] = parity({'epsilon': eps, 'mask': d0['mask']},
                                     {'epsilon': d2['truth_residual_r_s'], 'mask': d2['mask']})
        if parity_records[key]['epsilon']['max_normalized_error'] > TOL:
            raise ValueError(f'Residual parity failed: {key}')
        rho = np.linalg.norm(truth[:, :2] - np.array(spec['anchor'][:2]), axis=1)
        slant = np.hypot(rho, spec['anchor'][2] - spec['robot_z_m'])
        cases.append({k: cell[k] for k in ('anchor', 'bias', 'route')} | {
            't': packet['t'], 'pose_id': packet['pose_id'], 'rho': rho, 'slant': slant, 'epsilon': eps,
            'R_eff_diagonal': d0['Reff'].diagonal(axis1=1, axis2=2), 'mask': d0['mask'],
            'reference_metrics': d0_scores[key]['e0']})
    if len(cases) != lock['scope']['n_expected'] or len(parity_records) != len(cases):
        raise ValueError('Incomplete D4 case inventory')
    return cases, parity_records


def save_table(path, primary, sensitivity):
    rows = []
    for geometry, data in [('horizontal', primary), ('slant', sensitivity)]:
        for entry in data['bins']:
            row = dict(entry)
            ref = row.pop('reference_metrics')
            row = {'distance_geometry': geometry, **row, 'e0_heading_rmse_deg': ref['heading_rmse_deg'],
                   'e0_xy_rmse_cm': ref['xy_rmse_cm']}
            rows.append(row)
    with path.open('x', newline='', encoding='utf-8-sig') as handle:
        csv_writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        csv_writer.writeheader()
        csv_writer.writerows(rows)


def run(contract, out):
    lock = authenticate(contract)
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from feature_d4 import analyze_support
    from residual_d4 import D4_THRESHOLDS, analyze, synthetic_checks

    if lock['thresholds'] != D4_THRESHOLDS:
        raise ValueError('D4 thresholds differ from executable constants')
    out.mkdir(exist_ok=False)
    receipt = {'question': QUESTION, 'started_utc': now(), 'python': sys.version, 'numpy': np.__version__,
               'command': sys.argv, 'contract_sha256': sha(contract)}
    try:
        synthetic = synthetic_checks()
        _, _, model, native_hashes = load_original_model(lock['native'])
        receipt['native_source_hashes'] = native_hashes
        cases, parity_records = load_cases(lock, model)
        primary = analyze(cases)
        sensitivity = analyze([case | {'rho': case['slant']} for case in cases])
        save_table(out / 'RESIDUAL_BINS.csv', primary, sensitivity)
        feature = analyze_support(lock['feature_assessment'], lock['cells'])
        dump(out / 'HGB_FEATURE_SUPPORT.json', feature)
        dump(out / 'RESULTS.json', {'question': QUESTION, 'classification': lock['classification'],
                                    'horizontal': primary, 'slant_sensitivity': sensitivity,
                                    'HGB_feature_support': 'HGB_FEATURE_SUPPORT.json',
                                    'claim_boundary': lock['hypothesis_boundary']})
        dump(out / 'CHECKS.json', {'synthetic': synthetic, 'D2_reconstruction_and_mask_parity': parity_records})
        receipt.update(status='PASS_EXECUTION', exit_code=0)
    except Exception as error:
        receipt.update(status='FAIL_EXECUTION', exit_code=1, error=str(error))
        raise
    finally:
        receipt.update(finished_utc=now(), outputs={p.name: sha(p) for p in out.iterdir() if p.is_file()})
        dump(out / 'EXECUTION.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('freeze', 'run'))
    parser.add_argument('--contract', type=Path, default=LOCK)
    parser.add_argument('--out', type=Path, default=HERE / 'run_01')
    args = parser.parse_args()
    freeze(args.contract) if args.phase == 'freeze' else run(args.contract, args.out)
