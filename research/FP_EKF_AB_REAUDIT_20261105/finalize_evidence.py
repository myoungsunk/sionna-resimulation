#!/usr/bin/env python3
"""Finalize the audit package only after all analysis log writers have closed.
This does not execute a scientific filter. Original source is retained unchanged.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path

LEGACY = ('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/'
          'ANALYSIS_FP_EKF_20261105/verify_c1_selfgate.py')

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def finalize(root: Path) -> None:
    root = root.resolve()
    old_path = root / 'evidence/inputs' / LEGACY
    original = old_path.read_text()
    old = 'var=Ppost if yes else Pprior'
    new = 'var=Pprior-float(kp@S@kp) if yes else Pprior'
    if original.count(old) != 1:
        raise ValueError('Pinned C1 source does not have the expected single bug site')
    fixed = original.replace(old, new)
    patch = root / 'patches'
    patch.mkdir(exist_ok=True)
    (patch / 'verify_c1_selfgate_fixed.py').write_text(fixed)
    (patch / 'c1_covariance.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), fixed.splitlines(True),
        fromfile=LEGACY + ' (original)', tofile=LEGACY + ' (isolated correction)')))
    for source in patch.glob('*.py'):
        compile(source.read_text(), str(source), 'exec')
    qa = json.loads((root/'evidence/QA.json').read_text())
    ext = json.loads((root/'evidence/EXTENDED_QA.json').read_text())
    if not qa['S2_S3']['all_arithmetic_pass'] or not ext['all_28_buffer_failures_reproduced']:
        raise ValueError('Do not package a failed or incomplete science audit as passing')
    manifest_path = root / 'evidence/OUTPUT_SHA256.json'
    receipt = root / 'evidence/PACKAGING_QA.json'
    files = sorted(p for p in root.rglob('*') if p.is_file()
                   and p not in (manifest_path, receipt) and '__pycache__' not in p.parts)
    meta = dict(status='PASS', manifest_path='evidence/OUTPUT_SHA256.json',
                manifest_scope='audit-folder-relative paths; includes hidden .gitattributes and closed logs; excludes manifest itself and __pycache__',
                manifest_entries=len(files)+1, legacy_c1_source_sha256=sha(old_path),
                original_sources_unchanged=True, patched_nonlinear_performance_run=False,
                note='Earlier intermediate artifact included a log hash before the writer closed and omitted hidden .gitattributes. Finalize after closed logs and upload hidden files.')
    receipt.write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
    entries = {p.relative_to(root).as_posix():sha(p) for p in sorted(files+[receipt])}
    manifest_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2)+'\n')
    for rel, expected in entries.items():
        if sha(root/rel) != expected:
            raise ValueError('Post-finalization byte mismatch: '+rel)
    print(json.dumps(meta, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    finalize(parser.parse_args().root)
