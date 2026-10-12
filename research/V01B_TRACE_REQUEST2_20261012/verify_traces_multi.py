#!/usr/bin/env python3
"""Pre-delivery check for one trace set. Read-only.
Usage: verify_traces_multi.py <dir> --set R2_aA|R2_aB|R4_aA|R5_aA|R5_aB [--tier 1|2]
Per required tag: <tag>_trace.npz and <tag>_trace_receipt.json exist; npz has the required keys, status == 'OK', consistent shapes
(jones [K,n,3,3], tau [n], ang [4,n], present [K,n], node_bins [K]), node bin 128 present, finite values, tag x/y == npz x/y == receipt x/y.
Receipt: command has the expected --tasks file, --anchor-x and --nodes 17; solver and materials equal the frozen values  -> FAIL if not.
Receipt versions / runner_sha256 differing from the frozen values -> WARN (explain it; not an automatic failure).
Files in the directory that are not required tags are reported as EXTRA (WARN). Exit code 0 only if there is no FAIL/MISSING.
"""
import argparse,json,re,sys
from pathlib import Path
import numpy as np
H=Path(__file__).parent;M=json.loads((H/'TRACE_REQUEST2_MANIFEST.json').read_text());E=M['receipt_expected']
def check(d,tag,st):
    r=dict(tag=tag,fail=[],warn=[]);npz=d/f'{tag}_trace.npz';rc=d/f'{tag}_trace_receipt.json'
    if not npz.exists():r['status']='MISSING_NPZ';return r
    if not rc.exists():r['status']='MISSING_RECEIPT';return r
    try:
        z=np.load(npz,allow_pickle=False);miss=[k for k in M['npz_required_keys'] if k not in z.files]
        if miss:r['status']='MISSING_KEYS';r['keys']=miss;return r
        j,tau,ang,pres,nb=z['jones'],z['tau'],z['ang'],z['present'],z['node_bins'];K,n=len(nb),tau.size
        if str(z['status'])!=E['status']:r['fail'].append('status')
        if list(j.shape)!=[K,n,3,3]:r['fail'].append('jones_shape')
        if list(ang.shape)!=[4,n]:r['fail'].append('ang_shape')
        if list(pres.shape)!=[K,n]:r['fail'].append('present_shape')
        if M['required_node_bin'] not in set(nb.tolist()):r['fail'].append('node128')
        if not (np.isfinite(tau).all() and np.isfinite(ang).all()):r['fail'].append('nonfinite')
        elif list(pres.shape)==[K,n] and not np.isfinite(j[pres.astype(bool)]).all():r['fail'].append('nonfinite_jones')
        m=re.fullmatch(r'x(-?\d+\.\d{4})_y(-?\d+\.\d{4})',tag)
        if not m or abs(float(m[1])-float(z['x']))>1e-9 or abs(float(m[2])-float(z['y']))>1e-9:r['fail'].append('tag_xy')
        c=json.loads(rc.read_text())
        if c.get('tag')!=tag or abs(float(c['x'])-float(z['x']))>1e-9 or abs(float(c['y'])-float(z['y']))>1e-9:r['fail'].append('receipt_xy')
        cmd=c.get('command','');tf=re.search(r'--tasks\s+(\S+)',cmd);ax=re.search(r'--anchor-x\s+(\S+)',cmd);nd=re.search(r'--nodes\s+(\S+)',cmd)
        if not tf or Path(tf[1]).name!=st['tasks_file']:r['fail'].append('tasks_file')
        if not ax or abs(float(ax[1])-st['anchor_x_m'])>1e-9:r['fail'].append('anchor_x')
        if not nd or nd[1]!='17':r['fail'].append('nodes')
        if c.get('solver')!=E['solver']:r['fail'].append('solver')
        if [[x['object'],x['itu_type'],x['thickness_m']] for x in c.get('materials',[])]!=E['materials']:r['fail'].append('materials')
        if c.get('versions')!=E['versions']:r['warn'].append('versions')
        if c.get('runner_sha256')!=E['runner_sha256_in_R4_aB']:r['warn'].append('runner_sha256')
        r['status']='FAIL' if r['fail'] else 'PASS'
    except Exception as e:r['status']='LOAD_ERROR';r['error']=repr(e)
    return r
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dir',type=Path);ap.add_argument('--set',required=True,choices=list(M['sets']));ap.add_argument('--tier',type=int,default=1,choices=[1,2]);a=ap.parse_args()
    st=M['sets'][a.set];tags=(H/st['tags_tier1' if a.tier==1 else 'tags_all']).read_text().split()
    rows=[check(a.dir,t,st) for t in tags];bad=[r for r in rows if r['status']!='PASS'];warn=[r for r in rows if r['warn']]
    req={f'{t}_trace.npz' for t in tags}|{f'{t}_trace_receipt.json' for t in tags};extra=sorted(p.name for p in a.dir.iterdir() if p.is_file() and p.name not in req)
    for r in bad:print(json.dumps(r))
    if warn:print('WARN',len(warn),'tags:',sorted({w for r in warn for w in r['warn']}))
    if extra:print('EXTRA files (not required):',len(extra),extra[:5])
    print('SET',a.set,'TIER',a.tier,'CHECKED',len(rows),'PASS',len(rows)-len(bad),'NOT_PASS',len(bad));print('RESULT','ALL_PASS' if not bad else 'NOT_ALL_PASS');sys.exit(0 if not bad else 1)
