"""Post-inference scorer; truth read ONLY after replay trace files are frozen.

Computes honest per-level/mount/channel/arm one-step and recursive RMSE,
position/heading NEES, 95% coverage, bias recovery and packet gate rates.
Not a site-generalization or independent per-timestamp significance claim.
"""
from __future__ import annotations
import argparse,csv,io,json,math,os
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from p3_frozen_inputs import open_verified_archive
from r2_bias_audit import ARCHIVE
from r2_bias_replay import BIAS_LEVELS,CASES,CHANNELS,METHODS,MODES,sha_file,verify_audit

CHI3=7.814727903251179
CHI1=3.841458820694124
def score_one(x,P,true,mask,obs_status,true_bias_rad_s,has_bias):
 valid=mask&np.isfinite(x[:,:3]).all(axis=1)&np.isfinite(P[:,:3,:3]).all(axis=(1,2))
 n=int(valid.sum())
 if n==0:return {"frames_valid":0}
 e=x[valid,:3]-true[valid,:3]
 e[:,2]=(e[:,2]+math.pi)%(2*math.pi)-math.pi
 C=P[valid,:3,:3]
 if np.linalg.eigvalsh(C).min()<=0:
  raise RuntimeError("SCORED_POSTERIOR_NON_PD")
 nees=np.einsum("bi,bi->b",e,np.linalg.solve(C,e[:,:,None])[:,:,0])
 hnees=e[:,2]**2/C[:,2,2]
 gate=mask & (obs_status=="APPLIED")
 rejection=mask & (obs_status=="REJECT")
 metrics={"frames_valid":n,"pose_rmse_m":float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
   "heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
   "heading_mean_signed_error_deg":float(np.degrees(np.mean(e[:,2]))),
   "heading_sigma_rms_deg":float(np.degrees(np.sqrt(np.mean(C[:,2,2])))),
   "pose_nees_mean":float(np.mean(nees)),"pose_nees_median":float(np.median(nees)),
   "pose_nees_p95":float(np.percentile(nees,95)),
   "pose_nees_p99":float(np.percentile(nees,99)),
   "heading_nees_mean":float(np.mean(hnees)),
   "heading_nees_median":float(np.median(hnees)),
   "heading_nees_p95":float(np.percentile(hnees,95)),
   "pose95_coverage":float(np.mean(nees<=CHI3)),
   "heading95_coverage":float(np.mean(hnees<=CHI1)),
   "gate_applied":int(gate.sum()),"gate_rejected":int(rejection.sum())}
 if has_bias:
  b=x[valid,3];Pb=P[valid,3,3]
  metrics.update({"estimated_bias_mean_dps":float(np.degrees(np.mean(b))),
    "bias_rmse_dps":float(np.degrees(np.sqrt(np.mean((b-true_bias_rad_s)**2)))),
    "bias_final_estimate_dps":float(np.degrees(b[-1])),
    "bias_final_sigma_dps":float(np.degrees(math.sqrt(Pb[-1]))),
    "bias95_coverage":float(np.mean((b-true_bias_rad_s)**2<=CHI1*Pb)),
    "bias_pose_crosscov_abs_mean":float(np.mean(np.abs(P[valid,2,3])))})
 else:metrics.update({"estimated_bias_mean_dps":None,"bias_rmse_dps":None,
       "bias_final_estimate_dps":None,"bias_final_sigma_dps":None,"bias95_coverage":None,
       "bias_pose_crosscov_abs_mean":None})
 return metrics

def run(raw_artifact,root,audit,out):
 verify_audit(audit)
 if sha_file(raw_artifact)!=ARCHIVE:raise RuntimeError("ORIGINAL_ARCHIVE_CHANGED")
 root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=False)
 job=json.loads((root/"FINAL.json").read_text())
 if not(job["status"]=="RUN_COMPLETED" and job["git_sha"]==os.environ["GITHUB_SHA"]
        and job["total_case_level_channels"]==16):
  raise RuntimeError("NO_COMPLETE_REPLAY_TO_SCORE")
 rows=[];truth_cache={}
 with open_verified_archive(raw_artifact) as archive:
  for case in CASES:
   for channel in CHANNELS:
    trace=f"P2_OUT/{case}_{channel}_seed0_ONE_STEP.npz"
    with np.load(io.BytesIO(archive.read(trace)),allow_pickle=False) as d:
     truth_cache[(case,channel)]=(d["truth_for_offline_scoring_only"].copy(),
         d["t_s"].copy(),d["pose_id"].copy())
 for name,truebias in BIAS_LEVELS.items():
  for case in CASES:
   for channel in CHANNELS:
    true,t,id1=truth_cache[(case,channel)]
    evalmask=t>=30.
    for mode in MODES:
     path=root/(case+"_"+channel+"_"+name+"_seed0_"+mode+".npz")
     if not path.exists():raise RuntimeError("REPLAY_TRACE_MISSING:"+path.name)
     with np.load(path,allow_pickle=False) as z:
      x=z["estimate"].copy()
      P=z["covariance"].copy()
      status=z["status"].copy()
      poseid=z["pose_id"].copy()
      tt=z["t_s"].copy()
      methods=z["names"].tolist()
     if not(np.array_equal(tt,t) and np.array_equal(poseid,id1)
            and x.shape==(len(t),8,4) and P.shape==(len(t),8,4,4)
            and methods==list(METHODS)):
      raise RuntimeError("SCORER_REPLAY_IDENTITY_OR_SHAPE")
     for j,method in enumerate(METHODS):
      got=score_one(x[:,j],P[:,j],true,evalmask,status[:,j],math.radians(truebias),method.endswith('4'))
      if got["frames_valid"]!=int(evalmask.sum()):
       raise RuntimeError("INVALID_RECURSIVE_OR_ONE_STEP_FRAME:"+path.name+":"+method+":"+str(got["frames_valid"]))
      row={"case":case,"mount_deg":0 if case.endswith("m0") else 45,
          "rf_channel":channel,"level":name,"gyro_bias_true_dps":truebias,
          "evaluation_mode":mode,"method":method,"seed":0,
          "eval_frames_expected":int(evalmask.sum()),**got}
      rows.append(row)
      print("R2_BIAS_METRIC "+json.dumps({k:row[k] for k in
        ("case","rf_channel","level","evaluation_mode","method","heading_rmse_deg",
         "pose_rmse_m","heading95_coverage","bias_final_estimate_dps")}),flush=True)
 if len(rows)!=16*2*8:
  raise RuntimeError("FINAL_METRIC_DENOMINATOR_MISMATCH")
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (out/"R2_BIAS_METRICS.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
 # Pairwise s vs joint, 3/4 and relinearized, and 3->4 changes.
 contrasts=[]
 by={(r["case"],r["rf_channel"],r["level"],r["evaluation_mode"],r["method"]):r for r in rows}
 for case in CASES:
  for channel in CHANNELS:
   for level in BIAS_LEVELS:
    for mode in MODES:
     for lhs,rhs in (("S3","J3"),("S4","J4"),("S3","SR3"),
                     ("S4","SR4"),("S3","S4"),("J3","J4"),
                     ("SR3","SR4"),("DR3","DR4"),("DR4","S4")):
      l=by[(case,channel,level,mode,lhs)]
      r=by[(case,channel,level,mode,rhs)]
      contrasts.append({"case":case,"channel":channel,"level":level,
        "evaluation_mode":mode,"pair":rhs+"-minus-"+lhs,
        "heading_rmse_difference_deg":r["heading_rmse_deg"]-l["heading_rmse_deg"],
        "pose_rmse_difference_m":r["pose_rmse_m"]-l["pose_rmse_m"],
        "heading_coverage_difference":r["heading95_coverage"]-l["heading95_coverage"]})
 with (out/"R2_BIAS_CONTRASTS.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(contrasts[0]))
  w.writeheader();w.writerows(contrasts)
 final={"schema":"R2_L012_BIAS_RMSE_NEES_COVERAGE_RECURSIVE_V1",
        "git_sha":os.environ["GITHUB_SHA"],
        "run_id":os.environ.get("GITHUB_RUN_ID"),
        "frozen_source_archive_sha":ARCHIVE,
        "experiment_status":"COMPLETED","metrics_count":len(rows),
        "contrasts_count":len(contrasts),
        "technical_PASS":True,"scientific_PASS":False,
        "comparison":{"B0":0.,"L0":.01,"L1":.05,"L2":.2},
        "noise":"frozen sensor-v2 seed0; pair-white noise, bias-only perturbation",
        "scope_warning":"one R2 corridor trajectory and one sensor seed; timestamps and mount replicates are not independent scenes",
        "observation_warning":"FROZEN full channel is multipath model mismatch; LoS LUT physical accuracy not established by parity alone",
        "method_warning":"one-step uses separately propagated DR-only 3/4-state priors; recursive propagates each RF posterior",
        "bias_effect_warning":"one-step b estimate does not carry to next timestep; 4-state prior pose-b cross-cov can be nonzero after DR4 predictions",
        "sources_sha256":{"R2_BIAS_METRICS.csv":sha_file(out/"R2_BIAS_METRICS.csv"),
                          "R2_BIAS_CONTRASTS.csv":sha_file(out/"R2_BIAS_CONTRASTS.csv")},
        "created_utc":datetime.now(timezone.utc).isoformat()}
 (out/"FINAL.json").write_text(json.dumps(final,indent=2,ensure_ascii=False)+"\n")
 print("R2_BIAS_SCORE_FINAL "+json.dumps({k:final[k] for k in
  ("experiment_status","metrics_count","contrasts_count","technical_PASS")}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 for n in ("archive","root","audit","out"):p.add_argument("--"+n,required=True)
 a=p.parse_args()
 raise SystemExit(run(a.archive,a.root,a.audit,a.out))
