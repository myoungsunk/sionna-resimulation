#!/usr/bin/env python3
"""Safe additive patch for exact 4d2414a. Copies baseline into a NEW folder.
Never writes to the Git repository or the frozen RF / E1 result directories.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path

BASE_SHA='4d2414a7238176b6e116cae2d10546e724b66b8d'
RELATIVE='research/DS_REASSESS_STAGE235_V21_20261028'
VERSION='RF_CAUSAL_7_8_20261028_V1'
SOURCE_CODE_HASHES={
  'dsreassess/__init__.py':'9f55017fc72532692ed069f29895298d08deac267dd41b7d630e4a5aea3a0569',
  'dsreassess/engine.py':'f0c58ff3b166d3b4f6baedf85d6589b5dadecb6beed87f9ba475a5bf9c9d777c',
  'dsreassess/io.py':'33b9191ecff37d2090414764f575a9d0a4f006da6f01e5f41a00857d2081c2fc',
  'dsreassess/numerics.py':'84626fbb6e0ace42932ee853f0a7b33bd8457cb646dd38386b1e95f83179282c',
  'dsreassess/observability.py':'9f4381f21676fbe1c8ff4db31cde5cac3cc84c358aacb2f7ca4dd0c89cf5c3bf',
  'dsreassess/stage12.py':'89b2dcfd8126604abba546167e55108aaa6ef8f0a59244781f271dc325a5342b',
  'dsreassess/stage34.py':'e2ef7fbdaeb41fbee8635c367c87233d22de5eecc701b11b3b557e95032b094b',
  'dsreassess/stage56.py':'558852f1dec80d42ff50f29dc5bede1b2ccbd3187276ef41b9c120ed97499e66',
  'dsreassess/fisher_independent.py':'018d677d6f5fe1aaab8392f8487e6f951461870f4702526920146abf128210ec',
  'run.py':'750f68edf42bbbc7d6c2261872651cce5d63848aa6672ef570b4f3d9700c81f2',
}

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for buf in iter(lambda:f.read(1<<20),b''):h.update(buf)
    return h.hexdigest()

def apply(repo,code_out,package_root):
    repo=repo.resolve();code_out=code_out.resolve()
    if not repo.is_dir():raise ValueError('repo-root must be existing checkout')
    head=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    if head!=BASE_SHA:raise RuntimeError(f'REPOSITORY_NOT_EXACT_4d2414a: {head}')
    if code_out.exists():raise RuntimeError(f'CODE_OUT_MUST_NOT_EXIST: {code_out}')
    if repo==code_out or repo in code_out.parents:
        raise RuntimeError('CODE_OUT_MUST_BE_OUTSIDE_REPO')
    src=repo/RELATIVE/'code'
    if not src.is_dir():raise RuntimeError(f'MISSING_BASE_CODE {src}')
    final=repo/RELATIVE/'results/PATCH_V2_FINAL.json'
    if not final.is_file():raise RuntimeError('MISSING_PRIOR_STAGE235_TECHNICAL_GATE')
    detail=json.loads(final.read_text(encoding='utf-8'))
    if detail.get('status')!='TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION':
        raise RuntimeError('STAGE235_GATE_NOT_PASS')
    canonical_lf={}
    for name,expected in SOURCE_CODE_HASHES.items():
        f=src/name
        if not f.is_file():raise RuntimeError(f'FROZEN_BASE_SOURCE_MISSING {name}')
        if digest(f)==expected:continue
        # Windows core.autocrlf=true can turn Git's canonical LF into CRLF.
        # Normalize only if raw worktree bytes differ *solely* by line endings.
        # git show reads the canonical committed blob; it never edits the tree.
        gp=f'{RELATIVE}/code/{name}'
        blob=subprocess.run(['git','-C',str(repo),'show',f'{BASE_SHA}:{gp}'],
                            capture_output=True,check=True).stdout
        true_hash=hashlib.sha256(blob).hexdigest()
        if true_hash!=expected or f.read_bytes().replace(b'\r\n',b'\n')!=blob:
            raise RuntimeError(f'FROZEN_BASE_SOURCE_MISMATCH {name}: not LF/CRLF only')
        canonical_lf[name]=blob
    patched=detail['contract']['source_code_hashes']
    for name,expected in SOURCE_CODE_HASHES.items():
        if patched.get(name.replace('/','\\'))!=expected:
            raise RuntimeError(f'FINAL_CODE_MANIFEST_MISMATCH {name}')
    files=[('dsreassess/causal_evidence.py','dsreassess/causal_evidence.py'),
           ('run_causal.py','run_causal.py'),
           ('tests/test_causal_evidence.py','tests/test_causal_evidence.py')]
    overlay=package_root/'overlay'
    for _,key in files:
        if not (overlay/key).is_file():raise RuntimeError(f'PATCH_INCOMPLETE {key}')
        if (src/key).exists():raise RuntimeError(f'PATCH_ALREADY_PRESENT_IN_BASE {key}')
    code_out.parent.mkdir(parents=True,exist_ok=True)
    # Files are copied, not hardlinked: local changes can never mutate original.
    try:
        shutil.copytree(src,code_out,symlinks=False,
                        ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','*.pyc'))
        for name,blob in canonical_lf.items():
            (code_out/name).write_bytes(blob)
        for _,relative in files:
            target=code_out/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(overlay/relative,target)
        for name,expected in SOURCE_CODE_HASHES.items():
            if digest(code_out/name)!=expected:
                raise RuntimeError(f'BASE_COPY_CHANGED {name}')
        lock={'base_commit':BASE_SHA,'version':VERSION,'files':{
                 str(p.relative_to(code_out)).replace('\\','/'):digest(p)
                 for p in sorted(code_out.rglob('*.py'))},
              'baseline_hashes':SOURCE_CODE_HASHES,
              'patch_added':[x[1] for x in files],
              'original_repo_unmodified':True}
        with (code_out/'CAUSAL_CODE_LOCK.json').open('x',encoding='utf-8') as f:
            json.dump(lock,f,indent=2,sort_keys=True,ensure_ascii=False)
        print('APPLY_PASS',code_out,'checked',len(SOURCE_CODE_HASHES),'base files; locked',len(lock['files']),'python files')
        return lock
    except BaseException:
        # The NEW partial copy is deliberately left for forensic inspection;
        # never touch source. User must choose a new path to retry.
        raise

def main():
    p=argparse.ArgumentParser(description='Copy exact 4d2414a code to clean folder and add only two new experimental stages')
    p.add_argument('--repo-root',required=True,type=Path)
    p.add_argument('--code-out',required=True,type=Path)
    a=p.parse_args()
    apply(a.repo_root,a.code_out,Path(__file__).resolve().parent)

if __name__=='__main__':main()
