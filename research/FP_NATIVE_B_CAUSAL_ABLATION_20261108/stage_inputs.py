#!/usr/bin/env python3
"""Fail-closed staging of exact previously-published FFDbanks & inputs for R45 experiments."""
from __future__ import annotations
import argparse,hashlib,json,pathlib,shutil

def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def copy_verified(original,dest,expected):
    if dest.exists():
        assert h(dest)==expected,('EXISTING_STAGED_SHA_MISMATCH',str(dest))
        return
    partial=dest.with_suffix(dest.suffix+'.part')
    shutil.copyfile(original,partial)
    assert h(partial)==expected,('COPY_SHA_MISMATCH',str(dest))
    partial.replace(dest)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=pathlib.Path,required=True);ap.add_argument('--assets',type=pathlib.Path,required=True);ap.add_argument('--out',type=pathlib.Path,required=True);a=ap.parse_args()
    repo=a.repo.resolve();root=repo/'research/FP_SC_RECOVERY_R0_R5_20261107'
    manifest=json.loads((root/'RUN_002/SUMMARY.json').read_text())['source_hashes']
    src=root/'R45_sources'; lock=json.loads((src/'SOURCE_LOCK.json').read_text())
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    staged=[]
    for name in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
        files=list(a.assets.glob(name));assert len(files)==1,(name,len(files))
        original=files[0];expected=lock[name]
        assert h(original)==expected,('FFD_BANK_HASH_MISMATCH',name,h(original),expected)
        dest=src/name
        copy_verified(original,dest,expected)
        staged.append({'name':name,'sha256':expected,'bytes':dest.stat().st_size})
    inp=root/'inputs';inp.mkdir(exist_ok=True)
    for path,data in manifest.items():
        if not path.endswith(('/online.npz','/evaluator.npz','/ROWS.json.gz')):continue
        original=(a.assets/(pathlib.Path(path).parent.name+'__'+pathlib.Path(path).name)) if path.endswith('.npz') else repo/path
        assert original.is_file(),('MISSING_ORIGINAL',path)
        with original.open('rb') as f:head=f.read(48)
        assert not head.startswith(b'version https://git-lfs.github.com/spec/v1'),('LFS_POINTER',path)
        assert h(original)==data['sha256'],('INPUT_SHA_MISMATCH',path,h(original),data['sha256'])
        dest=inp/(hashlib.sha256(path.encode()).hexdigest()[:20]+'_'+pathlib.Path(path).name)
        copy_verified(original,dest,data['sha256'])
        staged.append({'name':path,'sha256':data['sha256'],'bytes':dest.stat().st_size})
    assert len(staged)==11,('STAGED_COUNT',len(staged))
    (out/'INPUT_RECEIPT.json').write_text(json.dumps({'status':'PASS_STAGED_HASHED_INPUTS','source_commit':'c141839093d1a2e4a76f91eea632cb6467163e28','files':staged},indent=2)+'\n')
    print('PASS_STAGED_HASHED_INPUTS',len(staged),flush=True)
if __name__=='__main__':main()
