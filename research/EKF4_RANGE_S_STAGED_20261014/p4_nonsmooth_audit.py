"""Audit original frozen P4 MAP failure artifact before any nonsmooth solve."""
import ast,hashlib,json,os,subprocess,argparse
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WORKFLOW=ROOT/".github/workflows/ekf4-r4-p4-nonsmooth-pilot.yml"
BASE={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
ZIP_SHA="db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4"
def getsha(p):
 p=Path(p);n=p.stat().st_size
 a=hashlib.sha1(b"blob "+str(n).encode()+b"\0")
 b=hashlib.sha256()
 with p.open("rb") as f:
  for piece in iter(lambda:f.read(1<<20),b""):a.update(piece);b.update(piece)
 return a.hexdigest(),b.hexdigest()
def verify(path):
 receipt=json.loads(Path(path).read_text())
 if receipt["decision"]!="GO" or receipt["git_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("NONSMMOOTH_PREAUDIT_NOT_GO")
 for rel,hash in receipt["source_sha256"].items():
  p=ROOT/rel
  if getsha(p)[1]!=hash:raise RuntimeError("SOURCE_CHANGED_AFTER_AUDIT:"+rel)
 return receipt
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];hashes={}
 try:
  if os.getenv("GITHUB_ACTIONS")!="true":errors.append("CLOUD_REQUIRED")
  if subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()!=os.getenv("GITHUB_SHA"):
   errors.append("SOURCE_SHA_MISMATCH")
  for rel,blob in BASE.items():
   p=ROOT/rel
   if not p.exists():errors.append("FROZEN_SOURCE_MISSING:"+rel);continue
   git,sha=getsha(p)
   if git!=blob:errors.append("FROZEN_SOURCE_CHANGED:"+rel)
   hashes[rel]=sha
  for name in ("p4_nonsmooth_audit.py","p4_nonsmooth_local.py",
               "p4_lut_boundary.py","test_p4_lut_boundary.py",
               "test_p4_nonsmooth.py","p4_nonsmooth_pilot.py"):
   rel="research/EKF4_RANGE_S_STAGED_20261014/"+name
   p=ROOT/rel
   if not p.exists():errors.append("CODE_MISSING:"+name);continue
   ast.parse(p.read_text(),filename=name)
   hashes[rel]=getsha(p)[1]
  if WORKFLOW.is_file():
   wf=WORKFLOW.read_text()
   commands=["p4_nonsmooth_audit.py --out","test_p4_nonsmooth.py",
             "p4_nonsmooth_pilot.py --artifact"]
   # Test file in paths is not execution; search actual pytest prefix.
   test=wf.find("python -m pytest --noconftest -q -s -c research/EKF4_RANGE_S_STAGED_20261014/pytest.ini research/EKF4_RANGE_S_STAGED_20261014/test_p4_nonsmooth.py")
   positions=[wf.find(commands[0]),test,wf.find(commands[2])]
   if -1 in positions or positions!=sorted(positions):errors.append("AUDIT_NOT_FIRST")
   if "test_p4_lut_boundary.py" not in wf or "p4_lut_boundary.py" not in wf:
    errors.append("LUT_BOUNDARY_DETECTOR_TEST_NOT_IN_WORKFLOW")
   if not("actions: read" in wf and ZIP_SHA in wf and "if: always()" in wf and "set -euo pipefail" in wf):
    errors.append("WORKFLOW_PROVENANCE_MISSING")
   hashes[".github/workflows/ekf4-r4-p4-nonsmooth-pilot.yml"]=getsha(WORKFLOW)[1]
  else:errors.append("WORKFLOW_MISSING")
  src=(HERE/"p4_nonsmooth_pilot.py").read_text()
  if "truth_for_offline_scoring_only" in src:errors.append("TRUTH_LEAKAGE_IN_SOLVER_PILOT")
 except Exception as exc:errors.append("AUDIT_EXCEPTION:"+repr(exc))
 rec={"schema":"P4_NONSMMOOTH_SOLVER_PREAUDIT_V1",
      "git_sha":os.getenv("GITHUB_SHA"),"run_id":os.getenv("GITHUB_RUN_ID"),
      "decision":"GO" if not errors else "HOLD","fatal":errors,
      "source_sha256":hashes,"frozen_blobs":BASE,
      "original_artifact_sha256":ZIP_SHA,
      "scientific_PASS":False,
      "assumptions":["same fixed Gaussian posterior","no interpolation smoothing",
                     "new local nonsmooth criterion separate from original 1e-8 smooth gradient",
                     "20 purposively selected failures; not a prevalence estimate"],
      "date_utc":datetime.now(timezone.utc).isoformat()}
 (out/"PREAUDIT.json").write_text(json.dumps(rec,indent=2)+"\n")
 print("NONSMMOOTH_PREAUDIT "+json.dumps({k:rec[k] for k in
   ("decision","fatal","git_sha")}),flush=True)
 return 0 if not errors else 2
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--out",required=True)
 x=p.parse_args();raise SystemExit(audit(x.out))
