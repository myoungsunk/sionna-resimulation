"""R2-5b: P4(c) transfer test of the FROZEN all-route E1 model (and B) on the existing OFFICE sweep (branch claude/office-e-layout, full35_stride1): a different scene
(10 x 12 x 2.7 m, desks + partitions, anchor (5.0, 2.2), 35 positions x 19 yaws x 257 bins, same FFD banks / solver). No refit, no threshold change. Criteria: R25B_OFFICE_PREREG_KO.md (frozen before this script was run).
usage: r25b_office_p4c.py OFFICE_DIR OUT_JSON FROZEN.json FREQS"""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import p3_common as P
OFF=Path(sys.argv[1]);fz=json.load(open(sys.argv[3]));freq=np.load(sys.argv[4])
sys.path.insert(0,str(OFF/'src'))
from qclean_uwb.scenarios.office import OfficeSetup
cs=OfficeSetup();anc=np.asarray(cs.anchor_position)
RUN=OFF/'results/OFFICE_SNOWBALL_20261008_819fa93/full35_stride1';geo={(g['x'],g['y']):g for g in json.load(open(OFF/'results/OFFICE_SNOWBALL_20261008_819fa93/geom_check/GEOM_LOS_CHECK.json'))}
assert len(geo)==35
HS={}
for (x,y),g in geo.items():
    tag=f'office_x{x}_y{y}';H=np.load(RUN/tag/f'{tag}_H.npy');assert H.shape==(19,257,2,2) and np.isfinite(H).all();HS[(x,y)]=H
def run(exp,snr,seed):
    nv=P.O.noise_var_from_snr(snr) if snr else None;thr=P.O.detection_threshold(nv) if snr else None;rows=[];rng=np.random.default_rng([20261012,snr or 0,seed])
    for (x,y),H in HS.items():
        r=P.predict(H,0,freq,fz,noise_var=nv,rng=rng,threshold=thr);d=float(np.linalg.norm(cs.tag_position(x,y)-anc))
        for i in range(19):rows.append(dict(exp=exp,x=x,y=y,yaw=10*i,clear=bool(geo[(x,y)]['geometric_clear']),det=bool(r['detected'][i]),d=d,eB=float(r['B_old'][i]-d),eE=float(r['chosen'][i]-d)))
    return pd.DataFrame(rows)
def summ(q,boot=True):
    q=q[q.det]
    if len(q)==0:return None
    g=q.groupby(['x','y']);sB=(g.eB.apply(lambda v:(v**2).mean())).to_numpy();sE=(g.eE.apply(lambda v:(v**2).mean())).to_numpy()
    o=dict(n=int(len(q)),n_sites=int(len(sB)),rmse_B=float(np.sqrt(sB.mean())),rmse_E1=float(np.sqrt(sE.mean())),rel=float(np.sqrt(sE.mean())/np.sqrt(sB.mean())-1),mean_eB=float(q.eB.mean()),mean_eE1=float(q.eE.mean()),sd_eB=float(q.eB.std()),sd_eE1=float(q.eE.std()))
    if boot:
        rng=np.random.default_rng(20261012);rel=[np.sqrt(sE[p].mean())/np.sqrt(sB[p].mean())-1 for p in (rng.integers(0,len(sB),len(sB)) for _ in range(4000))];o['ci95']=[float(np.percentile(rel,2.5)),float(np.percentile(rel,97.5))]
    return o
res={'scene':'office 10x12x2.7, anchor (5.0,2.2,2.65)','n_positions':35,'n_clear':int(sum(g['geometric_clear'] for g in geo.values())),'experiments':{}}
for exp,snr in (('noise_free',None),('snr30',30),('snr10',10)):
    D=run(exp,snr,1);res['experiments'][exp]=dict(primary_clear=summ(D[D.clear]),blocked_descriptive=summ(D[~D.clear]),all35_descriptive=summ(D),detection_rate_clear=float(D[D.clear].det.mean()),detection_rate_blocked=float(D[~D.clear].det.mean()))
    if exp=='noise_free':
        c=D[D.clear&D.det];res['clear_bias_B_by_range_bin']={str(k):dict(n=int(len(g)),mean_eB=float(g.eB.mean()),mean_eE1=float(g.eE.mean())) for k,g in c.groupby(pd.cut(c.d,[0,3,5,8,20]))}
        res['clear_per_position_rel_distribution']=[float(np.sqrt((g.eE**2).mean())/np.sqrt((g.eB**2).mean())-1) for _,g in c.groupby(['x','y'])]
p=res['experiments']['noise_free']['primary_clear'];res['gate']=dict(rule='point <= -10% and ci95 upper < 0 on LoS-clear positions, noise-free',point=p['rel'],ci95=p['ci95'],passes=bool(p['rel']<=-0.10 and p['ci95'][1]<0))
Path(sys.argv[2]).write_text(json.dumps(res,indent=1))
print(json.dumps({k:v for k,v in res.items() if k not in('clear_per_position_rel_distribution',)},indent=1)[:5000])
