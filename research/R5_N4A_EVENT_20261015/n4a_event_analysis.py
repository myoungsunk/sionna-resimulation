"""N4-A2 focused extreme-event forensic test (read-only, no model training).

Pinned inputs: N1 L0/L1/L2 recursive x/P/status, N4-A Schur audit,
B0 physical R_G5/MU_G5 packet predictions, and original paired LoS/Full RF.

Focus: when/why the conditional XY *small eigen-axis* contributes enormous
NEES, and whether it coincides with Range/s innovations, signed RF model
mismatch, Jacobian-projected Kalman corrections, and differing gate decisions.

This is event-selected, within-trajectory evidence; NOT proof of temporal
causality or held-out prediction. All local counterfactuals start from the
same archived prior, with no recursive propagation or hindsight fit.
"""
from __future__ import annotations
import argparse, ast, csv, gzip, hashlib, io, json, math, os, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
N4A = ROOT / "research/R5_N4A_NEES_20261015"
R2 = ROOT / "research/EKF4_RANGE_S_STAGED_20261014"
UWB = ROOT / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"

ARCHIVE_SHA = {
 "RF":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "N1":"b633d0af900f26ab7d5a42c905adcb4abc01e5b262a154c774d10d5740fbaa40",
 "N4A":"83735d5551b6a70aec05874c73ac873cc9f4e09b3e45a6900f9af39098ff3ce3",
 "B0":"f31a04cf2ba39011a5d685b13985b947b1659e5b63c3a5910ec68175fa7e806a",
}
PINNED = {
 "research/R5_N4A_NEES_20261015/n4a_nees_rootcause.py":"f51b84ea3e02d1282f8a25277cd4842b1bbb738a",
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/R5_N0_N3_20261015/n1_bias_policies.py":"4ac2ca823dc7475a4330396042ef3084fda6bdf5",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9"
}
CASES=("R2_aA_m0","R2_aA_m45")
BIAS=("L0","L1","L2")
METHODS=("R0_J4","SOFT_G5_MEAN_RS")
ALL_QUALITY_METHODS=("R0_J4","SOFT_G5_RS","SOFT_G5_MEAN","SOFT_G5_MEAN_RS")
CHI2_99=9.210340371976184
TARGET=("R2_aA_m0","L2","SOFT_G5_MEAN_RS")

def digest(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def blob_hash(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def write(path,data):
 Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
                       encoding="utf-8")

def preaudit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];seen={}
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("ACTIONS_REQUIRED")
 try:
  head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
  if head!=os.getenv("GITHUB_SHA"):errors.append("HEAD_SHA_MISMATCH")
 except Exception as e:
  head=None;errors.append("GIT_HEAD_ERROR:"+repr(e))
 for name,expected in PINNED.items():
  p=ROOT/name
  if not p.is_file():errors.append("MISSING_FROZEN:"+name)
  else:
   got=blob_hash(p);seen[name]=got
   if got!=expected:errors.append("PINNED_BLOB_CHANGED:"+name)
 try:ast.parse((HERE/"n4a_event_analysis.py").read_text())
 except Exception as e:errors.append("SOURCE_SYNTAX:"+repr(e))
 workflow=ROOT/".github/workflows/r5-n4a-events.yml"
 if not workflow.is_file():errors.append("WORKFLOW_MISSING")
 else:
  s=workflow.read_text()
  tokens=("n4a_event_analysis.py --phase pre",
          "n4a_event_analysis.py --phase test",
          "n4a_event_analysis.py --phase run")
  if not(all(z in s for z in tokens) and
         s.index(tokens[0])<s.index(tokens[1])<s.index(tokens[2]) and
         "if: always()" in s and "actions: read" in s):
   errors.append("AUDIT_FIRST_WORKFLOW_CONTRACT")
 rec={"stage":"N4-A-event","decision":"GO" if not errors else "HOLD",
      "git_sha":head,"original_blobs":seen,
      "input_zip_sha256":ARCHIVE_SHA,"errors":errors,"scientific_PASS":False}
 write(out/"PRE_AUDIT.json",rec)
 print("N4AE_PRE "+json.dumps({"decision":rec["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2

def checked(path,key):
 got=digest(path)
 if got!=ARCHIVE_SHA[key]:raise RuntimeError("ARCHIVE_SHA_MISMATCH:"+key+" "+got)
 z=zipfile.ZipFile(path);bad=z.testzip()
 if bad:raise RuntimeError("ARCHIVE_CRC_FAIL:"+key+"/"+bad)
 return z

def member(z,name):
 found=[p for p in z.namelist() if p==name or p.endswith("/"+name)]
 if len(found)!=1:raise RuntimeError("ARCHIVE_MEMBER_NOT_UNIQUE:"+name+" "+str(len(found)))
 return found[0]

def load_npz(z,name,np):
 with np.load(io.BytesIO(z.read(member(z,name))),allow_pickle=False) as d:
  return {k:d[k].copy() for k in d.files}

def load_csv(z,name):
 return list(csv.DictReader(io.StringIO(z.read(member(z,name)).decode("utf-8"))))

def export(path,rows):
 if not rows:raise RuntimeError("EMPTY_EXPORT:"+str(path))
 with Path(path).open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]))
  w.writeheader();w.writerows(rows)

def vsummary(np,x):
 x=np.asarray(x,dtype=float)
 return {"mean":float(np.mean(x)),"median":float(np.median(x)),
         "p90":float(np.quantile(x,.90)),
         "p95":float(np.quantile(x,.95)),
         "max":float(np.max(x))}

def episodes(np,t,selected,max_count=6):
 ids=np.flatnonzero(selected)
 groups=[]
 for k in ids:
  if not groups or int(k)-groups[-1][-1]>2:groups.append([int(k)])
  else:groups[-1].append(int(k))
 return groups

def import_models():
 import numpy as np
 sys.path[:0]=[str(N4A),str(R2),str(UWB)]
 from n4a_nees_rootcause import decompose
 from r2_bias_replay import build_positive_bias_controls,predict_one
 from p3_rf_adapter4 import FrozenLut,R0
 from core import gaussian_update
 return np,decompose,build_positive_bias_controls,predict_one,FrozenLut,R0,gaussian_update

def axis_quantities(np,X,P,gt,prior,H,nu,R,accepted,decompose):
 """Project two joint innovation gain components on posterior conditional XY axis."""
 d=decompose(np,X[None],P[None],gt[None])[0] if False else decompose(
      np,X[None],P[None],gt[None])
 econd=d["err_xy_cond"][0]
 v=P[2,2];beta=P[:2,2]/v
 pc=P[:2,:2]-np.outer(P[:2,2],P[:2,2])/v
 eigval,U=np.linalg.eigh(pc)
 u=U[:,0]
 if float(u@econd)<0:u=-u
 projection=float(u@econd)
 # all angles from fixed (x,y) axes, not robot body orientation
 orientation=float(math.degrees(math.atan2(float(u[1]),float(u[0]))))
 hP=H@prior[1]@H.T+R
 K=np.linalg.solve(hP,(prior[1]@H.T).T).T
 predicted_step=K@nu
 gain_u=np.array([float(u@(K[:2,i]-beta*K[2,i])) for i in range(2)])
 contribution=gain_u*nu
 actual_step=X-prior[0]
 actual_step[2]=float((actual_step[2]+np.pi)%(2*np.pi)-np.pi)
 unit=math.sqrt(eigval[0])
 if accepted and np.max(abs(actual_step-predicted_step))>5e-6:
  raise RuntimeError("JOINT_UPDATE_NOT_EQUAL_GAIN_NU:"+str(np.max(abs(actual_step-predicted_step))))
 if not accepted and np.max(abs(actual_step))>1e-6:
  raise RuntimeError("REJECTED_RF_MODIFIED_STATE")
 nis=float(nu@np.linalg.solve(hP,nu))
 return {
  "axis_angle_deg":orientation,"axis_u_x":float(u[0]),"axis_u_y":float(u[1]),
  "small_axis_econd_projection_m":projection,
  "small_axis_normalized_error":float(projection/unit),
  "small_axis_variance_m2":float(eigval[0]),
  "large_axis_variance_m2":float(eigval[1]),
  "small_axis_nees":float(projection**2/eigval[0]),
  "small_axis_gain_contrib_range_m":float(contribution[0]),
  "small_axis_gain_contrib_s_m":float(contribution[1]),
  "small_axis_gain_per_range_m_per_m":float(gain_u[0]),
  "small_axis_gain_per_s_m":float(gain_u[1]),
  "small_axis_predicted_update_m":float(contribution.sum()),
  "kalman_heading_contrib_range_deg":float(math.degrees(K[2,0]*nu[0])),
  "kalman_heading_contrib_s_deg":float(math.degrees(K[2,1]*nu[1])),
  "kalman_bias_contrib_range_dps":float(math.degrees(K[3,0]*nu[0])),
  "kalman_bias_contrib_s_dps":float(math.degrees(K[3,1]*nu[1])),
  "joint_NIS_recomputed":nis,
  "marginal_norm_innov_range":float(nu[0]/math.sqrt(hP[0,0])),
  "marginal_norm_innov_s":float(nu[1]/math.sqrt(hP[1,1])),
  "post_pose_nees":float(d["pose_nees"][0]),
  "post_heading_nees":float(d["heading_nees"][0]),
  "post_xy_cond_nees":float(d["conditional_xy_nees"][0])
 }

def local_arms(np,xprior,Pprior,obs,mean,rs,gt,lut,case,R0,gaussian_update,decompose):
 # Four alternative *current packet only* updates from the SAME saved prior.
 # The posterior is never propagated; useful for mechanistic discrimination.
 def model(x):return lut.model(x,case)
 options=(("NO_RF",None,None),
          ("RAW_R0",obs,R0),
          ("MEAN_R0",obs-np.array([0.,mean]),R0),
          ("MEAN_G5_RS",obs-np.array([0.,mean]),np.diag([R0[0,0],rs])))
 out=[]
 for label,z,R in options:
  if z is None:
   x=xprior.copy();P=Pprior.copy();status=False;nis=None
  else:
   x,P,diag=gaussian_update(xprior,Pprior,z,model,R,gate_threshold=CHI2_99)
   status=bool(diag["accepted"]);nis=float(diag["NIS"])
  d=decompose(np,x[None],P[None],gt[None])
  out.append({"policy":label,"accepted":status,"nis":nis,
     "pose_nees":float(d["pose_nees"][0]),
     "heading_nees":float(d["heading_nees"][0]),
     "xy_cond_nees":float(d["conditional_xy_nees"][0]),
     "small_axis_nees":float(d["conditional_xy_first_eigen_nees"][0]),
     "small_axis_variance_m2":float(d["conditional_xy_eigen_small"][0]),
     "xy_cond_error_m":float(d["xy_cond_error_norm"][0]),
     "xy_rmse_instant_m":float(d["xy_error_norm"][0]),
     "heading_error_deg":float(math.degrees(d["err"][0,2]))})
 return out

def test():
 np,decompose,_,_,_,R0,gaussian_update=import_models()
 rng=np.random.default_rng(20261015)
 n=40
 M=rng.normal(size=(n,3,3))
 C=M@np.swapaxes(M,1,2)+np.eye(3)[None]*.07
 P=np.zeros((n,4,4));P[:,:3,:3]=C;P[:,3,3]=2e-4
 x=rng.normal(size=(n,4))*.025
 gt=rng.normal(size=(n,3))*.01
 d=decompose(np,x,P,gt)
 assert np.allclose(d["pose_nees"],d["heading_nees"]+d["conditional_xy_nees"],
                    atol=1e-10,rtol=1e-10)
 assert np.allclose(d["conditional_xy_nees"],d["conditional_xy_first_eigen_nees"]+
                    d["conditional_xy_second_eigen_nees"],atol=1e-10,rtol=1e-10)
 times=np.arange(12.)
 mask=np.zeros(12,dtype=bool);mask[[1,2,3,7,9,10]]=True
 assert len(episodes(np,times,mask))==2
 assert len(episodes(np,times,mask)[1])==3
 def toy(q):
  return np.array([q[0]+.1*q[1],q[2]-.02*q[0]]),np.array(
   [[1.,.1,0.,0.],[-.02,0.,1.,0.]])
 oldx=np.array([.4,.3,.02,0.])
 oldP=np.diag([.015,.022,.005,.0001])
 z=np.array([.8,.05])
 _,_,diag=gaussian_update(oldx,oldP,z,toy,R0,gate_threshold=CHI2_99)
 assert "accepted" in diag and "NIS" in diag
 print("N4AE_UNIT_PASS "+json.dumps({"spd":n,"tests":
     ["SCHUR","EIGEN","EPISODE_DEDUP","GAIN_CONTRACT","GATE_CONTRACT"]}),flush=True)
 return 0

def run(out,receipt_path,rawpath,n1path,n4apath,b0path):
 (np,decompose,build_positive_bias_controls,predict_one,
     FrozenLut,R0,gaussian_update)=import_models()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 receipt=json.loads(Path(receipt_path).read_text())
 if receipt["decision"]!="GO" or receipt["git_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("PREAUDIT_NOT_GO")
 lut=FrozenLut(ROOT)
 meta=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cases={v["id"]:v for v in meta["cases"]}
 allrows=[];mismatches=[];source_count=0
 with checked(rawpath,"RF") as zr,checked(n1path,"N1") as zn,checked(n4apath,"N4A") as za,checked(b0path,"B0") as zb:
  oldreceipt=json.loads(za.read(member(za,"N4A_FINAL.json")))
  n1receipt=json.loads(zn.read(member(zn,"N1_FINAL.json")))
  if oldreceipt.get("status")!="N4A_ARCHIVED_POSE_NEES_DECOMPOSITION_COMPLETE":
   raise RuntimeError("N4A_NOT_PASS")
  if n1receipt.get("status")!="N1_BIAS_EXTENDED_TECHNICAL_PASS":
   raise RuntimeError("N1_NOT_PASS")
  topprevious=load_csv(za,"N4A_TOP_EVENTS.csv")
  orig={(x["case"],x["channel"]):x for x in
       json.loads(zr.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  base={}
  for case in CASES:
   b0=load_npz(zb,f"{case}_full_B0_HARD_SOFT.npz",np)
   if "R_G5" not in b0 or "MU_G5" not in b0:raise RuntimeError("B0_QUALITY_FIELDS_MISSING")
   for channel in ("full","los"):
    rec=orig[(case,channel)]
    raw=zr.read("P2_OUT/"+rec["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=rec["trace_sha256"]:
     raise RuntimeError("ORIGINAL_RF_TRACE_SHA_FAILED")
    with np.load(io.BytesIO(raw),allow_pickle=False) as v:
     base[(case,channel)]={k:v[k].copy() for k in
      ("t_s","pose_id","truth_for_offline_scoring_only","z_r_m","z_s")}
   for name in ("t_s","pose_id","truth_for_offline_scoring_only"):
    if not np.array_equal(base[(case,"full")][name],base[(case,"los")][name]):
     raise RuntimeError("PAIRED_LOS_FULL_TRACE_MISMATCH:"+case+"/"+name)
   for level in BIAS:
    pack=load_npz(zn,f"N1_{case}_full_{level}.npz",np)
    raw=base[(case,"full")]
    if not(np.array_equal(pack["t_s"],raw["t_s"]) and
           np.array_equal(pack["pose_id"],raw["pose_id"])):
     raise RuntimeError("N1_POSE_IDS_NOT_MATCHED")
    if len(pack["methods"])!=15 or pack["estimate"].shape!=(979,15,4):
     raise RuntimeError("N1_SHAPE_INVALID")
    if not(np.allclose(pack["risk_pbad"],b0["PBAD_G5"],rtol=1e-11,atol=1e-11) and
           np.allclose(pack["mean_bias_correction"],b0["MU_G5"],rtol=1e-11,atol=1e-11)):
     raise RuntimeError("N1_B0_PHYSICAL_QUALITY_NOT_IDENTICAL")
    quality_rs=np.asarray(b0["R_G5"],float)
    if np.any(quality_rs<R0[1,1]-1e-11) or not np.isfinite(quality_rs).all():
     raise RuntimeError("RS_QUALITY_INVALID")
    t=raw["t_s"];gt=raw["truth_for_offline_scoring_only"]
    controls,_=build_positive_bias_controls(t,gt,level,seed=0)
    names=list(pack["methods"])
    gt_ref=np.column_stack([raw["z_r_m"],raw["z_s"]])
    los=base[(case,"los")]
    true_rf_error=np.empty((len(t),2))
    for k in range(len(t)):
     predicted,_=lut.model(np.r_[gt[k,:3],0.],cases[case])
     true_rf_error[k]=gt_ref[k]-predicted
    native_mp=np.column_stack([raw["z_r_m"]-los["z_r_m"],raw["z_s"]-los["z_s"]])
    if not np.isfinite(native_mp).all():raise RuntimeError("NATIVE_FULL_LOS_DIFF_NOT_FINITE")
    for method in METHODS:
     jj=names.index(method)
     X=pack["estimate"][:,jj];P=pack["covariance"][:,jj]
     flags=pack["status"][:,jj]
     d=decompose(np,X,P,gt)
     saved_name=f"N4A_TRACE_{case}_full_{level}_{method}.csv.gz"
     with gzip.open(io.BytesIO(za.read(member(za,saved_name))),"rt",encoding="utf-8") as f:
      tr=list(csv.DictReader(f))
     if len(tr)!=979:raise RuntimeError("N4A_TRACE_FRAME_COUNT")
     for k in range(979):
      if abs(d["pose_nees"][k]-float(tr[k]["pose_nees"]))>1e-7*max(1.,d["pose_nees"][k]):
       raise RuntimeError("N4A_ARCHIVED_RECOMPUTE_PARITY:"+str((case,level,method,k)))
     source_count+=len(tr)
     for k in range(len(t)):
      xp=Pp=None
      if k:
       ds,gyro,dt=(float(controls[u][k]) for u in ("ds_odom","dtheta_gyro","dt_s"))
       xp,Pp=predict_one(X[k-1],P[k-1],ds,gyro,dt)
      else:
       xp=X[k].copy();Pp=P[k].copy()
      h,H=lut.model(xp,cases[case])
      mean=float(pack["mean_bias_correction"][k]) if method=="SOFT_G5_MEAN_RS" else 0.
      R=R0.copy()
      if method=="SOFT_G5_MEAN_RS":R[1,1]=float(quality_rs[k])
      nu=gt_ref[k]-h-np.array([0.,mean])
      applied=bool(flags[k] in ("APPLIED","JOINT"))
      rejected=bool(flags[k] in ("REJECT","JOINT_REJECT"))
      if k:
       axis=axis_quantities(np,X[k],P[k],gt[k],(xp,Pp),H,nu,R,applied,decompose)
       if (axis["joint_NIS_recomputed"]>CHI2_99+3e-5 and applied) or (
           axis["joint_NIS_recomputed"]<CHI2_99-3e-5 and rejected):
        raise RuntimeError("N4AE_RECOMPUTED_GATE_DIFFERENCE:"+str(
           (case,level,method,k,axis["joint_NIS_recomputed"],str(flags[k]))))
       prior_desc=decompose(np,xp[None],Pp[None],gt[k:k+1])
       prior_pose=float(prior_desc["pose_nees"][0])
      else:
       axis=axis_quantities(np,X[k],P[k],gt[k],(xp,Pp),H,nu,R,False,decompose)
       prior_pose=None
      allrows.append({
       "case":case,"channel":"full","bias_level":level,"method":method,
       "k":k,"t_s":float(t[k]),"pose_id":int(raw["pose_id"][k]),
       "eval":bool(t[k]>=30),"gate_status":str(flags[k]),"gate_accepted":applied,
       "rf_model_error_r_GT_m":float(true_rf_error[k,0]),
       "rf_model_error_s_GT":float(true_rf_error[k,1]),
       "native_full_minus_los_r_m":float(native_mp[k,0]),
       "native_full_minus_los_s":float(native_mp[k,1]),
       "range_innovation_m":float(nu[0]),
       "pol_innovation_s":float(nu[1]),
       "pol_mean_correction":mean,"pol_R_variance":float(R[1,1]),
       "risk_pbad_G5":float(pack["risk_pbad"][k]),
       "H_s_psi_per_rad":float(H[1,2]),
       "prior_pose_nees":prior_pose,
       "post_minus_prior_nees":float(d["pose_nees"][k]-prior_pose) if prior_pose is not None else None,
       **axis
      })
  target_rows=[r for r in allrows if
    (r["case"],r["bias_level"],r["method"])==TARGET]
  if len(target_rows)!=979:raise RuntimeError("TARGET_EVENT_FRAMES_NOT_979")
  values=np.array([r["post_pose_nees"] for r in target_rows])
  time=np.array([r["t_s"] for r in target_rows])
  evalmask=time>=30
  cutoff=float(np.quantile(values[evalmask],.95))
  hot=evalmask & (values>=cutoff)
  clusters=episodes(np,time,hot)
  clusters=sorted(clusters,key=lambda g:float(np.max(values[g])),reverse=True)
  chosen=clusters[:6]
  event_rows=[];counterfactual=[];event_window=[]
  for rank,grp in enumerate(chosen,1):
   peak=max(grp,key=lambda k:values[k])
   start=time[grp[0]];end=time[grp[-1]]
   event_rows.append({"event_rank":rank,"case":TARGET[0],
     "method":TARGET[2],"bias_level":TARGET[1],
     "k_peak":int(peak),"peak_time_s":float(time[peak]),
     "peak_pose_id":int(target_rows[peak]["pose_id"]),
     "peak_pose_nees":float(values[peak]),
     "peak_small_axis_nees":float(target_rows[peak]["small_axis_nees"]),
     "peak_abs_error_on_small_axis_m":float(abs(target_rows[peak]["small_axis_econd_projection_m"])),
     "peak_small_axis_variance_m2":float(target_rows[peak]["small_axis_variance_m2"]),
     "event_start_s":float(start),"event_end_s":float(end),
     "hot_frame_count":len(grp)})
   # same-prior one-step, with ZERO fitted information from extreme event GT.
   case=TARGET[0];level=TARGET[1]
   pn=load_npz(zn,f"N1_{case}_full_{level}.npz",np)
   pos=list(pn["methods"]).index("SOFT_G5_MEAN_RS")
   base_row=base[(case,"full")]
   ctl,_=build_positive_bias_controls(base_row["t_s"],
                         base_row["truth_for_offline_scoring_only"],level,seed=0)
   xp,Pp=predict_one(pn["estimate"][peak-1,pos],pn["covariance"][peak-1,pos],
                 *(float(ctl[n][peak]) for n in ("ds_odom","dtheta_gyro","dt_s")))
   g=base_row["truth_for_offline_scoring_only"][peak]
   zz=np.array([base_row["z_r_m"][peak],base_row["z_s"][peak]])
   bm=load_npz(zb,f"{case}_full_B0_HARD_SOFT.npz",np)
   outcomes=local_arms(np,xp,Pp,zz,float(bm["MU_G5"][peak]),
                       float(bm["R_G5"][peak]),g,lut,cases[case],
                       R0,gaussian_update,decompose)
   savedpost=target_rows[peak]["post_pose_nees"]
   local_target=next(z for z in outcomes if z["policy"]=="MEAN_G5_RS")
   if abs(local_target["pose_nees"]-savedpost)>1e-5*max(1,savedpost):
    raise RuntimeError("SAME_PRIOR_LOCAL_G5_UPDATE_NOT_N1:"+str((peak,savedpost,local_target)))
   for r in outcomes:
    counterfactual.append({"event_rank":rank,"t_s":float(time[peak]),
                           "pose_id":int(target_rows[peak]["pose_id"]),**r})
   for row in allrows:
    if row["eval"] and row["case"] in CASES and abs(row["t_s"]-time[peak])<=3.0:
     event_window.append({"event_rank":rank,"event_peak_time_s":float(time[peak]),**row})
  topprior=[r for r in topprevious if
    r["case"]==TARGET[0] and r["channel"]=="full" and
    r["bias_level"]==TARGET[1] and r["method"]==TARGET[2]]
  if len(topprior)!=8:raise RuntimeError("N4A_TOP_EVENT_CHECK_MISSING")
  reported={(int(r["pose_id"]),round(float(r["pose_nees"]),5)) for r in topprior}
  for prev in topprior:
   j=next((r for r in target_rows if r["pose_id"]==int(prev["pose_id"])),None)
   if j is None or abs(j["post_pose_nees"]-float(prev["pose_nees"]))>1e-7*max(1,j["post_pose_nees"]):
    raise RuntimeError("N4A_TOP_EVENT_CHECK_FAILED")
  for rank,g in enumerate(chosen,1):
   peak=max(g,key=lambda k:values[k])
   keytime=float(time[peak])
   x=[r for r in event_window if
      r["event_rank"]==rank and r["case"]==TARGET[0] and
      r["bias_level"]==TARGET[1] and abs(r["t_s"]-keytime)<=3]
   # records sorted in allrows by condition/method rather than by time; do not infer
   # temporal order from CSV. Explicit indexed times are retained.
  # Gate divergence and event association (same packet and matching time).
  selected={}
  for case in CASES:
   for lvl in BIAS:
    a={r["k"]:r for r in allrows if r["case"]==case and
       r["bias_level"]==lvl and r["method"]=="R0_J4"}
    b={r["k"]:r for r in allrows if r["case"]==case and
       r["bias_level"]==lvl and r["method"]=="SOFT_G5_MEAN_RS"}
    if len(a)!=979 or len(b)!=979:raise RuntimeError("MISSING_GATE_PAIR")
    for k in range(979):
     key=(case,lvl,k)
     ra=a[k];rb=b[k]
     if abs(ra["rf_model_error_s_GT"]-rb["rf_model_error_s_GT"])>1e-13:
      raise RuntimeError("MEASUREMENT_RESIDUAL_SHOULD_MATCH_AT_FIXED_GT")
     selected[key]={"J4":ra,"G5":rb,
         "gate_category":("BOTH" if ra["gate_accepted"] and rb["gate_accepted"]
             else "G5_ONLY" if rb["gate_accepted"]
             else "J4_ONLY" if ra["gate_accepted"] else "NEITHER")}
  conditions=[]
  for case in CASES:
   for lvl in BIAS:
    rec=[(k,selected[(case,lvl,k)]) for k in range(979)
         if selected[(case,lvl,k)]["G5"]["eval"]]
    hist={name:sum(v["gate_category"]==name for _,v in rec)
          for name in ("BOTH","G5_ONLY","J4_ONLY","NEITHER")}
    for name in hist:
     if hist[name]<0:raise RuntimeError("BAD_GATE_CATEGORY")
    conditions.append({"case":case,"bias_level":lvl,
       "n_eval":len(rec),**{key+"_gate_count":v for key,v in hist.items()},
       "G5_more_accepted":hist["G5_ONLY"]-hist["J4_ONLY"],
       "mean_G5_xy_nees":float(np.mean([v["G5"]["post_xy_cond_nees"] for k,v in rec])),
       "mean_J4_xy_nees":float(np.mean([v["J4"]["post_xy_cond_nees"] for k,v in rec]))})
  extreme_rows=[]
  for name,mask in (("EXTREME_TOP5",hot),("OTHER_EVAL",evalmask & ~hot)):
   ids=np.flatnonzero(mask)
   g=[selected[(TARGET[0],TARGET[1],int(k))] for k in ids]
   target=[p["G5"] for p in g]
   extreme_rows.append({
     "group":name,"n":len(ids),
     "mean_pose_NEES":float(np.mean([r["post_pose_nees"] for r in target])),
     "mean_small_axis_NEES":float(np.mean([r["small_axis_nees"] for r in target])),
     "median_small_eigen_lambda_m2":float(np.median([r["small_axis_variance_m2"] for r in target])),
     "median_small_axis_abs_error_m":float(np.median([abs(r["small_axis_econd_projection_m"]) for r in target])),
     "mean_abs_oracle_r_error_m":float(np.mean([abs(r["rf_model_error_r_GT_m"]) for r in target])),
     "mean_abs_oracle_s_error":float(np.mean([abs(r["rf_model_error_s_GT"]) for r in target])),
     "mean_abs_r_innovation_m":float(np.mean([abs(r["range_innovation_m"]) for r in target])),
     "mean_abs_s_innovation":float(np.mean([abs(r["pol_innovation_s"]) for r in target])),
     "mean_abs_axis_range_gain_contrib_m":float(np.mean([abs(r["small_axis_gain_contrib_range_m"]) for r in target])),
     "mean_abs_axis_s_gain_contrib_m":float(np.mean([abs(r["small_axis_gain_contrib_s_m"]) for r in target])),
     "gate_G5_only_fraction":float(np.mean([z["gate_category"]=="G5_ONLY" for z in g])),
     "gate_J4_only_fraction":float(np.mean([z["gate_category"]=="J4_ONLY" for z in g])),
     "gate_both_fraction":float(np.mean([z["gate_category"]=="BOTH" for z in g])),
     "G5_gate_accepted_fraction":float(np.mean([r["gate_accepted"] for r in target])),
   })
  # Store every selected-window row and all compact original-case diagnostics.
  export(out/"N4AE_TOP_EPISODES.csv",event_rows)
  # For the extreme onset/peak, include ground-truth RF residual,
  # innovation NIS, covariance eigenvector, and Gain projections for
  # all bias levels and Mount choices without resimulating any RF.
  peak_indices=[e["k_peak"] for e in event_rows]
  peak_telemetry=[r for r in allrows if r["k"] in peak_indices]
  export(out/"N4AE_PEAK_TELEMETRY.csv",peak_telemetry)
  export(out/"N4AE_LOCAL_SAME_PRIOR_COUNTERFACTUALS.csv",counterfactual)
  export(out/"N4AE_GATE_COUNTS.csv",conditions)
  export(out/"N4AE_EXTREME_VS_OTHER.csv",extreme_rows)
  with gzip.open(out/"N4AE_SELECTED_EVENT_WINDOWS.csv.gz",
                 "wt",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(event_window[0]))
   w.writeheader();w.writerows(event_window)
  with gzip.open(out/"N4AE_ALL_FRAME_ALIGNED_DIAGNOSTICS.csv.gz",
                 "wt",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(allrows[0]))
   w.writeheader();w.writerows(allrows)
  final={"schema":"N4A_EVENT_RANGE_POLARIZATION_GATE_EIGEN_V1",
    "status":"N4A_EVENT_ALIGNED_SOURCE_AUDIT_AND_SAME_PRIOR_TEST_PASS",
    "source_git_sha":os.getenv("GITHUB_SHA"),
    "source_counts":{"cases":2,"bias_levels":3,"methods":2,
       "full_frame_rows":len(allrows),"n4a_parity_frames":source_count,
       "selected_hot_frames":int(hot.sum()),"hot_episodes":len(clusters),
       "reported_episode_peaks":len(chosen),"event_window_rows":len(event_window)},
    "target":"Full Mount0 L2 G5 Mean+Rs",
    "top5_nees_threshold":cutoff,
    "episodes":event_rows,
    "peak_telemetry_full_mount0_L2":[{
        "method":r["method"],"k":r["k"],"time_s":r["t_s"],
        "range_innovation_m":r["range_innovation_m"],
        "pol_innovation_s":r["pol_innovation_s"],
        "rf_model_error_r_GT_m":r["rf_model_error_r_GT_m"],
        "rf_model_error_s_GT":r["rf_model_error_s_GT"],
        "native_full_minus_los_r_m":r["native_full_minus_los_r_m"],
        "native_full_minus_los_s":r["native_full_minus_los_s"],
        "g5_rs_used":r["pol_R_variance"],
        "joint_NIS":r["joint_NIS_recomputed"],
        "gate":r["gate_status"],"small_axis_lambda_m2":r["small_axis_variance_m2"],
        "small_axis_projected_error_m":r["small_axis_econd_projection_m"],
        "small_axis_nees":r["small_axis_nees"],
        "axis_gain_range_m":r["small_axis_gain_contrib_range_m"],
        "axis_gain_s_m":r["small_axis_gain_contrib_s_m"],
        "axis_angle_deg":r["axis_angle_deg"],
       } for r in peak_telemetry if r["case"]==TARGET[0] and
             r["bias_level"]=="L2"],
    "gate_difference_by_condition":conditions,
    "tail_contrasts":extreme_rows,
    "same_prior_counterfactuals":counterfactual,
    "underlying_N4A_archive_sha256":ARCHIVE_SHA["N4A"],
    "limitations":[
      "Extreme times selected using GT-aided posterior NEES: purely retrospective; event associations are not held-out predictive accuracy",
      "Pre/post projection on posterior conditional covariance small eigenvector is a diagnostic, not a causal attribution",
      "Range/s Kalman Gain projections are joint linearized contributions, not independent physical paths",
      "One-step counterfactual comparisons share one saved G5 prior, not recursively propagated alternative policies",
      "G5 R_s and signed correction recovered from same pinned B0 physical model and parity-checked with N1",
      "Native Full-minus-LoS mismatch is not purely multipath unless FFD/LUT and first-path calibration errors are separately isolated",
      "One corridor, one gyro seed and highly correlated adjacent time samples",
    ],"physical_root_cause_fully_confirmed":False,"scientific_PASS":False}
  write(out/"N4AE_FINAL.json",final)
  print("N4AE_FINAL "+json.dumps({"status":final["status"],
     "source_counts":final["source_counts"],"events":event_rows,
     "peak_telemetry":final["peak_telemetry_full_mount0_L2"],
     "gate_counts":conditions,"tail_contrasts":extreme_rows,
     "same_prior_counterfactuals":counterfactual},ensure_ascii=False),flush=True)
  return 0

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","test","run"),required=True)
 p.add_argument("--out",required=False)
 for key in ("audit","raw","n1","n4a","b0"):p.add_argument("--"+key)
 a=p.parse_args()
 if a.phase=="pre":return preaudit(a.out)
 if a.phase=="test":return test()
 if not all((a.out,a.audit,a.raw,a.n1,a.n4a,a.b0)):
  raise RuntimeError("MISSING_PINNED_ARGUMENT")
 return run(a.out,a.audit,a.raw,a.n1,a.n4a,a.b0)

if __name__=="__main__":raise SystemExit(main())
