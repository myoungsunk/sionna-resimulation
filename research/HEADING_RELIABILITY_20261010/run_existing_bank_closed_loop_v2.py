#!/usr/bin/env python3
"""Bounded-bank continuous v2 EKF with low-quality triggered yaw probe, no new RF.

IMPORTANT: This is an ideal-sampled-stop / noise-free-RF exploratory pilot, not
arbitrary-XY RF on-demand closed loop nor full calibrated temporal covariance.
The sensor-v2 EKF runs at ALL retained normal and actual selected probe 5Hz steps.
"""
from __future__ import annotations
import argparse, csv, json, hashlib, math, pickle, time, warnings
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import chi2
warnings.filterwarnings("ignore",message="X has feature names")
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
B=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
T=ROOT/"results/DRIVE_SIM_20261007/S1/routes"
import sys
sys.path.insert(0,str(RUN/"source/src"))
from qclean_uwb.drivesim import sensor_v2 as V, filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
from qclean_uwb.drivesim.hs_lut import HsLut,s_model
CASES=["R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0","R4_aB_m0","R5_aA_m0","R5_aB_m0"]
LEVELS=(0,1,2)
ARMS=["D_DEFAULT","E_PASSIVE","F3_ACTIVE","F2_PAIRED","SHAM_F3"]
THRESHOLD=.5
MAX_EVENTS=3
COOLDOWN_G=50
GATE_SITE_S=.12
GATE_SITE_YAW_DEG=8.0
BATCH_GATE_QUANTILE=.99
NOMINAL_DT=.2
EVAL_PROGRESS_T=30.
MISSING_PROBE_RATE=0.
 
def filehash(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(2*1024*1024),b""):h.update(b)
 return h.hexdigest()
 
def static_inputs():
 lutp=RUN/"LUT/hs_lut_2deg.npy"
 expected="711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079"
 actual=filehash(lutp)
 assert actual==expected,("LUT_HASH_MISMATCH",actual,expected)
 m=json.loads((RUN/"LUT/hs_lut_meta.json").read_text())["meta"]
 phi=np.arange(m["phi_deg"][0],m["phi_deg"][1]+.01,m["phi_deg"][2])
 lut=HsLut(dict(theta_deg=m["theta_deg"],phi_deg=phi,s=np.load(lutp)))
 cases={c["case"]:c for c in json.loads((B/"CASES.json").read_text())}
 feature=pd.read_csv(RUN/"OUTPUT/01_FEATURES.csv")
 assert not feature.duplicated(["case","pose_id"]).any()
 features={}
 for case,g in feature.groupby("case"):
  features[case]={int(row["pose_id"]):row for row in g.to_dict("records")}
 packs={}
 for route in ("R2","R4","R5"):
  with open(RUN/"RELIABILITY"/f"{route}_DPK.pkl","rb") as f:
   packs[route]=compile_model(pickle.load(f))
 return lut,cases,features,packs,m

def compile_model(p):
 cols=list(p["columns"])
 if p["constant"] is not None:
  return dict(cols=cols,const=float(p["constant"]),kind="constant")
 z=p["base"].named_steps
 imp=z["simpleimputer"];sc=z["standardscaler"];lr=z["logisticregression"]
 stats=np.asarray(imp.statistics_,float)
 keep=np.isfinite(stats)
 indicators=np.asarray(imp.indicator_.features_,int)
 assert len(sc.mean_)==int(keep.sum())+len(indicators)
 calibrator=p.get("calibrator")
 calibration=None
 if calibrator is not None:
  calibration=(float(calibrator.coef_[0,0]),float(calibrator.intercept_[0]))
 return dict(cols=cols,kind="linear",stats=stats,keep=keep,indicators=indicators,
             mu=np.asarray(sc.mean_,float),std=np.asarray(sc.scale_,float),
             weight=np.asarray(lr.coef_[0],float),bias=float(lr.intercept_[0]),
             calib=calibration)

def fast_predict(pack,feat):
 if pack["kind"]=="constant":return pack["const"]
 x=np.asarray([feat.get(k,np.nan) for k in pack["cols"]],float)
 bad=~np.isfinite(x)
 xi=np.where(bad,pack["stats"],x)[pack["keep"]]
 xx=np.r_[xi,bad[pack["indicators"]].astype(float)]
 logit=pack["bias"]+float(pack["weight"]@((xx-pack["mu"])/pack["std"]))
 if pack["calib"] is not None:
  slope,intercept=pack["calib"];logit=slope*logit+intercept
 return float(expit(logit))
 
def route_files():
 rows={}
 for route in ("R2","R4","R5"):
  all_df=pd.read_csv(T/f"timeline_{route}_T10.csv")
  none=pd.read_csv(T/f"timeline_{route}_Tnone.csv")
  normal=all_df[all_df.phase!="probe"].reset_index()
  assert len(normal)==len(none)
  for col in ("pose_id","drive_g","phase"):
   assert normal[col].astype(str).to_list()==none[col].astype(str).to_list(),(route,col)
  for col in ("x","y","yaw_body_deg"):
   assert np.allclose(normal[col],none[col],rtol=0,atol=1e-12),(route,col)
  group={}
  for drive_g,g in all_df[all_df.phase=="probe"].groupby("drive_g",sort=True):
   cc=g[["idx","probe_offset_deg","pose_id"]].to_numpy()
   # group index: original DataFrame row index.
   cs=[(int(v[0]),float(v[1]),int(v[2])) for v in cc]
   def select(n):
    up=[5.,10.] if n==2 else [5.,10.,15.,20.]
    down=[5.,0.] if n==2 else [15.,10.,5.,0.]
    forward=[]
    for u in up:
     matches=[q for q in cs if abs(q[1]-u)<1e-8]
     forward.append(matches[0])
    back=[]
    for u in down:
     matches=[q for q in cs if abs(q[1]-u)<1e-8]
     back.append(matches[-1])
    data=forward+back
    assert all(data[j][0]<data[j+1][0] for j in range(len(data)-1))
    return data
   group[int(drive_g)]={2:select(2),3:select(3)}
  # Independently compare original route full raw rows.
  pose=all_df[["x","y","yaw_body_deg"]].to_numpy(float)
  pose[:,2]=np.radians(pose[:,2])
  t=all_df.t_s.to_numpy(float)
  ds,dth=V.motion_increments(t,pose,convention="legacy-euler",tolerance=1e-8)
  assert len(ds)==len(all_df)
  rows[route]=dict(full=all_df,none=none,normal=normal,groups=group,
                   t=t,pose=pose,ds=ds,dtheta=dth,
                   alignment_max_xy=float(np.max(np.abs(normal[["x","y"]].to_numpy()-none[["x","y"]].to_numpy()))))
 return rows
 
def config(c,meta):
 return FilterConfig(model_version="sensor-v2",kind="ekf",s_mode="direct",
  use_range=True,use_s=True,anchor_xyz=tuple(c["anchor_xyz"]),mount_deg=float(c["mount_deg"]),
  robot_z=float(c["robot_z"]),bias_rw_std=0.,known_wheelbase_error=0.,
  range_offset=float(meta["range_bias"]["mean_m"]))
 
def pre_rf_q(f,case,source_idx,obs,input_s,pack,c,lut,
             effective_heading_offset=0.):
 x,P=f.mean_cov()
 h,J=s_model(lut,c["anchor_xyz"],c["robot_z"],float(x[0]),float(x[1]),
             float(x[2]+effective_heading_offset),c["mount_deg"],with_jac=True)
 H=np.asarray(J,float)
 var=float(H@P[:3,:3]@H)+.09**2
 var=max(var,1e-15)
 feat=obs.copy()
 feat.update(K_distance=float(obs["range_m"]),
             K_slope_per_rad=abs(float(H[2])),
             K_position_variance=float(P[0,0]+P[1,1]),
             K_heading_variance=float(P[2,2]),
             K_gyro_wheel_discrepancy=float(input_s["dtheta_gyro"][source_idx]-input_s["dtheta_odom"][source_idx]),
             K_innovation_standardized=float((obs["s"]-float(h))/np.sqrt(var)))
 q=fast_predict(pack,feat)
 return float(q),float(h),H,float(var)
 
def s_quality_update(f,z,power,h,J,q,mode):
 if mode=="D_DEFAULT":
  return f.s_record(z,power)
 if q<THRESHOLD:return (None,None,None,"reliability_abstained")
 R=f._s_R(float(power[0]),float(power[1]))*min(100,max(1,1/max(q,.1)**2))
 H=np.zeros(6);H[:3]=J
 return f.scalar(float(z),float(h),H,R,"s")
 
def run_one(case,level,seed,arm,problem,sources,forced=None,keep_trace=False):
 lut,cases,features,packs,meta=sources
 c=cases[case]; route=case.split("_")[0]
 timeline=problem[route]; full=timeline["full"];normal=timeline["normal"]
 params=V.SensorV2Config(level=level,condition="all")
 sensor,ev=V.generate(timeline["t"],timeline["ds"],timeline["dtheta"],params,seed)
 x0=np.r_[timeline["pose"][0].copy(),0.,0.,0.]
 x0[:3]+=V.rng(seed,"initial").normal(size=3)*np.asarray(config(c,meta).p0_std[:3])
 f=F.SensorV2Filter(config(c,meta),lut,x0)
 pack=packs[route];fmap=features[case]
 triggered=[];event=[];errs=[];elapsed=0.;maxprobe=MAX_EVENTS
 recorded_g=set();lastg=-10**9
 normal_counter=-1;n_low=0;n_offbank_low=0;n_s_applied=0;n_s_rejected=0
 record=[]
 def one_tick(k):
  nonlocal elapsed
  if k:
   f.step(float(sensor["ds_odom"][k]),float(sensor["dtheta_gyro"][k]),
          float(sensor["dtheta_odom"][k]),NOMINAL_DT)
   elapsed+=NOMINAL_DT
  obs=fmap[int(full.iloc[k].pose_id)]
  if bool(obs["detected"]) and np.isfinite(obs["range_m"]):
   f.range_record(float(obs["range_m"]))
  return obs
 
 def batch_probe(packets,turn_idxs):
  # Filter state is AFTER 8 (or 4) noisy gyro/wheel body turns, now nominal original yaw.
  nonlocal n_s_applied
  x,P=f.mean_cov()
  corrected=np.array([
     (float(sensor["dtheta_gyro"][ix])-float(x[3])*NOMINAL_DT)/(1+float(x[4]))
     for ix in turn_idxs],float)
  Js=[];pred=[];z=[];qs=[];offsets=[]
  for packet in packets:
   # record at baseline before turn index -1 or after turn index j.
   src=int(packet["source_k"]); pos=int(packet["turn_pos"])
   offset=-float(corrected[pos+1:].sum())
   p=packet["obs"];z.append(float(p["s"]));offsets.append(offset)
   h,J=s_model(lut,c["anchor_xyz"],c["robot_z"],float(x[0]),float(x[1]),
               float(x[2]+offset),c["mount_deg"],with_jac=True)
   pred.append(float(h));H=np.zeros(6);H[:3]=np.asarray(J,float);Js.append(H)
   q,_,_,_=pre_rf_q(f,case,src,p,sensor,pack,c,lut,effective_heading_offset=offset)
   qs.append(q)
  H=np.stack(Js);residual=np.array(z)-np.array(pred)
  sigma=np.array([.09/max(q,.1) for q in qs])
  hp=H[:,2];tau=math.radians(GATE_SITE_YAW_DEG)
  R=np.diag(sigma**2)+GATE_SITE_S**2*np.ones((len(z),len(z)))+tau**2*np.outer(hp,hp)
  S=H@P@H.T+R
  nis=float(residual@np.linalg.solve(S,residual))
  limit=float(chi2.ppf(BATCH_GATE_QUANTILE,len(z)))
  inflate=min(100.,max(1.,nis/limit))
  R=inflate*R;S=H@P@H.T+R
  K=np.linalg.solve(S,H@P).T
  y=K@residual
  cc=f.comps[0]
  cc.x=x+y;cc.x[2]=V.wrap(cc.x[2])
  M=np.eye(6)-K@H
  cc.P=M@P@M.T+K@R@K.T
  cc.P=(cc.P+cc.P.T)*.5
  eig=np.linalg.eigvalsh(cc.P)
  if eig.min()<-1e-9:raise FloatingPointError("Batch covariance not PSD")
  n_s_applied+=1
  return dict(batch_maha=nis,batch_R_inflation=inflate,batch_qs=[round(float(z),3) for z in qs],
              delta_meas_deg=[round(math.degrees(x),3) for x in offsets],
              batch_residual=[round(float(v),4) for v in residual],
              batch_R_offdiag=float(R[0,1]) if len(z)>1 else 0.,
              heading_change_deg=float(math.degrees(V.wrap(cc.x[2]-x[2]))),
              heading_sigma_after_deg=float(math.degrees(math.sqrt(max(cc.P[2,2],0)))))
 
 def enact(g,n_points,quality_at_checkpoint,source_k,do_joint):
  nonlocal elapsed
  cfgturn=timeline["groups"][g][n_points]
  packets=[dict(source_k=source_k,turn_pos=-1,obs=fmap[int(full.iloc[source_k].pose_id)])]
  turns=[]
  if abs(float(full.iloc[source_k].yaw_body_deg)-float(full.iloc[cfgturn[0][0]].yaw_body_deg)+5)>1e-4:
   raise AssertionError("Turn not at matching station yaw")
  for j,(ix,offset,pid) in enumerate(cfgturn):
   p=one_tick(ix)
   assert abs(float(full.iloc[ix].x)-float(full.iloc[source_k].x))<1e-8
   assert abs(float(full.iloc[ix].y)-float(full.iloc[source_k].y))<1e-8
   turns.append(ix)
   if offset==10. and j<4:
    packets.append(dict(source_k=ix,turn_pos=j,obs=p))
   if offset==20. and n_points==3 and j<4:
    packets.append(dict(source_k=ix,turn_pos=j,obs=p))
  assert len(packets)==n_points,(g,n_points,len(packets))
  if abs(float(full.iloc[turns[-1]].yaw_body_deg)-float(full.iloc[source_k].yaw_body_deg))>1e-8:
   raise AssertionError("Return heading is not nominal start")
  info=batch_probe(packets,turns) if do_joint else dict(batch_maha=None,batch_R_inflation=None,
                                  batch_qs=[],delta_meas_deg=[],batch_residual=[],
                                  batch_R_offdiag=None,heading_change_deg=0.,heading_sigma_after_deg=None)
  rec=dict(case=case,route=route,drift=level,seed=seed,arm=arm,station_g=int(g),
           physical_x=float(full.iloc[source_k].x),physical_y=float(full.iloc[source_k].y),
           trigger_quality_q=float(quality_at_checkpoint),points=n_points,
           elapsed_added_s=len(turns)*NOMINAL_DT,source_original_poseid=int(full.iloc[source_k].pose_id),
           probe_rf_pose_ids=[int(v["obs"]["pose_id"]) for v in packets],
           do_joint=bool(do_joint),**info)
  event.append(rec)
 
 for k,row in full.iterrows():
  if row.phase=="probe":continue
  normal_counter+=1
  assert int(normal.iloc[normal_counter].pose_id)==int(row.pose_id)
  ob=one_tick(k)
  q,h,J,var=pre_rf_q(f,case,k,ob,sensor,pack,c,lut)
  islow=q<THRESHOLD
  if islow:n_low+=1
  eligible=row.phase=="drive" and int(row.drive_g) in timeline["groups"]
  permit=int(row.drive_g)-lastg>=COOLDOWN_G
  forced_event=forced is not None and int(row.drive_g) in forced and eligible
  triggered_now=(arm=="F3_ACTIVE" and forced is None and islow and eligible and permit and len(triggered)<maxprobe) or forced_event
  if arm=="D_DEFAULT":
   ans=s_quality_update(f,float(ob["s"]),(float(ob["power1"]),float(ob["power2"])),h,J,q,"D_DEFAULT")
  else:
   if triggered_now:
    ans=(None,None,None,"probe_withheld")
   else:
    ans=s_quality_update(f,float(ob["s"]),(float(ob["power1"]),float(ob["power2"])),h,J,q,"E_PASSIVE")
  if ans[3]=="applied":n_s_applied+=1
  if ans[3]=="rejected":n_s_rejected+=1
  if islow and not eligible and row.phase=="drive":n_offbank_low+=1
  if triggered_now:
   lastg=int(row.drive_g)
   triggered.append(lastg)
   # The bank station is a real stop at the exact current XY; source sample time step is 0.2s.
   num=2 if arm=="F2_PAIRED" else 3
   enact(lastg,num,q,k,arm in ("F3_ACTIVE","F2_PAIRED"))
  # Always evaluate at original base-route samples, not the inserted rotations.
  x,P=f.mean_cov()
  truth=timeline["pose"][k]
  err=truth-x[:3];err[2]=V.wrap(err[2])
  pv=P[:3,:3]
  eig=np.linalg.eigvalsh(P)
  if eig.min()<-1e-9:raise FloatingPointError("v2 6x6 covariance not PSD")
  nees=float(err@np.linalg.solve(pv,err)) if np.linalg.eigvalsh(pv).min()>1e-12 else np.nan
  if float(normal.iloc[normal_counter].t_s)>=EVAL_PROGRESS_T:
   errs.append((int(normal_counter),float(err[0]),float(err[1]),float(err[2]),nees,
                float(P[2,2]),float(q),int(row.pose_id)))
  if keep_trace and (normal_counter%10==0 or triggered_now):
   record.append(dict(case=case,arm=arm,drift=level,seed=seed,base_index=normal_counter,
              original_pose_id=int(row.pose_id),t_progress=float(normal.iloc[normal_counter].t_s),
              real_elapsed_s=float(elapsed),x=float(x[0]),y=float(x[1]),yaw=float(x[2]),
              true_x=float(truth[0]),true_y=float(truth[1]),true_yaw=float(truth[2]),
              heading_error_deg=math.degrees(err[2]),pose_nees=nees,P6=json.dumps(P.tolist()),
              quality_q=q,probe_trigger=bool(triggered_now)))
 assert normal_counter+1==len(normal)
 a=np.array(errs,dtype=float)
 assert len(a)>0
 he=np.degrees(a[:,3]);pos=np.hypot(a[:,1],a[:,2]);pvar=a[:,5]
 metrics=dict(case=case,route=route,anchor=case.split("_")[1],mount_deg=int(c["mount_deg"]),drift=level,
   seed=seed,arm=arm,n_progress_matched=int(len(a)),n_normal_samples=len(normal),
   heading_rmse_deg=float(np.sqrt(np.mean(he**2))),heading_mae_deg=float(np.mean(abs(he))),
   heading_p95_deg=float(np.quantile(abs(he),.95)),pos_rmse_m=float(np.sqrt(np.mean(pos**2))),
   pose_nees_mean=float(np.nanmean(a[:,4])),pose95_coverage=float(np.nanmean(a[:,4]<=chi2.ppf(.95,3))),
   heading95_coverage=float(np.mean(abs(he)<=math.degrees(1.959963984540054*np.sqrt(pvar)))),
   real_elapsed_s=float(elapsed),n_triggered=int(len(triggered)),
   n_low_q=int(n_low),n_low_outside_station=int(n_offbank_low),n_s_updated=int(n_s_applied),
   n_s_rejected=int(n_s_rejected),trigger_station_g=json.dumps(triggered),
   full_covariance_evaluated=True,no_RF_added=True,closedloop_coverage="T10 bank only",
   error="")
 return metrics,event,record,triggered
 
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--out",type=Path,required=True)
 p.add_argument("--smoke",action="store_true")
 p.add_argument("--seeds",type=int,default=8)
 arg=p.parse_args()
 o=arg.out;o.mkdir(parents=True,exist_ok=True)
 started=time.time()
 source=static_inputs()
 problems=route_files()
 audit={"source":"frozen sensor-v2 16d22fc","case_count":7,
        "lut_sha":filehash(RUN/"LUT/hs_lut_2deg.npy"),
        "paths":{route:dict(n_T10=len(p["full"]),n_Tnone=len(p["none"]),
          n_normal=len(p["normal"]),n_valid_probe_stations=len(p["groups"]),
          max_xy_diff=p["alignment_max_xy"]) for route,p in problems.items()},
        "protocol":"5Hz persistent 6state EKF; test only T10-eligible station active probes",
        "threshold":THRESHOLD,"max_events":MAX_EVENTS,"cooldown_drive_steps":COOLDOWN_G,
        "obs_h":"original FP firstpath s; existing no-noise multipath","note":"Ideal zero-latency sample stop, no new H"}
 (o/"INPUT_ALIGNMENT.json").write_text(json.dumps(audit,indent=2))
 jobs=[("R2_aA_m0",0,0)] if arg.smoke else [(case,lev,seed)
     for case in CASES for lev in LEVELS for seed in range(arg.seeds)]
 output=[];events=[];traces=[];fail=[]
 for ni,(case,lev,seed) in enumerate(jobs,1):
  try:
   q={}
   order=["D_DEFAULT","E_PASSIVE","F3_ACTIVE","F2_PAIRED","SHAM_F3"]
   forced=None
   for arm in order:
    ret,ev,tr,gs=run_one(case,lev,seed,arm,problems,source,forced=forced if arm in ("F2_PAIRED","SHAM_F3") else None,
                          keep_trace=(seed==0 and lev==0))
    output.append(ret);events.extend(ev);traces.extend(tr)
    if arm=="F3_ACTIVE":forced=set(gs)
   key=[(x["arm"],x["n_progress_matched"]) for x in output[-5:]]
   assert len(set(v for _,v in key))==1,key
  except Exception as e:
   import traceback
   fail.append(dict(case=case,drift=lev,seed=seed,error=str(e),traceback=traceback.format_exc()))
   print("FAILED",case,lev,seed,str(e),flush=True)
   if arg.smoke:raise
  if ni%7==0 or arg.smoke:print("PROGRESS",ni,len(jobs),"elapsed",round(time.time()-started,2),flush=True)
 pd.DataFrame(output).to_csv(o/"PER_RUN_METRICS.csv",index=False)
 pd.DataFrame(events).to_csv(o/"EVENT_LOG.csv",index=False)
 pd.DataFrame(traces).to_csv(o/"REPRESENTATIVE_CONTINUOUS_P6_TRACE.csv.gz",index=False)
 (o/"FAILURES.json").write_text(json.dumps(fail,indent=2))
 if fail:raise RuntimeError(f"{len(fail)} runs failed; see FAILURES.json")
 a=pd.DataFrame(output)
 q=a.groupby("arm")[["heading_rmse_deg","pos_rmse_m","pose_nees_mean","pose95_coverage",
                     "heading95_coverage","n_triggered","real_elapsed_s"]].agg(["mean","median"])
 q.to_csv(o/"ARM_SUMMARY.csv")
 qcase=a.groupby(["case","arm"])[["heading_rmse_deg","pos_rmse_m","pose_nees_mean",
                    "pose95_coverage","n_triggered"]].mean()
 qcase.to_csv(o/"CASE_SUMMARY.csv")
 paired=a.pivot(index=["case","drift","seed"],columns="arm",
                values=["heading_rmse_deg","pos_rmse_m","pose_nees_mean","pose95_coverage","real_elapsed_s"])
 contrasts=[]
 for arm in ["D_DEFAULT","E_PASSIVE","SHAM_F3","F2_PAIRED"]:
  for metric in ["heading_rmse_deg","pos_rmse_m","pose_nees_mean","pose95_coverage","real_elapsed_s"]:
   d=paired[(metric,"F3_ACTIVE")]-paired[(metric,arm)]
   contrasts.append(dict(contrast="F3_ACTIVE minus "+arm,metric=metric,
                         paired_n=len(d),mean_delta=float(d.mean()),
                         fraction_improved=float((d<0).mean()) if metric not in ("pose95_coverage","real_elapsed_s") else None))
 pd.DataFrame(contrasts).to_csv(o/"PAIRED_CONTRASTS.csv",index=False)
 summary={
  "status":"EXPLORATORY_EXISTING_BANK_CONTINUOUS_EKF_COMPLETED",
  "jobs":len(jobs),"num_completed_filter_runs":len(a),"failed":len(fail),
  "num_probe_events":len(events),
  "num_active_trigger_events":int(a[a.arm=="F3_ACTIVE"].n_triggered.sum()),
  "n_active_runs_zero_probes":int((a[a.arm=="F3_ACTIVE"].n_triggered==0).sum()),
  "n_eval_base_steps_per_case":dict(a[a.arm=="D_DEFAULT"].groupby("case").n_progress_matched.first()),
  "source":"sensor-v2 frozen native v2 filter, existing T10 bank, out-of-route DPK q",
  "primary_full_route_not_offline":True,"ideal_station_stop":True,
  "mount45_missing_five_cases":True,"arbitrary_triggered_XY_not_supported":True,
  "actual_both_port_CIR_trigger":"NOT_TESTED_THIS_PILOT",
  "full_RF_noise_added":False,
  "Q_sensor_is_realized":"gyro/wheel slip at every actual emitted timestep; no unmodeled stop latency",
  "F01_F02":"OPEN","scientific_PASS":False,"elapsed_s":time.time()-started,
  "arm_summary":json.loads(a.groupby("arm")[["heading_rmse_deg","pos_rmse_m",
    "pose_nees_mean","pose95_coverage","n_triggered","real_elapsed_s"]].mean().reset_index().to_json(orient="records"))
 }
 (o/"PILOT_STATUS.json").write_text(json.dumps(summary,indent=2))
 with (o/"SUMMARY_KO.md").open("w",encoding="utf-8") as f:
  f.write("# 기존 RF bank 기반 연속 Sensor-v2 EKF + 조건부 제자리 프로브 실행 결과\n\n")
  f.write("정상 주행 5Hz EKF는 모든 retained step에서 구동. 원본 T10의 제자리 회전 관측 2/3점을 low-confidence checkpoint에서만 삽입. Probe 갱신 후 모든 이후 filter step에 상태/P6 유지. Source RF 신호는 기존 7케이스 noise-free full H이고 gyro/wheel에는 원 sensor-v2 drift/noise/slip이 포함됨.\n\n")
  f.write("**bounded bank**: R2 18, R4 10, R5 26 잠재 probe 위치, 자유로운 임의 trigger 좌표 테스트는 아님. Sample-boundary 즉시 정지 가정, 실제 decel/settle 없음. 각 반복은 route progress로 paired, 시간은 probe 시간 포함. F2/SHAM은 F3 발동 station 일정 고정. 멀티각 R 및 gyro relative angle 오차 모델은 calibration 미완료.\n\n")
  f.write("## Main per-run mean\n\n")
  f.write(a.groupby("arm")[["heading_rmse_deg","pos_rmse_m","pose_nees_mean","pose95_coverage",
                  "heading95_coverage","n_triggered","real_elapsed_s"]].mean().to_markdown())
  f.write("\n\n## Case × arm means\n\n")
  f.write(qcase.to_markdown())
  f.write("\n\n## F3 paired contrasts\n\n")
  f.write(pd.DataFrame(contrasts).to_markdown(index=False))
  f.write("\n\nF01/F02 OPEN; no physical uncertainty calibration or cross-geometry transfer. Original future 06/08/09 simulation still required for mount balance, detector generalization and physical stop model.\n")
 print("ACTIVE_PROBE_RESULT",json.dumps(summary,allow_nan=False),flush=True)
 
if __name__=="__main__":main()
