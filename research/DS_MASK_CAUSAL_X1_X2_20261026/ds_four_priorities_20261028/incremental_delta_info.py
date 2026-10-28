#!/usr/bin/env python3
"""P3 independent RF data check: incremental held-route information in signed CIR delta-s.
This is a measurement-level conditional prediction test, NOT yet a 5-state EKF proof.
All labels are evaluation-only; features depend on Full CIR and frozen online E1 prior.
"""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np,pandas as pd
P=argparse.ArgumentParser();P.add_argument("--input-root",required=True);P.add_argument("--out",required=True);a=P.parse_args()
root=Path(a.input_root);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"reflect_model"))
import common as C
CASES=list(C.CASES);OFF=[1,2,4,8]
def taps(h):
 h=np.asarray(h)
 if h.ndim==4: h=h[:,:,:,0]
 assert h.ndim==3 and h.shape[-1]==2,h.shape
 n,nf,_=h.shape;win=np.hanning(nf)
 z=np.fft.ifft(h*win[None,:,None],n=4*nf,axis=1)*nf
 power=abs(z)**2;amp=np.sqrt(power);ii=np.arange(n)
 strong=amp[ii,:,amp.max(axis=1).argmax(axis=1)]
 tap=(strong>=0.3*strong.max(axis=1)[:,None]).argmax(axis=1)
 def s(o):
  idx=np.clip(tap+o,0,4*nf-1);p=power[ii,idx]
  return (p[:,0]-p[:,1])/np.maximum(p.sum(axis=1),1e-30)
 s0=s(0)
 return np.column_stack([s(o)-s0 for o in OFF]),s0,tap,np.maximum(strong.max(axis=1),1e-30)
rows=[]
for case in CASES:
 Hf,Hl,samples=C.load_rf(case)
 assert len(Hf)==len(Hl)==len(samples),(case,len(Hf),len(Hl),len(samples))
 ids=np.array([x["pose_id"] for x in samples],dtype=int)
 dmap={int(x):i for i,x in enumerate(ids)}
 rawds=[];raws=[];loss=[];pows=[]
 for k in range(0,len(ids),96):
  df,sf,tf,pf=taps(Hf[k:k+96]);dl,sl,tl,pl=taps(Hl[k:k+96])
  rawds.append(df);raws.append(sf);loss.append(sl);pows.append(pf)
 ds=np.concatenate(rawds);sf=np.concatenate(raws);sl=np.concatenate(loss);pw=np.concatenate(pows)
 assert len(ds)==len(ids)
 for bias in ["B0","L2"]:
  tr=C.load_control(case,bias);jb=tr["jb"];t=np.asarray(tr["t_s"],float)
  trids=np.asarray(tr["pose_id"],int)
  pos=np.array([dmap[int(i)] for i in trids])
  # The prior and h are endogenous, but both are available online. GT only for the label.
  z=tr["nu"][:,jb,:]+tr["h"][:,jb,:]+tr["mu"][:,jb,:]
  assert np.nanmax(abs(z[:,1]-sf[pos]))<3e-8,(case,bias,"raw CIR parity")
  d0=z[:,1]-tr["h"][:,jb,1]
  y=sf[pos]-sl[pos]-tr["mu"][:,jb,1]
  data={"case":case,"route":case.split("_")[0],"bias":bias,"pose_id":trids,
        "target_residual_s":y,
        "prior_pol_innov":d0,"mean_s":tr["mu"][:,jb,1],
        "prior_range_innov":z[:,0]-tr["h"][:,jb,0],
        "log_first_power":np.log(np.maximum(pw[pos],1e-30)),
        "s_obs":sf[pos]}
  for j,o in enumerate(OFF):data[f"ds_{o}"]=ds[pos,j]
  rows.append(pd.DataFrame(data))
D=pd.concat(rows,ignore_index=True)
# Independent route heldout; B0 only for learning/scoring to avoid double counting shared RF.
D=D[D.bias=="B0"].copy()
base=["mean_s","prior_pol_innov","prior_range_innov","log_first_power"]
plus=base+[f"ds_{o}" for o in OFF]
def fit(tr,te,cols):
 x=tr[cols].to_numpy(float);xt=te[cols].to_numpy(float)
 y=tr.target_residual_s.to_numpy(float)
 mean=x.mean(0);std=x.std(0);std=np.where(std<1e-8,1.,std)
 X=(x-mean)/std;Xt=(xt-mean)/std
 X=np.c_[np.ones(len(X)),X];Xt=np.c_[np.ones(len(Xt)),Xt]
 # fixed shrinkage; regression coefficients only trained on other routes
 lam=20.0;M=X.T@X+np.eye(X.shape[1])*lam;M[0,0]-=lam
 return Xt@np.linalg.solve(M,X.T@y)
scores=[]
for held in ["R2","R4","R5"]:
 tr=D[D.route!=held].replace([np.inf,-np.inf],np.nan).dropna(subset=plus+["target_residual_s"])
 te=D[D.route==held].replace([np.inf,-np.inf],np.nan).dropna(subset=plus+["target_residual_s"])
 assert len(te)>100 and len(tr)>100
 preds={k:fit(tr,te,cols) for k,cols in [("BASE",base),("BASE_PLUS_DELTA",plus)]}
 for case,g in te.groupby("case"):
  ix=te.index.get_indexer(g.index);y=g.target_residual_s.to_numpy()
  for model,pred in preds.items():
   pred=pred[ix];den=np.mean(y*y);r2=1-np.mean((y-pred)**2)/den
   scores.append(dict(case=case,route=held,model=model,n=len(y),r2_uncentered=float(r2),residual_rms=float(np.sqrt(np.mean((y-pred)**2))),raw_rms=float(np.sqrt(den))))
score=pd.DataFrame(scores)
score.to_csv(out/"P3_HELD_ROUTE_R2.csv",index=False,float_format="%.16g")
piv=score.pivot(index="case",columns="model",values="r2_uncentered")
piv["incremental_R2"]=piv.BASE_PLUS_DELTA-piv.BASE
piv.reset_index().to_csv(out/"P3_INCREMENTAL.csv",index=False,float_format="%.16g")
status={"status":"MEASUREMENT_INFO_ONLY_NOT_EKF_ADOPTION","n_cases":len(piv),"n_routes":3,"incremental_positive_cases":int((piv.incremental_R2>0).sum()),"median_incremental_r2":float(piv.incremental_R2.median()),"limitations":["LORO is not independent new-scene validation","R2 gain does not establish conditional Fisher information of a five-state filter","reuse of s(fp) inside signed delta requires explicit covariance in any future EKF"]}
(out/"P3_DECISION.json").write_text(json.dumps(status,indent=2),encoding="utf8")
print(json.dumps(status,indent=2))
