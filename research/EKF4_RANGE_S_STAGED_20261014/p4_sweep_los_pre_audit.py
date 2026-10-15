"""Read-only S0 sweep LUT preexecution source and workflow audit."""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BLOBS={
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF4_RANGE_S_STAGED_20261014/p3_frozen_inputs.py":"3ba19cf01bd225ccf98335e5e92448530713b045",
"research/EKF4_RANGE_S_STAGED_20261014/p4_lut_boundary.py":"fac3f9acb973498cfde5457dab3292efc02b7317",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"}
RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
WF=ROOT/".github/workflows/ekf4-r5-yaw-sweep-los-template.yml"
def checks(f):
 f=Path(f);sha=hashlib.sha1(b"blob "+str(f.stat().st_size).encode()+b"\0")
 s=hashlib.sha256()
 with f.open("rb") as file:
  for b in iter(lambda:file.read(1<<20),b""):sha.update(b);s.update(b)
 return sha.hexdigest(),s.hexdigest()
def run(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];sha={}
 try:
  if os.environ.get("GITHUB_ACTIONS")!="true":errors.append("GITHUB_CLOUD_REQUIRED")
  if subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()!=os.getenv("GITHUB_SHA"):errors.append("GIT_SHA_DIFFERENT")
  for rel,expected in BLOBS.items():
   p=ROOT/rel
   if not p.is_file():errors.append("FROZEN_NOT_FOUND:"+rel);continue
   blob,digest=checks(p);sha[rel]=digest
   if blob!=expected:errors.append("FROZEN_BLOB_CHANGED:"+rel)
  for name in ("p4_sweep_los_pre_audit.py","p4_sweep_los_templates.py"):
   f=HERE/name;ast.parse(f.read_text(),filename=name);sha[str(f.relative_to(ROOT))]=checks(f)[1]
  wf=WF.read_text()
  a=wf.find("p4_sweep_los_pre_audit.py --out");b=wf.find("p4_sweep_los_templates.py --archive")
  if not(0<=a<b) or RF_SHA not in wf or "if: always()" not in wf or "actions: read" not in wf:errors.append("WORKFLOW_PROVENANCE_OR_AUDIT_ORDER_INVALID")
  sha[str(WF.relative_to(ROOT))]=checks(WF)[1]
 except Exception as e:errors.append("AUDIT_DEFECT:"+repr(e))
 receipt={"schema":"R5_SWEEP_LOS_S0_PREEXEC_AUDIT_V1",
  "git_sha":os.getenv("GITHUB_SHA"),"decision":"GO" if not errors else "HOLD",
  "errors":errors,"source_sha256":sha,"original_RF_SHA":RF_SHA,
  "scope":"LoS frozen-LUT templates only; no Full yaw scans and no physical heading accuracy evidence",
  "scientific_PASS":False}
 (out/"PRE_AUDIT.json").write_text(json.dumps(receipt,indent=2)+"\n")
 print("SWEEP_LOS_PREAUDIT "+json.dumps({"decision":receipt["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--out",required=True)
 a=p.parse_args();raise SystemExit(run(a.out))