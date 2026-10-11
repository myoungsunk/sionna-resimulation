#!/usr/bin/env python3
"""Reconstruct cross-time P6 from F/G/Q + applied Kalman gains, compare to
independent sensor+RF noise MC on SAME archived Sionna full channel.

Scope: one original R2-A-m0 T10 station [0,+10,+20] body orientations,
continuous Sensor-v2 range-only EKF, repeated N independent seeds.
NO new ray tracing or independent geometry. No final scientific calibration.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
BLOCK=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
ROUTES=ROOT/"results/DRIVE_SIM_20261007/S1/routes"
import sys
sys.path.insert(0,str(RUN/"source/src"))
from qclean_uwb.drivesim import sensor_v2 as V, filter_v2 as F, observation as O
from qclean_uwb.drivesim.filters import FilterConfig

CASE="R2_aA_m0"
G=50;SNR=30.
def cov2(a,b):
 a=np.asarray(a,float);b=np.asarray(b,float)
 ca=a-a.mean(axis=0);cb=b-b.mean(axis=0)
 return np.einsum("ni,nj->ij",ca,cb)/(len(a)-1)
def basic_context():
 full=pd.read_csv(ROUTES/"timeline_R2_T10.csv")
 g=full[(full.drive_g==G)]
 i0=int(g[g.phase=="drive"].index[0])
 i1=int(g[(g.phase=="probe")&(np.isclose(g.probe_offset_deg,10))].index[0])
 i2=int(g[(g.phase=="probe")&(np.isclose(g.probe_offset_deg,20))].index[0])
 assert i0<i1<i2
 time=full.t_s.to_numpy(float)
 true=full[["x","y","yaw_body_deg"]].to_numpy(float)
 true[:,2]=np.radians(true[:,2])
 ds,dth=V.motion_increments(time,true,convention="legacy-euler",tolerance=1e-8)
 indices=(i0,i1,i2)
 H=np.load(BLOCK/"FULL_RF"/f"H_{CASE}.npy",mmap_mode="r")
 freq=np.load(BLOCK/"freqs_hz.npy")
 truthlabels=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
 truthlabels=truthlabels[truthlabels.case==CASE].set_index("pose_id")
 params=json.loads((RUN/"LUT/hs_lut_meta.json").read_text())
 offset=float(params["range_bias"]["mean_m"])
 c=json.loads((BLOCK/"CASES.json").read_text())
 c=next(z for z in c if z["case"]==CASE)
 return full,time,true,ds,dth,indices,H,freq,truthlabels,offset,c

def seed_run(seed,ctx):
 full,time,true,ds,dth,indices,H,freq,truthlabels,offset,c=ctx
 last=indices[-1]
 inputs,evals=V.generate(time,ds,dth,V.SensorV2Config(level=1,condition="all"),seed)
 initial=np.r_[true[0].copy(),0.,0.,0.]
 cfg=FilterConfig(model_version="sensor-v2",kind="ekf",s_mode="direct",use_s=False,
    use_range=True,anchor_xyz=tuple(c["anchor_xyz"]),mount_deg=float(c["mount_deg"]),
    robot_z=float(c["robot_z"]),bias_rw_std=0.,known_wheelbase_error=0.,
    range_offset=offset)
 initial[:3]+=V.rng(seed,"initial").normal(size=3)*np.asarray(cfg.p0_std[:3])
 filt=F.SensorV2Filter(cfg,None,initial)
 nvar=O.noise_var_from_snr(SNR)
 rng=np.random.default_rng([20261011,int(seed),715])
 obs=O.observe(np.asarray(H[:last+1]),freq,nvar,rng,tx=0)
 assert obs["s"].shape==(last+1,)
 mode_parameters=dict(zip([str(s) for s in evals["parameter_names"]],
                            evals["true_parameters"]))
 all_A=[]
 snapshots=[]
 pkts=[]
 sensor_R=float(cfg.range_sigma**2+cfg.range_quant_var+cfg.range_extra_sigma**2)
 for k in range(last+1):
  if k:
   xp=filt.comps[0].x.copy();PP=filt.comps[0].P.copy()
   r=filt.step(float(inputs["ds_odom"][k]),float(inputs["dtheta_gyro"][k]),
       float(inputs["dtheta_odom"][k]),float(inputs["dt_s"][k]))
   FF,GG,QQ,hh,C=np.array(r["F"]),np.array(r["G"]),np.array(r["Q"]),np.array(r["H"]),np.array(r["C"])
   pp=FF@PP@FF.T+GG@QQ@GG.T
   if r["status"]=="applied":
    kk=(pp@hh+C)/float(r["S"])
    A_odom=FF-np.outer(kk,hh) # H is wrt PRE-step x, not predicted x.
   else:A_odom=FF
  else:A_odom=np.eye(6)
  kkR=np.zeros(6);Hr=np.zeros(6)
  # Save predicted R Kalman operator before scalar update.
  if bool(obs["detected"][k]) and np.isfinite(obs["range_m"][k]):
   xr=filt.comps[0].x;Pr=filt.comps[0].P.copy()
   dd=math.sqrt((xr[0]-c["anchor_xyz"][0])**2+
       (xr[1]-c["anchor_xyz"][1])**2+(c["anchor_xyz"][2]-c["robot_z"])**2)
   Hr[:2]=(xr[:2]-np.asarray(c["anchor_xyz"][:2]))/dd
   Sr=float(Hr@Pr@Hr+sensor_R)
   y=float(obs["range_m"][k]-dd-offset)
   if y*y/Sr<=cfg.gate: kkR=Pr@Hr/Sr
   result=filt.range_record(float(obs["range_m"][k]))
   if (result[3]=="applied") != bool(np.linalg.norm(kkR)>0):
    raise AssertionError("range K/gating mismatch")
  A_step=(np.eye(6)-np.outer(kkR,Hr))@A_odom
  all_A.append(A_step)
  if k in indices:
   est,P=filt.mean_cov()
   true6=np.r_[true[k],float(evals["true_bias_rad_s"][k]),
          float(mode_parameters["gyro_sf"]),float(mode_parameters["wheel_asymmetry"])]
   e=true6-est
   e[2]=V.wrap(e[2])
   ii=int(full.iloc[k].pose_id)
   lab=truthlabels.loc[ii]
   vr=float(obs["range_m"][k]-lab.true_distance_m-offset)
   vs=float(obs["s"][k]-lab.s_lut_truth)
   snapshots.append(dict(k=k,e=e,P=P.copy(),K_r=kkR.copy(),R_model=sensor_R,
      vr=vr,vs=vs,s=float(obs["s"][k]),z_range=float(obs["range_m"][k]),
      true_range=float(lab.true_distance_m),H_r=Hr.copy(),
      estimated_pose=est[:3].copy(),true_pose=true[k].copy()))
  if k>last:break
 if len(snapshots)!=3:raise RuntimeError("missing probe snapshots")
 predicted={}
 for i in range(3):
  for j in range(i,3):
   mat=np.eye(6)
   for t in range(indices[i]+1,indices[j]+1):mat=all_A[t]@mat
   predicted[f"{i}:{j}"]=snapshots[i]["P"]@mat.T
 return snapshots,predicted

def run():
 ap=argparse.ArgumentParser()
 ap.add_argument("--out",required=True,type=Path)
 ap.add_argument("--seeds",type=int,default=128)
 arg=ap.parse_args()
 o=arg.out;o.mkdir(parents=True,exist_ok=True)
 context_=basic_context();idx=context_[5]
 snaps=[];theory=[]
 for seed in range(arg.seeds):
  v,p=seed_run(seed,context_)
  snaps.append(v);theory.append(p)
  if (seed+1)%32==0:print("MC_PROGRESS",seed+1,arg.seeds,flush=True)
 errors=np.array([[s["e"] for s in z] for z in snaps]) # [seed,3,6]
 P_i=np.array([[s["P"] for s in z] for z in snaps])
 radio=np.array([[s["vr"],s["vs"]] for z in snaps for s in z]).reshape(arg.seeds,3,2)
 tab=[];preds={}
 for i in range(3):
  for j in range(i,3):
   Cemp=cov2(errors[:,i,:],errors[:,j,:])
   Cmse=errors[:,i,:].T@errors[:,j,:]/len(errors)
   Cpred=np.mean(np.stack([q[f"{i}:{j}"] for q in theory]),axis=0)
   den=max(float(np.linalg.norm(Cpred[:3,:3])),1e-12)
   tab.append(dict(i=i,j=j,n_seed=arg.seeds,dt_s=float(context_[1][idx[j]]-context_[1][idx[i]]),
       pred_cross_psi_psi=float(Cpred[2,2]),
       emp_centered_cross_psi_psi=float(Cemp[2,2]),
       emp_MSE_cross_psi_psi=float(Cmse[2,2]),
       pred_cross_xy_trace=float(np.trace(Cpred[:2,:2])),
       emp_centered_cross_xy_trace=float(np.trace(Cemp[:2,:2])),
       emp_MSE_cross_xy_trace=float(np.trace(Cmse[:2,:2])),
       relative_Frobenius_pose_centered=float(np.linalg.norm(Cemp[:3,:3]-Cpred[:3,:3])/den),
       relative_Frobenius_pose_MSE=float(np.linalg.norm(Cmse[:3,:3]-Cpred[:3,:3])/den),
       mean_pose_bias_norm_m=float(np.linalg.norm(errors[:,j,:2].mean(axis=0)))))
   preds[f"{i}:{j}"]=dict(
       theoretical=np.asarray(Cpred).tolist(),
       empirical_centered=np.asarray(Cemp).tolist(),
       empirical_MSE=np.asarray(Cmse).tolist())
 df=pd.DataFrame(tab);df.to_csv(o/"POSE_P6_CROSS_TIME_THEORY_VS_MC.csv",index=False)
 rv=[]
 for mode in ("range","polarization"):
  iidx=0 if mode=="range" else 1
  arr=radio[:,:,iidx]
  means=arr.mean(axis=0)
  c=np.cov(arr,rowvar=False,ddof=1)
  for i in range(3):
   for j in range(3):
    rv.append(dict(variable=mode,i=i,j=j,mean_i=float(means[i]),
        empirical_centered_cov=float(c[i,j]),
        empirical_correlation=float(np.corrcoef(arr,rowvar=False)[i,j]) if np.std(arr[:,i])>1e-14 and np.std(arr[:,j])>1e-14 else None,
        n_independent_thermal_streams=arg.seeds))
 pd.DataFrame(rv).to_csv(o/"THREE_YAW_THERMAL_ENSEMBLE_COV.csv",index=False)
 sx=[]
 for i in range(3):
  for j in range(3):
   for v,lab in enumerate(("range","polarization")):
    cc=cov2(errors[:,i,:],radio[:,j,v:v+1])
    sx.append(dict(state_time_i=i,rf_time_j=j,rf_type=lab,
                   n_seed=arg.seeds,
                   empirical_crosscov_x=float(cc[0,0]),
                   empirical_crosscov_y=float(cc[1,0]),
                   empirical_crosscov_heading_rad=float(cc[2,0]),
                   empirical_crosscov_bg=float(cc[3,0])))
 pd.DataFrame(sx).to_csv(o/"EMPIRICAL_STATE_RF_CROSS_TIME_MC.csv",index=False)
 info=dict(status="EXPLORATORY_CROSS_TIME_MC_EXECUTED",
       case=CASE,station_drive_g=G,snr_nominal_db=SNR,
       n_independent_sensor_and_receiver_seed=arg.seeds,
       saved_time_index=list(idx),
       saved_time_s=[float(context_[1][k]) for k in idx],
       mode="range-only original sensor-v2; no s assimilated; 3 yaw snapshots",
       input_rf="original archived full complex H; NO new Sionna solver",
       source_cov="original F/G/Q plus odom/range effective Kalman gains after each step",
       predicted_cov_assumption="independent linearized zero-mean innovations; no RF site bias state",
       empirical_cov_definition="centered Monte Carlo across independent seeded sensor/thermal streams at same fixed physical trajectory",
       empirical_mse_definition="uncentered errors include deterministic RF-induced mean bias",
       limitations=[
        "One RF setting, one station, one corridor, no cross-scene validation",
        "Original T10 0.2-s physical yaw ideal trajectory, motor slip not physical",
        "Full range+s joint batch, position-RF cross modality and site latent model not re-evaluated",
        "True gyro calibration parameter prior differs from Gaussian approximation and drives may be biased",
        "No nominal q_site/site bias uncertainty calibrated",
        "Centering across seeds can remove fixed but harmful RF bias, compare uncentered MSE"],
       per_pair=json.loads(df.to_json(orient="records")),
       model_range_sigma_m=float(math.sqrt(snaps[0][0]["R_model"])))
 (o/"STATUS.json").write_text(json.dumps(info,indent=2,allow_nan=False))
 (o/"POSE_6X6_MATRIX.json").write_text(json.dumps(preds))
 with (o/"REPORT_KO.md").open("w") as f:
  f.write("# 기존 RF H의 여러 독립 Sensor-v2/receiver seed에 대한 3각 시점 간 P6 교차공분산 검증\n\n")
  f.write(f"Existing R2-A-m0 T10 g={G}, exact 3 yaw packet time indexes {idx}, N={arg.seeds} independent sensor/thermal seeds, receiver nominal SNR {SNR}dB. Used full F/G/Q and applied correlated odometry gain, plus range gain; no new raytracing.\n\n")
  f.write(df.to_markdown(index=False,floatfmt=".6f"))
  f.write("\n\n주의: 이는 1 station의 조건부 검증이며 수신 site multipath bias의 169-site 분포를 다시 sampling한 실험이 아닙니다. Centered covariance가 predicted P와 일치해도 fixed site bias 때문에 uncentered MSE와 full-route NEES는 나쁠 수 있습니다.\n")
 print("CROSS_TIME_RESULT",json.dumps({"nseed":arg.seeds,"summary":df[["i","j","relative_Frobenius_pose_centered","relative_Frobenius_pose_MSE","mean_pose_bias_norm_m"]].to_dict("records"),
 "thermal_cov":rv},allow_nan=False),flush=True)
if __name__=="__main__":run()
