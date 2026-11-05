#!/usr/bin/env python3
"""Execute only the preregistered A2 numerical baseline reproduction.

Original E0 output and historical control-byte failures remain immutable.
This entrypoint cannot run a selector, receiver sweep, or higher stage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from qclean_uwb.fp_sc.contracts import git_head, sha256, verify_lock, write_json


def execute(lock_path: Path, approval_path: Path, output: Path):
    lock, approval = json.loads(lock_path.read_text()), json.loads(approval_path.read_text())
    if lock.get('amendment') != 'A2_REMATERIALIZED_CONTROLS':
        raise ValueError('A2_EXPLICIT_AMENDMENT_REQUIRED')
    if approval.get('execution_lock_sha256') != sha256(lock_path):
        raise ValueError('EXECUTION_LOCK_AUTHORIZATION_MISMATCH')
    review_path = REPO / approval['code_review_file']
    if sha256(review_path) != approval['code_review_sha256']:
        raise ValueError('CODE_REVIEW_DRIFT')
    review = json.loads(review_path.read_text())
    if review.get('code_lock_sha256') != sha256(REPO / lock['code_lock_file']):
        raise ValueError('REVIEW_CODE_LOCK_MISMATCH')
    if review.get('verdict') != 'PASS_FOR_E0_A2_EXECUTION':
        raise ValueError('A2_CODE_REVIEW_NOT_ACCEPTED')
    identities = verify_lock(REPO, lock, approval)
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema='FP_SC_E0_A2_RUN_V1', stage='E0', amendment=lock['amendment'],
        utc_start=dt.datetime.now(dt.timezone.utc).isoformat(), status='RUNNING',
        execution_commit=git_head(REPO), implementation_commit=lock['implementation_commit'],
        execution_lock_sha256=sha256(lock_path), approval_sha256=sha256(approval_path),
        pre_execution=identities, exact_historical_control_bytes='UNRESOLVED_R4_R5',
        external_independent_accept=False, next_stage_GO=False, hypotheses_H1_H7='NOT_TESTED')
    write_json(output / 'RUN_MANIFEST.json', manifest)
    from qclean_uwb.fp_sc.e0_baseline import run_baseline
    try:
        result = run_baseline(REPO, output / 'baseline', mode='full',
            rematerialized_registry=REPO / lock['rematerialized_controls_registry'])
        manifest['results'] = {'baseline': result}
        manifest['status'] = ('NUMERICAL_REPRODUCTION_WITH_REMATERIALIZED_CONTROLS'
            if result['status'] == 'PASS_FULL_BASELINE_PARITY' else result['status'])
    except Exception as exc:
        manifest.update(status='FAILED', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        manifest['utc_end'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(output / 'RUN_MANIFEST.json', manifest)
        write_json(output / 'ARTIFACT_HASHES.json', {
            p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob('*'))
            if p.is_file() and p.name != 'ARTIFACT_HASHES.json'})
    print(json.dumps({'status': manifest['status'], 'next_stage_GO': False}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    execute(args.lock.resolve(), args.approval.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
