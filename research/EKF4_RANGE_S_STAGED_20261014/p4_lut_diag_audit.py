"""Mandatory static pre-run audit for independently replaying R4 P4 MAP failures."""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WORKFLOW=ROOT/".github/workflows/ekf4-r4-p4-lut-rootcause.yml"
FROZEN_BLOBS={
    "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
    "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
    "research/EKF4_RANGE_S_STAGED_20261014/p4_one_step_models.py":"20ae8eb7455cf34c3e9558e4bf3940a0c357ef6a",
    "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
    "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
    "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
ORIGINAL_COMMIT="46d679a32f55cae460d9ed35b4bb944bc48cc4ce"
ARTIFACT_SHA="db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4"
def hashes(path):
    size=path.stat().st_size
    g=hashlib.sha1();g.update(b"blob "+str(size).encode()+b"\0")
    s=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):
            g.update(b);s.update(b)
    return g.hexdigest(),s.hexdigest()

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    fatal=[];sha={}
    try:
        if os.getenv("GITHUB_ACTIONS")!="true":
            fatal.append("NOT_GITHUB_ACTIONS")
        if subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()!=os.getenv("GITHUB_SHA"):
            fatal.append("SOURCE_GIT_SHA_MISMATCH")
        for relative,b in FROZEN_BLOBS.items():
            p=ROOT/relative
            if not p.is_file():
                fatal.append("REQUIRED_SOURCE_MISSING:"+relative);continue
            gb,sh=hashes(p);sha[relative]=sh
            if gb!=b:fatal.append("IMMUTABLE_BLOB_MISMATCH:"+relative)
        for file in ("p4_lut_diag_audit.py","p4_lut_failure_diag.py"):
            p=HERE/file
            if not p.is_file():fatal.append("AUDIT_OR_DIAG_MISSING:"+file);continue
            sha[file]=hashes(p)[1]
            ast.parse(p.read_text(),filename=file)
        wf=WORKFLOW.read_text()
        if not(wf.index("p4_lut_diag_audit.py --out") <
               wf.index("p4_lut_failure_diag.py --artifact")):
            fatal.append("AUDIT_NOT_BEFORE_DIAGNOSTIC")
        if not("actions: read" in wf and ARTIFACT_SHA in wf
               and "if: always()" in wf and "set -euo pipefail" in wf):
            fatal.append("WORKFLOW_READONLY_OR_FAILCLOSED_MISSING")
        sha["workflow"]=hashes(WORKFLOW)[1]
        src=(HERE/"p4_lut_failure_diag.py").read_text()
        if "truth_for_offline_scoring_only" in src:
            fatal.append("DIAGNOSTIC_ESTIMATOR_TRUTH_LEAKAGE")
    except Exception as e:fatal.append("AUDIT_EXCEPTION:"+repr(e))
    result={"schema":"R4_P4_MAP_FAILURE_AUDIT_V1",
            "git_sha":os.environ.get("GITHUB_SHA"),"run_id":os.getenv("GITHUB_RUN_ID"),
            "source_original_p4_commit":ORIGINAL_COMMIT,"p4_artifact_sha256":ARTIFACT_SHA,
            "source_sha256":sha,"frozen_blob_sha1":FROZEN_BLOBS,
            "fatal":fatal,"decision":"GO" if not fatal else "HOLD",
            "scientific_PASS":False,"independent_peer_audit":False,
            "date_utc":datetime.now(timezone.utc).isoformat()}
    (out/"P4_D4_PREAUDIT.json").write_text(json.dumps(result,indent=2)+"\n")
    print("P4_D4_PREAUDIT "+json.dumps({k:result[k] for k in ("decision","fatal","git_sha")}),flush=True)
    return 0 if not fatal else 2

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True)
    a=p.parse_args();raise SystemExit(run(a.out))
