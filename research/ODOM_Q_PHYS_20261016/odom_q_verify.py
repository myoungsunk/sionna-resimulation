"""Independent read-only check of original audited ODOM-Q source and finished artifact.
Never refits or changes the original experiment. Comparisons remain single-scene pilots.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,os,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE_BLOB="71813b103077a2d5bcc3e6802fbc6e3971094606"
ARCHIVE_SHA="__ORIGINAL_ARTIFACT_SHA__"
def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for v in iter(lambda:f.read(1<<20),b""):h.update(v)
 return h.hexdigest()
def blob(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with open(p,"rb") as f:
  for v in iter(lambda:f.read(1<<20),b""):h.update(v)
 return h.hexdigest()
def store(path,obj):
 Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def member(z,name):
 names=[p for p in z.namelist() if p==name or p.endswith("/"+name)]
 if len(names)!=1:raise RuntimeError("ZIP_MEMBER_INVALID:"+name)
 return names[0]
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 e=[]
 head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
 if head!=os.getenv("GITHUB_SHA") or os.getenv("GITHUB_ACTIONS")!="true":
  e.append("HEAD_RUNNER_DIFFERENCE")
 p=ROOT/"research/ODOM_Q_PHYS_20261016/odom_q_experiment.py"
 if not p.is_file() or blob(p)!=SOURCE_BLOB:e.append("ORIGINAL_SIMULATOR_CHANGED")
 if ARCHIVE_SHA.startswith("__"):e.append("PREPARED_ARTIFACT_SHA_NOT_PINNED")
 try:ast.parse((HERE/"odom_q_verify.py").read_text())
 except Exception as ex:e.append("SELF_AST_ERROR:"+repr(ex))
 wf=ROOT/".github/workflows/odom-q-verify-v1.yml"
 if not wf.exists():e.append("WORKFLOW_MISSING")
 else:
  s=wf.read_text();a=s.find("odom_q_verify.py --phase pre")
  b=s.find("odom_q_verify.py --phase run")
  if not(0<=a<b and "if: always()" in s and "actions: read" in s):
   e.append("SOURCE_AUDIT_ORDER")
 receipt={"decision":"GO" if not e else "HOLD","original_code_blob":SOURCE_BLOB,
  "original_archive_sha":ARCHIVE_SHA,"source_sha":head,"issues":e}
 store(out/"PRE_AUDIT.json",receipt)
 print("ODOM_Q_VERIFY_PRE "+json.dumps({"decision":receipt["decision"],"issues":e}),flush=True)
 return 0 if not e else 2
def execute(out,prepath,archive):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(prepath).read_text())
 if a["decision"]!="GO" or a["source_sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("SOURCE_NOT_AUDITED")
 if sha(archive)!=ARCHIVE_SHA:raise RuntimeError("RESULT_HASH_CHANGED")
 with zipfile.ZipFile(archive) as z:
  if z.testzip():raise RuntimeError("ORIGINAL_ZIP_CRC_FAILED")
  meta=json.loads(z.read(member(z,"ODOM_Q_FINAL.json")))
  orig=json.loads(z.read(member(z,"SOURCE_AUDIT.json")))
  if orig["decision"]!="GO" or meta["status"]!=\
      "ODOM_Q_ACTUAL_GENERATOR_AND_RECURSIVE_STRESS_COMPLETE":
   raise RuntimeError("ORIGINAL_EXPERIMENT_NOT_COMPLETE")
  def read(name):
   return list(csv.DictReader(io.StringIO(z.read(member(z,name)).decode("utf8"))))
  records=read("ODOM_Q_ALL_RECURSIVE.csv")
  parity=read("ODOM_Q_SOURCE_PARITY.csv")
  mc=read("ODOM_Q_SENSOR_MC.csv")
  if len(records)!=160 or len(parity)!=48 or len(mc)!=4:
   raise RuntimeError("EVIDENCE_TABLE_ROW_COUNT:"+str((len(records),len(parity),len(mc))))
  if any(int(p["gate_differences"])!=0 or float(p["max_state"])>1e-6 or
     float(p["max_cov"])>1e-6 for p in parity):
   raise RuntimeError("FROZEN_R0_AND_POWER_SOURCE_PARITY_FAIL")
  if any(r["R0_or_POWER_R_s_changed"]!="False" for r in records):
   raise RuntimeError("NOT_FROZEN_R_MEASUREMENT_INPUT")
  if any(int(r["n"])!=829 for r in records):
   raise RuntimeError("SCORING_MASK_NOT_829")
  if any(int(r["n_seeds"])!=32 for r in mc):
   raise RuntimeError("SENSOR_INDEPENDENT_SEED_COUNT")
  for m in mc:
   if m["original_seed0_control_parity"]!="BIT_EXACT":
    raise RuntimeError("SENSOR_V2_ORIGINAL_CONTROLS_NOT_IDENTICAL")
   for k in ("wheel_std_residual_variance","gyro_std_residual_variance"):
    if not .8<float(m[k])<1.2:raise RuntimeError("MC_SENSOR_STATISTICAL_MISMATCH:"+k+":"+m["level"])
  index={(r["case"],r["channel"],r["bias"],r["solver"],r["RF_model"],r["odometry_Q"]):r for r in records}
  if len(index)!=len(records):raise RuntimeError("EXPERIMENT_ARM_NOT_UNIQUE")
  paired=[]
  for row in records:
   if row["odometry_Q"]=="NATIVE":continue
   base=index[(row["case"],row["channel"],row["bias"],row["solver"],row["RF_model"],"NATIVE")]
   p={
    "case":row["case"],"channel":row["channel"],"bias":row["bias"],
    "solver":row["solver"],"RF":row["RF_model"],"Q":row["odometry_Q"],
    "delta_heading_rmse_deg":float(row["heading_rmse_deg"])-float(base["heading_rmse_deg"]),
    "delta_bias_rmse_dps":float(row["bias_rmse_dps"])-float(base["bias_rmse_dps"]),
    "delta_xy_rmse_m":float(row["xy_rmse_m"])-float(base["xy_rmse_m"]),
    "delta_cond_xy_nees":float(row["conditional_xy_nees"])-float(base["conditional_xy_nees"]),
    "delta_narrow_xy_nees":float(row["conditional_xy_narrow_nees"])-float(base["conditional_xy_narrow_nees"]),
    "delta_pose_nees":float(row["pose_nees"])-float(base["pose_nees"]),
    "delta_pose_95":float(row["pose_95coverage"])-float(base["pose_95coverage"]),
    "delta_rf_accepts":int(row["RF_accepts"])-int(base["RF_accepts"]),
    "nearly_no_heading_change":abs(float(row["heading_rmse_deg"])-float(base["heading_rmse_deg"]))<.02,
    "improves_xy_narrow_and_preserves_heading_bias":
       float(row["conditional_xy_narrow_nees"])<float(base["conditional_xy_narrow_nees"]) and
       float(row["heading_rmse_deg"])<=float(base["heading_rmse_deg"])+1e-8 and
       float(row["bias_rmse_dps"])<=float(base["bias_rmse_dps"])+1e-8}
   paired.append(p)
  candidates={}
  for variant in ("D2","D4","D16","D64","LEGACY_LATERAL_PROXY"):
   g=[p for p in paired if p["channel"]=="full" and p["RF"]=="POWER_JOINT" and
         p["Q"]==variant]
   if len(g)!=16:raise RuntimeError("Q_VARIANT_NOT_ALL_MOUNT_BIAS_SOLVER:"+variant)
   candidates[variant]={"frames":len(g),
    "consistent_non_degradation_16":all(p["improves_xy_narrow_and_preserves_heading_bias"] for p in g),
    "mean_cond_xy_nees_change":sum(p["delta_cond_xy_nees"] for p in g)/len(g),
    "mean_heading_rmse_change":sum(p["delta_heading_rmse_deg"] for p in g)/len(g)}
  with (out/"PAIRED_FROM_ORIGINAL.csv").open("w",newline="",encoding="utf8") as f:
   w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
  final={"status":"INDEPENDENT_ODO_Q_REPRODUCIBILITY_AUDIT_PASS",
    "n_metrics":len(records),"n_baseline_original_parity":len(parity),
    "n_seed_mc_levels":len(mc),"mc_diagnostics":mc,"variant_tests":candidates,
    "source_SHA256":ARCHIVE_SHA,
    "scientific_sensor_Q_recalibration_PASS":False,
    "interpretation_limits":[
      "Original Qdistance and Gyro input covariance already correctly implemented in this simulated Sensor-v2",
      "D2-64 Q scalings are deliberately miscalibrated hypothesis controls, not measured true wheel noise",
      "Legacy lateral proxy models deterministic dynamics mismatch as random noise, diagnostic only",
      "Any narrowed NEES without independent noise model and scene cannot be declared a probabilistic correction",
      "Frozen POWER_JOINT R_s, R_r, C_rs and signed mean not changed by this experiment"]}
  store(out/"VERIFY_FINAL.json",final)
  print("ODOM_Q_VERIFY_FINAL "+json.dumps({"status":final["status"],
    "rows":len(records),"parity":len(parity),"sensor_mc":mc,
    "candidates":candidates},ensure_ascii=False),flush=True)
 return 0
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("pre","run"),required=True)
 ap.add_argument("--out",required=True);ap.add_argument("--receipt");ap.add_argument("--archive")
 a=ap.parse_args()
 return pre(a.out) if a.phase=="pre" else execute(a.out,a.receipt,a.archive)
if __name__=="__main__":raise SystemExit(main())
