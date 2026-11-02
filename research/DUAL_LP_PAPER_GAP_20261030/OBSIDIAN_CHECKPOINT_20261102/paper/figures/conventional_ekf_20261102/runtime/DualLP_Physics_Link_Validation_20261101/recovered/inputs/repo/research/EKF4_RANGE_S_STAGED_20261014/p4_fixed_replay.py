"""Audit-bound P4 canary, full frozen-linear, and local MAP one-step execution.

Every frame is independent (restarts from original DR-only prior). No truth in
this script; scoring is deferred to a separate post-inference script.
"""
from __future__ import annotations
import argparse,csv,json,math,os,traceback
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from p4_pre_run_audit import require_p4_audit, digest
from p4_frozen_cases import load_cases,original_joint_posterior
from p3_rf_adapter4 import FrozenLut
from p4_one_step_models import common_gate,fixed_methods,map_methods

FIXED=("D0","J3","J4","SF4_R","SF4_S","SR4")
MAP=("M4_P","M4_R")
EXPECTED_COUNTS={"total":14502,"accepted":14186,"rejected":316}
def write(path,data):
    p=Path(path);p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n")

def compact(obj):
    if isinstance(obj,np.ndarray):return obj.tolist()
    if isinstance(obj,(np.integer,np.floating)):return obj.item()
    raise TypeError(type(obj).__name__)

def canary_indices(trace):
    t=trace.t_s;n=len(t)
    selected={0,int(np.flatnonzero(t>=30.)[0]),n//2,n-1,
              int(np.argmax(trace.nis))}
    for time in (30.,180.4):
        nearest=int(np.argmin(abs(t-time)))
        if abs(float(t[nearest])-time)<1e-5:
            selected.add(nearest)
    return sorted(selected)

def diag_name(case,channel,k,method):
    return f"{case}_{channel}_k{k:04d}_{method}"

def record_map_failure(folder,case,trace,k,which,prior,diag):
    folder.mkdir(parents=True,exist_ok=True)
    stem=diag_name(case["id"],trace.channel,k,which)
    obj={"case":case["id"],"channel":trace.channel,
         "pose_id":int(trace.pose_id[k]),"k":int(k),
         "t_s":float(trace.t_s[k]),"method":which,
         "prior_mu4":prior["mu4"].tolist(),
         "prior_P4":prior["P4"].tolist(),
         "z_range_s":prior["z"].tolist(),
         "R":prior["R"].tolist(),
         "H_at_prior":prior["H"].tolist(),
         "h_at_prior":prior["h"].tolist(),
         "nis":prior["nis"],
         "source_note":"P3 frozen physical RF, one-step numerical invalid; not an accepted estimate",
         "solver":diag}
    write(folder/(stem+".json"),obj)
    return stem

def safe_map(prior,case,lut):
    try:
        return map_methods(prior,case,lut)
    except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
        d={"status":"NUMERICAL_EXCEPTION","error_type":type(exc).__name__,
           "error":str(exc),"traceback":traceback.format_exc()}
        return [(None,None,"NUMERICAL_INVALID",d),
                (None,None,"NUMERICAL_INVALID",d)]

def stage_canary(archive,out,lut):
    rows=[];cases=[];failures=[]
    for case,trace in load_cases(archive):
        for k in canary_indices(trace):
            prior=common_gate(trace,k,case,lut)
            fixed,parity=fixed_methods(prior,case,lut)
            rec={"case":case["id"],"channel":trace.channel,
                 "route":case["route"],"k":k,
                 "pose_id":int(trace.pose_id[k]),
                 "t_s":float(trace.t_s[k]),
                 "common_gate":prior["status"],"nis":prior.get("nis"),
                 "fixed_linear_parity":parity,
                 "methods":{}}
            maps=safe_map(prior,case,lut)
            for method,(x,P,status,diag) in zip(MAP,maps):
                rec["methods"][method]={"status":status,
                    "gradient_inf":None if diag is None else diag.get("gradient_inf"),
                    "iterations":None if diag is None else diag.get("iterations")}
                if status=="NUMERICAL_INVALID":
                    path=record_map_failure(out/"P4_FAILURE_SNAPSHOTS",case,trace,k,method,prior,diag)
                    failures.append({"case":case["id"],"channel":trace.channel,
                                     "pose_id":int(trace.pose_id[k]),"k":k,
                                     "method":method,"snapshot":path})
            rows.append(rec)
        cases.append({"case":case["id"],"channel":trace.channel,
                      "canary_steps":len(canary_indices(trace))})
        print("P4_CANARY_CASE "+json.dumps({**cases[-1],
              "total_numeric_failures":len(failures)}),flush=True)
    write(out/"P4_C_CANARY.json",{
        "rows":rows,"cases":cases,"failures":failures,
        "status":"CANARY_COMPUTED_WITH_INVALID_CASES" if failures else "PASS",
        "history_repro_note":"Older R3 30.0/180.4s may use different prior; time match does not mean same failure fixture.",
        "scientific_PASS":False})
    if len(cases)!=14:raise RuntimeError("CANARY_CASE_COUNT_MISMATCH")
    return {"canary_frames":len(rows),"map_numerically_invalid":len(failures),
            "status":"PASS_WITH_SCOPED_NUMERIC_INVALIDS" if failures else "PASS"}

def pad(x,C):
    n=len(x)
    if n==4:return x,C
    p=np.full(4,np.nan);p[:n]=x
    cov=np.full((4,4),np.nan);cov[:n,:n]=C
    return p,cov

def stage_fixed(archive,out,lut):
    cases=[];n_total=0;rejected=0;eligible=0
    for case,trace in load_cases(archive):
        n=len(trace.t_s)
        x=np.full((n,len(FIXED),4),np.nan)
        P=np.full((n,len(FIXED),4,4),np.nan)
        nis=np.full(n,np.nan)
        accepted=np.zeros(n,bool)
        status=np.empty(n,dtype="<U20")
        errors={}
        refx,refP=original_joint_posterior(archive,case["id"],trace.channel)
        max_refx=max_refP=0.
        for k in range(n):
            prior=common_gate(trace,k,case,lut)
            fixed,parity=fixed_methods(prior,case,lut)
            status[k]=prior["status"]
            nis[k]=float(prior["nis"]) if prior["nis"] is not None else np.nan
            accepted[k]=bool(prior["accepted"])
            for j,name in enumerate(FIXED):
                x[k,j],P[k,j]=pad(*fixed[name])
            d3=x[k,1,:3]-refx[k]
            d3[2]=(d3[2]+np.pi)%(2*np.pi)-np.pi
            max_refx=max(max_refx,float(np.max(abs(d3))))
            max_refP=max(max_refP,float(np.max(abs(P[k,1,:3,:3]-refP[k]))))
            if max_refx>1e-9 or max_refP>1e-9:
                raise RuntimeError(f"ARCHIVED_J3_POSTERIOR_MISMATCH {case['id']} {trace.channel} step={k} pos={max_refx} cov={max_refP}")
            if parity.get("accepted"):
                for key,val in parity.items():
                    if key!="accepted":errors[key]=max(errors.get(key,0.),float(val))
        if max(errors.values(),default=0.)>1e-9:
            raise RuntimeError("FROZEN_JOINT_SEQUENTIAL_PARITY_OVER_THRESHOLD")
        unique=f"{case['id']}_{trace.channel}"
        np.savez_compressed(out/(unique+"_P4_FIXED.npz"),
                            t_s=trace.t_s,pose_id=trace.pose_id,
                            methods=np.array(FIXED),estimate=x,covariance=P,
                            nis=nis,accepted=accepted,status=status)
        cnt={"case":case["id"],"channel":trace.channel,"n":n,
             "accepted":int(accepted.sum()),
             "rejected":int((~accepted).sum()),
             "original_j3_max_pose":max_refx,
             "original_j3_max_cov":max_refP,
             "max_parity":max(errors.values(),default=0.),
             "source_trace_pose_first":int(trace.pose_id[0]),
             "source_trace_pose_last":int(trace.pose_id[-1])}
        cases.append(cnt);n_total+=n;eligible+=cnt["accepted"];rejected+=cnt["rejected"]
        print("P4_FIXED_CASE "+json.dumps(cnt),flush=True)
        write(out/"P4_FIXED_PROGRESS.json",{"cases":cases,"n":n_total,
                                          "accepted":eligible,"rejected":rejected})
    if not(n_total==EXPECTED_COUNTS["total"] and eligible==EXPECTED_COUNTS["accepted"]
            and rejected==EXPECTED_COUNTS["rejected"] and len(cases)==14):
        raise RuntimeError(f"FULL_FIXED_COUNTS_INCORRECT n={n_total}, eligible={eligible}, rejected={rejected}")
    result={"schema":"P4_FIXED_LINEAR_FULL_V1","git_sha":os.environ["GITHUB_SHA"],
            "status":"P4_FIXED_LINEAR_PARITY_PASS","cases":cases,
            "model_names":FIXED,"total":n_total,
            "common_accepted":eligible,"common_rejected":rejected,
            "scientific_PASS":False}
    write(out/"P4_FIXED_FINAL.json",result)
    return {"status":result["status"],"count":n_total,"accepted":eligible}

def stage_map(archive,out,lut):
    cases=[];n_total=0;done=0;failures=0;rejected=0
    for case,trace in load_cases(archive):
        n=len(trace.t_s);estim=np.full((n,2,4),np.nan)
        cov=np.full((n,2,4,4),np.nan)
        status=np.full((n,2),"NOT_RUN",dtype="<U24")
        iterations=np.full((n,2),-1,int)
        gradients=np.full((n,2),np.nan)
        failed_input=[];accepted=0
        for k in range(n):
            prior=common_gate(trace,k,case,lut)
            if prior["accepted"]:accepted+=1
            results=safe_map(prior,case,lut)
            for j,(x,P,s,diagnostic) in enumerate(results):
                status[k,j]=s
                if x is not None:estim[k,j]=x;cov[k,j]=P
                if diagnostic is not None:
                    iterations[k,j]=diagnostic.get("iterations",-1)
                    gradients[k,j]=diagnostic.get("gradient_inf",np.nan)
                if s=="NUMERICAL_INVALID":
                    key=record_map_failure(out/"P4_FAILURE_SNAPSHOTS",
                                           case,trace,k,MAP[j],prior,diagnostic)
                    failed_input.append({"name":key,"k":k,"model":MAP[j],
                                         "t_s":float(trace.t_s[k]),
                                         "gradient_inf":diagnostic.get("gradient_inf")})
        name=case["id"]+"_"+trace.channel
        np.savez_compressed(out/(name+"_P4_MAP.npz"),
                            t_s=trace.t_s,pose_id=trace.pose_id,
                            methods=np.array(MAP),estimate=estim,
                            covariance=cov,status=status,
                            iterations=iterations,gradient_inf=gradients)
        done_case=int(np.count_nonzero(status=="CONVERGED"))
        failed_case=int(np.count_nonzero(status=="NUMERICAL_INVALID"))
        invalid_count_by_model={m:int(np.count_nonzero(status[:,j]=="NUMERICAL_INVALID"))
                                for j,m in enumerate(MAP)}
        row={"case":case["id"],"channel":trace.channel,"samples":n,
             "gate_eligible":accepted,
             "converged_updates":done_case,"invalid_updates":failed_case,
             "invalid_by_model":invalid_count_by_model,
             "failure_examples":failed_input[:8]}
        cases.append(row)
        n_total+=n;done+=done_case;failures+=failed_case;rejected+=n-accepted
        write(out/"P4_MAP_PROGRESS.json",{"cases":cases,"processed_times":n_total,
              "converged_model_updates":done,"invalid_model_updates":failures,
              "gate_rejected_frames":rejected,"scientific_PASS":False})
        print("P4_MAP_CASE "+json.dumps(row),flush=True)
    if not(n_total==14502 and rejected==316 and done+failures==14186*2):
        raise RuntimeError(f"P4_MAP_COUNTS_INVALID n={n_total} reject={rejected},valid={done},fail={failures}")
    final={"schema":"P4_LOCAL_MAP_FULL_V1","git_sha":os.environ["GITHUB_SHA"],
           "status":"P4_NONLINEAR_ONE_STEP_EVALUATED",
           "total_frames":n_total,"gate_eligible":14186,
           "converged_model_updates":done,"invalid_model_updates":failures,
           "gate_rejected_frames":rejected,
           "cases":cases,"scientific_PASS":False}
    write(out/"P4_MAP_FINAL.json",final)
    return {"status":final["status"],"converged":done,"invalid":failures}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--phase",required=True,choices=("canary","fixed","map"))
    ap.add_argument("--archive",required=True,type=Path)
    ap.add_argument("--audit",required=True,type=Path)
    ap.add_argument("--input-index",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    a=ap.parse_args()
    require_p4_audit(a.audit)
    idx=json.loads(a.input_index.read_text())
    if not(idx["status"]=="PASS" and idx["git_sha"]==os.environ["GITHUB_SHA"]
           and idx["sample_count"]==14502 and idx["rejected"]==316):
        raise RuntimeError("P4_INPUT_GATE_INVALID")
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    start={"phase":a.phase,"git_sha":os.getenv("GITHUB_SHA"),
           "start_utc":datetime.now(timezone.utc).isoformat(),
           "status":"STARTED","archive_sha256":digest(a.archive),
           "p4_input_index_sha256":digest(a.input_index),
           "scientific_PASS":False}
    write(out/"P4_START.json",start)
    try:
        lut=FrozenLut()
        result={"canary":stage_canary,"fixed":stage_fixed,"map":stage_map}[a.phase](a.archive,out,lut)
        final={**start,**result,"exit_code":0,
               "end_utc":datetime.now(timezone.utc).isoformat()}
        write(out/"P4_PHASE_FINAL.json",final)
        print("P4_PHASE_FINAL "+json.dumps({k:final.get(k) for k in
              ("phase","status","exit_code","count","accepted","converged","invalid","canary_frames","map_numerically_invalid")}),flush=True)
        return 0
    except Exception as exc:
        write(out/"P4_PHASE_FINAL.json",{**start,"status":"HARD_EXECUTION_ERROR",
           "error":repr(exc),"traceback":traceback.format_exc(),"exit_code":2})
        raise
if __name__=="__main__":raise SystemExit(main())
