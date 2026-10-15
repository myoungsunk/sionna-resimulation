"""Pre-execution code and original 3-case identity audit, source read only."""
from pathlib import Path
import argparse,ast,hashlib,json,os,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WF=ROOT/".github/workflows/ekf4-r5-roundtrip-probe.yml"
SOURCE={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF4_RANGE_S_STAGED_20261014/p4_nonsmooth_local.py":"ca950a5883c5a265feba76322315e1db1abdf6b6",
"research/EKF4_RANGE_S_STAGED_20261014/p4_lut_boundary.py":"fac3f9acb973498cfde5457dab3292efc02b7317",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb"
}
P4_ARCHIVE_SHA="db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4"
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def blob(path):
    p=Path(path);h=hashlib.sha1()
    h.update(b"blob "+str(p.stat().st_size).encode()+b"\0")
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def audit(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    errors=[];hashes={}
    try:
        if os.getenv("GITHUB_ACTIONS")!="true":errors.append("CLOUD_REQUIRED")
        if subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()!=os.getenv("GITHUB_SHA"):
            errors.append("HEAD_SHA_MISMATCH")
        for path,expected in SOURCE.items():
            p=ROOT/path
            if not p.exists():errors.append("MISSING:"+path);continue
            hashes[path]=sha(p)
            if blob(p)!=expected:errors.append("MUTATED_FROZEN:"+path)
        for n in ("p4_roundtrip_preaudit.py","p4_roundtrip_probe.py"):
            p=HERE/n
            hashes[str(p.relative_to(ROOT))]=sha(p)
            ast.parse(p.read_text(),filename=n)
        wf=WF.read_text()
        if not (wf.find("p4_roundtrip_preaudit.py --out") <
                wf.find("p4_roundtrip_probe.py --artifact") and
                P4_ARCHIVE_SHA in wf and "actions: read" in wf and
                "set -euo pipefail" in wf and "if: always()" in wf):
            errors.append("WORKFLOW_ORDER_OR_PROVENANCE")
        hashes[str(WF.relative_to(ROOT))]=sha(WF)
        if "truth_for_offline_scoring_only" in (HERE/"p4_roundtrip_probe.py").read_text():
            errors.append("TRUTH_LEAKAGE")
    except Exception as e:errors.append("AUDIT_ERROR:"+repr(e))
    result={"decision":"GO" if not errors else "HOLD","fatal":errors,
            "git_sha":os.getenv("GITHUB_SHA"),"source_sha256":hashes,
            "original_artifact_sha256":P4_ARCHIVE_SHA,"scientific_PASS":False}
    (out/"PRE_AUDIT.json").write_text(json.dumps(result,indent=2)+"\n")
    print("P4_ROUNDTRIP_AUDIT "+json.dumps({"decision":result["decision"],"fatal":errors}),flush=True)
    return 0 if not errors else 2
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True)
    a=p.parse_args();raise SystemExit(audit(a.out))
