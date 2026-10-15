"""Post-inference truth-only offline scorer for P4 stored one-step results.

This is the ONLY P4 module reading "truth_for_offline_scoring_only".
It is NEVER called by an estimator or RF measurement adapter.
"""
from __future__ import annotations
import argparse,csv,io,json,math,os,zipfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from p4_pre_run_audit import require_p4_audit,digest
from p4_frozen_cases import P0
from p3_frozen_inputs import open_verified_archive
FIXED=("D0","J3","J4","SF4_R","SF4_S","SR4")
MAP=("M4_P","M4_R")
def metrics(states,covariances,truth,mask):
    valid=mask&np.isfinite(states[:,:3]).all(axis=1)&np.isfinite(covariances[:,:3,:3]).all(axis=(1,2))
    n=int(np.count_nonzero(valid))
    if n==0:return {"evaluated":0,"position_RMSE_m":None,
                    "heading_RMSE_deg":None,"pose_NEES_mean":None,
                    "heading_NEES_mean":None,"pose95":None,"heading95":None}
    e=states[valid,:3]-truth[valid]
    e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
    C=covariances[valid,:3,:3]
    if min(np.linalg.eigvalsh(C).min(axis=1))<=0:
        raise RuntimeError("POSTERIOR_SCORE_P_NOT_PD")
    sol=np.linalg.solve(C,e[:,:,None])[:,:,0]
    nees=np.einsum("bi,bi->b",e,sol)
    hnees=e[:,2]**2/C[:,2,2]
    return {"evaluated":n,
            "position_RMSE_m":float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
            "heading_RMSE_deg":float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
            "pose_NEES_mean":float(np.mean(nees)),
            "heading_NEES_mean":float(np.mean(hnees)),
            "pose95":float(np.mean(nees<=7.814727903251179)),
            "heading95":float(np.mean(hnees<=3.841458820694124))}

def save_csv(path,rows):
    if not rows:return
    columns=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=columns)
        w.writeheader();w.writerows(rows)

def score(archive,fixed,maproot,audit,out):
    require_p4_audit(audit)
    fx=json.loads((Path(fixed)/"P4_PHASE_FINAL.json").read_text())
    mp=json.loads((Path(maproot)/"P4_PHASE_FINAL.json").read_text())
    if not(fx["status"]=="P4_FIXED_LINEAR_PARITY_PASS"
           and fx["exit_code"]==0
           and mp["status"]=="P4_NONLINEAR_ONE_STEP_EVALUATED"
           and mp["exit_code"]==0
           and fx["git_sha"]==mp["git_sha"]==os.environ["GITHUB_SHA"]):
        raise RuntimeError("P4_INFERENCE_NOT_FINISHED_BEFORE_TRUTH_SCORING")
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(P0.read_text())
    by_case={c["id"]:c for c in manifest["cases"]}
    all_rows=[];raw_scores=[]
    with open_verified_archive(archive) as z:
        summary=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
        for desc in summary["per_case"]:
            case,ch=desc["case"],desc["channel"]
            with np.load(io.BytesIO(z.read("P2_OUT/"+desc["trace_file"])),
                         allow_pickle=False) as original:
                # Offline truth used strictly after model outputs and their
                # input identity are frozen. No module calling MAP sees truth.
                truth=original["truth_for_offline_scoring_only"].copy()
                t=original["t_s"].copy()
                raw_r=original["z_r_m"].copy()
                raw_s=original["z_s"].copy()
                predicted=original["predicted_z"][:,2].copy()
            name=case+"_"+ch
            with np.load(Path(fixed)/(name+"_P4_FIXED.npz"),allow_pickle=False) as df:
                fstate=df["estimate"].copy();fP=df["covariance"].copy()
                t_fixed=df["t_s"].copy();faccept=df["accepted"].copy()
                ids_fixed=df["pose_id"].copy()
            with np.load(Path(maproot)/(name+"_P4_MAP.npz"),allow_pickle=False) as dm:
                mstate=dm["estimate"].copy();mP=dm["covariance"].copy()
                mstatus=dm["status"].copy();t_map=dm["t_s"].copy()
                ids_map=dm["pose_id"].copy()
            if not(np.array_equal(t,t_fixed) and np.array_equal(t,t_map)
                    and np.array_equal(ids_fixed,ids_map)):
                raise RuntimeError("SCORE_TRACE_TIME_OR_POSE_ID_MISMATCH")
            base=t>=30.
            for j,label in enumerate(FIXED):
                row={"case":case,"channel":ch,"route":by_case[case]["route"],
                     "model":label,"all_time_count":len(t),
                     "evaluation_count":int(base.sum()),
                     "common_gate_accepted_eval":int((base&faccept).sum()),
                     "common_gate_rejected_eval":int((base&~faccept).sum()),
                     "numerical_invalid":0,
                     **metrics(fstate[:,j],fP[:,j],truth,base)}
                all_rows.append(row)
            for j,label in enumerate(MAP):
                invalid=mstatus[:,j]=="NUMERICAL_INVALID"
                valid=np.isin(mstatus[:,j],("CONVERGED","GATE_REJECT","MISSING"))
                row={"case":case,"channel":ch,"route":by_case[case]["route"],
                     "model":label,"all_time_count":len(t),
                     "evaluation_count":int(base.sum()),
                     "common_gate_accepted_eval":int((base&faccept).sum()),
                     "common_gate_rejected_eval":int((base&~faccept).sum()),
                     "numerical_invalid":int(np.count_nonzero(base&invalid)),
                     **metrics(mstate[:,j],mP[:,j],truth,base&valid)}
                all_rows.append(row)
            rerr=raw_r-predicted[:,1]
            serr=raw_s-predicted[:,0]
            raw_scores.append({"case":case,"channel":ch,
                "route":by_case[case]["route"],"n_eval":int(base.sum()),
                "range_residual_mean_m":float(np.mean(rerr[base])),
                "range_residual_rmse_m":float(np.sqrt(np.mean(rerr[base]**2))),
                "s_residual_mean":float(np.mean(serr[base])),
                "s_residual_rmse":float(np.sqrt(np.mean(serr[base]**2)))})
    if len(all_rows)!=14*(len(FIXED)+len(MAP)):
        raise RuntimeError("SCORE_MODEL_CASE_COUNT_MISMATCH")
    for ch in ("los","full"):
        rows=[r for r in all_rows if r["channel"]==ch]
        if sum(r["evaluation_count"] for r in rows if r["model"]=="D0")!=6201:
            raise RuntimeError("P4_SCORE_EVALUATION_DENOMINATOR_MISMATCH")
    save_csv(out/"P4_METRICS.csv",all_rows)
    save_csv(out/"P4_RF_RESIDUALS.csv",raw_scores)
    result={"schema":"EKF4_P4_OFFLINE_SCORING_V1",
        "status":"EVALUATED","git_sha":os.environ["GITHUB_SHA"],
        "scoring_time_utc":datetime.now(timezone.utc).isoformat(),
        "input_model_comparison_done_before_truth":True,
        "per_case_model_rows":len(all_rows),
        "raw_observation_residual_case_channels":raw_scores,
        "metrics":all_rows,
        "statistics_warning":"Correlated timestamps, one corridor/seed0; no independent scene bootstrap.",
        "MAP_selection_warning":"Numerically invalid MAP results are excluded with denominators, not imputed.",
        "scientific_PASS":False}
    (out/"P4_SCORE_FINAL.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("P4_OFFLINE_SCORE "+json.dumps({
        "status":"EVALUATED","rows":len(all_rows),
        "map_invalid_evaluation_total":sum(r["numerical_invalid"] for r in all_rows),
        "channels":["los","full"]}),flush=True)
    return 0
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for a in ("archive","fixed","map","audit","out"):p.add_argument("--"+a,required=True)
    a=p.parse_args();raise SystemExit(score(a.archive,a.fixed,a.map,a.audit,a.out))
