"""Audited, paired R2 recursive bias-decoupling experiment. No truth in filter."""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,zipfile
from pathlib import Path
import numpy as np
from core import predict,wrap,gaussian_update
from p3_rf_adapter4 import FrozenLut,R0,GATE_JOINT
from p3_frozen_inputs import open_verified_archive
from r2_bias_replay import build_positive_bias_controls,BIAS_LEVELS,CASES,CHANNELS,INITIAL_POSE_STD,BIAS_PRIOR_STD,predict_one
from r2_bias_audit import ARCHIVE
METHODS=("J4","FREEZE_ALL","FREEZE_NIS","CLAMP_NIS","ABSTAIN_NIS")
# A pre-registered two-dof joint NIS warning threshold (not learned from truth).
WARN_NIS=5.991464547107979  # 95% chi-square(2)
BIAS_CLAMP_DPS=0.002  # per accepted update, degrees / second
def digest(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for s in iter(lambda:f.read(1048576),b""):h.update(s)
 return h.hexdigest()
def joseph(P,K,H,R):
 A=np.eye(4)-K@H
 C=A@P@A.T+K@R@K.T
 return (C+C.T)/2
def update(x,P,z,case,lut,method):
 if method=="J4":
  y,C,diag=gaussian_update(x,P,z,lambda q:lut.model(q,case),R0,gate_threshold=GATE_JOINT)
  return y,C,("APPLIED" if diag["accepted"] else "REJECT"),diag["NIS"],0.
 h,H=lut.model(x,case);nu=z-h;S=H@P@H.T+R0
 nis=float(nu@np.linalg.solve(S,nu))
 if nis>GATE_JOINT:
  return x,P,"REJECT",nis,0.
 if method=="ABSTAIN_NIS" and nis>WARN_NIS:
  return x,P,"ABSTAIN",nis,0.
 K=np.linalg.solve(S,H@P).T
 raw_bias_step=float(K[3]@nu)
 if method=="FREEZE_ALL" or (method in ("FREEZE_NIS","CLAMP_NIS") and nis>WARN_NIS):
  if method=="CLAMP_NIS":
   limit=math.radians(BIAS_CLAMP_DPS)
   # Scale bias gain row, retaining its direction; bound realized innovation.
   alpha=min(1.,limit/max(abs(raw_bias_step),1e-30))
   K[3,:]*=alpha
  else:K[3,:]=0.
 y=x+K@nu;y[2]=float(wrap(y[2]))
 C=joseph(P,K,H,R0)
 if not np.isfinite(y).all() or np.linalg.eigvalsh(C).min()<=0:
  raise RuntimeError("NONFINITE_OR_NON_POSITIVE_POSTERIOR")
 return y,C,"APPLIED",nis,raw_bias_step
def filter_sequence(t,controls,z,case,lut,x0):
 n=len(t)
 P0=np.zeros((4,4));P0[:3,:3]=np.diag(INITIAL_POSE_STD**2)
 P0[3,3]=BIAS_PRIOR_STD**2
 state={m:(np.r_[x0,0.].copy(),P0.copy()) for m in METHODS}
 out={m:{"x":np.zeros((n,4)),"P":np.zeros((n,4,4)),
         "status":np.empty(n,dtype="U12"),"nis":np.full(n,np.nan),
         "bias_step":np.zeros(n)} for m in METHODS}
 for k in range(n):
  for m in METHODS:
   x,P=state[m]
   if k:
    x,P=predict_one(x,P,controls["ds_odom"][k],
                    controls["dtheta_gyro"][k],controls["dt_s"][k])
   y,C,status,nis,raw=update(x,P,z[k],case,lut,m)
   state[m]=(y,C)
   rec=out[m];rec["x"][k]=y;rec["P"][k]=C
   rec["status"][k]=status;rec["nis"][k]=nis;rec["bias_step"][k]=raw
 return out
def score(xs,Ps,truth,t,truebias):
 valid=t>=30
 e=xs[valid,:3]-truth[valid]
 e[:,2]=wrap(e[:,2])
 C=Ps[valid,:3,:3]
 n3=np.einsum("bi,bi->b",e,np.linalg.solve(C,e[...,None])[...,0])
 nh=e[:,2]**2/C[:,2,2]
 b=xs[valid,3];sb=Ps[valid,3,3];be=b-math.radians(truebias)
 return dict(frames=int(valid.sum()),heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
  position_rmse_m=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
  bias_rmse_dps=float(np.degrees(np.sqrt(np.mean(be**2)))),
  bias_final_dps=float(np.degrees(b[-1])),
  bias95=float(np.mean(be**2<=3.841458820694124*sb)),
  heading_nees=float(np.mean(nh)),pose_nees=float(np.mean(n3)),
  heading95=float(np.mean(nh<=3.841458820694124)),
  pose95=float(np.mean(n3<=7.814727903251179)))
def execute(archive,baseline,out):
 out.mkdir(parents=True,exist_ok=False)
 assert digest(archive)==ARCHIVE,"FROZEN_ARCHIVE_HASH"
 assert digest(baseline)=="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399","BASELINE_ARTIFACT_HASH"
 zbaseline=zipfile.ZipFile(baseline)
 lut=FrozenLut();rows=[]
 with open_verified_archive(archive) as z:
  summary=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  from r2_bias_replay import ROOT
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  cases={x["id"]:x for x in manifest["cases"]}
  descriptors={(d["case"],d["channel"]):d for d in summary["per_case"]}
  for label,bias in BIAS_LEVELS.items():
   truth0=None;t0=None;ids0=None
   for case in CASES:
    for channel in CHANNELS:
     desc=descriptors[(case,channel)]
     raw=z.read("P2_OUT/"+desc["trace_file"])
     assert hashlib.sha256(raw).hexdigest()==desc["trace_sha256"]
     with np.load(io.BytesIO(raw),allow_pickle=False) as data:
      t=data["t_s"].copy();ids=data["pose_id"].copy()
      truth=data["truth_for_offline_scoring_only"].copy()
      obs=np.column_stack([data["z_r_m"],data["z_s"]])
     if truth0 is None:
      truth0,t0,ids0=truth,t,ids
     else:
      assert np.array_equal(truth,truth0) and np.array_equal(t,t0) and np.array_equal(ids,ids0)
     controls,x0=build_positive_bias_controls(t,truth,label,0)
     result=filter_sequence(t,controls,obs,cases[case],lut,x0)
     reference="_temp/r2_bias_replay/"+case+"_"+channel+"_"+label+"_seed0_recursive.npz"
     with np.load(io.BytesIO(zbaseline.read(reference)),allow_pickle=False) as v:
      j=int(np.where(v["names"]=="J4")[0][0])
      difference=float(max(np.max(abs(result["J4"]["x"]-v["estimate"][:,j])),
        np.max(abs(result["J4"]["P"]-v["covariance"][:,j,:4,:4]))))
      statuses=np.array(v["status"][:,j],dtype=str)
      assert np.array_equal(result["J4"]["status"],statuses), "BASELINE_GATE_PARITY"
      if difference>1e-9:raise RuntimeError("BASELINE_REPLAY_PARITY "+str(difference))
     for m in METHODS:
      a=result[m]
      path=out/(case+"_"+channel+"_"+label+"_"+m+".npz")
      np.savez_compressed(path,t_s=t,pose_id=ids,x=a["x"],P=a["P"],
                          status=a["status"],nis=a["nis"],raw_bias_step=a["bias_step"])
      sc=score(a["x"],a["P"],truth,t,bias)
      mask=t>=30
      rows.append(dict(case=case,channel=channel,level=label,true_bias_dps=bias,
          method=m,baseline_max_parity=difference,
          warnings=int(np.count_nonzero((a["nis"]>WARN_NIS)&(a["nis"]<=GATE_JOINT)&mask)),
          applied=int(np.count_nonzero((a["status"]=="APPLIED")&mask)),
          abstained=int(np.count_nonzero((a["status"]=="ABSTAIN")&mask)),
          rejected=int(np.count_nonzero((a["status"]=="REJECT")&mask)),**sc))
 def csvout(path,data):
  with open(path,"w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
 csvout(out/"METRICS.csv",rows)
 assert len(rows)==16*len(METHODS)
 report={"status":"COMPLETED_PAIRED","scenarios":16,"methods":list(METHODS),
         "metrics_rows":len(rows),"baseline_parity_max":max(r["baseline_max_parity"] for r in rows),
         "warning_nis":WARN_NIS,"bias_clamp_dps":BIAS_CLAMP_DPS,
         "archive_sha256":digest(archive),"reference_sha256":digest(baseline),
         "scientific_PASS":False,"limitations":"single corridor, seed0, +bias only; NIS warning can miss persistent multipath"}
 (out/"FINAL.json").write_text(json.dumps(report,indent=2)+"\n")
 print(json.dumps(report,indent=2))
if __name__=="__main__":
 p=argparse.ArgumentParser()
 for name in ("archive","baseline","out"):p.add_argument("--"+name,required=True)
 a=p.parse_args();execute(Path(a.archive),Path(a.baseline),Path(a.out))
