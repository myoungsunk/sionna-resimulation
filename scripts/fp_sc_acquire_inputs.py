#!/usr/bin/env python3
"""Retrieve *existing* public GitHub LFS payloads, checking their pinned OIDs.

This is data acquisition, not scientific execution. Never reinterpret pointer
bytes as an array. A hash failure leaves the old worktree file unchanged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import quote
from urllib.request import Request, urlopen


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def retrieve(repo, source, repository, relative, staging):
    target = (repo / relative).resolve()
    if not target.is_relative_to(repo.resolve()):
        raise ValueError('Path outside repository')
    pointer = subprocess.check_output(['git', 'show', f'{source}:{relative}'], cwd=repo)
    match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\r?\noid sha256:([0-9a-f]{64})\r?\nsize ([0-9]+)\r?\n?', pointer)
    if not match:
        raise ValueError(f'Pinned object is not an LFS pointer: {relative}')
    expected, size = match[1].decode(), int(match[2])
    result = dict(path=relative, source_commit=source, expected_sha256=expected,
                  expected_size=size, pointer_sha256=hashlib.sha256(pointer).hexdigest())
    start = time.monotonic()
    if target.is_file() and target.stat().st_size == size and digest(target) == expected:
        return dict(result, status='VERIFIED_EXISTING', bytes=size, sha256=expected)
    if target.is_file():
        with target.open('rb') as existing:
            prefix = existing.read(48)
        if not prefix.startswith(b'version https://git-lfs.github.com/spec/v1'):
            return dict(result, status='BLOCKED_DATA', error='EXISTING_NONPOINTER_PAYLOAD_MISMATCH_PRESERVED')
    url = f'https://media.githubusercontent.com/media/{repository}/{source}/{quote(relative, safe="/")}'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=staging, delete=False, suffix='.part') as f:
            temporary = Path(f.name)
            h, count = hashlib.sha256(), 0
            with urlopen(Request(url, headers={'User-Agent': 'FP-SC-001-existing-input-verifier'}), timeout=60) as response:
                if response.status != 200:
                    raise ValueError(f'HTTP status {response.status}')
                for block in iter(lambda: response.read(8 * 1024 * 1024), b''):
                    f.write(block); h.update(block); count += len(block)
                    if count > size:
                        raise ValueError('Payload exceeds pinned size')
        if count != size or h.hexdigest() != expected:
            raise ValueError(f'Payload identity mismatch: size={count}, sha256={h.hexdigest()}')
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
        return dict(result, status='VERIFIED_DOWNLOADED', bytes=count, sha256=expected,
                    elapsed_s=time.monotonic() - start)
    except Exception as exc:
        return dict(result, status='BLOCKED_DATA', error=f'{type(exc).__name__}: {exc}',
                    elapsed_s=time.monotonic() - start)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--staging', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if not re.fullmatch('[0-9a-f]{40}', plan['source_commit']):
        parser.error('Immutable full source SHA required')
    if plan['repository'] != 'myoungsunk/sionna-resimulation':
        parser.error('Unexpected repository')
    if not 1 <= args.workers <= 8:
        parser.error('workers must be 1..8')
    if len(plan['paths']) != len(set(plan['paths'])):
        parser.error('Duplicate input paths')
    args.staging.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(retrieve, args.repo, plan['source_commit'], plan['repository'], p,
                            args.staging): p for p in plan['paths']}
        for future in as_completed(jobs):
            try:
                result = future.result()
            except Exception as exc:
                result = dict(path=jobs[future], status='BLOCKED_DATA', error=f'{type(exc).__name__}: {exc}')
            results.append(result)
            print(json.dumps({k: result[k] for k in ('path', 'status', 'bytes', 'error') if k in result}), flush=True)
    results.sort(key=lambda r: r['path'])
    receipt = dict(schema='FP_SC_INPUT_ACQUISITION_V1', source_commit=plan['source_commit'],
                   plan_sha256=digest(args.plan), files=results,
                   verified=sum(r['status'].startswith('VERIFIED') for r in results),
                   blocked=sum(r['status'] == 'BLOCKED_DATA' for r in results),
                   new_rf_runs=0)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    raise SystemExit(2 if receipt['blocked'] else 0)


if __name__ == '__main__':
    main()
