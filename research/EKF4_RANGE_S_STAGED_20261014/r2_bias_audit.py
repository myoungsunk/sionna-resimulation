"""Static source / RF / experiment-contract audit BEFORE R2 bias numerics.

Audits B0/L0/L1/L2, two R2 mounts, LoS/Full, both one-step and recursive,
and paired motion seed. Does not import NumPy, RF or estimator.
"""
import ast,hashlib,json,os,subprocess,argparse
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WF=ROOT/".github/workflows/ekf4-r2-bias-l012.yml"
ARCHIVE="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
BASE={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/sensor_v2.py":"87ce04aa3c43130f3499008840fa395174f1124e",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/sensors.py":"c083291b8fafab112242c2fee2412b46bf6f8918",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
FILES=["r2_bias_audit.py","r2_bias_replay.py","r2_bias_score.py","test_r2_bias.py"]
def hashb(path):
 size=path.stat().st_size;git=hashlib.sha1()
 git.update(b"blob "+str(size).encode()+b"\0")
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):git.update(b);h.update(b)
 return git.hexdigest(),h.hexdigest()
def check(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];checks={}
 try:
  if os.getenv("GITHUB_ACTIONS")!="true":errors.append("GITHUB_ONLY")
  head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
  if head!=os.getenv("GITHUB_SHA"):errors.append("SHA_NOT_EXACT")
  for relative,blob in BASE.items():
   p=ROOT/relative
   if not p.exists():errors.append("MISSING_FROZEN:"+relative);continue
   b,h=hashb(p);checks[relative]=h
   if b!=blob:errors.append("FROZEN_SHA_CHANGED:"+relative)
  for name in FILES:
   p=HERE/name
   if not p.exists():errors.append("MISSING_MODULE:"+name);continue
   ast.parse(p.read_text(encoding="utf-8"),filename=name)
   checks["research/EKF4_RANGE_S_STAGED_20261014/"+name]=hashb(p)[1]
  wf=WF.read_text()
  commands=["r2_bias_audit.py --out","python -m pytest --noconftest -q -s -c research/EKF4_RANGE_S_STAGED_20261014/pytest.ini research/EKF4_RANGE_S_STAGED_20261014/test_r2_bias.py","r2_bias_replay.py --archive","r2_bias_score.py --archive"]
  positions=[wf.index(x) for x in commands]
  if positions!=sorted(positions):errors.append("BAD_STAGE_ORDER")
  if not ("actions: read" in wf and ARCHIVE in wf and "if: always()" in wf and "set -euo pipefail" in wf):
   errors.append("UNSAFE_WORKFLOW")
  checks[".github/workflows/ekf4-r2-bias-l012.yml"]=hashb(WF)[1]
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  idset={v["id"] for v in manifest["cases"]}
  if not {"R2_aA_m0","R2_aA_m45"}.issubset(idset):errors.append("R2_MOUNT_NOT_FOUND")
  s=(HERE/"r2_bias_replay.py").read_text()
  for token in ('"gyro_bias"', '"noise_pair"', '"all"', "DRIFT_LEVELS",
                "positive_bias", 'condition="all"', 'slip_mode="off"',
                "run_filters"):
   if token not in s:errors.append("MISSING_PAIRED_SENSITIVITY_CONTRACT:"+token)
  # Strict method dispatch is source-critical: the initial audited run
  # incorrectly sent SR3/SR4 to s-only via startswith("S").
  if ('if alg in ("S3","S4"):' not in s or
      'if alg.startswith("S"):' in s or
      'if not alg.startswith("SR"):' not in s):
   errors.append("SR_RELINEARIZED_BRANCH_DISPATCH_NOT_VERIFIED")
  # The estimator function must accept already-generated inputs, not truth.
  tree=ast.parse(s)
  fun=next((node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="run_filters"),None)
  if fun is None:errors.append("NO_RUN_FILTERS")
  elif any(isinstance(n,ast.Name) and n.id in ("truth","true_bias") for n in ast.walk(fun)):
   errors.append("TRUTH_LEAKAGE_IN_FILTER")
 except Exception as e:errors.append("AUDIT_SCRIPT:"+repr(e))
 record={"schema":"R2_BIAS_L012_AUDIT_V1","git_sha":os.getenv("GITHUB_SHA"),
  "run_id":os.getenv("GITHUB_RUN_ID"),"decision":"GO" if not errors else "HOLD",
  "fatal":errors,"source_sha256":checks,"frozen_blob_sha":BASE,
  "frozen_archive_sha256":ARCHIVE,
  "scope":{"route":"R2","case_ids":["R2_aA_m0","R2_aA_m45"],
           "bias_levels_dps":{"B0":0.,"L0":.01,"L1":.05,"L2":.2},
           "sensor":"gyro bias + same original white noise, other drift suppressed",
           "seed":0,"channels":["los","full"],"methods":["DR3","DR4","S3","S4","J3","J4","SR3","SR4"],
           "evaluation":["one_step_DR_prior","recursive"]},
  "scientific_PASS":False,
  "time_utc":datetime.now(timezone.utc).isoformat()}
 (out/"AUDIT.json").write_text(json.dumps(record,indent=2)+"\n")
 print("R2_BIAS_PREAUDIT "+json.dumps({k:record[k] for k in ("decision","fatal","git_sha")}),flush=True)
 return 0 if not errors else 2
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--out",required=True)
 a=p.parse_args();raise SystemExit(check(a.out))
