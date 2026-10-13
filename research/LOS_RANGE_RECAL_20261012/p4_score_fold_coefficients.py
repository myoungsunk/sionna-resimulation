"""R2-4d: blind P4 scoring of the P5 coefficient sets (leave-one-route-out E1 fold coefficients) on the same 960 P4 poses, because P5 used fold coefficients while P4 scored the all-route fit.
Truth is opened only in the scoring block, as in p4_blind_range_eval.py. usage: p4_score_fold_coefficients.py OUT_JSON BLIND_DIR FROZEN.json FREQS"""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import p3_common as P
out=Path(sys.argv[1]);blind=Path(sys.argv[2]);fz=json.load(open(sys.argv[3]));freq=np.load(sys.argv[4])
HF=[];HL=[];K=[]
for p in sorted(blind.glob('shard*.npz')):
    z=np.load(p);HF.append(z['H_full']);HL.append(z['H_los']);K+=list(zip(z['site_id'],z['anchor_x'],z['mount']))
HF=np.concatenate(HF);HL=np.concatenate(HL);site=np.array([k[0] for k in K]);anc=np.array([k[1] for k in K]);mnt=np.array([k[2] for k in K])
models={'ALL_ROUTE(P4)':fz}
for held in ('R2','R4','R5'):models['FOLD_'+held]={'chosen':'E1_on_B','params':{'E1':fz['loro_fold_params'][held]['E1']}}
pred={}
for exp,snr in (('noise_free',None),('snr30',30),('snr10',10)):
    nv=P.O.noise_var_from_snr(snr) if snr else None;thr=P.O.detection_threshold(nv) if snr else None
    for kind,H in (('full',HF),('los',HL)):
        for name,m in models.items():
            rng=np.random.default_rng([20261012,snr or 0,0 if kind=='los' else 1]);r=P.predict(H,mnt,freq,m,noise_var=nv,rng=rng,threshold=thr);pred[(exp,kind,name)]=r
# ---- scoring (truth opened here)
sites=json.load(open(HERE/'out_p0_p5/R1/P4_TEST_SITES_FROZEN.json'))['sites'];sd={s['site_id']:s for s in sites}
sys.path.insert(0,str(P.ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
from qclean_uwb.scenarios.corridor import CorridorSetup
tr={}
for ax in (4.0,10.0):
    cs=CorridorSetup(anchor_x_m=ax)
    for s in sites:tr[(s['site_id'],ax)]=float(np.linalg.norm(cs.robot_position(s['x'],s['y'])-np.asarray(cs.anchor_position)))
dtrue=np.array([tr[(s,a)] for s,a in zip(site,anc)]);res={}
for (exp,kind,name),r in pred.items():
    det=r['detected'];eB=(r['B_old']-dtrue);eC=(r['chosen']-dtrue)
    df=pd.DataFrame(dict(s=site,eB=eB,eC=eC))[det];g=df.groupby('s');sB=(g.eB.apply(lambda x:(x**2).mean())).to_numpy();sC=(g.eC.apply(lambda x:(x**2).mean())).to_numpy()
    rng=np.random.default_rng(20261012);rel=[np.sqrt(sC[p].mean())/np.sqrt(sB[p].mean())-1 for p in (rng.integers(0,len(sB),len(sB)) for _ in range(4000))]
    res[f'{exp}/{kind}/{name}']=dict(rmse_B=float(np.sqrt(sB.mean())),rmse_model=float(np.sqrt(sC.mean())),rel=float(np.sqrt(sC.mean())/np.sqrt(sB.mean())-1),ci95=[float(np.percentile(rel,2.5)),float(np.percentile(rel,97.5))],n_site_clusters=int(len(sB)),detection_rate=float(det.mean()))
out.write_text(json.dumps(res,indent=1))
for k,v in res.items():
    if '/full/' in k:print(k,round(v['rmse_B'],4),round(v['rmse_model'],4),round(v['rel'],3),[round(x,3) for x in v['ci95']])
