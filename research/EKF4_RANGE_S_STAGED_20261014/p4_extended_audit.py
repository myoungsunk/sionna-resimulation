"""Audit FIRST: immutable frozen R4 P4, P3 LUT and R5 solver, before numerics."""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WF=ROOT/".github/workflows/ekf4-r5-phi-nonsmooth-extended.yml"
BLOBS={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF4_RANGE_S_STAGED_20261014/p4_nonsmooth_local.py":"ca950a5883c5a265feba76322315e1db1abdf6b6",
"research/EKF4_RANGE_S_STAGED_20261014/p4_lut_boundary.py":"fac3f9acb973498cfde5457dab3292efc02b7317",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
P4_SHA="db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4"
ORIGINAL_RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
CODES=("p4_extended_audit.py","p4_extended_phi.py","p4_extended_validation.py","test_p4_extended_guard.py")
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def blobhash(path):
    h=hashlib.sha1()
    n=Path(path).stat().st_size
    h.update(b"blob "+str(n).encode()+b"\x00")
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def require_audit(path):
    receipt=json.loads(Path(path).read_text())
    if receipt["decision"]!="GO" or receipt["git_sha"]!=os.getenv("GITHUB_SHA") or os.getenv("GITHUB_ACTIONS")!="true":
        raise RuntimeError("EXTENDED_AUDIT_INVALID_OR_NOT_SAME_SOURCE")
    for key,val in receipt["source_sha256"].items():
        path=ROOT/key
        if digest(path)!=val:raise RuntimeError("SOURCE_CHANGED_AFTER_AUDIT:"+key)
    return receipt
def audit(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    errors=[];hashes={}
    try:
        if os.environ.get("GITHUB_ACTIONS")!="true":errors.append("NOT_ACTIONS")
        if subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()!=os.environ.get("GITHUB_SHA"):
            errors.append("GIT_HEAD_MISMATCH")
        for rel,sha in BLOBS.items():
            f=ROOT/rel
            if not f.is_file():
                errors.append("FROZEN_MISSING:"+rel);continue
            hashes[rel]=digest(f)
            if blobhash(f)!=sha:errors.append("FROZEN_BLOB_MUTATED:"+rel)
        for name in CODES:
            f=HERE/name
            if not f.is_file():errors.append("EXTENDED_CODE_MISSING:"+name);continue
            ast.parse(f.read_text(),filename=name)
            hashes[str(f.relative_to(ROOT))]=digest(f)
        wf=WF.read_text()
        commands=["p4_extended_audit.py --out",
                  "p4_extended_phi.py --archive",
                  "p4_extended_validation.py --phase full-geometry",
                  "p4_extended_validation.py --phase stratified-solver"]
        ix=[wf.find(v) for v in commands]
        if -1 in ix or ix!=sorted(ix):errors.append("AUDIT_NOT_FIRST_OR_STAGES_OUT_OF_ORDER")
        if not ("if: always()" in wf and "set -euo pipefail" in wf
                and "actions: read" in wf and P4_SHA in wf and ORIGINAL_RF_SHA in wf):
            errors.append("PROVENANCE_OR_FAIL_CLOSED_MISSING")
        hashes[str(WF.relative_to(ROOT))]=digest(WF)
        for name in ("p4_extended_validation.py","p4_extended_phi.py"):
            code=(HERE/name).read_text()
            if "truth_for_offline_scoring_only" in code:
                errors.append("ESTIMATOR_USED_TRUTH:"+name)
        m=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
        if len(m["assets"])!=39 or len(m["cases"])!=7:errors.append("P0_SCHEMA_CHANGE")
    except Exception as exc:errors.append("AUDIT_IMPLEMENTATION_ERROR:"+repr(exc))
    result={"schema":"R5_PHI_NONSMMOOTH_EXPANDED_AUDIT_V1",
      "decision":"GO" if not errors else "HOLD",
      "fatal":errors,"git_sha":os.getenv("GITHUB_SHA"),
      "run_id":os.getenv("GITHUB_RUN_ID"),
      "source_sha256":hashes,"frozen_blob_sha1":BLOBS,
      "original_P4_artifact_sha256":P4_SHA,"original_RF_artifact_sha256":ORIGINAL_RF_SHA,
      "scientific_PASS":False,"independent_peer_review":False,
      "scope":"No new RF scene, R5 candidate still exploratory; all 4124 fixed failure geometry + stratified re-optimization",
      "time_utc":datetime.now(timezone.utc).isoformat()}
    (output/"PRE_AUDIT.json").write_text(json.dumps(result,indent=2)+"\n")
    print("R5_EXTENDED_PREAUDIT "+json.dumps({"decision":result["decision"],"fatal":errors,"sha":result["git_sha"]}),flush=True)
    return 0 if not errors else 2
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True)
    a=p.parse_args();raise SystemExit(audit(a.out))
