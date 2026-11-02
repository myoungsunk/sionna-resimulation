#!/usr/bin/env python3
"""Exploratory P4 FULL AB/ABC fixed R inflation replay on exact original C0.

Frozen original P4 full outputs remain immutable. Replays EXACT pinned fourstate
f/F/Q, original B0/L2 controls and initial x/P, real Native Full or LoS A/B/C
range observations from frozen original 12 NPZ archive. Primary metric uses
all trajectories; 1/4/16/64 range-R multiplier with own 99pct chi2 gate.
Gamma=16 frozen original acceptance-mask contrast is a pure mathematical
fixed-mask sensitivity, NOT a normal deployable gating policy.
Ground truth is offline scoring-only. No fit, new RT, new scene or seed.
"""
from __future__ import annotations
import csv,hashlib,io,json,math,os,pathlib,sys,traceback,time,datetime,zipfile,platform
from collections import defaultdict
import numpy as np
ROOT=pathlib.Path.cwd()
SRC=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/runs/P4_FULL_C0PLUS_NATIVE_41435839892"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
ARCH=SRC/"P4_FULL_12_COMPLETE_4STATE_EKF_TRACES.zip"
OUT=pathlib.Path(os.getenv("P4_R_SENS_OUT","/tmp/p4_r_scale_sensitivity"));OUT.mkdir(parents=True,exist_ok=True)
ACTUAL_SHA="5ecf2a326ec17c8ce4ccc7a42fe76227ecf6ad7ec027df9cdfcd2304dcb0acfe"
ORIG_CORE_BLOB="0a0851e6867c14fec5eefe02df471100cb9e9e1d"
RR=.0068578637;OFFSET=-.5315983906250129
ANCH=np.asarray([[4.,0.,2.65],[10.,0.,2.65],[16.,.8,2.65]])
CASES={"R2":979,"R4":742,"R5":1415}
MODES=("los","full");BIASES={"B0":0.,"L2":.2}
ARMS=(("R4_AB_FULL",3,2),("R4_ABC_FULL",4,3))
SETTINGS=((1.,"self_gate"),(4.,"self_gate"),(16.,"self_gate"),(64.,"self_gate"),(16.,"original_mask"))
START=time.monotonic();ROWS=[];POOL=[];DIFF=[];CHECK={};ERROR=[]
def file_sha(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def chk(name,passed,measure):
 CHECK[name]={"status":"PASS" if passed else "FAIL","measured":measure}
 if not passed:ERROR.append(dict(key=name,details=measure))
 print("P4_R_SENS_CHECK",name,CHECK[name]["status"],str(measure)[:300],flush=True)
def require(v,msg):
 if not bool(v):raise RuntimeError(msg)
def readcsv(p):
 with pathlib.Path(p).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def wrap(v):return (np.asarray(v)+np.pi)%(2*np.pi)-np.pi
def writerows(path,records):
 if not records:
  pathlib.Path(path).write_text("EMPTY\n");return
 with pathlib.Path(path).open("w",newline="",encoding="utf-8") as f:
  writer=csv.DictWriter(f,fieldnames=list(records[0]),extrasaction="ignore")
  writer.writeheader();writer.writerows(records)
def h_range(x,dim):
 dr=np.asarray(x[:2])[None,:]-ANCH[:dim,:2]
 z=(.45-ANCH[:dim,2])
 dis=np.sqrt(np.sum(dr*dr,axis=1)+z*z)
 H=np.zeros((dim,4),float)
 H[:,:2]=dr/dis[:,None]
 return dis+OFFSET,H
def simulate(core,data,arm,idx,dim,scale,mode,truth):
 n=len(data["t_s"]);r0=np.eye(dim)*(RR*scale)
 x=data["initial_x0"].copy();P=data["initial_P0"].copy()
 status_ref=data["status"][:,idx]
 post_x=np.empty((n,4));post_P=np.empty((n,4,4))
 status=np.empty(n,dtype="<U15");NIS=np.empty(n)
 max_x_diff=0.;max_P_diff=0.;gate_diff=0
 for step in range(n):
  if step:
   ds=float(data["ds_odom"][step]);dt=float(data["dt_s"][step])
   gyro=float(data["dtheta_gyro"][step])
   q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
   x,P,_,_=core.predict(x,P,ds,gyro,dt,q)
  y=data["raw_native_ABC_z"][step,:dim,0]
  if mode=="original_mask" and status_ref[step]=="REJECT":
   prediction,H=h_range(x,dim)
   nu=y-prediction;S=H@P@H.T+r0
   nis=float(nu@np.linalg.solve(S,nu))
   out=x.copy();cov=P.copy();applied=False
  else:
   expected=lambda state:h_range(state,dim)
   threshold=({"R4_AB_FULL":9.210340371976184,
      "R4_ABC_FULL":11.344866730144373}[arm] if mode=="self_gate" else None)
   out,cov,diag=core.gaussian_update(x,P,y,expected,r0,gate_threshold=threshold)
   nis=float(diag["NIS"]);applied=bool(diag["accepted"])
  status[step]="APPLIED" if applied else "REJECT"
  NIS[step]=nis
  x=out;P=cov
  post_x[step]=x;post_P[step]=P
  if mode=="self_gate" and scale==1:
   de=x-data["xpost"][step,idx];de[2]=wrap(de[2])
   max_x_diff=max(max_x_diff,float(np.max(abs(de))))
   max_P_diff=max(max_P_diff,float(np.max(abs(P-data["Ppost"][step,idx]))))
   gate_diff+=int(status[step]!=status_ref[step])
 keep=data["t_s"]>=30
 e=post_x[keep,:3]-truth[keep,:3]
 e[:,2]=wrap(e[:,2])
 err_xy2=np.sum(e[:,:2]**2,axis=1)
 h2=e[:,2]**2
 bb=(post_x[keep,3]-math.radians(BIASES[data["bias"].item()]))**2
 pose_cov=post_P[keep,:3,:3]
 pose_nees=np.einsum("ij,ij->i",e,np.linalg.solve(pose_cov,e[:,:,None])[:,:,0])
 center=np.mean(post_P[keep,0,0]+post_P[keep,1,1])
 assert np.isfinite(pose_nees).all() and np.linalg.eigvalsh(pose_cov).min()>0
 r=dict(route=data["route"].item(),channel=data["channel"].item(),bias=data["bias"].item(),
  arm=arm,R_scale=scale,gate_policy=mode,n_eval=int(keep.sum()),
  heading_rmse_deg=math.degrees(math.sqrt(float(np.mean(h2)))),
  xy_rmse_m=math.sqrt(float(np.mean(err_xy2))),
  bias_rmse_deg_s=math.degrees(math.sqrt(float(np.mean(bb)))),
  pose95=float(np.mean(pose_nees<=7.814727903251179)),
  heading95=float(np.mean(h2/post_P[keep,2,2]<=3.841458820694124)),
  mean_pose_nees=float(np.mean(pose_nees)),
  mean_P_xy_trace_m2=float(center),
  rmse_xy_over_p_sigma=float(np.sqrt(np.mean(err_xy2)/center)),
  n_accepted=int(np.count_nonzero(status=="APPLIED")),
  n_rejected=int(np.count_nonzero(status=="REJECT")),
  mean_NIS=float(np.mean(NIS)),accepted_NIS_mean=float(np.mean(NIS[status=="APPLIED"])) if np.any(status=="APPLIED") else None,
  max_state_error_vs_original= float(max_x_diff) if scale==1 else None,
  max_covariance_error_vs_original=float(max_P_diff) if scale==1 else None,
  statuses_different_from_original=int(gate_diff) if scale==1 else None,
  one_scene_only=True,source_Rr_original_m2=RR,
  note="Gamma selected posthoc; original-mask sensitivity not a deployable filter")
 return r
def main():
 require(file_sha(ARCH)==ACTUAL_SHA,"ORIGINAL_12_TRACE_SHA_CHANGED")
 sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
 import core
 # Original upstream source code hash checked by git for an unmodified
 # core source; do not reinterpret it as new model.
 import subprocess
 source=ROOT/"research/EKF4_RANGE_S_STAGED_20261014/core.py"
 blob=subprocess.check_output(["git","hash-object",str(source)],text=True).strip()
 require(blob==ORIG_CORE_BLOB,"PINNED_EKF4_CORE_GIT_BLOB_CHANGED")
 chk("S00_ORIGINAL_SOURCE_PROVENANCE",True,{"trace_SHA":ACTUAL_SHA,"EKF4_core_git_blob":blob})
 p1=json.loads((P1/"P1_INPUT_LOCK.json").read_text())
 truth={}
 for route,n in CASES.items():
  a=next(x for x in p1["base_assets"] if x["kind"]=="TIMELINE_TNONE" and "timeline_"+route+"_" in x["path"])
  path=ROOT/a["path"];require(file_sha(path)==a["sha256"],"GT_SHA_CHANGED")
  r=readcsv(path)
  require(len(r)==n,"GT_COUNT_WRONG")
  truth[route]=np.asarray([[float(x["x"]),float(x["y"]),math.radians(float(x["yaw_body_deg"]))] for x in r])
 freeze={ (x["channel"],x["bias"],x["arm"]):x
   for x in readcsv(SRC/"P4_FULL_28_POOLED_METRICS.csv")}
 with zipfile.ZipFile(ARCH) as z:
  require(z.testzip() is None,"ORIGINAL_ZIP_CRC_FAILED")
  for route,n in CASES.items():
   for channel in MODES:
    for bias in BIASES:
     name=f"traces/P4_FULL_{route}_{channel}_{bias}_7STATE_EKF.npz"
     with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as s:
      data={k:s[k].copy() for k in s.files}
     require(data["names"].tolist()[3]=="R4_AB_FULL" and len(data["t_s"])==n,
             "SOURCE_NOT_EXPECTED_4STATE_NPZ")
     for arm,idx,dim in ARMS:
      for gamma,policy in SETTINGS:
       r=simulate(core,data,arm,idx,dim,gamma,policy,truth[route])
       ROWS.append(r)
       print("P4_R_SENS_SCORING",route,channel,bias,arm,gamma,policy,
         "xy",round(r["xy_rmse_m"],5),"pose95",round(r["pose95"],4),
         "accepted",r["n_accepted"],flush=True)
 require(len(ROWS)==120,"NOT_ALL_RETROSPECTIVE_SENSITIVITY_RUNS")
 max_baseline_x=max(x["max_state_error_vs_original"] or 0 for x in ROWS if x["R_scale"]==1)
 max_baseline_P=max(x["max_covariance_error_vs_original"] or 0 for x in ROWS if x["R_scale"]==1)
 bad_gate=sum(x["statuses_different_from_original"] for x in ROWS if x["R_scale"]==1)
 chk("S01_GAMMA1_FULL_4STATE_SOURCE_REPLAY",max(max_baseline_x,max_baseline_P)<=1e-9 and bad_gate==0,
     {"n_source_control_traces":24,"max_state_diff":max_baseline_x,"max_P_diff":max_baseline_P,
      "gate_mismatches":bad_gate})
 require(not ERROR,"GAMMA1_FROZEN_REPRODUCTION_FAILED")
 groups=defaultdict(list)
 for r in ROWS:groups[(r["channel"],r["bias"],r["arm"],r["R_scale"],r["gate_policy"])].append(r)
 for key,part in sorted(groups.items()):
  n=sum(z["n_eval"] for z in part)
  rmse=lambda col:math.sqrt(sum(z["n_eval"]*z[col]**2 for z in part)/n)
  avg=lambda col:sum(z["n_eval"]*z[col] for z in part)/n
  POOL.append(dict(channel=key[0],bias=key[1],arm=key[2],R_scale=key[3],gate_policy=key[4],
   n_eval=n,original_scene_n=1,route_n=len(part),
   heading_rmse_deg=rmse("heading_rmse_deg"),xy_rmse_m=rmse("xy_rmse_m"),
   bias_rmse_deg_s=rmse("bias_rmse_deg_s"),
   pose95=avg("pose95"),heading95=avg("heading95"),
   mean_pose_nees=avg("mean_pose_nees"),
   mean_P_xy_trace_m2=avg("mean_P_xy_trace_m2"),
   n_accepted=sum(x["n_accepted"] for x in part),
   n_rejected=sum(x["n_rejected"] for x in part),
   mean_NIS=avg("mean_NIS")))
 published_diff=0.
 for item in POOL:
  if item["R_scale"]==1 and item["gate_policy"]=="self_gate":
   reference=freeze[(item["channel"],item["bias"],item["arm"])]
   for key in ("heading_rmse_deg","xy_rmse_m","pose95"):
    published_diff=max(published_diff,abs(item[key]-float(reference[key])))
 chk("S02_GAMMA1_ORIGINAL_POOLED_EXACT",published_diff<=1e-9,{"max_abs_source_metric_diff":published_diff})
 require(not ERROR,"SOURCE_P4_METRIC_IDENTITY_FAIL")
 lookup={(r["channel"],r["bias"],r["arm"],r["R_scale"],r["gate_policy"]):r for r in POOL}
 for item in POOL:
  source=lookup[(item["channel"],item["bias"],item["arm"],1.,"self_gate")]
  change=dict(channel=item["channel"],bias=item["bias"],arm=item["arm"],gamma=item["R_scale"],gate_policy=item["gate_policy"],
   source_gamma1_heading_rmse_deg=source["heading_rmse_deg"],
   resulting_heading_rmse_deg=item["heading_rmse_deg"],
   delta_heading_deg=item["heading_rmse_deg"]-source["heading_rmse_deg"],
   source_gamma1_xy_rmse_m=source["xy_rmse_m"],resulting_xy_rmse_m=item["xy_rmse_m"],
   delta_xy_m=item["xy_rmse_m"]-source["xy_rmse_m"],
   source_gamma1_pose95=source["pose95"],resulting_pose95=item["pose95"],
   delta_pose95=item["pose95"]-source["pose95"],
   n_accepted_gamma1=source["n_accepted"],n_accepted_modified=item["n_accepted"],
   delta_n_accepted=item["n_accepted"]-source["n_accepted"])
  DIFF.append(change)
 chk("S03_SENSITIVITY_SAMPLE_COVERAGE",len(POOL)==40 and len(DIFF)==40 and
     all(x["n_eval"]==2686 for x in POOL),{"runs":len(ROWS),"pooled":len(POOL),"full_t_ge30_n":2686})
 write=writerows
 write(OUT/"P4_R_SCALE_120_CASE_METRICS.csv",ROWS)
 write(OUT/"P4_R_SCALE_40_POOLED_METRICS.csv",POOL)
 write(OUT/"P4_R_SCALE_40_DELTA_FROM_ORIGINAL.csv",DIFF)
 report=dict(schema="DLP_P4_FULL_EXPLORATORY_R_SCALE_MECHANISM_V1",
  status="PASS_RETROSPECTIVE_SENSITIVITY_NUMERIC_NOT_CONFIRMATORY",
  source_original_zip_sha256=ACTUAL_SHA,
  frozen_core_git_blob=ORIG_CORE_BLOB,
  results_120=len(ROWS),results_40_pooled=len(POOL),
  gamma_modes={"self_gate":[1,4,16,64],"frozen_original_mask":[16]},
  matched_full_los_original=True,original_single_C0_simulation_scene_n=1,
  no_new_R_training=True,no_new_RT=True,
  primary_full_results=[x for x in POOL if x["channel"]=="full"],
  numeric_checks=CHECK,failures=ERROR,
  scientific_warning="Gamma was selected posthoc and tested on the known C0 Full trace and same seed; NOT a prevalidated sensor-noise estimate or independently replicated covariance calibration.",
  gamma16_fixedmask_warning="Mask from original gamma1 filter, not a deployable new innovation gate policy; sensitivity-only.",
  code_sha256=file_sha(__file__),github_run=os.environ.get("GITHUB_RUN_ID"),
  execution_s=time.monotonic()-START,
  utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (OUT/"P4_R_SCALE_SENSITIVITY_QA.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
 print("P4_R_SCALE_SENSITIVITY_FINAL",report["status"],"cases",len(ROWS),"pooled",len(POOL),flush=True)
if __name__=="__main__":
 try:main()
 except Exception as e:
  ERROR.append(dict(id="SENSITIVITY_FAILURE",error=repr(e),traceback=traceback.format_exc()))
  (OUT/"P4_R_SCALE_SENSITIVITY_BLOCKED.json").write_text(json.dumps(dict(
    status="BLOCKED",source_sha=ACTUAL_SHA,errors=ERROR,
    numeric_checks=CHECK,script_sha=file_sha(__file__)),indent=2)+"\n")
  print("P4_R_SCALE_SENSITIVITY_FATAL",repr(e),traceback.format_exc(),flush=True)
  sys.exit(1)
