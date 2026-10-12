#!/usr/bin/env python3
"""Pre-delivery check for traces_R4_aB. Read-only. Usage: verify_traces.py <traces dir> [--tier 1|2]
Checks per required tag: <tag>_trace.npz and <tag>_trace_receipt.json exist; npz has the required keys; status == 'OK';
array shapes are mutually consistent (jones [K,n,3,3], tau [n], ang [4,n], present [K,n], node_bins [K]); node bin 128 is present;
tau/ang finite; receipt tag/x/y agree with the npz. Missing or malformed files are reported, never skipped silently.
Exit code 0 only if every required tag passes.
"""
import argparse,json,sys
from pathlib import Path
import numpy as np
H=Path(__file__).parent;M=json.loads((H/'TRACE_REQUEST_MANIFEST.json').read_text())
def check(d,tag):
    r=dict(tag=tag);npz=d/f'{tag}_trace.npz';rc=d/f'{tag}_trace_receipt.json'
    if not npz.exists():r['status']='MISSING_NPZ';return r
    if not rc.exists():r['status']='MISSING_RECEIPT';return r
    try:
        z=np.load(npz,allow_pickle=False);miss=[k for k in M['npz_required_keys'] if k not in z.files]
        if miss:r['status']='MISSING_KEYS';r['keys']=miss;return r
        j=z['jones'];tau=z['tau'];ang=z['ang'];pres=z['present'];nb=z['node_bins'];K=len(nb);n=tau.size
        ok=dict(status_ok=str(z['status'])==M['expected_status'],jones_shape=list(j.shape)==[K,n,3,3],ang_shape=list(ang.shape)==[4,n],present_shape=list(pres.shape)==[K,n],
                node128=int(M['required_node_bin']) in set(nb.tolist()),finite=bool(np.isfinite(tau).all() and np.isfinite(ang).all() and np.isfinite(j[pres.astype(bool)]).all() if pres.shape==j.shape[:2] else False))
        rec=json.loads(rc.read_text());ok['receipt_tag']=rec.get('tag')==tag and abs(float(rec.get('x'))-float(z['x']))<1e-9 and abs(float(rec.get('y'))-float(z['y']))<1e-9
        r.update(ok);r['n_paths']=int(n);r['n_nodes']=int(K);r['status']='PASS' if all(ok.values()) else 'FAIL'
    except Exception as e:r['status']='LOAD_ERROR';r['error']=repr(e)
    return r
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dir',type=Path);ap.add_argument('--tier',type=int,default=1,choices=[1,2]);a=ap.parse_args()
    tags=(H/M['tier1' if a.tier==1 else 'tier2']['file']).read_text().split()
    rows=[check(a.dir,t) for t in tags];bad=[r for r in rows if r['status']!='PASS']
    for r in bad:print(json.dumps(r))
    print('CHECKED',len(rows),'PASS',len(rows)-len(bad),'NOT_PASS',len(bad));print('RESULT','ALL_PASS' if not bad else 'NOT_ALL_PASS');sys.exit(0 if not bad else 1)
