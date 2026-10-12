"""Verify the downloaded V01b-R LoS-H release assets.
Stage 1 (always): SHA256SUMS + manifest SHA, bytes, dtype, shape, finiteness, row count == pose count, rf_poses SHA.
Stage 2 (optional, --src --traces-root --poses-dir): pose-row mapping. Regenerates the LoS H row-by-row from the delivered
  position traces (shortest-delay path, h_for_antenna_yaws with yaw_body+45) and compares every sampled row; also tests that a
  1-row shift is NOT equal, so a wrong pose order would be detected.
usage: python -I verify_release.py --dir DOWNLOAD_DIR --poses-dir DIR_WITH_rf_poses_R*.json [--src frozen/src --traces-root DIR --rows 40]
"""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--dir',required=True);ap.add_argument('--poses-dir',required=True)
ap.add_argument('--src');ap.add_argument('--traces-root');ap.add_argument('--rows',type=int,default=40);a=ap.parse_args()
here=Path(__file__).resolve().parent;man=json.load(open(here/'RELEASE_MANIFEST.json'));d=Path(a.dir);bad=[]
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1<<20),b''):h.update(c)
    return h.hexdigest()
sums=dict(l.split()[::-1] for l in (here/'SHA256SUMS.txt').read_text().split('\n') if l.strip())
for e in man['arrays']:
    p=d/e['file']
    if not p.exists():bad.append(f"{e['file']}: MISSING");continue
    s=sha(p);ok_sha=(s==e['sha256']==sums[e['file']]);H=np.load(p,mmap_mode='r')
    poses=json.load(open(Path(a.poses_dir)/f"rf_poses_{e['route']}.json"));ps=hashlib.sha256((Path(a.poses_dir)/f"rf_poses_{e['route']}.json").read_bytes()).hexdigest()
    chk=dict(sha=ok_sha,bytes=p.stat().st_size==e['bytes'],dtype=str(H.dtype)==e['dtype'],shape=list(H.shape)==e['shape'],rows_eq_poses=H.shape[0]==len(poses)==e['n_poses'],
             poses_sha=ps==e['rf_poses_sha256'],pose_ids_sequential=[q['pose_id'] for q in poses]==list(range(len(poses))),finite=bool(np.isfinite(np.asarray(H)).all()))
    print(e['file'],'STAGE1',all(chk.values()),{k:v for k,v in chk.items() if not v} or 'all ok')
    bad+=[f"{e['file']}:{k}" for k,v in chk.items() if not v]
    if a.src and a.traces_root:
        sys.path.insert(0,a.src)
        from qclean_uwb.drivesim.rf_store import load_banks,tag_of,h_for_antenna_yaws,load_trace
        tdir=[q for q in Path(a.traces_root).rglob(f"traces_{e['route']}_{e['trace_set'].split('_')[-1]}") if q.is_dir()]
        if not tdir:bad.append(e['file']+': trace dir not found');continue
        banks=load_banks();rows=np.unique(np.linspace(0,len(poses)-1,a.rows).astype(int));rel=[];relshift=[]
        for i in rows:
            q=poses[i];tr=load_trace(tdir[0]/f"{tag_of(q['x'],q['y'])}_trace.npz");i0=int(np.argmin(tr['tau']));one=dict(tr)
            for k,sl in (('jones',lambda z:z[:,i0:i0+1]),('tau',lambda z:z[i0:i0+1]),('ang',lambda z:z[:,i0:i0+1]),('present',lambda z:z[:,i0:i0+1])):one[k]=sl(tr[k])
            r=h_for_antenna_yaws(one,banks,[q['yaw_body_deg']+e['mount_deg']])[0];h=np.asarray(H[i])
            rel.append(float(np.linalg.norm(r-h)/np.linalg.norm(h)))
            j=i+1 if i+1<len(poses) else i-1;relshift.append(float(np.linalg.norm(r-np.asarray(H[j]))/np.linalg.norm(h)))
        ok=max(rel)<=1e-12 and min(relshift)>10*max(rel)
        print('   STAGE2 rows=%d max rel(regen vs asset)=%.2e  min rel(regen vs neighbour row)=%.2e  ->'%(len(rows),max(rel),min(relshift)),'OK' if ok else 'FAIL')
        if not ok:bad.append(e['file']+': pose mapping')
print('RESULT','PASS' if not bad else 'FAIL',bad)
sys.exit(1 if bad else 0)
