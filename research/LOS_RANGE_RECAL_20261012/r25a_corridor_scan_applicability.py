"""R2-5a (supplementary, descriptive, NOT a gate): can the existing CORRIDOR_* yaw-sweep channels be used to test the frozen E1 model?
Same scene (CorridorSetup defaults: 20 x 2.4 x 2.7 m, same materials/banks/solver), anchor aA (x=4,y=0), robot yaw 0..180 deg, 257 bins. NOT a new scene -> does not lift GENERALIZATION_NOT_VERIFIED for P4(c).
Evaluates the frozen all-route E1 and the B baseline on every (position, yaw) channel (noise-free), clustered by position; also by yaw bin and by |y| (training |y|<=0.52).
usage: r25a_corridor_scan_applicability.py OUT_JSON FROZEN.json FREQS"""
import glob,json,os,re,sys
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import p3_common as P
fz=json.load(open(sys.argv[2]));freq=np.load(sys.argv[3])
sys.path.insert(0,str(P.ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
from qclean_uwb.scenarios.corridor import CorridorSetup
cs=CorridorSetup(anchor_x_m=4.0);rows=[];seen=set()
for f in sorted(glob.glob(str(P.ROOT/'results/CORRIDOR_SCAN2_20261007/x*/x*_H.npy'))+glob.glob(str(P.ROOT/'results/CORRIDOR_SCAN_20261006/x*/x*_H.npy'))+glob.glob(str(P.ROOT/'results/CORRIDOR_SWEEP_20261006/pos*/position_*_H.npy'))):
    rc=json.load(open(f.replace('_H.npy','_receipt.json')));x,y=rc['robot_xy_m'];key=(round(x,4),round(y,4))
    if key in seen:continue
    seen.add(key);H=np.load(f);assert H.shape==(len(rc['yaws']),257,2,2)
    r=P.predict(H,0,freq,fz);d=float(np.linalg.norm(cs.robot_position(x,y)-np.asarray(cs.anchor_position)))
    for i,yaw in enumerate(rc['yaws']):rows.append(dict(src=Path(f).parts[-3],x=x,y=y,yaw=yaw,det=bool(r['detected'][i]),eB=float(r['B_old'][i]-d),eC=float(r['chosen'][i]-d),d_true=d))
D=pd.DataFrame(rows);D=D[D.det];D['site']=D.x.astype(str)+'|'+D.y.astype(str)
def summ(q):
    sB=(q.eB**2).groupby(q.site).mean();sC=(q.eC**2).groupby(q.site).mean();return dict(n=int(len(q)),n_sites=int(len(sB)),rmse_B=float(np.sqrt(sB.mean())),rmse_E1=float(np.sqrt(sC.mean())),rel=float(np.sqrt(sC.mean())/np.sqrt(sB.mean())-1),mean_eB=float(q.eB.mean()),mean_eE1=float(q.eC.mean()))
out={'all':summ(D),'positions':int(D.site.nunique()),'yaw_bins':{str(k):summ(g) for k,g in D.groupby(pd.cut(D.yaw,[-1,30,60,120,150,181]))},'abs_y_le_0p52':summ(D[D.y.abs()<=0.52]),'abs_y_gt_0p52':summ(D[D.y.abs()>0.52]),'yaw_0_or_180':summ(D[D.yaw.isin([0.0,180.0])])}
rng=np.random.default_rng(20261012);sites=D.site.unique();gB={s:(g.eB**2).mean() for s,g in D.groupby('site')};gC={s:(g.eC**2).mean() for s,g in D.groupby('site')};a=np.array([gB[s] for s in sites]);b=np.array([gC[s] for s in sites])
rel=[np.sqrt(b[p].mean())/np.sqrt(a[p].mean())-1 for p in (rng.integers(0,len(sites),len(sites)) for _ in range(4000))];out['all']['ci95']=[float(np.percentile(rel,2.5)),float(np.percentile(rel,97.5))]
out['note']='descriptive, same scene, post-hoc selection of data; not a P4(c) substitute'
Path(sys.argv[1]).write_text(json.dumps(out,indent=1));print(json.dumps({k:v for k,v in out.items() if k!='note'},indent=1))
