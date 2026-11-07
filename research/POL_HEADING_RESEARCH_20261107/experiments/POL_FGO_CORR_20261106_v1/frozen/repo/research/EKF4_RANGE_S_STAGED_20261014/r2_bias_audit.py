"""Snowball source/input self-check. Not an independent scientific audit."""
import argparse, ast, hashlib, json, os
from pathlib import Path
from anchor_b_inputs import ROOT, LOCK, read_lock, sha_file

HERE=Path(__file__).resolve().parent
ARCHIVE=read_lock()['archive_sha256'] if LOCK.exists() else None

def verify_sources(source_lock,root=ROOT):
    for relative,expected in source_lock.items():
        p=root/relative
        if not p.is_file() or sha_file(p)!=expected:
            raise RuntimeError('SOURCE_CHANGED:'+relative)

def check(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    errors=[];checks={};lock={}
    try:
        lock=read_lock()
        if os.environ.get('GITHUB_SHA')!=lock['upstream_commit']:
            raise RuntimeError('UPSTREAM_SHA_MISMATCH')
        checks=lock['source_sha256']
        if not checks:raise RuntimeError('EMPTY_SOURCE_LOCK')
        actual={str(p.relative_to(ROOT)).replace('\\','/') for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.py','.json','.npy','.ini','.sh')}
        if actual!=set(checks):raise RuntimeError('SOURCE_LOCK_COVERAGE_MISMATCH')
        verify_sources(checks)
        frozen=json.loads((ROOT.parent/'FROZEN_BASE.json').read_text())
        for rel,expected in frozen.items():
            p=ROOT/rel
            raw=p.read_bytes()
            blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if blob!=expected:raise RuntimeError('FROZEN_BASE_CHANGED:'+rel)
        manifest=json.loads((ROOT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
        case=next(x for x in manifest['cases'] if x['id']=='R2_aB_m0')
        if case['mount_deg']!=0 or any(abs(a-b)>1e-12 for a,b in zip(case['anchor'],[10,0,2.65])):
            raise RuntimeError('ANCHORB_GEOMETRY_CHANGED')
        source=(HERE/'r2_bias_replay.py').read_text()
        tree=ast.parse(source)
        cases=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CASES' for t in n.targets))
        if cases!=('R2_aB_m0',):raise RuntimeError('WRONG_CASE_SCOPE')
        fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_filters')
        if any(isinstance(n,ast.Name) and n.id in ('truth','true_bias') for n in ast.walk(fun)):
            raise RuntimeError('TRUTH_LEAKAGE')
        if 'if alg in ("S3","S4"):' not in source or 'if not alg.startswith("SR"):' not in source:
            raise RuntimeError('SR_DISPATCH_CHANGED')
        if 'if max(parity)>1e-7:raise RuntimeError' not in source:
            raise RuntimeError('B0_PARITY_GATE_REMOVED')
        from anchor_b_inputs import open_verified_archive
        with open_verified_archive(ROOT.parent/'input/anchor_b_frozen.zip'):pass
    except Exception as exc:errors.append(str(exc))
    receipt={'question_id':'DLP-ANCHORB-8ARM-20261102','decision':'HOLD' if errors else 'GO',
        'git_sha':os.environ.get('GITHUB_SHA'),'upstream_commit':lock.get('upstream_commit'),
        'execution_lock_sha256':sha_file(LOCK) if LOCK.exists() else None,
        'frozen_archive_sha256':ARCHIVE,'source_sha256':checks,'fatal':errors,
        'independent_audit':False,'scientific_PASS':False}
    (out/'AUDIT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
    return 2 if errors else 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True)
    raise SystemExit(check(p.parse_args().out))
