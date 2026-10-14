"""Mandatory, read-only P3 pre-execution source/input contract audit.

This executable intentionally imports no estimation or numerical library.
No diagnostic, model inference, or scientific test runs before audit GO.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORKFLOW = REPO / ".github/workflows/ekf4-r4-p3-frozen-rf.yml"
P0_FILE = "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
ROOT_LUT = "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/"
ORIGINAL_ZIP_ID = 11782748118
ORIGINAL_ZIP_SHA = "88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
FROZEN_BLOBS = {
    "research/EKF4_RANGE_S_STAGED_20261014/core.py": "0a0851e6867c14fec5eefe02df471100cb9e9e1d",
    "research/EKF4_RANGE_S_STAGED_20261014/synthetic.py": "4ed7ae3a00ae9b49c70bae6c1a7a5aa0e6d07f08",
    "research/EKF4_RANGE_S_STAGED_20261014/P2_SPEC.json": "70f0fa1787879634e8511ea73d4bf8fbffefaafd",
    P0_FILE: "8bf216cf606f5e3c11139cacbf42f15a44556feb",
    "research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py": "507e0f6588d6cddcc358c630c538770ccbaaedbc",
    ROOT_LUT + "hs_lut_meta.json": "5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
    ROOT_LUT + "hs_lut_2deg.npy": "9a53057f6f646f63574574b9a70186452cb5aca9",
}
CODE = ("p3_pre_run_audit.py", "p3_frozen_inputs.py",
        "p3_rf_adapter4.py", "p3_parity.py", "p3_export.py",
        "test_p3_adapter.py")
PLAN = "P3_R4_IMPLEMENTATION_PLAN_20261014_KO.md"

def hashes(path):
    size = path.stat().st_size
    h1 = hashlib.sha1()
    h1.update(b"blob " + str(size).encode("ascii") + b"\0")
    h2 = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1 << 20), b""):
            h1.update(data)
            h2.update(data)
    return h1.hexdigest(), h2.hexdigest()

def audit(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    fatal = []
    warnings = []
    source_hash = {}
    sha = os.getenv("GITHUB_SHA")
    if os.getenv("GITHUB_ACTIONS") != "true" or not sha:
        fatal.append("NOT_IN_EXACT_GITHUB_ACTIONS")
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        if head != sha:
            fatal.append("GIT_SHA_CHECKOUT_MISMATCH")
        for path, expected in FROZEN_BLOBS.items():
            p = REPO / path
            if not p.is_file():
                fatal.append("FROZEN_MISSING:" + path)
            else:
                blob, digest = hashes(p)
                source_hash[path] = digest
                if blob != expected:
                    fatal.append("FROZEN_BLOB_MISMATCH:" + path)
        for name in CODE + (PLAN,):
            p = HERE / name
            if not p.is_file():
                fatal.append("SOURCE_MISSING:" + name)
            else:
                source_hash[name] = hashes(p)[1]
                if name.endswith(".py"):
                    ast.parse(p.read_text(encoding="utf-8"), filename=name)
        manifest = json.loads((REPO / P0_FILE).read_text(encoding="utf-8"))
        if not (manifest.get("schema") == "EKF3_P0_FREEZE_V1"
                and len(manifest["assets"]) == 39
                and len(manifest["cases"]) == 7
                and len(manifest["routes"]) == 3):
            fatal.append("ORIGINAL_P0_CONTRACT_MUTATED")
        assets = {a["path"]: a for a in manifest["assets"]}
        for name in ("hs_lut_2deg.npy", "hs_lut_meta.json"):
            p = ROOT_LUT + name
            if p not in assets or assets[p]["sha256"] != source_hash.get(p):
                fatal.append("LUT_SHA256_NOT_P0_FROZEN:" + p)
        ids = [c["id"] for c in manifest["cases"]]
        if len(set(ids)) != 7:
            fatal.append("DUPLICATE_CASE_ID")
        physical = manifest["physical_contract"]
        if (physical["state"] != ["x_m","y_m","yaw_rad"]
            or physical["observer"].find("Hann") < 0
            or "s=(P1-P2)/(P1+P2)" not in physical["observer"]):
            fatal.append("RF_OBSERVER_PHYSICAL_CONTRACT_MUTATED")
        # Verify the new solver-independent audit genuinely comes before all
        # numerical code and that the upload is unconditional on test success.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        stages = ["p3_pre_run_audit.py", "p3_frozen_inputs.py",
                  "p3_parity.py", "test_p3_adapter.py", "p3_export.py"]
        offsets = [workflow.find("python research/EKF4_RANGE_S_STAGED_20261014/" + x)
                   if x != "test_p3_adapter.py" else workflow.find("test_p3_adapter.py")
                   for x in stages]
        if not all(x >= 0 for x in offsets) or offsets != sorted(offsets):
            fatal.append("WORKFLOW_AUDIT_NOT_FIRST_OR_STAGE_ORDER")
        if ("if: always()" not in workflow or "set -euo pipefail" not in workflow
                or "actions: read" not in workflow
                or str(ORIGINAL_ZIP_ID) not in workflow
                or ORIGINAL_ZIP_SHA not in workflow):
            fatal.append("WORKFLOW_PROVENANCE_OR_FAIL_CLOSED_MISSING")
        source_hash["workflow"] = hashes(WORKFLOW)[1]
        warnings.append("Prior 39-asset P0 SHA/shape/pose check reused only for unchanged frozen SHA; not a new channel regeneration.")
        warnings.append("R0 s/r independence uncalibrated; single frozen corridor and seed0; scientific_PASS=false.")
        meta = json.loads((REPO / (ROOT_LUT+"hs_lut_meta.json")).read_text(encoding="utf-8"))["meta"]
        if not(len(meta["theta_deg"])==46 and meta["phi_deg"]==[-180.0,178.0,2.0]):
            fatal.append("LUT_AXIS_METADATA_MISMATCH")
    except Exception as exc:
        fatal.append("AUDIT_CODE_ERROR:" + type(exc).__name__ + ":" + str(exc))
    result = {
        "schema":"EKF4_R4_P3_PRE_RUN_AUDIT_V1",
        "stage":"P3_FROZEN_RF_ELIGIBILITY_AND_ADAPTER",
        "git_sha":sha,
        "run_id":os.getenv("GITHUB_RUN_ID"),
        "decision":"HOLD" if fatal else "GO",
        "fatal":fatal, "warnings":warnings,
        "source_sha256":source_hash,
        "frozen_blob_sha1":FROZEN_BLOBS,
        "archive_id":ORIGINAL_ZIP_ID, "archive_sha256":ORIGINAL_ZIP_SHA,
        "reuse_prior_P0_run":38556465417,
        "reuse_prior_one_step_run":38331588521,
        "scientific_PASS":False,
        "independent_peer_review":False,
        "created_utc":datetime.now(timezone.utc).isoformat()
    }
    (destination/"P3_PRE_AUDIT.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("P3_PRE_AUDIT " + json.dumps({
        "decision":result["decision"],"fatal":fatal,
        "git_sha":sha,"source_files":len(source_hash)
    },ensure_ascii=False),flush=True)
    return 0 if not fatal else 2

if __name__ == "__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--out",type=Path,required=True)
    a=cli.parse_args()
    raise SystemExit(audit(a.out))
