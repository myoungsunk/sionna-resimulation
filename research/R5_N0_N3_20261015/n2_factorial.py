"""N2 factorial counterfactual: LoS/Full Range x LoS/Full dual-LP s.

One-step and recursive; original R2 predictor, 4-state J4 & SR4;
natural per-arm gate and shared E11 acceptance schedule. Mixes E10/E01
are diagnostic counterfactuals, NOT realizable joint RF channels.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
R2=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
N0_SHA="aade786b83357086c9e645fa9b87467a869289aa93040e3b48410f44af2d08fb"
CASES=("R2_aA_m0","R2_aA_m45")
LEVELS={"B0":0.,"L0":.01,"L1":.05,"L2":.2}
MIXES=("E00","E10","E01","E11")
METHODS=("J4","SR4")
MODES=("one_step","recursive")
GATES=("natural","common")
PINNED={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9"}
def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 fail=[];got={}
 if os.getenv("GITHUB_ACTIONS")!="true":fail.append("GITHUB_ONLY")
 git=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if git!=os.getenv("GITHUB_SHA"):fail.append("BAD_HEAD")
 for p,h in PINNED.items():
  f=ROOT/p
  if not f.exists():fail.append("MISSING_FROZEN:"+p)
  else:
   digest=blob(f);got[p]=digest
   if digest!=h:fail.append("FROZEN_DIFF:"+p)
 try:ast.parse((HERE/"n2_factorial.py").read_text())
 except Exception as e:fail.append("SOURCE_INVALID:"+repr(e))
 wf=ROOT/".github/workflows/r5-n0n3-n2.yml"
 if not wf.is_file():fail.append("WF_MISSING")
 else:
  w=wf.read_text()
  if not(0<=w.find("n2_factorial.py --phase pre")<w.find("n2_factorial.py --phase test")<
         w.find("n2_factorial.py --phase run") and "if: always()" in w and "actions: read" in w):
   fail.append("AUDIT_ORDER_CONTRACT_FAIL")
 receipt={"stage":"N2","decision":"GO" if not fail else "HOLD",
    "source_commit":git,"frozen_git_blobs":got,"N0_zip_sha256":N0_SHA,
    "original_RF_sha256":RF_SHA,"original_R2_sha256":R2_SHA,"errors":fail,
    "counterfactual_warning":"E10/E01 mix channels not physically joint","scientific_PASS":False}
 save(out/"N2_PRE_AUDIT.json",receipt)
 print("N2_PRE "+json.dumps({"decision":receipt["decision"],"errors":fail}),flush=True)
 return 0 if not fail else 2
def verified_zip(path,expect):
 if sha(path)!=expect:raise RuntimeError("ZIP_SHA_MISMATCH:"+str(path))
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ZIP_CRC_FAIL")
 return z
def member(z,name):
 hits=[v for v in z.namelist() if v==name or v.endswith("/"+name)]
 if len(hits)!=1:raise RuntimeError("ZIP_MEMBER_NOT_UNIQUE:"+name)
 return hits[0]
def check_n0(p):
 with verified_zip(p,N0_SHA) as z:
  d=json.loads(z.read(member(z,"N0_RECONCILIATION.json")))
  if d["status"]!="N0_SCOPED_GO_POSE_NEES_NOT_NUMERICALLY_IDENTICAL":
   raise RuntimeError("N0_NOT_SCOPED_GO")
def setup():
 import numpy as np
 sys.path.insert(0,str(R2))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 return np
def _anglewrap(x):
 return (x+math.pi)%(2*math.pi)-math.pi
def unit():
 np=setup()
 from core import gaussian_update
 from p3_rf_adapter4 import R0,GATE_JOINT
 from r2_bias_replay import filter_one
 class LinearDummy:
  @staticmethod
  def model(v,c):
   return np.array([v[0],v[2]]),np.array([[1.,0.,0.,0.],[0.,0.,1.,0.]])
 lut=LinearDummy()
 x=np.array([1.,2.,.2,.0]);P=np.diag([.2,.2,.04,.01]);z=np.array([1.1,.15])
 for method in METHODS:
  xx,pp,status,nis=filter_one(x,P,z,method,{},lut)
  if status!="APPLIED":raise AssertionError("CANARY_REJECTED")
  if np.linalg.eigvalsh(pp).min()<=0:raise AssertionError("CANARY_NOT_SPD")
  if not np.isfinite(xx).all():raise AssertionError("CANARY_NONFINITE")
 # common E11 branch matches natural linear Gaussian if accepted
 n,cp,_=gaussian_update(x,P,z,lambda q:lut.model(q,{}),R0,gate_threshold=GATE_JOINT)
 m,mp,_=gaussian_update(x,P,z,lambda q:lut.model(q,{}),R0)
 np.testing.assert_allclose(n,m,atol=1e-13,rtol=0)
 np.testing.assert_allclose(cp,mp,atol=1e-13,rtol=0)
 print("N2_UNIT_PASS "+json.dumps({"joint_and_sr4":True,"fixed_gate_parity":True}),flush=True)
 return 0
def pred_motion(t,controls,x0,np):
 from r2_bias_replay import predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD
 x=np.r_[x0,0.];P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 X=np.empty((len(t),4));C=np.empty((len(t),4,4))
 for k in range(len(t)):
  if k:x,P=predict_one(x,P,float(controls["ds_odom"][k]),
                    float(controls["dtheta_gyro"][k]),float(controls["dt_s"][k]))
  X[k]=x;C[k]=P
 return X,C
def update(x,P,z,case,lut,method,allow_gate,force_allow,np):
 from core import gaussian_update
 from p3_rf_adapter4 import R0
 from r2_bias_replay import filter_one
 if allow_gate:
  xx,pp,status,nis=filter_one(x,P,z,method,case,lut)
  return xx,pp,status=="APPLIED",nis
 if not force_allow:return x.copy(),P.copy(),False,float("nan")
 if method=="J4":
  xx,pp,diag=gaussian_update(x,P,z,lambda q:lut.model(q,case),R0)
  return xx,pp,True,float(diag["NIS"])
 def rm(q):
  h,H=lut.model(q,case);return h[:1],H[:1,:]
 def sm(q):
  h,H=lut.model(q,case);return h[1:],H[1:,:]
 xa,pa,_=gaussian_update(x,P,z[:1],rm,R0[:1,:1])
 xb,pb,_=gaussian_update(xa,pa,z[1:],sm,R0[1:,1:])
 return xb,pb,True,float("nan")
def simulate(np,t,controls,x0,obs,case,lut,method,mode,gate,
             precomputed_one=None,common_mask=None):
 from r2_bias_replay import predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD
 x=np.r_[x0,0.]
 P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 n=len(t);xx=np.empty((n,4));PP=np.empty((n,4,4))
 accepted=np.zeros(n,bool);nis=np.full(n,np.nan)
 if gate=="common" and common_mask is None:raise ValueError("COMMON_MASK_REQUIRED")
 for k in range(n):
  if mode=="one_step":
   x=precomputed_one[0][k].copy();P=precomputed_one[1][k].copy()
  elif k:
   x,P=predict_one(x,P,float(controls["ds_odom"][k]),
                        float(controls["dtheta_gyro"][k]),float(controls["dt_s"][k]))
  xa,pa,ap,niss=update(x,P,obs[k],case,lut,method,
                       allow_gate=(gate=="natural"),
                       force_allow=True if gate=="natural" else bool(common_mask[k]),np=np)
  if np.linalg.eigvalsh(pa).min()<=0 or not(np.isfinite(pa).all() and np.isfinite(xa).all()):
   raise RuntimeError("NUMERIC_STATE_INVALID:"+str((mode,gate,method,k)))
  x=xa;P=pa;xx[k]=xa;PP[k]=pa;accepted[k]=ap;nis[k]=niss
 return {"estimate":xx,"covariance":PP,"accepted":accepted,"nis":nis}
def score(np,t,truth,bias,result):
 mask=t>=30.;mu=result["estimate"][mask]
 P=result["covariance"][mask];e=mu[:,:3]-truth[mask,:3]
 e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
 h=e[:,2]**2/P[:,2,2]
 C=P[:,:3,:3]
 nees=np.einsum("bi,bi->b",e,np.linalg.solve(C,e[:,:,None])[:,:,0])
 b=mu[:,3]-math.radians(bias)
 return {"n":int(mask.sum()),
  "heading_mse_deg2":float(np.degrees(1)**2*np.mean(e[:,2]**2)),
  "heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
  "heading_signed_mean_deg":float(np.degrees(np.mean(e[:,2]))),
  "heading_nees_mean":float(h.mean()),"heading95":float(np.mean(h<=3.841458820694124)),
  "pose_mse_m2":float(np.mean(np.sum(e[:,:2]**2,axis=1))),
  "pose_nees_mean":float(nees.mean()),"pose95":float(np.mean(nees<=7.814727903251179)),
  "bias_mse_dps2":float(np.degrees(1)**2*np.mean(b*b)),
  "bias_rmse_dps":float(np.degrees(np.sqrt(np.mean(b*b)))),
  "bias_final_dps":float(np.degrees(result["estimate"][-1,3])),
  "accepted_eval":int(result["accepted"][mask].sum())}
def run(out,pre,n0,raw,r2path):
 np=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 auditdata=json.loads(Path(pre).read_text())
 if auditdata["decision"]!="GO" or auditdata["source_commit"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("AUDIT_NOT_GO")
 check_n0(n0)
 from r2_bias_replay import build_positive_bias_controls,METHODS as REF_METHODS
 from p3_rf_adapter4 import FrozenLut
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cm={c["id"]:c for c in manifest["cases"]}
 lut=FrozenLut(ROOT)
 rows=[];refcheck=[]
 with verified_zip(raw,RF_SHA) as za,verified_zip(r2path,R2_SHA) as zb:
  entries={(x["case"],x["channel"]):x for x in json.loads(za.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  for case in CASES:
   rawdata={}
   for channel in ("los","full"):
    ent=entries[(case,channel)];entry=za.read("P2_OUT/"+ent["trace_file"])
    if hashlib.sha256(entry).hexdigest()!=ent["trace_sha256"]:
     raise RuntimeError("SOURCE_TRACE_SHA_FAIL")
    with np.load(io.BytesIO(entry),allow_pickle=False) as v:
     rawdata[channel]={key:v[key].copy() for key in
        ("t_s","pose_id","truth_for_offline_scoring_only","z_s","z_r_m")}
   los=rawdata["los"];full=rawdata["full"]
   for k in ("t_s","pose_id","truth_for_offline_scoring_only"):
    if not np.array_equal(los[k],full[k]):raise RuntimeError("LOSS_FULL_NOT_PAIRED:"+k)
   t=full["t_s"];truth=full["truth_for_offline_scoring_only"]
   obs={
    "E00":np.column_stack([los["z_r_m"],los["z_s"]]),
    "E10":np.column_stack([full["z_r_m"],los["z_s"]]),
    "E01":np.column_stack([los["z_r_m"],full["z_s"]]),
    "E11":np.column_stack([full["z_r_m"],full["z_s"]])}
   for lvl,bias in LEVELS.items():
    ctrl,x0=build_positive_bias_controls(t,truth,lvl,seed=0)
    one=pred_motion(t,ctrl,x0,np)
    for mode in MODES:
     for method in METHODS:
      # E11 accepted timeline is a real J4/SR4 reference, separately per mode/method.
      primary=simulate(np,t,ctrl,x0,obs["E11"],cm[case],lut,method,mode,"natural",one)
      source_name=f"{case}_full_{lvl}_seed0_{mode}.npz"
      with np.load(io.BytesIO(zb.read(member(zb,source_name))),allow_pickle=False) as p:
       names=p["names"].tolist()
       jj=names.index(method)
       expected_x=p["estimate"][:,jj,:]
       expected_p=p["covariance"][:,jj,:,:]
       statuses=p["status"][:,jj]=="APPLIED"
      dif=primary["estimate"]-expected_x;dif[:,2]=(dif[:,2]+np.pi)%(2*np.pi)-np.pi
      max_state=float(np.max(np.abs(dif)))
      max_cov=float(np.max(np.abs(primary["covariance"]-expected_p)))
      mask_diff=int(np.sum(primary["accepted"]!=statuses))
      if max_state>1e-6 or max_cov>1e-6 or mask_diff:
       raise RuntimeError("E11_ORIGINAL_PARITY_FAIL:"+str((case,lvl,mode,method,max_state,max_cov,mask_diff)))
      refcheck.append({"case":case,"level":lvl,"mode":mode,"method":method,
         "max_state_diff":max_state,"max_cov_diff":max_cov,
         "acceptance_diff":mask_diff,"strict_1e9":bool(max(max_cov,max_state)<=1e-9)})
      for gate in GATES:
       results={}
       for mix in MIXES:
        outstate=(primary if mix=="E11" and gate=="natural" else
                  simulate(np,t,ctrl,x0,obs[mix],cm[case],lut,
                     method,mode,gate,one,common_mask=primary["accepted"]))
        results[mix]=outstate
        summary=score(np,t,truth,bias,outstate)
        rows.append({"case":case,"mount_deg":cm[case]["mount_deg"],
           "bias_level":lvl,"bias_true_dps":bias,"mode":mode,
           "method":method,"gate":gate,"mix":mix,
           "range_channel":"full" if mix[1]=="1" else "los",
           "s_channel":"full" if mix[2]=="1" else "los",
           **summary})
       xx0=results["E11"];xx1=results["E11"] if gate=="natural" else results["E11"]
       if gate=="common":
        if np.max(np.abs(xx0["estimate"]-primary["estimate"]))>1e-10:
         raise RuntimeError("COMMON_E11_NOT_ORIGINAL")
       np.savez_compressed(out/f"N2_{case}_{lvl}_{mode}_{method}_{gate}.npz",
        t_s=t,pose_id=full["pose_id"],mixes=np.asarray(MIXES),
        estimate=np.stack([results[k]["estimate"] for k in MIXES],axis=1),
        covariance=np.stack([results[k]["covariance"] for k in MIXES],axis=1),
        accepted=np.stack([results[k]["accepted"] for k in MIXES],axis=1))
      print("N2_CASE "+json.dumps({"case":case,"level":lvl,
             "mode":mode,"method":method,"accepted":int(primary["accepted"].sum())}),flush=True)
 def export(name,arr):
  with (out/name).open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(arr[0]));w.writeheader();w.writerows(arr)
 export("N2_FACTORIAL_ALL.csv",rows)
 export("N2_E11_PARITY.csv",refcheck)
 contrasts=[]
 lookup={(q["case"],q["bias_level"],q["mode"],q["method"],q["gate"],q["mix"]):q for q in rows}
 for case in CASES:
  for lvl in LEVELS:
   for mode in MODES:
    for method in METHODS:
     for gate in GATES:
      key=(case,lvl,mode,method,gate)
      data={mix:lookup[key+(mix,)] for mix in MIXES}
      record={"case":case,"level":lvl,"mode":mode,"method":method,"gate":gate}
      for metric in ("heading_mse_deg2","bias_mse_dps2","pose_mse_m2"):
       val={m:data[m][metric] for m in MIXES}
       record["range_effect_"+metric]=val["E10"]-val["E00"]
       record["s_effect_"+metric]=val["E01"]-val["E00"]
       record["interaction_"+metric]=val["E11"]-val["E10"]-val["E01"]+val["E00"]
      record.update({m+"_heading_rmse_deg":data[m]["heading_rmse_deg"] for m in MIXES})
      record.update({m+"_pose_nees":data[m]["pose_nees_mean"] for m in MIXES})
      contrasts.append(record)
 export("N2_2X2_EFFECTS.csv",contrasts)
 final={"stage":"N2","status":"N2_FACTORIAL_AUDITED_TECHNICAL_PASS",
   "rows":len(rows),"contrast_rows":len(contrasts),
   "original_E11_parity":refcheck,
   "R0_source":"Frozen LUT / original R0 unchanged",
   "common_gate_definition":"hold E11 original model acceptance timeline fixed separately per (bias,mount,mode,method)",
   "counterfactual_mix_definitions":{"E00":"r_LoS,s_LoS","E10":"r_Full,s_LoS",
     "E01":"r_LoS,s_Full","E11":"r_Full,s_Full"},
   "warnings":["E10 and E01 are not realizable RF co-measurements",
     "Gate is fixed per E11 path in common condition, not a provider-independent physical oracle",
     "Cross-time dependence remains; factorial effects are model-conditioned counterfactuals",
     "NEES/Pose coverage must be validated independently of heading MSE",
     "One corridor, one sensor seed, no independent environment"],
   "scientific_PASS":False}
 save(out/"N2_FINAL.json",final)
 print("N2_FINAL "+json.dumps({"status":final["status"],"rows":len(rows),
    "contrast_rows":len(contrasts),
    "full_recursive_joint_effects":[q for q in contrasts if
      q["mode"]=="recursive" and q["method"]=="J4" and q["gate"]=="common"]}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=("pre","test","run"))
 p.add_argument("--out");p.add_argument("--audit");p.add_argument("--n0")
 p.add_argument("--raw");p.add_argument("--r2")
 a=p.parse_args()
 raise SystemExit(audit(a.out) if a.phase=="pre" else unit() if a.phase=="test" else
  run(a.out,a.audit,a.n0,a.raw,a.r2))
