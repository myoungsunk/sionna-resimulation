#!/usr/bin/env python3
"""RA3: numerical intervention on sigma_b lookup time only; no changes to source data/filters.
Original: posterior before predict; candidate: predicted prior at packet k. Shared BASE masks.
Requires REFLECT_ROOT populated by reflect_model/fetch_inputs.sh FETCH_RF=0.
"""
from __future__ import annotations
import hashlib, json, math, os, sys, pathlib
import numpy as np
import pandas as pd

HERE=pathlib.Path(__file__).resolve()
BASE=HERE.parents[2] / "DS_MASK_CAUSAL_X1_X2_20261026"
sys.path.insert(0,str(BASE/"pol_bias_model"))
sys.path.insert(0,str(BASE/"reflect_model"))
import exp_pb as E
import common as C
from core import predict,wrap

CASES=("R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0","R4_aB_m0","R5_aA_m0","R5_aB_m0")
LEVELS=("B0","L0","L1","L2")
MODES=("BB","MB")
def sh(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def run_semantics(D,mu,model,lookup):
 """Independent reimplementation of E.run for its 4-state VAR arm only."""
 assert lookup in ("posterior_before_predict","predicted_prior_current")
 x=D["x0"].copy();P=D["P0"].copy();anchor=D["anchor"];n=len(D["t"])
 X=np.zeros((n,4)); PX=np.zeros((n,4,4)); pre=np.zeros(n);pri=np.zeros(n);which=np.zeros(n)
 for k in range(n):
  pre[k]=E.sig(math.hypot(x[0]-anchor[0],x[1]-anchor[1]))
  if k:
   ds,gy,dt=float(D["ds"][k]),float(D["gy"][k]),float(D["dt"][k])
   q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
   x,P,_,_=predict(x,P,ds,gy,dt,q)
  pri[k]=E.sig(math.hypot(x[0]-anchor[0],x[1]-anchor[1]))
  which[k]=pre[k] if lookup=="posterior_before_predict" else pri[k]
  if D["acc"][k]:
   h,H=model.batch(x[None],D["spec"]);h=h[0];H=H[0]
   z=D["z"][k];Rk=D["R"][k].copy();Rk[1,1]+=which[k]**2
   v=z-h-mu[k]
   S=H@P@H.T+Rk;S=.5*(S+S.T)
   K=np.linalg.solve(S,H@P).T
   y=x+K@v;y[2]=wrap(y[2])
   A=np.eye(4)-K@H
   Pn=A@P@A.T+K@Rk@K.T
   x=y;P=.5*(Pn+Pn.T)
  X[k]=x;PX[k]=P
 return X,PX,pre,pri,which
def math_fixture():
 r0,r1=1.,6.
 s0,s1=E.sig(r0),E.sig(r1)
 assert s1>s0 and s0>0
 P=np.diag([1.,1.]);H=np.eye(2);R=np.diag([.05**2,.02**2])
 v=np.array([.1,.2])
 def upd(s):
  Rk=R.copy();Rk[1,1]+=s*s
  S=H@P@H.T+Rk;K=np.linalg.solve(S,H@P).T
  return K@v
 assert abs(upd(s0)[1]-upd(s1)[1])>1e-4
 return {"rho_before":r0,"rho_predicted":r1,"sigma_before":s0,"sigma_after":s1,
         "delta_s_update":float(upd(s0)[1]-upd(s1)[1])}
def main(out):
 out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
 model=C.base_model();results=[];qa=[]
 for case in CASES:
  spec=C.CASES[case];anchor=np.asarray(spec["anchor"][:2],float)
  ref=C.load_control(case,"B0")
  jb,jm=ref["jb"],ref["jm"]
  t=ref["t_s"];gt=ref["truth_scoring_only"]
  z=ref["nu"][:,jb]+ref["h"][:,jb]+ref["mu"][:,jb]
  for level in LEVELS:
   ds,gy,dt,x0=E.build_controls(t,gt[:,:3],level)
   acc=E.gated_mask(z,ref["mu"][:,jb],ref["R"][:,jb],ds,gy,dt,np.r_[x0,0.],ref["Pprior"][0,jb],spec,model)
   if level in ("B0","L2"):
    tr=C.load_control(case,level)
    mism=int(np.count_nonzero(acc != tr["acc"][:,jb].astype(bool)))
    if mism:raise RuntimeError(f"ERR_GATE_PARITY {case}/{level}: {mism}")
   hg,_=model.batch(np.c_[gt[:,:3],np.zeros(len(t))],spec)
   D=dict(t=t,gt=gt,z=z,R=ref["R"][:,jb],acc=acc,ds=ds,gy=gy,dt=dt,
       x0=np.r_[x0,0.],P0=ref["Pprior"][0,jb],spec=spec,anchor=anchor,hg=hg)
   Xbase,Pbase,_,_=E.run(D,ref["mu"][:,jb],dict(mode="orig"),model)
   sb=E.scores(D,Xbase,Pbase)
   for bg,j in (("BB",jb),("MB",jm)):
    mu=ref["mu"][:,j]
    Xo,Po,_,_=E.run(D,mu,dict(mode="var"),model)
    Xa,Pa,pre,pri,which=run_semantics(D,mu,model,"posterior_before_predict")
    Xb,Pb,preb,prib,chosen=run_semantics(D,mu,model,"predicted_prior_current")
    dx=float(np.max(abs(Xo-Xa)));dp=float(np.max(abs(Po-Pa)))
    if dx>1e-10 or dp>1e-10:raise RuntimeError(f"ERR_ORIG_REPLAY_PARITY {case}/{level}/{bg}: dx={dx} dP={dp}")
    so=E.scores(D,Xo,Po);sn=E.scores(D,Xb,Pb)
    hd=float(max(abs(np.degrees(np.angle(np.exp(1j*(Xa[:,2]-Xb[:,2])))))))
    sdiff=preb-prib
    result=dict(case=case,level=level,bg=bg,n=len(t),accepted=int(acc.sum()),
      x_original_parity_max=dx,P_original_parity_max=dp,
      sigma_pre_prior_max_abs=float(np.max(abs(sdiff))),
      sigma_pre_prior_median_abs=float(np.median(abs(sdiff))),
      sigma_pre_prior_nonzero_gt1e7=int((abs(sdiff)>1e-7).sum()),
      delta_max_heading_state_deg=hd,
      delta_head_rmse_deg=float(sn["head_rmse"]-so["head_rmse"]),
      delta_xy_rmse_cm=float(sn["xy_rmse_cm"]-so["xy_rmse_cm"]),
      head_orig_deg=so["head_rmse"],head_pred_deg=sn["head_rmse"],
      bborig_head_deg=sb["head_rmse"],bborig_xy_cm=sb["xy_rmse_cm"],
      xy_orig_cm=so["xy_rmse_cm"],xy_pred_cm=sn["xy_rmse_cm"],
      delta_max_x_m=float(np.max(abs(Xa[:,:2]-Xb[:,:2]))),
      delta_max_P=float(np.max(abs(Pa-Pb))),
      mask_parity="same_frozen_BASE",R_extra_rule="sigma_b_squared_s_component_only")
    results.append(result);print(json.dumps(result),flush=True)
    qa.append({"case":case,"level":level,"background":bg,"source_original_implementation_parity":dx<=1e-10 and dp<=1e-10,"n":len(t)})
 df=pd.DataFrame(results)
 df.to_csv(out/"RA3_SIGMA_LOOKUP_28_CELLS.csv",index=False)
 mb=df[df.bg=="MB"].copy()
 conditions=[]
 for _,v in mb.iterrows():
  conditions.append({"case":v["case"],"bias":v["level"],
    "original_head_improved":bool(v["head_orig_deg"]<v["bborig_head_deg"]),
    "alternative_head_improved":bool(v["head_pred_deg"]<v["bborig_head_deg"]),
    "original_xy_improved":bool(v["xy_orig_cm"]<v["bborig_xy_cm"]),
    "alternative_xy_improved":bool(v["xy_pred_cm"]<v["bborig_xy_cm"])})
 totals={"n_conditions":len(conditions),"orig_head_improved":sum(x["original_head_improved"] for x in conditions),
   "alternative_head_improved":sum(x["alternative_head_improved"] for x in conditions),
   "orig_xy_improved":sum(x["original_xy_improved"] for x in conditions),
   "alternative_xy_improved":sum(x["alternative_xy_improved"] for x in conditions),
   "head_flip":sum(x["original_head_improved"]!=x["alternative_head_improved"] for x in conditions),
   "xy_flip":sum(x["original_xy_improved"]!=x["alternative_xy_improved"] for x in conditions)}
 (out/"RA3_SIGMA_28_TOTALS.json").write_text(json.dumps({"status":"TECHNICAL_RETROSPECTIVE_ONLY","totals":totals,"conditions":conditions,
 "dependent_source_H_unresolved_for_25_G3_rays":True,"independent_audit":False},indent=2))
 (out/"RA3_SIGMA_LOOKUP_QA.json").write_text(json.dumps(dict(
  status="TECHNICAL_RETROSPECTIVE_28_CELLS_COMPLETED",fixture=math_fixture(),n_arms=len(results),qa=qa,
  source_git_sha="f100a983cc389fcdef073592a254add61e7115da",
  input_lock=(C.ROOT/"out/INPUT_LOCK.sha256").read_text() if (C.ROOT/"out/INPUT_LOCK.sha256").exists() else "MISSING",
  code_sha256={"exp_pb.py":sh(BASE/"pol_bias_model/exp_pb.py"),"common.py":sh(BASE/"reflect_model/common.py"),"ra3_script":sh(HERE)},
  scientific_claim="Descriptive paired canary; no hypothesis or new H validity assertion.",
  additional_arms="7 cases x four levels analyzed retrospectively; original model untouched; not a prospective estimator update.",
  self_review_only=True),indent=2))
 print(json.dumps({"status":"TECHNICAL_RETROSPECTIVE_28_CELLS_COMPLETED","arms":len(results),"totals":totals,"max_delta_head_rmse_deg":float(df.delta_head_rmse_deg.abs().max()),"max_delta_xy_cm":float(df.delta_xy_rmse_cm.abs().max())}))
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "ra3_out")
