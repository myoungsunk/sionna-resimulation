"""Content-addressed E0 execution locks; pointers and drift fail closed."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import zipfile

import numpy as np


SCHEMA = 'FP_SC_E0_EXECUTION_LOCK_V1'
THREAD_VARIABLES = ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def git_head(repo):
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()


def environment():
    packages = {}
    for name in ('numpy', 'scipy', 'pandas', 'joblib', 'threadpoolctl'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    from threadpoolctl import threadpool_info
    blas = [{key: info.get(key) for key in ('user_api', 'internal_api', 'num_threads', 'prefix', 'version', 'architecture')}
            for info in threadpool_info()]
    return dict(python=sys.version, implementation=platform.python_implementation(),
                system=platform.system(), machine=platform.machine(),
                packages=packages, threads={name: os.environ.get(name) for name in THREAD_VARIABLES},
                numerical_libraries=blas, fft='numpy.fft pocketfft')


def _array_header(stream):
    version = np.lib.format.read_magic(stream)
    if version == (1, 0):
        shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
    elif version == (2, 0):
        shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
    else:
        raise ValueError(f'Unsupported npy header version {version}')
    if dtype.hasobject:
        raise ValueError('Object arrays are not permitted')
    return dict(shape=list(shape), dtype=str(dtype), fortran_order=bool(fortran))


def inspect_payload(repo, relative):
    path = (Path(repo) / relative).resolve()
    if not path.is_relative_to(Path(repo).resolve()):
        raise ValueError('Input path outside repository')
    entry = dict(path=relative)
    if not path.is_file():
        return dict(entry, status='MISSING')
    with path.open('rb') as f:
        prefix = f.read(160)
    entry.update(size_bytes=path.stat().st_size, sha256=sha256(path))
    if prefix.startswith(b'version https://git-lfs.github.com/spec/v1'):
        oid = re.search(rb'oid sha256:([a-f0-9]{64})', prefix)
        size = re.search(rb'size ([0-9]+)', prefix)
        return dict(entry, status='LFS_POINTER_ONLY',
                    expected_payload_sha256=oid[1].decode() if oid else None,
                    expected_payload_size=int(size[1]) if size else None)
    arrays = {}
    if path.suffix == '.npy':
        with path.open('rb') as f:
            arrays['array'] = _array_header(f)
    elif path.suffix == '.npz':
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith('.npy'):
                    raise ValueError(f'Unexpected NPZ member {name}')
                with archive.open(name) as f:
                    arrays[name[:-4]] = _array_header(f)
    return dict(entry, status='VERIFIED_BYTES_AND_SCHEMA' if arrays else 'VERIFIED_BYTES', arrays=arrays)


def verify_lock(repo, lock, approval):
    """Verify all identities before creating an output directory or running math."""
    repo = Path(repo).resolve()
    if lock.get('schema') != SCHEMA or lock.get('stage') != 'E0':
        raise ValueError('WRONG_STAGE_OR_SCHEMA')
    if lock.get('amendment') not in (None, 'A2_REMATERIALIZED_CONTROLS'):
        raise ValueError('UNRECOGNIZED_AMENDMENT')
    if not re.fullmatch('[0-9a-f]{40}', lock.get('implementation_commit', '')):
        raise ValueError('MISSING_IMPLEMENTATION_COMMIT')
    if approval.get('schema') != 'FP_SC_E0_OWNER_SCOPED_EXECUTION_V1' or not approval.get('GO_E0'):
        raise ValueError('MISSING_E0_OWNER_AUTHORIZATION')
    if approval.get('stage') != 'E0' or approval.get('implementation_commit') != lock['implementation_commit']:
        raise ValueError('AUTHORIZATION_SCOPE_MISMATCH')
    if approval.get('external_independent_accept') is not False:
        raise ValueError('INVALID_REVIEW_PROVENANCE')
    required_documents = {lock.get('environment_file'), lock.get('input_lock_file'), lock.get('code_lock_file')}
    if None in required_documents or not required_documents.issubset(lock['documents']):
        raise ValueError('MISSING_REQUIRED_DOCUMENT_HASH')
    reviewed_code_lock = json.loads((repo / lock['code_lock_file']).read_text())
    if lock['code'] != reviewed_code_lock.get('files'):
        raise ValueError('EXECUTION_REVIEWED_CODE_SET_MISMATCH')
    for name, expected in lock['documents'].items():
        if not (repo / name).is_file() or sha256(repo / name) != expected:
            raise ValueError(f'DOCUMENT_DRIFT: {name}')
    for name, expected in lock['code'].items():
        if not (repo / name).is_file() or sha256(repo / name) != expected:
            raise ValueError(f'CODE_DRIFT: {name}')
        committed = subprocess.check_output(['git', 'show', f'{lock["implementation_commit"]}:{name}'], cwd=repo)
        if hashlib.sha256(committed).hexdigest() != expected:
            raise ValueError(f'IMPLEMENTATION_COMMIT_CODE_MISMATCH: {name}')
    expected_env = json.loads((repo / lock['environment_file']).read_text())
    if environment() != expected_env:
        raise ValueError('ENVIRONMENT_DRIFT')
    if any(expected_env['threads'].get(name) != '1' for name in THREAD_VARIABLES):
        raise ValueError('SINGLE_THREAD_LOCK_REQUIRED')
    inputs = json.loads((repo / lock['input_lock_file']).read_text())
    observed_bytes = 0
    for entry in inputs['files']:
        path = repo / entry['path']
        if entry['status'] not in ('VERIFIED_BYTES', 'VERIFIED_BYTES_AND_SCHEMA'):
            raise ValueError(f'BLOCKED_DATA: {entry["path"]}')
        if not path.is_file() or path.stat().st_size != entry['size_bytes'] or sha256(path) != entry['sha256']:
            raise ValueError(f'INPUT_DRIFT: {entry["path"]}')
        observed_bytes += path.stat().st_size
    original_scope = {'sensor_seed': 10, 'baseline_cells': 12, 'dynamic_pose_ids': 3136,
                             'g4_conditions': 24, 'flat_samples': 14000, 'new_rt': 0, 'selector_runs': 0,
                             'sealed_trajectories': 0}
    a2_scope = {'sensor_seed': 10, 'baseline_cells': 12, 'dynamic_pose_ids': 0,
                'g4_conditions': 0, 'flat_samples': 0, 'new_rt': 0, 'selector_runs': 0,
                'sealed_trajectories': 0}
    allowed_scope = a2_scope if lock.get('amendment') == 'A2_REMATERIALIZED_CONTROLS' else original_scope
    if lock['run_scope'] != allowed_scope:
        raise ValueError('RUN_SCOPE_DRIFT')
    if lock.get('amendment') == 'A2_REMATERIALIZED_CONTROLS':
        registry = lock.get('rematerialized_controls_registry')
        if not registry or registry not in lock['documents']:
            raise ValueError('A2_CONTROLS_REGISTRY_NOT_LOCKED')
    return dict(status='PASS_PRE_EXECUTION_IDENTITIES', files=len(inputs['files']), bytes=observed_bytes,
                implementation_commit=lock['implementation_commit'], execution_commit=git_head(repo),
                external_independent_accept=False)
