#!/usr/bin/env python3
"""Prepare or execute the narrowly scoped FP-SC-001 E0 reproduction.

Run with OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1.
Preparation hashes inputs but runs no experiment. Execution requires a reviewed
content lock and the current owner's separately recorded E0 authorization.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import traceback

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

import numpy as np
from qclean_uwb.fp_sc.contracts import environment, git_head, inspect_payload, sha256, verify_lock, write_json


STUDY = Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001')
E0 = STUDY / 'E0_20261105'
PHYSICAL = STUDY.parent
MBVAR = PHYSICAL.parent
RF = Path('results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C')


def prepare():
    folder = REPO / E0
    for name in ('INPUT_LOCK.json', 'ENV_LOCK.json', 'CODE_LOCK.json'):
        if (folder / name).exists():
            raise FileExistsError(f'Preparation output already exists: {name}')
    acquisition = json.loads((folder / 'ACQUISITION_PLAN.json').read_text())
    paths = set(acquisition['paths'])
    paths.add(str(RF / 'freqs_hz.npy'))
    for route in ('R2', 'R4', 'R5'):
        paths.add(str(RF / 'FULL_RF' / f'H_{route}_aB_m0.npy'))
        paths.add(str(RF / f'H_LoS_{route}_aB_m0.npy'))
    paths.update(str(p.relative_to(REPO)) for p in (
        REPO / PHYSICAL / 'C1/C1A_001/FROZEN_PACKETS/MANIFEST.json',
        REPO / PHYSICAL / 'C3/G4_001/RUN_001/CONDITIONS.json',
        REPO / PHYSICAL / 'C3/G4_001/PLAN.json',
        REPO / PHYSICAL / 'FP_PRIOR_PILOT_001/RESULTS_ORACLE_001/SUMMARY.json',
        REPO / PHYSICAL / 'FP_PRIOR_PILOT_001/RESULTS_ORACLE_001/SENSITIVITY_4CM.json',
        REPO / MBVAR / 'POST_S3_PROPOSER_20261104/R2_EXTENSION/FULL_002/NATURAL_INDEX.json',
        REPO / MBVAR / 'POST_S3_PROPOSER_20261104/R2_EXTENSION/NATIVE_001/NATURAL_INDEX.json',
        REPO / MBVAR / 'POST_S3_PROPOSER_20261104/R2_EXTENSION/inputs/INPUT_LOCK.json',
        REPO / MBVAR / 'A0_R3_REFIT/BASE_INPUTS.json',
        REPO / MBVAR / 'S1/runs/EVAL_001/TRACE_INDEX.json',
    ))
    entries = [inspect_payload(REPO, p) for p in sorted(paths)]
    blocked = [e for e in entries if not e['status'].startswith('VERIFIED')]
    write_json(folder / 'INPUT_LOCK.json', dict(schema='FP_SC_E0_INPUT_LOCK_V1',
        source_commit=acquisition['source_commit'], files=entries, blocked=blocked,
        verification='Actual file SHA256, bytes and safe array headers; finite-array checks occur in runners',
        total_verified_bytes=sum(e.get('size_bytes', 0) for e in entries if e['status'].startswith('VERIFIED'))))
    write_json(folder / 'ENV_LOCK.json', environment())
    code_paths = set()
    for directory in ('src/qclean_uwb/drivesim', 'src/qclean_uwb/scenarios', 'src/qclean_uwb/fp_sc'):
        code_paths.update(p.relative_to(REPO).as_posix() for p in (REPO / directory).glob('*.py'))
    code_paths.update([
        'src/qclean_uwb/__init__.py', 'scripts/fp_sc_e0.py', 'scripts/fp_sc_acquire_inputs.py',
        'research/FFD_P0P3_20261016/source_model.py', 'research/FFD_P0P3_20261016/p0_initial.py',
        'research/EKF4_RANGE_S_STAGED_20261014/core.py', 'research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py',
        str(MBVAR / 'S1/online.py'), 'tests/test_fp_sc_e0_baseline.py', 'tests/test_fp_sc_e0_receiver.py',
        'tests/test_fp_sc_contracts.py', str(E0 / 'audit/audit_reference_receiver.py'),
    ])
    code = {p: sha256(REPO / p) for p in sorted(code_paths)}
    write_json(folder / 'CODE_LOCK.json', dict(schema='FP_SC_CODE_CONTENT_V1', files=code))
    print(json.dumps(dict(status='PREPARED_NO_SCIENCE_EXECUTED', inputs=len(entries),
                          blocked=len(blocked), code_files=len(code))), flush=True)


def execute(lock_path, approval_path, output):
    lock = json.loads(lock_path.read_text())
    approval = json.loads(approval_path.read_text())
    if approval.get('execution_lock_sha256') != sha256(lock_path):
        raise ValueError('EXECUTION_LOCK_AUTHORIZATION_MISMATCH')
    review_path = REPO / approval['code_review_file']
    if sha256(review_path) != approval['code_review_sha256']:
        raise ValueError('CODE_REVIEW_DRIFT')
    review = json.loads(review_path.read_text())
    if review.get('code_lock_sha256') != sha256(REPO / E0 / 'CODE_LOCK.json'):
        raise ValueError('REVIEW_CODE_LOCK_MISMATCH')
    if review.get('verdict') != 'PASS_FOR_E0_EXECUTION':
        raise ValueError('E0_CODE_REVIEW_NOT_ACCEPTED')
    verification = verify_lock(REPO, lock, approval)
    output.mkdir(parents=True, exist_ok=False)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = dict(schema='FP_SC_E0_RUN_MANIFEST_V1', study='FP-SC-001', stage='E0',
                    status='RUNNING', utc_start=started, command_line=sys.argv,
                    execution_commit=git_head(REPO), implementation_commit=lock['implementation_commit'],
                    execution_lock_sha256=sha256(lock_path), approval_sha256=sha256(approval_path),
                    input_lock_sha256=sha256(REPO / lock['input_lock_file']),
                    environment_lock_sha256=sha256(REPO / lock['environment_file']),
                    pre_execution=verification, role='IMPLEMENTER',
                    external_independent_accept=False, stages_E1_E5_executed=False,
                    new_RT_runs=0, results={}, failures=[])
    write_json(output / 'RUN_MANIFEST.json', manifest)

    def perform(label, fn):
        print('START', label, flush=True)
        try:
            result = fn()
            manifest['results'][label] = result
            print('FINISH', label, result.get('status'), flush=True)
        except Exception as exc:
            failure = dict(component=label, error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
            manifest['failures'].append(failure)
            write_json(output / f'{label}_FAILURE.json', failure)
            print('FAILED', label, failure['error'], flush=True)
        write_json(output / 'RUN_MANIFEST.json', manifest)

    from qclean_uwb.fp_sc import e0_baseline as baseline, e0_receiver as receiver
    perform('baseline', lambda: baseline.run_baseline(REPO, output / 'baseline', mode='full'))
    traces = {f'{r}_{b}_{c}': str(baseline._reference_path(REPO, r, b, c)[0].relative_to(REPO))
              for r in ('R2', 'R4', 'R5') for b in ('B0', 'L2') for c in ('Full', 'Native_LoS')}
    perform('receiver', lambda: receiver.run_dynamic(REPO, output / 'receiver', trace_paths=traces))

    def g4():
        _, _, model, _ = baseline.load_original_model(REPO)
        return receiver.run_g4(REPO, output / 'g4', source_model=model)
    perform('g4', g4)
    frequencies = np.load(REPO / RF / 'freqs_hz.npy', allow_pickle=False)
    distances = np.arange(2.0, 16.0, 0.001)
    if len(distances) != lock['run_scope']['flat_samples']:
        raise ValueError('FLAT_SWEEP_SCOPE_MISMATCH')
    perform('flat_mapping', lambda: receiver.run_flat_sweep(frequencies, output / 'flat_mapping',
                distances_m=distances, b_old=baseline.B_OLD))
    # This manifest deliberately does not equate completing calculations with
    # an E0 gate pass. Separate reviewer/lineage/mapping findings decide that.
    manifest.update(status='COMPLETED_COMPONENTS_PENDING_E0_RESULT_REVIEW' if not manifest['failures'] else 'COMPLETED_WITH_FAILURES',
                    utc_end=dt.datetime.now(dt.timezone.utc).isoformat(),
                    next_stage_GO=False, hypothesis_H0='PENDING_RESULT_REVIEW',
                    hypotheses_H1_H7='NOT_TESTED')
    write_json(output / 'RUN_MANIFEST.json', manifest)
    hashes = {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob('*'))
              if p.is_file() and p.name != 'ARTIFACT_HASHES.json'}
    write_json(output / 'ARTIFACT_HASHES.json', hashes)
    print(json.dumps({'status':manifest['status'], 'components': {k:v.get('status') for k,v in manifest['results'].items()},
                      'failures':len(manifest['failures'])}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare')
    run = commands.add_parser('run')
    run.add_argument('--lock', type=Path, required=True)
    run.add_argument('--approval', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare()
    else:
        execute(args.lock.resolve(), args.approval.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
