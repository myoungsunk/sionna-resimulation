"""P4 read-only figure experiment pre-run static audit (NO NumPy/model import)."""
import ast,hashlib,json,os,subprocess,argparse
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WF=ROOT/".github/workflows/ekf4-r4-p4-kink-figure.yml"
BLOBS={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
ZIP_SHA="db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4"
def get_sha(path):
 b=Path(path).read_bytes()
 return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\x00"+b).hexdigest(),hashlib.sha256(b).hexdigest()
def run(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 fatal=[];hashes={}
 try:
  if os.environ.get("GITHUB_ACTIONS")!="true":fatal.append("GITHUB_ACTIONS_REQUIRED")
  if subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()!=os.getenv("GITHUB_SHA"):
   fatal.append("HEAD_MISMATCH")
  for path,expected in BLOBS.items():
   f=ROOT/path
   if not f.exists():fatal.append("FROZEN_MISSING:"+path);continue
   blob,sha=get_sha(f);hashes[path]=sha
   if blob!=expected:fatal.append("FROZEN_SOURCE_CHANGED:"+path)
  for name in ("p4_kink_fig_audit.py","p4_kink_actual_profile.py"):
   f=HERE/name
   ast.parse(f.read_text(encoding="utf-8"),filename=name)
   hashes[name]=get_sha(f)[1]
  wf=WF.read_text()
  a=wf.index("p4_kink_fig_audit.py --out")
  b=wf.index("p4_kink_actual_profile.py --artifact")
  if not a<b:fatal.append("FIGURE_AUDIT_NOT_FIRST")
  if ZIP_SHA not in wf or "actions: read" not in wf or "set -euo pipefail" not in wf or "if: always()" not in wf:
   fatal.append("WORKFLOW_NO_FROZEN_CONTRACT")
  hashes["workflow"]=get_sha(WF)[1]
 except Exception as exc:fatal.append(type(exc).__name__+":"+str(exc))
 receipt={"schema":"P4_KINK_ACTUAL_PROFILE_AUDIT_V1",
          "source_sha":os.getenv("GITHUB_SHA"),"source_hashes":hashes,
          "frozen_blobs":BLOBS,"original_p4_zip_sha256":ZIP_SHA,
          "decision":"GO" if not fatal else "HOLD","fatal":fatal,
          "time_utc":datetime.now(timezone.utc).isoformat(),"scientific_PASS":False}
 (out/"PRE_AUDIT.json").write_text(json.dumps(receipt,indent=2)+"\n")
 print("P4_KINK_PREAUDIT "+json.dumps({"decision":receipt["decision"],"fatal":fatal}),flush=True)
 return 0 if not fatal else 2
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--out",required=True)
 args=p.parse_args();raise SystemExit(run(args.out))
