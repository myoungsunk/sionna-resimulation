"""Separate end-to-end P2 full receipt validation; never confuse PASS with science.

Verify 600 input IDs, 2400 model results, input trace existence,
manifest SHA256, failure list, paired denominators, frozen contract.
"""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
def sh(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify(root,audit,out):
    from pre_run_audit import require_audit_receipt
    receipt=require_audit_receipt(audit)
    root=Path(root)
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False)
    final=json.loads((root/"FINAL.json").read_text())
    spec=json.loads((HERE/"P2_SPEC.json").read_text())
    rows=(root/"TRIAL_METRICS.csv").read_text().splitlines()
    fails=json.loads((root/"CASE_INVALID.json").read_text())
    groups=json.loads((root/"GROUP_METRICS.json").read_text())
    contrasts=json.loads((root/"PAIRED_CI.json").read_text())
    science=json.loads((root/"SCIENTIFIC_DECISION.json").read_text())
    expected=spec["trials_per_path_bias"]*len(spec["paths"])*len(spec["true_bias_dps"])
    n_models=len(spec["models"])
    errs=[]
    if (receipt["git_sha"]!=final["commit"] or final["phase"]!="full"
        or final["exit_code"]!=0 or final["status"]!="FULL_P2_COMPLETED"):
        errs.append("INVALID_FULL_P2_FINAL")
    if not (final["completed_model_trials"]==expected*n_models
            and final["complete_four_model_pairs"]==expected
            and final["invalid_model_cases"]==len(fails)==0):
        errs.append("MISSING_VALID_ESTIMATOR_RESULTS")
    if len(rows)!=expected*n_models+1:
        errs.append("TRIAL_METRICS_ROW_COUNT")
    if len(groups)!=len(spec["paths"])*len(spec["true_bias_dps"]) or any(
        g["complete_four_model_pairs"]!=spec["trials_per_path_bias"] for g in groups):
        errs.append("INCOMPLETE_PAIRED_GROUPS")
    if len(contrasts)!=6*3 or len(science["per_route_primary"])!=3:
        errs.append("MISSING_CONTRASTS")
    for p,d in final.get("sha256_outputs",{}).items():
        path=root/p
        if not path.is_file() or sh(path)!=d:
            errs.append("OUTPUT_HASH_MISMATCH:"+p)
    inp=list(root.glob("trials/*/*/*/INPUTS.npz"))
    model_files=list(root.glob("trials/*/*/*/*/MODEL_RESULT.json"))
    traces=list(root.glob("trials/*/*/*/*/*.npz"))
    if not (len(inp)==expected and len(model_files)==expected*n_models
            and len(traces)==expected*n_models):
        errs.append("INCOMPLETE_RAW_INPUT_STATE_COVARIANCE_TRACES")
    case_keys=set()
    for path in inp:
        pp=path.relative_to(root).parts
        case_keys.add((pp[1],float(pp[2]),int(pp[3])))
    expected_keys={(p,float(b),trial) for p in spec["paths"]
                   for b in spec["true_bias_dps"] for trial in range(spec["trials_per_path_bias"])}
    if case_keys!=expected_keys:errs.append("MISSING_OR_DUPLICATED_SEEDS")
    if len(final.get("sha256_outputs",{}))<expected*(1+2*n_models):
        errs.append("SHORT_FINAL_OUTPUT_MANIFEST")
    record={"schema":"R4_FULL_P2_INDEPENDENT_ARCHIVE_RECEIPT_V1",
       "git_sha":os.getenv("GITHUB_SHA"),"source_sha256":{
         k:sh(HERE/k) for k in ("core.py","synthetic.py","P2_SPEC.json","p2_v2.py")},
       "frozen_pairs":expected,"models":n_models,"model_cases":expected*n_models,
       "paired_valid":final["complete_four_model_pairs"],
       "invalid_cases":final["invalid_model_cases"],
       "input_archives":len(inp),"model_result_receipts":len(model_files),
       "trace_archives":len(traces),"manifest_count":len(final.get("sha256_outputs",{})),
       "groups":groups,"contrasts":contrasts,
       "scientific_decision":science,
       "audited_errors":errs,"pass":not errs,
       "scientific_PASS":False,
       "time_utc":datetime.now(timezone.utc).isoformat()}
    (out/"FINAL.json").write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n")
    print("R4_FULL_RECEIPT "+json.dumps({k:record[k] for k in
       ("pass","audited_errors","frozen_pairs","model_cases","paired_valid","invalid_cases",
        "input_archives","trace_archives","manifest_count")},ensure_ascii=False),flush=True)
    return 0 if not errs else 2

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--full",required=True)
    a.add_argument("--audit",required=True)
    a.add_argument("--out",required=True)
    v=a.parse_args()
    raise SystemExit(verify(v.full,v.audit,v.out))
