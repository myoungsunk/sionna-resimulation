#!/usr/bin/env python3
"""Self-check for V01b data deliveries. Reads REQUEST_MANIFEST.json; changes nothing.
Usage: python verify_delivery.py <dir with delivered .npy files> [--also-m0 <dir with the verified m0 files>]
Checks (per requested legacy file): exists, byte size, SHA256, dtype complex128, shape, all finite.
Exit code 0 only if every requested file passes. Missing files are reported, not skipped silently.
"""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
M=json.loads((Path(__file__).with_name('REQUEST_MANIFEST.json')).read_text())
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()
def check(path,exp_sha,shape,nbytes):
    r={'file':path.name}
    if not path.exists():r['status']='MISSING';return r
    r['bytes_ok']=path.stat().st_size==nbytes;r['sha256']=sha(path);r['sha_ok']=r['sha256']==exp_sha
    try:
        a=np.load(path,mmap_mode='r');r['dtype_ok']=str(a.dtype)=='complex128';r['shape_ok']=list(a.shape)==shape
        r['finite']=bool(np.isfinite(np.asarray(a)).all())
    except Exception as e:r['load_error']=repr(e)
    r['status']='PASS' if all(r.get(k) for k in ('bytes_ok','sha_ok','dtype_ok','shape_ok','finite')) else 'FAIL'
    return r
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dir',type=Path);a=ap.parse_args()
    rows=[check(a.dir/e['file'],e['sha256'],e['shape'],e['bytes']) for e in M['A_missing_legacy_files']]
    for r in rows:print(json.dumps(r))
    ok=all(r['status']=='PASS' for r in rows);print('RESULT','ALL_PASS' if ok else 'NOT_ALL_PASS');sys.exit(0 if ok else 1)
