"""R5-PHY B0 risk-label and pre/post RF Heading harm diagnostic.
Uses the *already completed* R5 B0 run and frozen R2 data.
Do not fit/tune on evaluation labels or modify any filter state.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
R2=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
SOURCE_SHA={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py":"24b7b0103a232662afaf5b1b79bfb542aa7123db",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"}
ORIG_RF="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
B0_RESULTS="f31a04cf2ba39011a5d685b13985b947b1659e5b63c3a5910ec68175fa7e806a"
CASES=("R2_aA_m0","R2_aA_m45")
def digest(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def blob(path):
 p=Path(path);h=hashlib.sha1()
 h.update(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def save(path,data):Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[]
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("ACTION_REQUIRED")
 rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if rev!=os.getenv("GITHUB_SHA"):errors.append("NOT_EXACT_SHA")
 for name,expected in SOURCE_SHA.items():
  p=ROOT/name
  if not p.is_file():errors.append("MISSING_SOURCE:"+name)
  elif blob(p)!=expected:errors.append("FROZEN_SOURCE_CHANGED:"+name)
 try:ast.parse((HERE/"r5_b0_risk_diagnostic.py").read_text())
 except Exception as e:errors.append("SCRIPT_SYNTAX:"+str(e))
 wf=ROOT/".github/workflows/r5-b0-rf-harm-label.yml"
 if not wf.is_file():errors.append("WF_MISSING")
 else:
  w=wf.read_text()
  one=w.find("r5_b0_risk_diagnostic.py --phase pre")
  two=w.find("r5_b0_risk_diagnostic.py --phase run")
  if not(0<=one<two and "if: always()" in w and "actions: read" in w):errors.append("WF_AUDIT_ORDER")
 record={"decision":"GO" if not errors else "HOLD","errors":errors,
    "git_sha":rev,"raw_RF_archive_sha256":ORIG_RF,
    "input_R5_B0_artifact_sha256":B0_RESULTS,
    "purpose":"offline causal-style one-step diagnostics, not policy counterfactual or calibrated Heading risk",
    "scientific_PASS":False}
 save(out/"PRE_AUDIT.json",record)
 print("R5_B0_RISK_PRE "+json.dumps({"decision":record["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2
def zmember(z,basename):
 names=[n for n in z.namelist() if n==basename or n.endswith("/"+basename)]
 if len(names)!=1:raise ValueError("ZIP_MEMBER_COUNT_"+basename+":"+str(len(names)))
 return names[0]
def get_npz(z,basename,np):
 with np.load(io.BytesIO(z.read(zmember(z,basename))),allow_pickle=False) as f:
  return {k:f[k].copy() for k in f.files}
def wrap(x):
 return (x+math.pi)%(2*math.pi)-math.pi
def checkzip(path,expected):
 if digest(path)!=expected:raise RuntimeError("ARTIFACT_SHA_MISMATCH:"+str(path))
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None:raise RuntimeError("ARTIFACT_CRC_MISMATCH")
def metric_fraction(num,den):return float(num/den) if den else None
def execute(raw_path,result_path,audit_file,out):
 import numpy as np
 from scipy.stats import spearmanr
 from sklearn.metrics import roc_auc_score,brier_score_loss
 sys.path.insert(0,str(R2))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 from r2_bias_replay import build_positive_bias_controls,predict_one
 from p3_rf_adapter4 import FrozenLut
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 receipt=json.loads(Path(audit_file).read_text())
 if receipt["decision"]!="GO" or receipt["git_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("PREAUDIT_HOLD")
 checkzip(raw_path,ORIG_RF);checkzip(result_path,B0_RESULTS)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 lookup={q["id"]:q for q in manifest["cases"]}
 lut=FrozenLut(ROOT)
 detail=[];scoring=[]
 with zipfile.ZipFile(raw_path) as zraw,zipfile.ZipFile(result_path) as zres:
  summ=json.loads(zraw.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  entries={(q["case"],q["channel"]):q for q in summ["per_case"]}
  for case in CASES:
   qdata={};obdata={}
   for ch in ("full","los"):
    row=entries[(case,ch)]
    raw=zraw.read("P2_OUT/"+row["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=row["trace_sha256"]:
     raise RuntimeError("ORIGINAL_P2_TRACE_SHA_INVALID")
    with np.load(io.BytesIO(raw),allow_pickle=False) as f:
     obdata[ch]={key:f[key].copy() for key in ("t_s","pose_id","truth_for_offline_scoring_only","z_s","z_r_m")}
    qdata[ch]=get_npz(zres,case+"_"+ch+"_B0_HARD_SOFT.npz",np)
   for key in ("t_s","pose_id","truth_for_offline_scoring_only"):
    if not np.array_equal(obdata["full"][key],obdata["los"][key]):
     raise RuntimeError("CHANNEL_ALIGNMENT_FAIL:"+case+"/"+key)
   diff=obdata["full"]["z_s"]-obdata["los"]["z_s"]
   target=np.abs(diff)>.1
   t=obdata["full"]["t_s"]
   tr=obdata["full"]["truth_for_offline_scoring_only"]
   controls,x0=build_positive_bias_controls(t,tr,"B0",0)
   for ch in ("full","los"):
    packet=obdata[ch];saved=qdata[ch]
    if not(np.array_equal(saved["t_s"],packet["t_s"]) and
           np.array_equal(saved["pose_id"],packet["pose_id"])):
     raise RuntimeError("QUALITY_PROVENANCE_MISMATCH")
    j=list(saved["methods"]).index("R0_J4")
    x=saved["estimate"][:,j];P=saved["covariance"][:,j]
    stats=saved["status"][:,j]
    quality=saved["PBAD_G5"]
    if not(np.isfinite(quality).all() and np.all((quality>=0)&(quality<=1))):
     raise RuntimeError("INVALID_QUALITY_SCORE")
    for k in range(1,len(t)):
     xp,Pp=predict_one(x[k-1],P[k-1],float(controls["ds_odom"][k]),
                      float(controls["dtheta_gyro"][k]),float(controls["dt_s"][k]))
     model,H=lut.model(xp,lookup[case])
     prior_deg=math.degrees(wrap(float(xp[2]-tr[k,2])))
     post_deg=math.degrees(wrap(float(x[k,2]-tr[k,2])))
     delta_sq=post_deg**2-prior_deg**2
     risk=float(quality[k])
     applied=bool(stats[k]=="APPLIED")
     if not applied and abs(delta_sq)>1e-9:
      raise RuntimeError("REJECTED_RF_CHANGED_HEADING")
     detail.append({
      "case":case,"channel":ch,"k":k,"pose_id":int(packet["pose_id"][k]),
      "time_s":float(t[k]),"RF_applied":applied,
      "predicted_pbad_MP_G5":risk,"highrisk_p50":risk>.5,"highrisk_p75":risk>.75,
      "oracle_MP_bad_gt0p1":bool(target[k]) if ch=="full" else False,
      "prior_heading_abs_error_deg":abs(prior_deg),
      "post_heading_abs_error_deg":abs(post_deg),
      "RF_heading_squared_error_change_deg2":float(delta_sq),
      "RF_heading_harm":bool(delta_sq>1e-10) if applied else False,
      "pre_s_innovation":float(packet["z_s"][k]-model[1]),
      "pre_s_jacobian_abs_per_rad":abs(float(H[1,2])),
      "prior_bias_abs_error_dps":abs(math.degrees(float(xp[3]))),
      "post_bias_abs_error_dps":abs(math.degrees(float(x[k,3])))
     })
    applied_mask=(stats[1:]=="APPLIED")
    if ch=="full":
     labels=target[1:]
     if not np.unique(labels).size==2:raise RuntimeError("NO_TWO_MP_CLASSES")
     auc=float(roc_auc_score(labels,quality[1:]))
     brier=float(brier_score_loss(labels,quality[1:]))
    else:
     auc=None;brier=None
    for high in (False,True):
     mask=((quality[1:]>.5)==high)
     group=[r for r in detail if r["case"]==case and r["channel"]==ch and r["highrisk_p50"]==high]
     apl=[r for r in group if r["RF_applied"]]
     bad=[r for r in apl if r["RF_heading_harm"]]
     groupcount=len(group)
     scoring.append({
      "case":case,"channel":ch,"risk_group":"P_BAD_GT_0P5" if high else "P_BAD_LE_0P5",
      "n":groupcount,"n_applied":len(apl),
      "oracle_mp_bad_fraction":float(np.mean([r["oracle_MP_bad_gt0p1"] for r in group])) if group else None,
      "observed_step_heading_harm_fraction_given_applied":metric_fraction(len(bad),len(apl)),
      "mean_signed_heading_squared_error_change_deg2_given_applied":
        float(np.mean([r["RF_heading_squared_error_change_deg2"] for r in apl])) if apl else None,
      "mean_abs_s_jacobian_per_rad":float(np.mean([r["pre_s_jacobian_abs_per_rad"] for r in group])) if group else None,
      "MP_proxy_prediction_AUROC_full_only":auc,
      "MP_proxy_Brier_full_only":brier
     })
    # User visible saved experiment feature predictions are the same held-out R2,
    # but test labels and oracle pose are ONLY supplied inside execute.
    print("R5_B0_RISK_CASE "+json.dumps({"case":case,"ch":ch,"mp_auc":auc,"mp_brier":brier,
       "q_high_frac":float(np.mean(quality[1:]>.5))}),flush=True)
 with (out/"R5_B0_ONE_STEP_HARM_OFFLINE.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(detail[0]));w.writeheader();w.writerows(detail)
 with (out/"R5_B0_RISK_GROUPS.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(scoring[0]));w.writeheader();w.writerows(scoring)
 final={"schema":"R5_B0_MP_RISK_VS_REAL_STEP_HEADING_HARM_V1",
        "status":"OFFLINE_HARM_DIAGNOSTIC_COMPLETE",
        "rows":len(detail),"risk_groups":scoring,
        "limitations":["mp classifier trained on R4/R5, checked R2 B0 only",
                       "per-step harm is diagnostic relative to original J4 trajectory, not a new gate policy counterfactual",
                       "GT yaw used only in offline scoring and prior harm labels",
                       "oracle e_MP is native LoS matched channel proxy, not an independent multipath truth",
                       "relative RF pose/covariance from original J4 only",
                       "not calibrated heading harm probability"],
        "scientific_PASS":False}
 save(out/"R5_B0_HARM_FINAL.json",final)
 print("R5_B0_RISK_FINAL "+json.dumps({"status":final["status"],"rows":len(detail),"groups":scoring}),flush=True)
 return 0
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",required=True,choices=["pre","run"])
 ap.add_argument("--out",required=True)
 ap.add_argument("--raw")
 ap.add_argument("--results")
 ap.add_argument("--audit")
 a=ap.parse_args()
 if a.phase=="pre":return pre(a.out)
 return execute(a.raw,a.results,a.audit,a.out)
if __name__=="__main__":raise SystemExit(main())
