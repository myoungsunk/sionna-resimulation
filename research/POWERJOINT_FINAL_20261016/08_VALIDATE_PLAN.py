"""Pre-execution contract audit ONLY. No scientific data simulation or fitting.

USAGE
  python3 research/POWERJOINT_FINAL_20261016/08_VALIDATE_PLAN.py
  python3 research/POWERJOINT_FINAL_20261016/08_VALIDATE_PLAN.py --json-report /tmp/plan_audit.json

Checks the document+manifest structure, pipeline DAG, required input statuses
and available source Git blob hashes. Missing FFD/Full new RF is BLOCKED_INPUT,
NOT a plan failure. This is not a scientific numerical result.
"""
from __future__ import annotations
import argparse,hashlib,json,re,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
MFILE=HERE/"07_EXPERIMENT_MANIFEST.json"
BLOB_RE=re.compile(r"^[a-f0-9]{40}$")
SHA_RE=re.compile(r"^[a-f0-9]{64}$")
EXPECTED_STAGE_IDS={f"F{i}" for i in range(8)}
REQUIRED_DOCS={f"{i:02d}_"+s for i,s in enumerate([
"MASTER_PLAN_KO.md","HYPOTHESIS_LEDGER_KO.md","EXPERIMENT_PROTOCOL_KO.md",
"CODE_AUDIT_CONTRACT_KO.md","SIMULATION_REQUEST_SPEC_KO.md","PAPER_STORY_KO.md",
"EXECUTION_RUNBOOK_KO.md"])}

def gitblob(path:Path)->str:
    h=hashlib.sha1(b"blob "+str(path.stat().st_size).encode()+b"\0")
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def audit():
    m=json.loads(MFILE.read_text(encoding="utf8"))
    errors,source_checks=[],{}
    if m.get("schema")!="POWERJOINT_FINAL_PREEXECUTION_PLAN_V1":
        errors.append("MANIFEST_SCHEMA_MISMATCH")
    if m.get("plan_only") is not True or m.get("scientific_experiments_executed_in_plan_branch") is not False:
        errors.append("PLAN_MUST_NOT_CLAIM_NEW_RESULTS")
    if set(m.get("documents",[]))!=REQUIRED_DOCS:
        errors.append("REQUIRED_DOCUMENTS_MISSING_IN_MANIFEST")
    for name in REQUIRED_DOCS:
        p=HERE/name
        if not p.is_file() or p.stat().st_size<200:
            errors.append("DOCUMENT_ABSENT_OR_EMPTY:"+name)
    for p,h in m.get("original_code_git_blobs",{}).items():
        if not BLOB_RE.fullmatch(h):
            errors.append("GIT_BLOB_SHA_FORMAT_INVALID:"+p)
        f=ROOT/p
        if f.is_file():
            actual=gitblob(f)
            source_checks[p]="MATCH" if actual==h else "DIFFERENT"
            if actual!=h:errors.append("FROZEN_SOURCE_CHANGED:"+p)
        else:
            source_checks[p]="EXTERNAL_REF_NOT_MATERIALIZED_FOR_STATIC_AUDIT"
    for k,h in m.get("original_artifact_sha256",{}).items():
        if not SHA_RE.fullmatch(h):
            errors.append("ARTIFACT_SHA_FORMAT:"+k)
    if not SHA_RE.fullmatch(m.get("original_lut_sha256","")):
        errors.append("ORIGINAL_LUT_SHA_FORMAT")
    stages=m.get("stages",[])
    ids=[s.get("id") for s in stages]
    if set(ids)!=EXPECTED_STAGE_IDS or len(ids)!=8:
        errors.append("EXPECTED_F0_THROUGH_F7_EXACTLY_ONCE")
    index={s["id"]:s for s in stages}
    for s in stages:
        if s.get("scientific_status")!="NOT_RUN":
            errors.append("PLAN_STAGE_ALREADY_CLAIMS_SCIENCE:"+s["id"])
        if not s.get("outputs") or not isinstance(s.get("outputs"),list):
            errors.append("MISSING_STAGE_OUTPUT_CONTRACT:"+s["id"])
    inputs=m.get("input_packages",[])
    input_map={i["id"]:i for i in inputs}
    if len(input_map)!=len(inputs):
        errors.append("DUPLICATE_INPUT_PACKAGE")
    if {"SIM_A_ORIGINAL_FFD","SIM_B_R4R5_MOTION",
        "SIM_C_INDEPENDENT_FULL_LOS_SCENES","SIM_D_HARDWARE"}!=set(input_map):
        errors.append("EXPECTED_INPUT_PACKAGES_MISSING")
    for s in stages:
        for req in s.get("requires",[]):
            if req not in input_map:
                errors.append("UNDECLARED_REQUIRED_INPUT:"+s["id"]+":"+req)
        for d in s.get("deps",[]):
            if d not in index:
                errors.append("MISSING_DEPENDENCY:"+s["id"]+":"+d)
    visited=set()
    def visit(i,stack):
        if i in stack:
            errors.append("CYCLIC_DEPENDENCIES:"+i);return
        if i in visited:return
        for d in index[i].get("deps",[]):
            if d in index:visit(d,stack+(i,))
        visited.add(i)
    for s in stages:visit(s["id"],())
    if input_map["SIM_B_R4R5_MOTION"].get("required") is True:
        errors.append("ARCHIVAL_R4R5_REPLAY_NOT_REQUIRED_FOR_INDEPENDENT_NEW_SCENES")
    if "SIM_B_R4R5_MOTION" in index["F6"]["requires"]:
        errors.append("SIM_B_MUST_NOT_BLOCK_FULL_NEW_SCENES")
    if any(i["available"] for i in inputs if i["id"] in (
        "SIM_A_ORIGINAL_FFD","SIM_C_INDEPENDENT_FULL_LOS_SCENES")):
        # At this plan freeze these are not accessible in the known source set.
        errors.append("UNVERIFIED_REQUIRED_ASSETS_FALSE_READY")
    if any(v is not False for v in m.get("integrity_rules",{}).values()):
        errors.append("DISALLOWED_LEAK_OR_FALSE_CLAIM_FLAG")
    if m.get("hard_locked_eval_config",{}).get("test_scene_minimum",0)<3:
        errors.append("TOO_FEW_UNSEEN_TEST_SCENES_PREDECLARED")
    if "F7" not in index or "F6" not in index["F7"].get("deps",[]):
        errors.append("F7_BYPASSES_FINAL_HOLDOUT")
    blocked=[i["id"] for i in inputs if not i["available"]]
    staged_pilot=[s["id"] for s in stages if
        s.get("readiness","").startswith("EXISTING_R2_PILOT_READY")]
    return {
        "plan_contract":"PASS" if not errors else "FAIL",
        "scientific_experiments_run_in_this_branch":0,
        "source_file_presence_versus_git_blob":source_checks,
        "required_input_statuses":{i["id"]:"AVAILABLE" if i["available"] else
                 "BLOCKED_INPUT" for i in inputs},
        "blocked_input_packages":blocked,
        "source_frozen_R2_pilot_prep_stages":staged_pilot,
        "science_ready_for_independent_scene_claim":False,
        "validation_scope":"metadata/documents/source-matches where available; not a numerical source/archive replay",
        "errors":errors,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--json-report",default=None)
    args=p.parse_args()
    result=audit()
    txt=json.dumps(result,ensure_ascii=False,indent=2)
    print(txt)
    if args.json_report:
        out=Path(args.json_report);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(txt+"\n",encoding="utf8")
    return 0 if result["plan_contract"]=="PASS" else 2

if __name__=="__main__":
    sys.exit(main())
