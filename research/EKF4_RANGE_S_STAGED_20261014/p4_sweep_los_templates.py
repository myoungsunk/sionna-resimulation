"""11-point +/-10 and 19-point +/-45 actual frozen LoS LUT templates.

The arrays are MODEL PREDICTIONS at pinned R2 saved DR priors, NOT new
measured Full multipath observations and NOT independent heading GT.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,zipfile
from pathlib import Path
from datetime import datetime,timezone
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from p3_rf_adapter4 import FrozenLut,RS
from p4_lut_boundary import lut_angles
from p3_frozen_inputs import load_frozen_rf_trace,open_verified_archive
from p4_sweep_los_pre_audit import checks,ROOT,RF_SHA
HERE=Path(__file__).resolve().parent
def digest(path):return checks(path)[1]
def covariance(n,rho):
 return RS*rho**np.abs(np.subtract.outer(np.arange(n),np.arange(n)))
def eliminate_offset_loglik(res,C):
 one=np.ones(len(res));i=np.linalg.solve(C,res);io=np.linalg.solve(C,one)
 offs=float(one@i/(one@io));r=res-one*offs
 return -.5*float(r@np.linalg.solve(C,r))
def curve(lut,angles,offsets,shift=0.):
 theta,tx,rx=angles
 return np.array([lut(theta,tx,rx-float(d)-float(shift))[0] for d in offsets],float)
def export_csv(path,rows):
 with Path(path).open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=tuple(rows[0]));w.writeheader();w.writerows(rows)
def main(archive,audit,out):
 receipt=json.loads(Path(audit).read_text())
 if receipt["decision"]!="GO" or receipt["git_sha"]!=os.getenv("GITHUB_SHA"):raise RuntimeError("PREAUDIT_NOT_GO")
 for k,v in receipt["source_sha256"].items():
  if digest(ROOT/k)!=v:raise RuntimeError("SOURCE_CHANGED_AFTER_AUDIT:"+k)
 if digest(archive)!=RF_SHA:raise RuntimeError("ARCHIVED_RF_SHA_CHANGED")
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 cases={}
 meta=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cases={c["id"]:c for c in meta["cases"]}
 lut=FrozenLut(ROOT)
 results=[]
 offsets={"FAST11":np.linspace(-10.,10.,11),"WIDE19":np.linspace(-45.,45.,19),
          "WIDE11_CONTROL":np.linspace(-45.,45.,11)}
 with open_verified_archive(archive) as z:
  summary=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  for case_id in ("R2_aA_m0","R2_aA_m45"):
   d=next(e for e in summary["per_case"] if e["case"]==case_id and e["channel"]=="los")
   t=load_frozen_rf_trace(z,d);c=cases[case_id]
   for target in (60.,120.):
    k=int(np.argmin(abs(t.t_s-target)))
    if abs(t.t_s[k]-target)>1e-5:raise RuntimeError("R2_TEMPLATE_TIME_MISSING")
    x=t.prior_x[k];angles=lut_angles(x,c)
    result={"case":case_id,"mount_deg":c["mount_deg"],"k":k,"pose_id":int(t.pose_id[k]),
            "t_s":float(t.t_s[k]),"theta_tx_rx_deg":angles.tolist(),
            "physics":"LoS frozen LUT only","samples":{},"profile":{},
            "scientific_PASS":False}
    for name,arr in offsets.items():
     val=curve(lut,angles,arr)
     samples=[{"sample_index":j,"relative_yaw_deg":float(delta),
               "frozen_LoS_predicted_s":float(y)} for j,(delta,y) in enumerate(zip(arr,val))]
     result["samples"][name]=samples
     for rho in (0.,.8):
      C=covariance(len(arr),rho)
      eps=np.linspace(-30,30,601)
      # Exact shape-only likelihood evaluated at synthetic injected
      # reference center shift=0. This is self-match observability,
      # never a noisy physical heading estimate.
      L=np.array([eliminate_offset_loglik(val-curve(lut,angles,arr,shift=e),C)
                  for e in eps])
      L-=np.max(L)
      loss=-2*L
      band=eps[loss<=3.841458820694124]
      result["profile"][name+"_AR1"+str(rho)]={
       "grid_step_deg":.1,
       "self_match_delta_best_deg":float(eps[np.argmin(loss)]),
       "chi2_95_delta_interval_deg":[float(band.min()),float(band.max())] if len(band) else None,
       "chi2_95_noncontiguous_warning":bool(np.any(np.diff(np.where(loss<=3.841458820694124)[0])>1)),
       "noise_assumption_AR1":rho,"s_variance":RS,
       "full_multipath_model_included":False}
     export_csv(out/(case_id+f"_t{int(target)}_"+name+"_LOS_TEMPLATE.csv"),samples)
    fig,ax=plt.subplots(figsize=(9.5,4.9))
    wide=np.linspace(-45,45,181);base=curve(lut,angles,wide)
    ax.plot(wide,base,linewidth=1.6,color="0.4",label="Continuous frozen LoS LUT template")
    for name,marker in (("FAST11","o"),("WIDE19","s")):
     rows=result["samples"][name]
     ax.plot([r["relative_yaw_deg"] for r in rows],
             [r["frozen_LoS_predicted_s"] for r in rows],
             marker=marker,linestyle="--",markersize=4.4,label=name)
    ax.set(xlabel="Measured-relative yaw offset (degrees, ideal model)",
           ylabel="Predicted s = (P1-P2)/(P1+P2)",
           title=f"R2 {case_id}, t={target:.0f}s, frozen LoS LUT (NO Full scan)")
    ax.legend();ax.grid(alpha=.24);fig.tight_layout()
    fig.savefig(out/(case_id+f"_t{int(target)}_FAST11_WIDE19.png"),dpi=175)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(9.5,4.9))
    for name in ("FAST11","WIDE19","WIDE11_CONTROL"):
     arr=offsets[name];v=curve(lut,angles,arr);C=covariance(len(arr),0.)
     shifts=np.linspace(-30,30,301)
     loss=np.array([-2*eliminate_offset_loglik(v-curve(lut,angles,arr,shift=d),C) for d in shifts])
     loss-=loss.min()
     ax.plot(shifts,loss,label=name)
    ax.axhline(3.841458820694124,linestyle=":",color="0.5",linewidth=1)
    ax.set(xlabel="Trial center yaw shift relative to controlled self-match (deg)",
           ylabel="Shape-only negative 2 log-likelihood difference (ideal LoS)",
           title=f"R2 {case_id} t={target:.0f}s: unknown common multipath offset removed")
    ax.legend();ax.grid(alpha=.23);fig.tight_layout()
    fig.savefig(out/(case_id+f"_t{int(target)}_SHAPE_LIKELIHOOD.png"),dpi=175)
    plt.close(fig)
    results.append(result)
    print("R5_SWEEP_TEMPLATE "+json.dumps({"case":case_id,"t":target,"fast11_span":max(r["frozen_LoS_predicted_s"] for r in result["samples"]["FAST11"])-min(r["frozen_LoS_predicted_s"] for r in result["samples"]["FAST11"]),
      "wide19_span":max(r["frozen_LoS_predicted_s"] for r in result["samples"]["WIDE19"])-min(r["frozen_LoS_predicted_s"] for r in result["samples"]["WIDE19"])}),flush=True)
 outsum={"schema":"R5_R2_FAST11_WIDE19_LOS_ONLY_SELF_MATCH_S0_V1",
   "git_sha":os.getenv("GITHUB_SHA"),"source_run_id":38331588521,
   "source_archive_sha256":RF_SHA,"cases":results,
   "controls":["FAST11 +/-10 step2","WIDE19 +/-45 step5","WIDE11_CONTROL +/-45 equal sample count"],
   "limitations":["Only LoS-LUT prediction, no Full orientation resolved raw H exists",
                  "Self-match/no simulated independent multipath; not a validation of heading accuracy",
                  "x,y and relative yaw errors held fixed at saved DR prior",
                  "Gaussian AR1/white s covariance is hypothetical, not Full calibrated"],
   "scientific_PASS":False,"status":"LOS_S0_TEMPLATE_COMPLETE",
   "time_utc":datetime.now(timezone.utc).isoformat()}
 (out/"FINAL.json").write_text(json.dumps(outsum,indent=2)+"\n")
 print("R5_SWEEP_TEMPLATE_FINAL "+json.dumps({"status":outsum["status"],"cases":len(results),
   "fast_points":11,"wide_points":19,"scientific_PASS":False}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 for n in ("archive","audit","out"):p.add_argument("--"+n,required=True)
 a=p.parse_args();raise SystemExit(main(a.archive,a.audit,a.out))
