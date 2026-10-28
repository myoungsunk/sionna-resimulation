#!/usr/bin/env python3
"""Apply exact 450a21f Stage2/3/5 patch to a NEW code directory only.

- Git original checkout: read-only; exact SHA+per-file SHA256 required.
- New destination: outside repository, no overwrite.
- git apply --check, apply, full patched hash parity, compile, pytest.
- Failure never modifies original Git repository/code/results.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

BASE='450a21fd38cf6be510d55352ae3741c8e808bc0a'
REL='research/DS_REASSESS_1_TO_6_20261027/code'
ROOT=Path(__file__).resolve().parent


def sha256(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):
            h.update(b)
    return h.hexdigest()


def command(argv,cwd=None):
    r=subprocess.run(argv,cwd=cwd,text=True,stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT)
    if r.returncode:
        raise RuntimeError(f'COMMAND FAILED (exit={r.returncode}) {argv!r}\n{r.stdout[-10000:]}')
    return r.stdout


def verify_files(root,manifest,title):
    paths=manifest['sha256']
    for relative,digest in paths.items():
        p=root/relative
        if not p.is_file():raise RuntimeError(f'{title}_FILE_MISSING: {p}')
        got=sha256(p)
        if got!=digest:raise RuntimeError(f'{title}_SHA256_MISMATCH: {p}\nexpected={digest}\nactual={got}')
    return len(paths)


def main():
    p=argparse.ArgumentParser(description='Safe exact SHA-gated Stage2/3/5 patch application')
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--code-out',type=Path,required=True)
    p.add_argument('--skip-tests',action='store_true',
                   help='Only for diagnosing a missing local pytest environment; not for validated delivery')
    a=p.parse_args()
    repo=a.repo_root.expanduser().resolve();dest=a.code_out.expanduser().resolve()
    src=repo/REL
    if not src.is_dir():raise RuntimeError('GIT_450_CODE_DIR_MISSING '+str(src))
    if repo==dest or repo in dest.parents or src==dest or src in dest.parents:
        raise RuntimeError('CODE_OUT_MUST_BE_OUTSIDE_REPOSITORY')
    if dest.exists():raise RuntimeError(f'CODE_OUT_ALREADY_EXISTS; no overwrite: {dest}')
    head=command(['git','-C',str(repo),'rev-parse','HEAD']).strip()
    if head!=BASE:
        raise RuntimeError('EXACT_450a21f_CHECKOUT_REQUIRED: '+head+' != '+BASE)
    base=json.loads((ROOT/'BASELINE_PY_SHA256.json').read_text('utf-8'))
    patched=json.loads((ROOT/'PATCHED_PY_SHA256.json').read_text('utf-8'))
    if base['commit']!=BASE or patched['commit_base']!=BASE:
        raise RuntimeError('PATCH_MANIFEST_WRONG_COMMIT')
    before=verify_files(src,base,'BASELINE')
    patch=ROOT/'STAGE235_V21_450a21f.patch'
    if not patch.is_file():raise RuntimeError('PATCH_FILE_MISSING')
    dest.parent.mkdir(parents=True,exist_ok=True)
    stage_root=Path(tempfile.mkdtemp(prefix='.stage235_v2_build_',dir=dest.parent))
    staging=stage_root/'code'
    receipt={'commit':BASE,'patch_sha256':sha256(patch),
             'original_source':str(src),'baseline_python_checks':before,
             'target':str(dest),'git_original_never_modified':True}
    try:
        shutil.copytree(src,staging,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
        command(['git','-c','core.autocrlf=false','-c','core.eol=lf','apply','--check',str(patch)],cwd=staging)
        command(['git','-c','core.autocrlf=false','-c','core.eol=lf','apply',str(patch)],cwd=staging)
        receipt['patched_python_checks']=verify_files(staging,patched,'PATCHED')
        # The SHA manifest becomes a mandatory code identity gate at runtime.
        shutil.copy2(ROOT/'PATCHED_PY_SHA256.json',staging/'PATCHED_PY_SHA256.json')
        command([sys.executable,'-m','compileall','-q','dsreassess','run_selective.py'],cwd=staging)
        if a.skip_tests:
            receipt['tests']='SKIPPED_NOT_FULLY_VERIFIED'
        else:
            out=command([sys.executable,'-m','pytest','-q','tests'],cwd=staging)
            (staging/'PATCH_APPLY_TESTS.log').write_text(out,encoding='utf-8')
            receipt['tests']=out.strip()
        receipt['status']='PATCH_APPLIED_HASH_VERIFIED'
        (staging/'PATCH_APPLY_RECEIPT.json').write_text(
            json.dumps(receipt,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        shutil.move(str(staging),str(dest))
    except Exception as e:
        # Leave an explicit failure log, but never keep a falsely successful code dir.
        (stage_root/'PATCH_APPLY_FAILURE.txt').write_text(traceback.format_exc(),encoding='utf-8')
        print('[HARD STOP] staging error saved:',stage_root,file=sys.stderr)
        raise
    else:
        shutil.rmtree(stage_root)
    print('[PASS] exact 450a21f baseline matches all files')
    print('[PASS] git apply --check and patched SHA256 match')
    print('[PASS] code staged outside original repository:',dest)
    print('[TESTS]',receipt['tests'])
    print('Next: RUN_VALIDATION.ps1 -Step preflight; then -Step all')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('[ERROR]',type(exc).__name__,str(exc),file=sys.stderr)
        raise SystemExit(2)
