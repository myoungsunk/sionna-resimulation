#!/usr/bin/env python3
"""P1R: exact SourceFFD polarization s and ds/dpsi on a heading-offset grid at GT position.

One case and one half of the offset grid per job. Offsets are degrees relative to GT body yaw.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
import v_replay as V

IN=REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz'
DEG2RAD=np.pi/180.
PARTS={'neg':list(range(-30,1)),'pos':list(range(1,31))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True)
    p.add_argument('--part',required=True,choices=sorted(PARTS));p.add_argument('--out',required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    D=pd.read_csv(IN,usecols=['case','pose_id'])
    cc=D[D.case==a.case].sort_values('pose_id')
    assert len(cc)>0 and cc.pose_id.is_unique,a.case
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case)
    poses=pd.DataFrame(json.loads((V.ROOT/case['samples_path']).read_text())).set_index('pose_id')
    base=poses.loc[cc.pose_id,['x','y','yaw_body_deg']].to_numpy(float)
    assert np.all(np.isfinite(base))
    offs=PARTS[a.part];model=V.SourceFFD()
    S=np.empty((len(cc),len(offs)));G=np.empty_like(S);t0=time.time()
    for j,off in enumerate(offs):
        coords=base.copy();coords[:,2]=np.deg2rad(coords[:,2]+off)
        hs=[];gs=[]
        for i in range(0,len(coords),32):
            h,H=model.batch(coords[i:i+32],case,gradient=True)
            hs.append(h[:,1]);gs.append(H[:,1,2]*DEG2RAD)
        S[:,j]=np.concatenate(hs);G[:,j]=np.concatenate(gs)
        print(f'GRID {a.case} off={off:+d} t={time.time()-t0:.0f}s',flush=True)
    assert np.isfinite(S).all() and np.isfinite(G).all()
    np.savez_compressed(out/f'GRID_{a.case}_{a.part}.npz',pose_id=cc.pose_id.to_numpy(),
                        offsets=np.asarray(offs,float),s=S,g_deg=G)
    print(f'GRID_DONE {a.case} {a.part} n={len(cc)} k={len(offs)} t={time.time()-t0:.0f}s',flush=True)

if __name__=='__main__':main()
