"""Read-only final per-file SHA/identity/denominator audit of P4 evidence."""
from __future__ import annotations
import argparse,json,os,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from p4_pre_run_audit import require_p4_audit,digest
from p4_one_step_models import BIAS_PRIOR_STD_RAD_S
from p4_frozen_cases import P0

def read(p):return json.loads(Path(p).read_text())
def audit(run_root,preaudit,index,canary,fixed,map_dir,score_dir,out):
    prior=require_p4_audit(preaudit)
    idx=read(index)
    c=read(Path(canary)/"P4_PHASE_FINAL.json")
    f=read(Path(fixed)/"P4_FIXED_FINAL.json")
    m=read(Path(map_dir)/"P4_MAP_FINAL.json")
    s=read(Path(score_dir)/"P4_SCORE_FINAL.json")
    errors=[]
    sha=os.environ["GITHUB_SHA"]
    if any(x.get("git_sha")!=sha for x in (idx,c,f,m,s)):
        errors.append("INCONSISTENT_SOURCE_IDENTITY")
    if idx["status"]!="PASS" or len(idx["cases"])!=14 or idx["sample_count"]!=14502:
        errors.append("INPUT_INDEX_NOT_VALID")
    if c["exit_code"]!=0 or c["status"] not in ("PASS","PASS_WITH_SCOPED_NUMERIC_INVALIDS"):
        errors.append("CANARY_STATUS_NOT_ELIGIBLE")
    if f["status"]!="P4_FIXED_LINEAR_PARITY_PASS" or f["total"]!=14502:
        errors.append("FIXED_TECHNICAL_PARITY_FAIL")
    if m["status"]!="P4_NONLINEAR_ONE_STEP_EVALUATED" or m["total_frames"]!=14502:
        errors.append("MAP_COMPLETENESS_FAIL")
    if s["status"]!="EVALUATED" or len(s["metrics"])!=112:
        errors.append("OFFLINE_METRIC_COUNTS_INVALID")
    manifests={}
    nfix=nmap=eligible=rejected=converged=invalid=0
    for d in idx["cases"]:
        stem=d["case"]+"_"+d["channel"]
        fpath=Path(fixed)/(stem+"_P4_FIXED.npz")
        mpath=Path(map_dir)/(stem+"_P4_MAP.npz")
        if not fpath.exists() or not mpath.exists():
            errors.append("RAW_TRACE_MISSING:"+stem);continue
        with np.load(fpath,allow_pickle=False) as a:
            if a["estimate"].shape!=(d["n"],6,4) or a["covariance"].shape!=(d["n"],6,4,4):
                errors.append("FIXED_SHAPE:"+stem)
            if len(np.unique(a["pose_id"]))!=d["n"]:
                errors.append("FIXED_POSE_DUPLICATE:"+stem)
            a_count=int(a["accepted"].sum())
            if a_count!=d["eligible"]:
                errors.append("ACCEPTANCE_COUNT_MISMATCH:"+stem)
            nfix+=len(a["t_s"]);eligible+=a_count;rejected+=d["n"]-a_count
        with np.load(mpath,allow_pickle=False) as a:
            if a["estimate"].shape!=(d["n"],2,4) or a["covariance"].shape!=(d["n"],2,4,4):
                errors.append("MAP_SHAPE:"+stem)
            labels=a["status"]
            if not set(labels.ravel()).issubset({"CONVERGED","GATE_REJECT","MISSING","NUMERICAL_INVALID"}):
                errors.append("MAP_UNRECOGNIZED_STATUS:"+stem)
            v=int(np.count_nonzero(labels=="CONVERGED"))
            q=int(np.count_nonzero(labels=="NUMERICAL_INVALID"))
            if v+q!=2*d["eligible"]:
                errors.append("MAP_PAIR_GATE_DENOMINATOR:"+stem)
            if np.any(np.isnan(a["estimate"][labels=="CONVERGED"])):
                errors.append("MAP_VALID_STATE_NAN:"+stem)
            if not np.all(np.isnan(a["estimate"][labels=="NUMERICAL_INVALID"])):
                errors.append("MAP_INVALID_OUTPUT_NOT_NULL:"+stem)
            nmap+=len(a["t_s"]);converged+=v;invalid+=q
        manifests[str(fpath)]=digest(fpath)
        manifests[str(mpath)]=digest(mpath)
    if not(nfix==nmap==14502 and eligible==14186 and rejected==316
            and converged+invalid==2*14186
            and invalid==m["invalid_model_updates"]):
        errors.append("FULL_P4_CONTRACT_COUNTS_MISMATCH")
    snaps=list((Path(map_dir)/"P4_FAILURE_SNAPSHOTS").glob("*.json"))
    if len(snaps)!=invalid:
        errors.append(f"MISSING_FAILURE_RAW_SNAPSHOTS {len(snaps)} != {invalid}")
    # All source artifacts are included in the manifest, along with all
    # independently-scored outputs. No output folder overwrite is permitted.
    for dr in (canary,fixed,map_dir,score_dir):
        for item in Path(dr).rglob("*"):
            if item.is_file():manifests[str(item)]=digest(item)
    final={
       "schema":"EKF4_R4_P4_FINAL_AUDIT_V1",
       "git_sha":sha,"run_id":os.environ.get("GITHUB_RUN_ID"),
       "preaudit_sha256":digest(preaudit),
       "input_index_sha256":digest(index),
       "p3_source_sha":prior["P3_original_sha"],
       "model_scope":"one-step frozen original DR prior, no recursive RF transfer",
       "full_total_timepoints":nfix,
       "gate_eligible":eligible,"gate_rejected":rejected,
       "map_converged_model_updates":converged,
       "map_numerically_invalid_updates":invalid,
       "fixed_technical_PASS":not any("FIXED" in e or "SOURCE" in e for e in errors),
       "nonlinear_one_step_evaluated":nmap==14502,
       "full_MAP_numerical_PASS":invalid==0,
       "scientific_PASS":False,
       "P5":"NOT_RUN","P6":"NOT_RUN",
       "source_archive_manifest":manifests,
       "file_count":len(manifests),
       "audit_errors":errors,
       "status":"P4_COMPLETED_WITH_SCOPED_NUMERICAL_INVALIDS" if (not errors and invalid)
             else ("P4_COMPLETED_TECHNICAL_PASS" if not errors else "HARD_AUDIT_FAIL"),
       "exit_code":0 if not errors else 2,
       "ended_utc":datetime.now(timezone.utc).isoformat()}
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    (out/"P4_FINAL.json").write_text(json.dumps(final,indent=2,ensure_ascii=False)+"\n")
    print("P4_FINAL "+json.dumps({k:final[k] for k in
        ("status","exit_code","full_total_timepoints","gate_eligible",
         "map_converged_model_updates","map_numerically_invalid_updates",
         "fixed_technical_PASS","full_MAP_numerical_PASS","audit_errors")},
         ensure_ascii=False),flush=True)
    return final["exit_code"]

if __name__=="__main__":
    p=argparse.ArgumentParser()
    for a in ("run-root","preaudit","index","canary","fixed","map","score","out"):
        p.add_argument("--"+a,required=True)
    a=p.parse_args()
    raise SystemExit(audit(a.run_root,a.preaudit,a.index,a.canary,a.fixed,a.map,a.score,a.out))
