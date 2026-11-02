"""Audit-bound exact five-case R3 numeric failure regression for R4 P2.

Read immutable original run 38562146793, archive 11892566974.
Both original Range-first and saved-final iterate are re-solved with same
fixed P2 objective and original 1e-8 gradient criterion.
No threshold relaxation, no truth data, no synthetic input modification.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import zipfile
import numpy as np
from core import SyntheticRF, map_update
from pre_run_audit import require_audit_receipt
from validate import sha, write

ORIGINAL_SHA="2547f147ea347563a186a886bd25a543871825f3"
ARTIFACT_SHA="931ee7cd8552820f3b6311877bb6ccc4ecc910669231290efb82e5868756c9b4"
CASES=[
    ("straight",0.0,0,"MAP3",84,"bd96668a8737c27105d3048433e39d038aa44c25765e4da126d8152bc4fe015c"),
    ("straight",0.0,0,"MAP4",74,"94b86e64df1896e88e0b4a60f4868d69c8d5f07244e7050b88b934d39e8a97c0"),
    ("straight",0.05,0,"MAP4",60,"b5bb6163073af2dab9e30f009853c3e90895c565a06111c5c334e417c7489e3a"),
    ("turn",0.05,0,"MAP3",63,"5d9b5c683feeb140bdf6d675956730b337623d626a78bd738875095229e5d341"),
    ("return",0.05,0,"MAP3",63,"a3840e530eb427ae3da02e32d68b5d3af99062f43e25776a9e1b7eb87d8592a0"),
]
HERE=Path(__file__).resolve().parent
digest=lambda data:hashlib.sha256(data).hexdigest()


def run(artifact,audit_path,out):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False)
    audit=require_audit_receipt(audit_path)
    result={"schema":"R4_ORIGINAL_FIVE_FIXED_FAILURE_REPLAY_V1",
        "git_sha":os.environ["GITHUB_SHA"],
        "source_run_id":38562146793,
        "source_commit":ORIGINAL_SHA,
        "original_zip_sha256":ARTIFACT_SHA,
        "audit_sha256":sha(audit_path),
        "criterion":{"gradient_inf":1e-8,"max_iter":80},
        "cases":[],"status":"STARTED","scientific_PASS":False}
    write(out/"START.json",result)
    try:
        if digest(Path(artifact).read_bytes()) != ARTIFACT_SHA:
            raise RuntimeError("Original archive hash mismatch")
        with zipfile.ZipFile(artifact) as zf:
            if zf.testzip() is not None:raise RuntimeError("Original archive CRC fail")
            prefix="_temp/p2_preflight/"
            old_final=json.loads(zf.read(prefix+"FINAL.json"))
            invalid=json.loads(zf.read(prefix+"CASE_INVALID.json"))
            if not (old_final["commit"]==ORIGINAL_SHA and
                    int(old_final["run_id"])==38562146793 and
                    old_final["invalid_model_cases"]==len(CASES)==5 and
                    old_final["phase"]=="preflight"):
                raise RuntimeError("Historical result metadata mismatch")
            keys={(x["path"],float(x["true_bias_dps"]),int(x["trial"]),x["model"]) for x in invalid}
            expected={(p,b,k,m) for p,b,k,m,_,_ in CASES}
            if keys!=expected:raise RuntimeError("Historical five-case set mismatch")
            for p,b,k,m,step,expected_sha in CASES:
                base=f"{prefix}trials/{p}/{b}/{k:03d}/{m}/"
                raw=zf.read(base+"FAILED_STEP.npz")
                if digest(raw)!=expected_sha:raise RuntimeError("Individual original fixture mismatch: "+base)
                old=json.loads(zf.read(base+"FAILURE.json"))
                if not(old["solver_status"]=="NUMERICALLY_STALLED" and old["step"]==step):
                    raise RuntimeError("Historical terminal snapshot mismatch: "+base)
                with np.load(io.BytesIO(raw),allow_pickle=False) as z:
                    mu,P,obs,R=(np.asarray(z[key]) for key in ("prior_x","prior_P","z","R"))
                    original_iterate=np.asarray(z["prior_delta"])
                records=[]
                for saved in (False,True):
                    kw={"range_first":not saved}
                    if saved:kw["initial_delta"]=original_iterate
                    trial=map_update(mu,P,obs,SyntheticRF(),R,
                        max_iter=80,gradient_tol=1e-8,**kw)
                    if trial.status!="CONVERGED" or trial.gradient_inf>1e-8:
                        raise RuntimeError(f"Fixed failure still unresolved {p}/{b}/{m} saved={saved}: {trial.status} g={trial.gradient_inf}")
                    Lp,Lr=np.linalg.cholesky(P),np.linalg.cholesky(R)
                    y=np.linalg.solve(Lp,trial.prior_delta)
                    h,H=SyntheticRF()(mu+trial.prior_delta)
                    v=np.linalg.solve(Lr,obs-h)
                    B=np.linalg.solve(Lr,H@Lp)
                    gradient=y-B.T@v
                    covariance=Lp@np.linalg.solve(np.eye(len(y))+B.T@B,Lp.T)
                    if max(abs(gradient))>1e-8 or abs(.5*(y@y+v@v)-trial.cost)>1e-12:
                        raise RuntimeError("Independent gradient/objective mismatch: "+base)
                    np.testing.assert_allclose(trial.P,covariance,atol=1e-12,rtol=1e-9)
                    if any(not np.isfinite(h["cost"]) for h in trial.history):
                        raise RuntimeError("Nonfinite intermediate objective")
                    if any(h.get("step_acceptance")=="STABLE_OBJECTIVE_DESCENT"
                           and (not np.isfinite(h.get("stable_delta",float("nan")))
                                or h["stable_delta"]>=0) for h in trial.history):
                        raise RuntimeError("Invalid signed stable descent")
                    records.append({"saved_start":saved,"gradient_inf":trial.gradient_inf,
                         "iterations":trial.iterations,"objective":trial.cost,
                         "stable_step_count":sum(h.get("step_acceptance")=="STABLE_OBJECTIVE_DESCENT"
                           for h in trial.history)})
                record={"path":p,"bias_dps":b,"trial":k,"model":m,
                    "old_step":step,"old_gradient_inf":old["gradient_inf"],
                    "source_npz_sha256":expected_sha,"new_results":records}
                result["cases"].append(record)
                print("R4_FIVE_CASE "+json.dumps(record,ensure_ascii=False),flush=True)
                write(out/"PROGRESS.json",result)
        result.update({"status":"PASS","exit_code":0,"five_cases_valid":5,
          "start_modes_checked":10,"finished_utc":datetime.now(timezone.utc).isoformat()})
        write(out/"FINAL.json",result)
        print("R4_FIVE_FINAL "+json.dumps({"status":"PASS","five_cases_valid":5,
              "start_modes_checked":10,"git_sha":result["git_sha"]}),flush=True)
        return 0
    except Exception as exc:
        result.update({"status":"FAILED","exit_code":2,"error":str(exc)})
        write(out/"FINAL.json",result)
        raise


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifact",type=Path,required=True)
    p.add_argument("--audit",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    raise SystemExit(run(a.artifact,a.audit,a.out))
