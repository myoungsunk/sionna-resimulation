"""Non-destructive polar-theta-zero LUT hotfix, actual frozen R2 recursion parity.
The source FFD bank has not been regenerated; this tests the documented hotfix,
not an independently rebuilt electromagnetic antenna model.
"""
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PIN={
"research/POLE_RECURSIVE_20261016/pole_lut_fix.py":"d2474fcac8bc02dc20d1bad253b6c39956412376",
"research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9"}
SHA={"rf":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
"r2":"ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399",
"n4b":"170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b",
"n4c":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9"}
CASES=["R2_aA_m0","R2_aA_m45"]
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
def hashfile(f):
 h=hashlib.sha256()
 with open(f,"rb") as g:
  for c in iter(lambda:g.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def blob(f):
 p=Path(f);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as q:
  for c in iter(lambda:q.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def save(f,o):
 p=Path(f);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False))
def zipcheck(p,expect):
 if hashfile(p)!=expect:raise RuntimeError("FROZEN_ARTIFACT_HASH_CHANGED")
 z=zipfile.ZipFile(p)
 if z.testzip():raise RuntimeError("ZIP_BAD_CRC")
 return z
def member(z,name):
 r=[q for q in z.namelist() if q==name or q.endswith("/"+name)]
 if len(r)!=1:raise RuntimeError("MISSING_OR_DUP:"+name)
 return r[0]
def audit(out):
 o=Path(out);o.mkdir(parents=True,exist_ok=False)
 errors=[];sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if sha!=os.getenv("GITHUB_SHA") or os.getenv("GITHUB_ACTIONS")!="true":errors.append("EXACT_RUN_REQUIRED")
 for file,h in PIN.items():
  p=ROOT/file
  if not p.exists():errors.append("MISSING:"+file)
  elif h.startswith("__") or blob(p)!=h:errors.append("SOURCE_CHANGED:"+file)
 try:ast.parse((HERE/"pole_recursive.py").read_text())
 except Exception as e:errors.append("SOURCE_AST_FAIL:"+str(e))
 w=(ROOT/".github/workflows/pole-recursive-check.yml").read_text()
 seq=["pole_recursive.py --phase audit","pole_recursive.py --phase test","pole_recursive.py --phase run"]
 if not all(s in w for s in seq) or not w.index(seq[0])<w.index(seq[1])<w.index(seq[2]):errors.append("AUDIT_NOT_FIRST")
 d={"decision":"GO" if not errors else "HOLD","source_sha":sha,"errors":errors,"frozen_git_blobs":PIN,"archive_hashes":SHA,
 "production_approved":False,"independent_EM_FFD_bank_regenerated":False}
 save(o/"PRE_AUDIT.json",d)
 print("POLE_AUDIT",json.dumps(d),flush=True)
 return 0 if not errors else 2
def setup():
 import numpy as np
 sys.path[:0]=[str(HERE),str(ROOT/"research/R5_N4C_20261015"),
  str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"),
  str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src")]
 import n4c_joint_sr4 as n4
 from p3_rf_adapter4 import FrozenLut
 from r2_bias_replay import build_positive_bias_controls,METHODS,predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD
 from pole_lut_fix import candidate_pole_consistent_table
 return np,n4,FrozenLut,build_positive_bias_controls,METHODS,predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD,candidate_pole_consistent_table
def test():
 np,n4,FrozenLut,*rest=setup()
 original=FrozenLut(ROOT);candidate=rest[-1](np.asarray(original.s))
 assert np.array_equal(candidate[1:],original.s[1:])
 assert not np.array_equal(candidate[0],original.s[0])
 class Lut:
  def __init__(self,s):
   self.raw=FrozenLut(ROOT);self.raw.s=s
  def model(self,x,case):return self.raw.model(x,case)
 anchor={"anchor":[4.,0.,2.65],"mount_deg":0,"robot_z_m":.45}
 # Jacobian finite differences for near-pole model state (not at exactly rho=0).
 l=Lut(candidate)
 for rho in (.025,.03839,.065):
  x=np.array([4+rho,0.017,.8,0.])
  z,H=l.model(x,anchor)
  eps=1e-5
  for k in (0,1,2):
   d=np.zeros(4);d[k]=eps
   up=l.model(x+d,anchor)[0][1];down=l.model(x-d,anchor)[0][1]
   if abs((up-down)/(2*eps)-H[1,k])>2e-3:
    raise RuntimeError("POLE_JACOBIAN_NOT_DIFFERENTIABLE")
 print("POLE_UNIT_PASS",json.dumps({"near_pole_fd_points":3,"untouched_other_theta":True}),flush=True)
 return 0
def recurse(np,n4,predict,x0,t,controls,z,quality,case,lut,method,policy):
 from r2_bias_replay import INITIAL_POSE_STD,BIAS_PRIOR_STD
 x=np.r_[x0,0.];P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 X=[];PP=[];st=[];nis=[];angular=[]
 for k in range(len(t)):
  if k:x,P=predict(x,P,float(controls["ds_odom"][k]),float(controls["dtheta_gyro"][k]),float(controls["dt_s"][k]))
  ax,ay,_=case["anchor"];rho=float(np.hypot(x[0]-ax,x[1]-ay))
  theta=math.degrees(math.atan2(rho,case["anchor"][2]-case["robot_z_m"]))
  angular.append(theta)
  x,P,status,chi,_=n4.perform_update(np,x,P,z[k],policy,quality[k],method,case,lut,"natural")
  X.append(x);PP.append(P);st.append(status);nis.append(chi)
 return {"state":np.asarray(X),"cov":np.asarray(PP),"status":np.asarray(st),"nis":np.asarray(nis),
         "robust_R_scale":np.ones(len(t)),"theta_prior_deg":np.asarray(angular)}
def run(out,auditfile,rf,r2,n4b,n4c):
 np,n4,FrozenLut,controls_fn,names,predict,_,_,fix=setup()
 o=Path(out);o.mkdir(parents=True,exist_ok=False)
 receipt=json.loads(Path(auditfile).read_text())
 if receipt["decision"]!="GO" or receipt["source_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("AUDIT_GATE_NOT_PASS")
 old=FrozenLut(ROOT);original_table=np.asarray(old.s)
 corrected=fix(original_table)
 import hashlib
 if hashfile(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy")!="711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079":
  raise RuntimeError("ORIGINAL_LUT_FILE_SHA_MISMATCH")
 # Three-way: original, direct temporary in-memory pole candidate. No mutation of on-disk LUT.
 class Candidate(FrozenLut):
  def __init__(self):
   super().__init__(ROOT);self.s=corrected
 new=Candidate()
 rows=[];parities=[];focus=[]
 with zipcheck(rf,SHA["rf"]) as zrf,zipcheck(r2,SHA["r2"]) as zr2,\
      zipcheck(n4b,SHA["n4b"]) as zb,zipcheck(n4c,SHA["n4c"]) as zc:
  import pandas as pd
  quality=n4.parse_n4b_prediction(np,pd,zb)
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  cases={c["id"]:c for c in manifest["cases"]}
  index={(v["case"],v["channel"]):v for v in json.loads(zrf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  for case in CASES:
   for channel in ("full","los"):
    src=index[(case,channel)];by=zrf.read("P2_OUT/"+src["trace_file"])
    if hashlib.sha256(by).hexdigest()!=src["trace_sha256"]:raise RuntimeError("TRACE_HASH")
    with np.load(io.BytesIO(by),allow_pickle=False) as z:
     t=z["t_s"].copy();pid=z["pose_id"].copy();truth=z["truth_for_offline_scoring_only"].copy()
     meas=np.column_stack([z["z_r_m"],z["z_s"]])
    for bias,bias_val in BIAS.items():
     controls,x0=controls_fn(t,truth,bias,seed=0)
     for method in ("J4","SR4"):
      models=("BASE_R0","POWER_JOINT") if channel=="full" else ("BASE_R0",)
      for model in models:
       q=[quality[(case,int(k))] for k in pid] if channel=="full" else [{} for _ in pid]
       runs={}
       for name,lut in (("ORIGINAL",old),("POLE_CANDIDATE",new)):
        runs[name]=recurse(np,n4,predict,x0,t,controls,meas,q,cases[case],lut,method,model)
        metric=n4.score(np,runs[name],t,truth,bias_val)
        m=t>=30
        theta=runs[name]["theta_prior_deg"]
        rows.append({"case":case,"channel":channel,"bias":bias,"method":method,
          "RF_policy":model,"lut":name,"n_near_prior_below_2_all":int((theta<2).sum()),
          "n_near_prior_below_2_scored":int(((theta<2)&m).sum()),**metric})
       dd=runs["ORIGINAL"]["state"]-runs["POLE_CANDIDATE"]["state"]
       dd[:,2]=(dd[:,2]+np.pi)%(2*np.pi)-np.pi
       focus.append({"case":case,"channel":channel,"bias":bias,"method":method,
         "RF_policy":model,"state_diff_max":float(np.max(abs(dd))),
         "P_diff_max":float(np.max(abs(runs["ORIGINAL"]["cov"]-runs["POLE_CANDIDATE"]["cov"]))),
         "gate_changes":int(np.sum(runs["ORIGINAL"]["status"]!=runs["POLE_CANDIDATE"]["status"])),
         "pole_prior_hits":int(sum(runs["ORIGINAL"]["theta_prior_deg"]<2)),
         "candidate_pole_prior_hits":int(sum(runs["POLE_CANDIDATE"]["theta_prior_deg"]<2))})
       # Original baseline parity, source artifacts.
       if model=="BASE_R0":
        with np.load(io.BytesIO(zr2.read(member(zr2,f"{case}_{channel}_{bias}_seed0_recursive.npz"))),allow_pickle=False) as f:
         i=list(names).index(method); xref=f["estimate"][:,i,:]; pref=f["covariance"][:,i,:,:];gate=(f["status"][:,i]=="APPLIED")
       else:
        with np.load(io.BytesIO(zc.read(member(zc,f"N4C_{case}_{channel}_{bias}_{method}.npz"))),allow_pickle=False) as f:
         mask=(f["policies"]=="POWER_JOINT")&(f["gate_modes"]=="natural")
         if mask.sum()!=1:raise RuntimeError("ORIGINAL_POWER_MISSING")
         i=int(np.flatnonzero(mask)[0]);xref=f["estimate"][:,i,:];pref=f["covariance"][:,i,:,:];gate=(f["status"][:,i]=="APPLIED")
       orig=runs["ORIGINAL"];dist=orig["state"]-xref;dist[:,2]=(dist[:,2]+np.pi)%(2*np.pi)-np.pi
       ex=float(np.max(abs(dist)));ep=float(np.max(abs(orig["cov"]-pref)))
       ng=int(np.sum((orig["status"]=="APPLIED")!=gate))
       if max(ex,ep)>1e-6 or ng:raise RuntimeError("ORIGINAL_REFERENCE_RECURSIVE_PARITY")
       parities.append({"case":case,"channel":channel,"bias":bias,"method":method,"policy":model,
         "max_state":ex,"max_cov":ep,"gate_changes":ng})
       if bias in ("B0","L2"):
        np.savez_compressed(o/f"POLE_{case}_{channel}_{bias}_{method}_{model}.npz",
           t=t,pose_id=pid,theta_old=runs["ORIGINAL"]["theta_prior_deg"],
           theta_new=runs["POLE_CANDIDATE"]["theta_prior_deg"],
           estimates=np.stack([runs[v]["state"] for v in ("ORIGINAL","POLE_CANDIDATE")],axis=1),
           covariances=np.stack([runs[v]["cov"] for v in ("ORIGINAL","POLE_CANDIDATE")],axis=1),
           NIS=np.stack([runs[v]["nis"] for v in ("ORIGINAL","POLE_CANDIDATE")],axis=1))
 def csvsave(fname,rr):
  with (o/fname).open("w",newline="",encoding="utf8") as f:
   w=csv.DictWriter(f,list(rr[0]));w.writeheader();w.writerows(rr)
 csvsave("POLE_ALL_RECURSIVE.csv",rows)
 csvsave("POLE_PAIR_DIFF.csv",focus)
 csvsave("POLE_ORIGINAL_PARITY.csv",parities)
 summary={"status":"POLE_R2_RECURSIVE_AUDITED","n_rows":len(rows),"n_original_parity":len(parities),
  "candidate_changes_only_theta_zero":True,"source_antenna_FFD_bank_regen":False,
  "n_nonzero_pair_differences":sum(v["state_diff_max"]>1e-10 for v in focus),
  "pair_diffs":focus,"science_final_LUT_GO":False}
 save(o/"POLE_FINAL.json",summary)
 print("POLE_FINAL",json.dumps({"status":summary["status"],"rows":len(rows),
    "parity":len(parities),"changed":summary["n_nonzero_pair_differences"],
    "nonzero":[p for p in focus if p["state_diff_max"]>1e-10]},ensure_ascii=False),flush=True)
 return 0
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("audit","test","run"),required=True)
 p.add_argument("--out");p.add_argument("--receipt");p.add_argument("--rf");p.add_argument("--r2");p.add_argument("--n4b");p.add_argument("--n4c")
 a=p.parse_args()
 return audit(a.out) if a.phase=="audit" else test() if a.phase=="test" else run(a.out,a.receipt,a.rf,a.r2,a.n4b,a.n4c)
if __name__=="__main__":raise SystemExit(main())
