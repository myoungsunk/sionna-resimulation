"""Correct timing contract: auxiliary RF poses are valid for static fitting,
not necessarily a temporal sequence. Fit memory from actual replay t/pose ids.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd


def recalibrate(work,rt,held):
    work=Path(work);q=pd.read_csv(work/'SOURCE_PACKET_FEATURES.csv.gz')
    full=q[q.channel=='full'].reset_index(drop=True);n4=rt['n4']
    _,mask,_=next(v for v in n4.feature_splits(np,full) if v[0]==held)
    train=full.loc[mask].reset_index(drop=True);w=n4.site_weights(np,pd,train)
    configs=json.loads((work/'FIT_CONFIG.json').read_text());cfg=next(c for c in configs if c['held_route']==held)
    index=pd.MultiIndex.from_frame(train[['case','pose_id']]);newstats={}
    for name,target in [('POWER_BIN_JOINT','temporal'),('SIMPLE_G4','temporal_rich')]:
        mu,C,_=n4.fit_model(np,train,train,w,name,rt['groups'])
        residual=train[['e_r','e_s']].to_numpy()-mu
        u=np.linalg.solve(np.linalg.cholesky(C),residual[...,None])[...,0]
        records={1:[],2:[]};dts=[];groupcounts=[]
        for cid in sorted(train.case.unique()):
            with np.load(work/(cid+'_full.npz'),allow_pickle=False) as a:t=a['t'];ids=a['pose_id']
            ix=index.get_indexer([(cid,int(i)) for i in ids]);dt=np.diff(t);positive=dt[dt>0];ref=float(np.median(positive));dts.extend(positive.tolist())
            gcount={}
            for lag in [1,2]:
                valid=(ix[:-lag]>=0)&(ix[lag:]>=0)&np.isclose(t[lag:]-t[:-lag],lag*ref,rtol=1e-6,atol=1e-8)
                # Do not bridge a removed spatial site, even at lag two.
                if lag==2:valid&=ix[1:-1]>=0
                gcount[str(lag)]=int(valid.sum())
                if np.any(valid):records[lag].append((u[ix[:-lag][valid]],u[ix[lag:][valid]]))
            groupcounts.append({'case':cid,'n_clock_frames':len(t),'eligible_frames':int((ix>=0).sum()),'dt_ref':ref,'pairs':gcount})
        rho=[]
        for lag in [1,2]:
            aa=np.concatenate([x[0] for x in records[lag]]);bb=np.concatenate([x[1] for x in records[lag]])
            aa-=aa.mean(0);bb-=bb.mean(0)
            rho.append((aa*bb).mean(0)/np.maximum(np.sqrt((aa*aa).mean(0)*(bb*bb).mean(0)),1e-12))
        r1,r2=rho;axis_a=np.clip(np.divide(r2,r1,out=np.zeros(2),where=r1>.02),.05,.995);axis_f=np.clip(r1/axis_a,.05,.95)
        stats={'a_ref':float(np.median(axis_a)),'f':float(np.median(axis_f)),'dt_ref':float(np.median(dts)),'rho1_whitened':r1.tolist(),'rho2_whitened':r2.tolist(),'axis_a':axis_a.tolist(),'axis_f':axis_f.tolist(),'clock_groups':groupcounts,'fit':'actual replay clock, outer-training only, contiguous eligible frames, no held-route data or auxiliary-pose pseudo-timeline'}
        cfg[target]=stats;newstats[target]=stats
    return cfg,newstats
