"""Stage B signed-range eligibility, Stage C guarded radial controls,
Stage E0 archived radial shadow (NOT G2/G3), and Stage F dependency verdict.

All science entrypoints require an immediately preceding source-bound audit.
No online inference reads ground truth, gyro injection label, case name, or route.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import log_ndtr

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/"research/G2G3_AUDITED_MINIMAL_20261014"))
import model

C=json.loads((ROOT/"CONTRACT.json").read_text())
CM=json.loads((REPO/"research/G2G3_AUDITED_MINIMAL_20261014/CONTRACT.json").read_text())["model"]
OUT=REPO/"outputs/g2g3_bf"
INPUT=REPO/"inputs/range_audit"


def save(name,data):
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/name
    if path.exists():raise FileExistsError(f"Results may not overwrite: {name}")
    def obj(v):
        if isinstance(v,np.generic):return v.item()
        if isinstance(v,np.ndarray):return v.tolist()
        raise TypeError(f"Unsupported serialization {type(v)}")
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=obj,allow_nan=False),encoding="utf-8")


def audit(stage):
    gate=OUT/("PRE_RUN_"+stage+".json")
    if not gate.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: no audit "+stage)
    receipt=json.loads(gate.read_text())
    if not receipt["audited_code_matches_execution_sha"] or receipt["run_decision"] not in ("GO","GO_WITH_CLAIM_LIMITATION"):
        raise RuntimeError("HARD_EXECUTION_BLOCK: not audited")
    for p,h in receipt["source_sha256"].items():
        if hashlib.sha256((REPO/p).read_bytes()).hexdigest()!=h:
            raise RuntimeError("HARD_EXECUTION_BLOCK: audited file mutated")
    return receipt


def load_reference():
    acq=json.loads((INPUT/"ACQUISITION.json").read_text())
    if acq["zip_sha256"]!=C["source_artifact"]["sha256"]:
        raise RuntimeError("HARD_EXECUTION_BLOCK: reference artifact mismatch")
    for k,expected in acq["file_sha256"].items():
        if hashlib.sha256((INPUT/k).read_bytes()).hexdigest()!=expected:
            raise RuntimeError("HARD_EXECUTION_BLOCK: extracted file hash")
    return acq


def p_rf_more_accurate(d,sig,z):
    """Direct posterior probability of |z-r|<|d-r|, not P(DR fault,RF inlier)."""
    d,sig,z=np.broadcast_arrays(np.asarray(d,float),np.asarray(sig,float),np.asarray(z,float))
    a=model.infer(d,sig,z,CM)
    midpoint=(d+z)/2
    lo=float(CM["lower_slant_m"])
    factors=[]
    for fault in (False,True):
        vd=sig**2+(float(CM["fault_radial_std_m"])**2 if fault else 0.)
        for rf in CM["rf_components"]:
            vr=float(rf["std_m"])**2
            vp=vd*vr/(vd+vr)
            mp=(vr*d+vd*(z-float(rf["bias_m"])))/(vd+vr)
            sp=np.sqrt(vp)
            logr=log_ndtr((mp-midpoint)/sp)-log_ndtr((mp-lo)/sp)
            val=np.where(midpoint>lo,-np.expm1(np.minimum(logr,0.)),0.)
            factors.append(np.clip(val,0.,1.))
    below=np.sum(a["weights"]*np.stack(factors,axis=-1),axis=-1)
    result=np.where(d>z,below,np.where(d<z,1-below,0.))
    return a,np.clip(result,0.,1.)


def guarded_radial(d,sig,z,nis):
    a,pr=p_rf_more_accurate(d,sig,z)
    chosen=(d>z)&(nis>C["thresholds"]["rf_gate_NIS"])&(pr>=C["thresholds"]["rf_dominance"])
    updated=np.where(chosen,a["mean"],d)
    if np.any(~np.isfinite(updated)) or np.any(updated<CM["lower_slant_m"]):
        raise RuntimeError("CASE_RESULT_INVALID: invalid radial output")
    return dict(updated=updated,selected=chosen,p_better=pr,
                posterior_mean=a["mean"],posterior_var=a["variance"])


def b_stage():
    acq=load_reference()
    df=pd.read_csv(INPUT/"RAW_RF_UNIQUE.csv.gz")
    needed={"route","case","channel","correction","pose_id","r_true_m","z_rf_m","rf_signed_error_m"}
    if not needed.issubset(df.columns):
        raise RuntimeError(f"HARD_EXECUTION_BLOCK: input schema mismatch {sorted(needed-set(df.columns))}")
    if len(df)!=18603 or df.duplicated(["case","channel","correction","pose_id"]).any():
        raise RuntimeError("HARD_EXECUTION_BLOCK: RF grain mismatch")
    results=[]
    for (ch,cal),a in df.groupby(["channel","correction"]):
        for route in sorted(df["route"].unique()):
            train=a[a["route"]!=route]
            held=a[a["route"]==route]
            if not len(train) or not len(held):raise RuntimeError("Cannot form route holdout")
            resid_train=train["rf_signed_error_m"].to_numpy(float)
            resid_test=held["rf_signed_error_m"].to_numpy(float)
            tau=max(0.,-float(np.quantile(resid_train,.01)))
            coverage=float(np.mean(resid_test>=-tau))
            results.append(dict(channel=ch,model=cal,heldout_route=route,
                  train_n=len(train),holdout_n=len(held),
                  train_tau01_m=tau,observed_heldout_coverage=coverage,
                  gap_to_99pct=coverage-.99,
                  holdout_negative_frequency=float(np.mean(resid_test<0.)),
                  holdout_signed_RMSE_m=float(np.sqrt(np.mean(resid_test**2)))))
    feasibility=pd.read_csv(REPO/
       "research/EKF3_INDEPENDENT_20261013/diagnostics/h3_offline/results/H3_OFFLINE_20261014_01a1380d/SPATIAL_HOLDOUT_FEASIBILITY.csv")
    spatial=feasibility.groupby("heldout_route")["n_buffer_valid"].sum().to_dict()
    for route in ("R2","R5"):
        if int(spatial.get(route,-1))!=0:raise RuntimeError("Unexpected spatial eligibility drift")
    pd.DataFrame(results).to_csv(OUT/"B_ROUTE_HOLDOUT_CALIBRATION.csv",index=False)
    status="CLAIM_BLOCK_INDEPENDENT_CALIBRATION"
    summary=dict(stage="B",execution="PASS",calculation="PASS_DESCRIPTIVE",
      hypothesis="INDEPENDENT_CALIBRATION_NOT_SUPPORTED_BY_CURRENT_SCENES",
      scientific_claim=status,scientific_PASS=False,
      n_unique_rf=len(df),route_fold_results=results,
      original_0p5m_buffer_valid_counts=spatial,
      observations="Route split performed, but R2/R5 have zero spatially eligible training at frozen 0.5 m buffer. Folds are NOT independent spatial scenes.",
      next="C synthetic math may run under frozen uncalibrated baseline; online calibrated adoption remains blocked.")
    save("B_RESULT.json",summary)
    print("STAGE_B",status,"route_coverages",[round(q["observed_heldout_coverage"],4) for q in results],flush=True)
    return summary


def c_stage():
    fixture=json.loads((REPO/"research/G2G3_AUDITED_MINIMAL_20261014/CONTRACT.json").read_text())["fixtures"]
    cases=[]
    for f in fixture:
        dr=float(f["mu_dr"]);sig=float(f["sigma_dr"]);rf=float(f["rf"])
        nis=(rf-dr)**2/(sig**2+0.0068578637)
        # Only the three allowed observational quantities enter the estimator.
        a=guarded_radial(dr,sig,rf,nis)
        new=float(a["updated"]);chosen=bool(a["selected"]);pr=float(a["p_better"])
        truth=float(f["truth"])  # post-hoc SCORING ONLY
        expected=f["id"]=="C2_DR_drift"
        protect=f["id"] in ("C1_nominal","C3_RF_overcorrection","C4_RF_long_path")
        safe=(abs(new-dr)<C["C"]["no_unnecessary_move_C1_C3_C4"]) if protect else (abs(new-truth)+C["C"]["min_improvement_C2_m"]<abs(dr-truth))
        valid=bool(chosen==expected and safe)
        cases.append(dict(id=f["id"],mu_DR=dr,rf=rf,truth=truth,
          nis=nis,probability_RF_better=pr,RF_chosen=chosen,guarded_radial_m=new,
          DR_abs_error_m=abs(dr-truth),updated_abs_error_m=abs(new-truth),
          expected_RF_chosen=expected,hypothesis="SUPPORTED" if valid else "CONTRADICTED"))
    valid=all(r["hypothesis"]=="SUPPORTED" for r in cases)
    result=dict(stage="C",execution="PASS",calculation="PASS",
      hypothesis="SUPPORTED_ON_FOUR_FIXED_SYNTHETIC_FIXTURES" if valid else "PARTIALLY_CONTRADICTED",
      scientific_claim="CLAIM_BLOCK_UNCALIBRATED_AND_NO_FULL_STATE",
      scientific_PASS=False,all_guardrails_passed=valid,controls=cases,
      next="D independent nonlinear integrator feasibility; if C contradicted, no new filter/threshold trial without revised contract")
    save("C_RESULT.json",result)
    print("STAGE_C",result["hypothesis"],[(r["id"],round(r["probability_RF_better"],4),r["RF_chosen"]) for r in cases],flush=True)
    return result


def e0_stage():
    b=json.loads((OUT/"B_RESULT.json").read_text())
    c_=json.loads((OUT/"C_RESULT.json").read_text())
    if b["calculation"]!="PASS_DESCRIPTIVE" or c_["calculation"]!="PASS":
        r=dict(stage="E0",execution="NOT_RUN_DEPENDENCY",calculation="NOT_RUN",
               scientific_claim="NOT_EVALUATED")
        save("E0_RESULT.json",r);return r
    load_reference()
    df=pd.read_csv(INPUT/"DR_RF_PAIRED_TRACE.csv.gz")
    if len(df)!=223236:raise RuntimeError("HARD_EXECUTION_BLOCK: paired grain changed")
    s2=df["dr_pred_range_sigma_m"].to_numpy(float)**2-0.0068578637
    if (s2<=0).any():raise RuntimeError("HARD_EXECUTION_BLOCK: DR prior negative sigma after Rr removal")
    dr=df["r_DR_m"].to_numpy(float);rf=df["z_rf_m"].to_numpy(float)
    out=guarded_radial(dr,np.sqrt(s2),rf,df["nis"].to_numpy(float))
    truth=df["r_true_m"].to_numpy(float)
    chosen=out["selected"]
    pred=out["updated"]
    df["guarded_radial_m"]=pred
    df["guarded_selected"]=chosen
    df["direct_probability"]=out["p_better"]
    df["eDR"]=dr-truth
    df["e_new"]=pred-truth
    df["eRF"]=rf-truth
    df.to_csv(OUT/"E0_RADIAL_SHADOW_TRACE.csv.gz",index=False,compression="gzip")
    summaries=[]
    for keys,g in df.groupby(["channel","correction","condition","level"],sort=True):
        e0=g["eDR"].to_numpy(float);en=g["e_new"].to_numpy(float)
        mask=g["guarded_selected"].to_numpy(bool)
        errors=g["eRF"].to_numpy(float)
        summaries.append(dict(zip(["channel","correction","condition","level"],keys),
          n=int(len(g)),selected=int(mask.sum()),
          selected_fraction=float(mask.mean()),
          false_selected_RF=int(np.sum(mask & (np.abs(errors)>=np.abs(e0)))),
          MAE_DR_m=float(np.mean(np.abs(e0))),
          MAE_guarded_m=float(np.mean(np.abs(en))),
          RMSE_DR_m=float(np.sqrt(np.mean(e0*e0))),
          RMSE_guarded_m=float(np.sqrt(np.mean(en*en))),
          selected_rescue_delta_MAE_m=float(np.mean(np.abs(e0[mask])-np.abs(en[mask]))) if mask.any() else None))
    pd.DataFrame(summaries).to_csv(OUT/"E0_RADIAL_SUMMARY.csv",index=False)
    claims=dict(stage="E0",execution="PASS",calculation="PASS_ON_FROZEN_RADIAL_SHADOW",
      hypothesis="DESCRIPTIVE_AND_MODEL_SENSITIVE",scientific_claim="CLAIM_BLOCK_NOT_FULL_G2G3_OR_INDEPENDENT",
      scientific_PASS=False,n=len(df),selected=int(chosen.sum()),erroneous_selected_RF=int(np.sum(
        chosen&(np.abs(rf-truth)>=np.abs(dr-truth)))),
      summaries=summaries,
      important="Scalar radial-only. Does NOT update x,y,psi or P and is NOT one-step full G2/G3. Original Full G3 failure remains invalid.",
      next="F only after independent B source calibration + D real numerical + full one-step E")
    save("E0_RESULT.json",claims)
    print("STAGE_E0",claims["calculation"],"selected",claims["selected"],flush=True)
    return claims


def f_stage():
    results={}
    for x in ("B","C","D","E0"):
        p=OUT/(x+"_RESULT.json")
        results[x]=json.loads(p.read_text()) if p.exists() else {"execution":"MISSING"}
    full_ready=False
    # This is not a vacuous PASS: required calibration + full nonlinear one-step are absent.
    reasons=[]
    if results["B"].get("scientific_claim")!="PASS_INDEPENDENT_CALIBRATION":
        reasons.append("B has no certified independent spatial calibration")
    if results["D"].get("actual_G3_reference")!="PASS_INDEPENDENT_NUMERICAL":
        reasons.append("D full nonlinear G3 reference is not independently validated")
    reasons.append("Full 3state E has not been run; E0 is a distinct radial-only diagnostic")
    result=dict(stage="F",execution="NOT_RUN_DEPENDENCY",
      calculation="NOT_RUN",hypothesis="NOT_EVALUATED",
      scientific_claim="CLAIM_BLOCK_FULL_RECURSIVE_AND_GENERALIZATION",
      scientific_PASS=False,recursive_pose_Heading_NEES="NOT_RUN",
      dependent_blocks=reasons,
      unaffected_prior_results_reused=True,
      timeline=["A:prior_signed_RF_audit_PASS","B:current_scope_calibration_CLAIM_BLOCK",
       "C:synthetic_controls", "D:nonlinear_feasibility", "E0:radial_only_diagnostic",
       "E:full_one_step_NOT_RUN","F:recursive_NOT_RUN"],
      next="STOP at dependency; revise calibration and/or integrator only after bounded diagnosis and user direction")
    save("F_RESULT.json",result)
    print("STAGE_F",result["execution"],reasons,flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=["B","C","E0","F"])
    stage=p.parse_args().stage
    audit(stage)
    globals()[stage.lower()+"_stage"]()


if __name__=="__main__":
    main()
