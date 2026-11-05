"""Fail-closed execution identities for the E1-01 candidate-only canary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

from .contracts import environment, git_head, sha256, THREAD_VARIABLES


SCOPE = {'dynamic_waveforms': 6272, 'g4_waveforms': 48, 'packet_mode_rows': 12640,
         'selector_runs': 0, 'ekf_runs': 0, 'new_rt': 0, 'parameter_settings': 1}
FIXED = {'eta_prominence': 0.06, 'local_leading_edge_amplitude_fraction': 0.30,
         'neighbor_radius_taps': 1, 'candidate_min_fraction_of_local_peak': 0.15,
         'minimum_noise_sigma': 3.0, 'packet_union_bound_pfa': 0.001,
         'numeric_floor_epsilon_multiplier': 64, 'max_candidates_for_usable_pool': 64,
         'per_bin_complex_noise_variance': 0.0, 'denominator_power_floor': 0.0,
         'waveform_class': 'CLEAN_EXACT',
         'candidate_modes': ['STRONGEST_ONLY', 'TWO_PORT_UNION']}


def _path(repo, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not (repo / p).resolve().is_relative_to(repo):
        raise ValueError('E1_PATH_OUTSIDE_REPOSITORY')
    return repo / p


def _read(repo, relative):
    return json.loads(_path(repo, relative).read_text())


def verify_e1_lock(repo: Path, lock_path: Path, approval_path: Path) -> dict:
    """Read/hash only; refuse every scientific calculation until all gates pass."""
    repo = Path(repo).resolve()
    lock = json.loads(Path(lock_path).read_text())
    approval = json.loads(Path(approval_path).read_text())
    if lock.get('schema') != 'FP_SC_E1_01_EXECUTION_LOCK_V1' or lock.get('stage') != 'E1-01':
        raise ValueError('E1_WRONG_STAGE_OR_SCHEMA')
    if lock.get('run_scope') != SCOPE:
        raise ValueError('E1_SCOPE_DRIFT')
    commit = lock.get('implementation_commit', '')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('E1_MISSING_IMPLEMENTATION_COMMIT')
    if (approval.get('schema') != 'FP_SC_E1_01_OWNER_SCOPED_EXECUTION_V1'
            or approval.get('stage') != 'E1-01' or approval.get('GO_E1_01') is not True
            or approval.get('implementation_commit') != commit
            or approval.get('external_independent_accept') is not False):
        raise ValueError('E1_AUTHORIZATION_SCOPE_MISMATCH')
    if approval.get('execution_lock_sha256') != sha256(lock_path):
        raise ValueError('E1_AUTHORIZATION_LOCK_MISMATCH')
    required = {lock.get(k) for k in ('code_lock_file', 'input_lock_file', 'environment_file',
                                     'policy_spec_file', 'prerequisite_gate_file')}
    if None in required or not required.issubset(lock.get('documents', {})):
        raise ValueError('E1_REQUIRED_DOCUMENTS_NOT_LOCKED')
    for path, expected in lock['documents'].items():
        if sha256(_path(repo, path)) != expected:
            raise ValueError('E1_DOCUMENT_DRIFT: ' + path)
    review_path = approval.get('code_review_file')
    if not review_path or sha256(_path(repo, review_path)) != approval.get('code_review_sha256'):
        raise ValueError('E1_CODE_REVIEW_DRIFT')
    review = _read(repo, review_path)
    if (review.get('verdict') != 'PASS_FOR_E1_01_EXECUTION'
            or review.get('code_lock_sha256') != sha256(_path(repo, lock['code_lock_file']))
            or review.get('external_independent_accept') is not False):
        raise ValueError('E1_CODE_REVIEW_SCOPE_MISMATCH')
    code = _read(repo, lock['code_lock_file']).get('files')
    if not code or lock.get('code') != code:
        raise ValueError('E1_REVIEWED_CODE_SET_MISMATCH')
    for path, expected in code.items():
        if sha256(_path(repo, path)) != expected:
            raise ValueError('E1_CODE_DRIFT: ' + path)
        value = subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=repo)
        if hashlib.sha256(value).hexdigest() != expected:
            raise ValueError('E1_COMMITTED_CODE_MISMATCH: ' + path)
    spec = _read(repo, lock['policy_spec_file'])
    if spec.get('schema') != 'FP_SC_E1_01_CANDIDATE_SPEC_V1' or spec.get('experiment_id') != 'E1-01':
        raise ValueError('E1_POLICY_SCOPE_MISMATCH')
    cfg = spec.get('fixed_generator', {})
    if any(cfg.get(k) != value for k, value in FIXED.items()):
        raise ValueError('E1_PREREGISTERED_GENERATOR_CHANGED')
    gate = _read(repo, lock['prerequisite_gate_file'])
    if (gate.get('verdict') != 'PASS_FUNCTIONAL_H0_WITH_REMATERIALIZED_CONTROLS'
            or gate.get('GO_E1_01_CANDIDATE_AVAILABILITY') is not True
            or gate.get('E1_02_E5_GO') is not False
            or gate.get('external_independent_accept') is not False):
        raise ValueError('E1_H0_PREREQUISITE_NOT_ACCEPTED')
    if not gate.get('evidence_files'):
        raise ValueError('E1_H0_EVIDENCE_MISSING')
    for path, expected in gate['evidence_files'].items():
        if sha256(_path(repo, path)) != expected:
            raise ValueError('E1_H0_EVIDENCE_DRIFT: ' + path)
    expected_env = _read(repo, lock['environment_file'])
    if environment() != expected_env or any(expected_env['threads'].get(k) != '1' for k in THREAD_VARIABLES):
        raise ValueError('E1_ENVIRONMENT_DRIFT')
    inputs = _read(repo, lock['input_lock_file'])
    if inputs.get('blocked') or not inputs.get('files'):
        raise ValueError('E1_INPUTS_BLOCKED_OR_EMPTY')
    total = 0
    for item in inputs['files']:
        path = _path(repo, item['path'])
        if item['status'] not in ('VERIFIED_BYTES', 'VERIFIED_BYTES_AND_SCHEMA'):
            raise ValueError('E1_INPUT_NOT_MATERIALIZED: ' + item['path'])
        if path.stat().st_size != item['size_bytes'] or sha256(path) != item['sha256']:
            raise ValueError('E1_INPUT_DRIFT: ' + item['path'])
        total += item['size_bytes']
    return {'status': 'PASS_PRE_EXECUTION_IDENTITIES', 'stage': 'E1-01',
            'implementation_commit': commit, 'execution_commit': git_head(repo),
            'files': len(inputs['files']), 'bytes': total, 'run_scope': SCOPE,
            'external_independent_accept': False, 'E1_02_E5_GO': False}
