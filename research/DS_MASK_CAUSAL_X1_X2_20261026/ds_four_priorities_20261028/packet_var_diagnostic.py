#!/usr/bin/env python3
"""P4 packet-level same-prior RF covariance ablation; original BASE mask frozen.
Reports which original MB updates are beneficial/harmful in Heading and whether
VAR would have suppressed them, then independent full-replay parity.
"""
import argparse,sys,math,json
from pathlib import Path
import numpy as np,pandas as pd
p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/"pol_bias_model"))
import exp_pb as E
sys.path.insert(0,str(BASE/"reflect_model"))
import common as C
model=C.base_model()
CASE=["R2_aA_m45","R4_aB_m0","R5_aA_m0"]
records=[];summary=[]
def wrap(x):return float(C.wrap(x))
for case in CASE:
 for bias in ["B0","L0","L1","L2"]:
  if case=="R5_aA_m0" and bias not in ("B0","L2"):continue
  ref=C.load_control(case,"B0"); jb,jm=ref["jb"],ref["jm"]
  t=ref["t_s"];gt=ref["truth_scoring_only"];z=ref["nu"][:,jb]+ref["h"][:,jb]+ref["mu"][:,jb]
  ds,gy,dt,x0=E.build_controls(t,gt[:,:3],bias)
  sig=C.CASES[case]
  acc=E.gated_mask(z,ref["mu"][:,jb],ref["R"][:,jb],ds,gy,dt,np.r_[x0,0.],ref["Pprior"][0,jb],sig,model)
  D=dict(t=t,gt=gt,z=z,R=ref["R"][:,jb],acc=acc,ds=ds,gy=gy,dt=dt,
         x0=np.r_[x0,0.],P0=ref["Pprior"][0,jb],spec=sig,
         anchor=np.array(sig["anchor"][:2]))
  mu=ref["mu"][:,jm]
  # Full independent replay, MB original and VAR. Cross-check upstream PB reference scores.
  for name,var in [("MB_ORIG",False),("MB_VAR",True)]:
   x=D["x0"].copy();P=D["P0"].copy(); trace=[]
   for k in range(len(t)):
    # Exact upstream exp_pb.run convention: distance-dependent variance is
    # evaluated on the previous posterior BEFORE the current propagation.
    rr=float(np.linalg.norm(x[:2]-D["anchor"]))
    if k:x,P=C.predict_one(x,P,ds[k],gy[k],dt[k])
    xp=x.copy();Pp=P.copy()
    hk,Hk=model.batch(x[None],sig);h=hk[0];H=Hk[0]
    nu=z[k]-h-mu[k];R=ref["R"][k,jb].copy()
    if var:R[1,1]+=E.sig(rr)**2
    S=H@P@H.T+R
    K=np.linalg.solve(S,H@P).T
    ur=K[:,0]*nu[0];us=K[:,1]*nu[1]
    # Predicted pre-update errors at identical prior are valid for instant causal contrasts
    pre=wrap(xp[2]-gt[k,2]);dr=float(ur[2]);dss=float(us[2])
    incr_s=(2*pre*dss+dss*dss)
    # Geometry gate frozen, not changed by this arm
    if acc[k]:
     y=x+ur+us;y[2]=wrap(y[2])
     A=np.eye(4)-K@H;P=A@P@A.T+K@R@K.T
     x=y
    trace.append(dict(case=case,bias=bias,arm=name,k=k,t_s=t[k],acc=bool(acc[k]),
      gt_dist_m=float(np.linalg.norm(gt[k,:2]-D["anchor"])),
      prior_head_error_deg=math.degrees(pre),
      update_r_psi_deg=math.degrees(dr) if acc[k] else 0.,
      update_s_psi_deg=math.degrees(dss) if acc[k] else 0.,
      heading_sq_effect_s_deg2=(math.degrees(1.)**2)*incr_s if acc[k] else 0.,
      posterior_head_error_deg=math.degrees(wrap(x[2]-gt[k,2])),
      innovation_s=float(nu[1]),Rss=float(R[1,1]),K_spsi=float(K[2,1]),
      e_tan_cm=float(100*((x[:2]-gt[k,:2])@np.array([-(gt[k,1]-D["anchor"][1]),gt[k,0]-D["anchor"][0]])/max(np.linalg.norm(gt[k,:2]-D["anchor"]),1e-6)))))
   trace=pd.DataFrame(trace)
   assert trace.acc.sum()==np.count_nonzero(acc)
   result=E.scores(D,np.zeros((len(t),4)),np.repeat(np.eye(4)[None],len(t),axis=0)) if False else None
   # For each arm record trajectory score directly
   ss=trace[t>=30]
   hr=float(np.sqrt(np.mean(ss.posterior_head_error_deg**2)))
   upstream=None
   # Read original PB score result if available in repo checkout.
   pbpath=BASE/"pol_bias_model/results/run_40652679303/PB_SCORES.csv"
   if pbpath.is_file():
    tab=pd.read_csv(pbpath)
    mm=tab[(tab.case==case)&(tab.bias==bias)&(tab.arm==name)]
    assert len(mm)==1
    upstream=float(mm.head_rmse.iloc[0])
    assert abs(upstream-hr)<1e-7,(case,bias,name,hr,upstream)
   summary.append(dict(case=case,bias=bias,arm=name,heading_rmse=hr,upstream_pb_rmse=upstream,
     accepted=int(acc.sum()),sum_signed_heading_s=float(ss.update_s_psi_deg.sum()),
     mean_abs_s_heading=float(ss.update_s_psi_deg.abs().mean()),
     s_locally_beneficial=int(((ss.heading_sq_effect_s_deg2<0)&ss.acc).sum()),
     s_locally_harmful=int(((ss.heading_sq_effect_s_deg2>0)&ss.acc).sum()),
     sum_local_s_squared_error_effect_deg2=float(ss.heading_sq_effect_s_deg2.sum())))
   records.extend(trace.to_dict("records"))
ledger=pd.DataFrame(records)
ledger.to_csv(out/"P4_PACKET_LEDGER.csv.gz",compression="gzip",index=False,float_format="%.16g")
agg=pd.DataFrame(summary);agg.to_csv(out/"P4_RECURSIVE_PARITY_AND_SUMMARY.csv",index=False,float_format="%.16g")
# Same-prior local intervention: differences in gain alone, not recursive donor state.
l=ledger[(ledger.t_s>=30)&(ledger.acc)]
piv=l.pivot(index=["case","bias","k"],columns="arm",values=["heading_sq_effect_s_deg2","update_s_psi_deg","prior_head_error_deg","gt_dist_m"])
rows=[]
for (case,bias),g in piv.groupby(level=["case","bias"]):
 base=g["heading_sq_effect_s_deg2"]["MB_ORIG"].to_numpy()
 var=g["heading_sq_effect_s_deg2"]["MB_VAR"].to_numpy()
 # This paired comparison is *not* at fixed prior: includes recursion.
 rows.append(dict(case=case,bias=bias,n=len(g),sum_s_sq_effect_orig=float(base.sum()),sum_s_sq_effect_var=float(var.sum()),sum_s_sq_effect_diff=float(var.sum()-base.sum()),
 prior_trajectory_changed=True,causal_claim="DESCRIPTIVE_DIFFERENT_PRIORS_NOT_SAME_PRIOR"))
pd.DataFrame(rows).to_csv(out/"P4_PACKET_GAIN_PAIRING.csv",index=False)
print(agg[["case","bias","arm","heading_rmse","s_locally_beneficial","s_locally_harmful"]].to_string(index=False))
