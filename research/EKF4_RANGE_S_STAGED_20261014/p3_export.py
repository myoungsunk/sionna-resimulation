"""P3 P4-handoff read-only final validation and source-bound evidence index."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from p3_frozen_inputs import assert_audit, sha_file

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def export(audit,source,parity,junit,out):
    receipt=assert_audit(audit)
    input_data=json.loads(Path(source).read_text())
    p=json.loads(Path(parity).read_text())
    xml=ET.parse(junit).getroot()
    suites=xml.findall("testsuite")
    if xml.tag=="testsuite":
        suites=[xml]
    counts={k:sum(int(s.attrib.get(k,"0")) for s in suites)
            for k in ("tests","failures","errors","skipped")}
    errors=[]
    if not(counts["tests"]>=10 and counts["failures"]==counts["errors"]==counts["skipped"]==0):
        errors.append("TEST_CONTRACT_NOT_ALL_PASS:"+repr(counts))
    if not(input_data["status"]=="PASS" and input_data["git_sha"]==os.environ["GITHUB_SHA"]
           and input_data["verified_steps"]==14502 and len(input_data["cases"])==14):
        errors.append("INPUTS_NOT_ELIGIBLE")
    if not(p["status"]=="PASS" and p["git_sha"]==os.environ["GITHUB_SHA"]
           and p["verified_timepoints"]==14502
           and p["detected_parity_points"]==14502
           and len(p["cases"])==14):
        errors.append("PARITY_NOT_COMPLETE")
    if max(float(p.get("max_h_abs",float("inf"))),0.)>1e-8:
        errors.append("H_FORWARD_MODEL_PARITY_FAILED")
    if p.get("max_H_abs",float("inf"))>1e-5:
        errors.append("JACOBIAN_PARITY_FAILED")
    data_path=Path(parity).parent/"P3_PARITY.csv"
    status_path=Path(parity).parent/"P3_CASE_STATUS.csv"
    if not(data_path.is_file() and status_path.is_file()):
        errors.append("MISSING_PARITY_CSV_EVIDENCE")
    else:
        with data_path.open(newline="") as f:
            rows=list(csv.DictReader(f))
        if len(rows)!=14502 or len({
          (r["case"],r["channel"],r["pose_id"]) for r in rows})!=14502:
            errors.append("DUPLICATED_OR_MISSING_POSE_PARITY")
    expected_pair={(c["case"],c["channel"]) for c in input_data["cases"]}
    actual_pair={(c["case"],c["channel"]) for c in p["cases"]}
    if expected_pair!=actual_pair:
        errors.append("SOURCE_AND_MODEL_CASE_SET_DIFFERENT")
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    contract={
      "schema":"EKF4_P3_CANONICAL_ADAPTER_CONTRACT_V1",
      "source_commit":os.environ["GITHUB_SHA"],
      "observation_order":["range_raw_m","s"],
      "state_order":["px_m","py_m","yaw_rad","gyro_bias_rad_s"],
      "R0":{"range_variance_m2":0.0068578637,"s_variance":0.0081,
            "cross_covariance":0.,"cross_covariance_calibrated":False},
      "range_offset_mean_m":-0.5315983906250129,
      "bias_column_zero_direct":True,
      "case_count":7,"channel_count_per_case":2,
      "sample_count":14502,
      "source_run_id":38331588521,
      "source_artifact_id":11782748118,
      "source_archive_sha256":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
      "input_receipt_sha256":sha_file(source),
      "parity_receipt_sha256":sha_file(parity),
      "parity_csv_sha256":sha_file(data_path) if data_path.exists() else None,
      "case_status_csv_sha256":sha_file(status_path) if status_path.exists() else None,
      "negative_unit_tests":counts,
      "source_sha256":receipt["source_sha256"],
      "truth_access":"offline scoring only; excluded from FrozenRFTrace",
      "physical_scene_independence":"one corridor, fixed H; 14 traces are case-channel, not independent scenes",
      "P4":"NOT_RUN","P5":"NOT_RUN","P6":"NOT_RUN",
      "scientific_PASS":False,
      "validation_errors":errors,
      "status":"P3_INPUT_ELIGIBLE_AND_ADAPTER_PARITY_PASS" if not errors else "P3_INVALID",
      "end_utc":datetime.now(timezone.utc).isoformat()
    }
    (out/"P3_ADAPTER_INDEX.json").write_text(json.dumps(contract,indent=2,ensure_ascii=False)+"\n")
    final={**contract,
           "exit_code":0 if not errors else 2,
           "P3_technical_PASS":not errors}
    (out/"P3_FINAL.json").write_text(json.dumps(final,indent=2,ensure_ascii=False)+"\n")
    print("P3_FINAL "+json.dumps({k:final[k] for k in
            ("status","exit_code","P3_technical_PASS","sample_count",
             "case_count","scientific_PASS","validation_errors")},
            ensure_ascii=False),flush=True)
    return final["exit_code"]

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--audit",type=Path,required=True)
    cli.add_argument("--source",type=Path,required=True)
    cli.add_argument("--parity",type=Path,required=True)
    cli.add_argument("--junit",type=Path,required=True)
    cli.add_argument("--out",type=Path,required=True)
    args=cli.parse_args()
    raise SystemExit(export(args.audit,args.source,args.parity,args.junit,args.out))
