#!/usr/bin/env python3
"""Descriptive signed RF-Range and DR-vs-RF directional audit.

Do NOT tune filters, reject observations, modify RF inputs, or train on scored truth.
All truth is used exclusively for post-hoc scoring and assessing a proposed
one-sided Range decision rule. Distinct sensor seeds share each frozen RF scene.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
H3=HERE/"h3_offline"/"results"/"H3_OFFLINE_20261014_01a1380d"
sys.path.insert(0,str(H3))
import d6_d9_common as c
import h3_offline as h
h.REPO=REPO

CONDITIONS=(("noise_pair",1),("gyro_bias",0),("gyro_bias",1),("gyro_bias",2))
SEEDS=(0,1,2)
PAIR_MODELS=(("los","B_OLD"),("full","B_OLD"),("full","E1_FULL_LORO"))
NIS99=c.GATE_1D_99
REF_D04=HERE/"results"/"AUDITED_RUN_20261013_701b8d2"/"OUTPUT_D0_D4_SEED0"/"D4_RANGE_RESIDUAL_BY_DISTANCE.csv"
REF_D0=H3/"STAGE4_SMOKE_01"/"D0_PARITY.csv"


def fnum(x):
    return float(x) if x is not None else float("nan")


def q(a,prob):
    return float(np.quantile(np.asarray(a,float),prob))


def desc_rf(df,group):
    residual=df["rf_signed_error_m"].to_numpy(dtype=float)
    under=np.maximum(-residual,0.)
    n=len(residual)
    return dict(group=group,n=n,mean_error_m=float(residual.mean()),
                median_error_m=float(np.median(residual)),
                std_error_m=float(residual.std()),
                rmse_error_m=float(np.sqrt(np.mean(residual**2))),
                min_error_m=float(residual.min()),max_error_m=float(residual.max()),
                q01_error_m=q(residual,.01),q05_error_m=q(residual,.05),
                q10_error_m=q(residual,.10),q90_error_m=q(residual,.90),
                q95_error_m=q(residual,.95),q99_error_m=q(residual,.99),
                p_rf_under_truth=float(np.mean(residual < 0)),
                p_under_by_5cm=float(np.mean(residual < -.05)),
                p_under_by_10cm=float(np.mean(residual < -.10)),
                tau95_m=q(under,.95),tau99_m=q(under,.99),
                within_tau95=float(np.mean(residual >= -q(under,.95))),
                within_tau99=float(np.mean(residual >= -q(under,.99))))


def score_subset(df,tag,extra=None):
    if len(df)==0:return None
    n=len(df)
    fw=df["rf_wins"].to_numpy(bool)
    dw=df["dr_wins"].to_numpy(bool)
    eRF=df["rf_abs_error_m"].to_numpy(float)
    eDR=df["dr_abs_error_m"].to_numpy(float)
    es=df["rf_signed_error_m"].to_numpy(float)
    delta=df["delta_dr_minus_rf_m"].to_numpy(float)
    res=dict(subset=tag,n=n,rf_win_fraction=float(fw.mean()),
             dr_win_fraction=float(dw.mean()),
             tie_fraction=float(1-fw.mean()-dw.mean()),
             rf_abs_mae_m=float(eRF.mean()),
             dr_abs_mae_m=float(eDR.mean()),
             rf_rmse_m=float(np.sqrt(np.mean(eRF**2))),
             dr_rmse_m=float(np.sqrt(np.mean(eDR**2))),
             median_delta_m=float(np.median(delta)),
             median_abs_delta_m=float(np.median(np.abs(delta))),
             q95_abs_delta_m=q(np.abs(delta),.95),
             mean_improvement_m=float((eDR-eRF).mean()),
             frac_rf_under_truth=float((es<0).mean()),
             NIS_median=float(np.median(df["nis"])),
             NIS_p95=q(df["nis"],.95),
             distinct_cases=int(df["case"].nunique()),
             distinct_routes=int(df["route"].nunique()))
    if extra:res.update(extra)
    return res


def subsets(df):
    positive=df["delta_dr_minus_rf_m"]>1e-10
    negative=df["delta_dr_minus_rf_m"]< -1e-10
    n=df["nis"]>NIS99
    n50=df["nis"]>50
    return {
        "ALL":np.ones(len(df),bool),
        "RF_SHORTER":positive.to_numpy(),
        "RF_LONGER":negative.to_numpy(),
        "RF_SHORTER_NIS_REJECT":(positive & n).to_numpy(),
        "RF_LONGER_NIS_REJECT":(negative & n).to_numpy(),
        "RF_SHORTER_NIS_GT50":(positive & n50).to_numpy(),
        "RF_LONGER_NIS_GT50":(negative & n50).to_numpy(),
    }


def input_dr(p0,route,condition,level,seed):
    case=next(v for v in p0["cases"] if v["route"]==route)
    t,tr,pids,motion,_=c.case_motion(p0,case,seed,level,condition)
    f=c.DiagnosticFilter(c.initial_state(tr[0],seed))
    x=[];P=[]
    for i in range(len(t)):
        if i:
            f.predict(float(motion["ds_odom"][i]),
                      float(motion["dtheta_gyro"][i]),
                      float(motion["dt_s"][i]))
        x.append(f.pose.copy())
        P.append(f.Ppose.copy())
    x=np.asarray(x);P=np.asarray(P)
    mask=t>=30
    err=x[mask]-tr[mask]
    err[:,2]=h.wrap(err[:,2])
    m=dict(n=int(mask.sum()),
           heading_rmse_deg=float(np.sqrt(np.mean(err[:,2]**2))*h.RAD),
           xy_rmse_m=float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))))
    return dict(t=t,truth=tr,pose_ids=pids,x=x,P=P,metrics=m)


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    receipt=dict(status="RUNNING",scope="RF_SIGNED_RESIDUAL_AND_DR_RF_SIGN_WINRATE_ONLY",
       scientific_PASS=False,rf_policy_evaluated=False,
       g2_g3_new_filter="NOT_IMPLEMENTED",g2_g3_performance="NOT_RUN",
       trained_model="NONE",frozen_nis99=NIS99,
       independent_units="7 case RF scenes with shared routes; 3 seeds and 4 conditions reuse RF measurements",
       input_parity="NOT_DONE")
    try:
        p0=c.check_inputs(full_p0=False)
        freqs=c.spectrum(p0)
        routes=c.timelines(p0)
        fold_data=json.loads(c.P3_MODEL.read_text())["loro_fold_params"]
        refd04=pd.read_csv(REF_D04)
        refd0=pd.read_csv(REF_D0)
        receipt["git_commit"]=subprocess.check_output(
             ["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
        receipt["frozen_source_sha"]=c.check_frozen_baseline_files()
        receipt["frozen_p3_sha256"]=c.file_sha(c.P3_MODEL)
        rf_dfs=[]
        rf_parity=[]
        source_signatures={}
        print("REBUILD frozen RF once per case/channel; no per-seed RF duplication",flush=True)
        for case in p0["cases"]:
            route=case["route"]
            t,tr,ids=routes[route]
            if len(t)!=len(ids) or tr.shape!=(len(t),3):
                raise RuntimeError("Timeline parse error")
            dz=float(case["anchor"][2]-case["robot_z_m"])
            ax=np.asarray(case["anchor"][:2],float)
            truth_slant=np.sqrt(np.sum((tr[:,:2]-ax)**2,axis=1)+dz*dz)
            mask=t>=30
            for channel in ("los","full"):
                det=c.rf_case(p0,case,channel,freqs,ids)
                corrections=c.corrected_ranges(
                    det,fold_data[route],allow_e1_on_los=False,channel=channel)
                for model in ("B_OLD","E1_FULL_LORO"):
                    if model not in corrections:continue
                    values=np.asarray(corrections[model],float)
                    if len(values)!=len(t):
                        raise RuntimeError("Range/timeline alignment mismatch")
                    if not np.isfinite(values).all():
                        raise RuntimeError("Nonfinite corrected RF ranges")
                    data=pd.DataFrame(dict(
                        case=case["id"],route=route,channel=channel,correction=model,
                        sample=np.flatnonzero(mask),pose_id=ids[mask],
                        t_s=t[mask],r_true_m=truth_slant[mask],
                        z_rf_m=values[mask],
                        rf_signed_error_m=values[mask]-truth_slant[mask]
                    ))
                    if data.empty:raise RuntimeError("No evaluation data")
                    rf_dfs.append(data)
                    bins=((0,5,"lt5m"),(5,10,"5to10m"),(10,np.inf,"ge10m"))
                    for lo,hi,name in bins:
                        part=data[(data["r_true_m"]>=lo)&(data["r_true_m"]<hi)]
                        rr=refd04[
                            (refd04["case"]==case["id"]) &
                            (refd04["channel"]==channel) &
                            (refd04["correction"]==model) &
                            (refd04["distance_bin"]==name)]
                        if len(rr)!=int(len(part)>0):
                            raise RuntimeError("Frozen D04 residual bin count mismatch")
                        if len(part)>0:
                            target=rr.iloc[0]
                            e=part["rf_signed_error_m"].to_numpy()
                            diff=max(abs(float(e.mean())-float(target["mean_residual_m"])),
                                     abs(float(e.std())-float(target["sd_residual_m"])),
                                     abs(int(len(e))-int(target["n"])))
                            if diff>1e-8:
                                raise RuntimeError("Frozen D04 range parity failed: "+
                                                   str((case["id"],channel,model,name,diff)))
                            rf_parity.append(dict(case=case["id"],channel=channel,
                                                  correction=model,distance_bin=name,
                                                  n=len(e),max_abs_difference=diff))
                    print("RF_PARITY",case["id"],channel,model,len(data),flush=True)
                source_signatures[case["id"]+"_"+channel]=dict(
                    rf_sha256=c.file_sha(REPO/case[channel+"_path"]),
                    sample_sha256=c.file_sha(REPO/case["samples_path"]))
        rf=pd.concat(rf_dfs,ignore_index=True)
        rf.to_csv(out/"RAW_RF_UNIQUE.csv.gz",index=False,compression="gzip")
        summary_rf=[]
        for (channel,model),grp in rf.groupby(["channel","correction"],sort=True):
            summary_rf.append(dict(channel=channel,correction=model,**desc_rf(grp,"ALL_CASES")))
            for route,sub in grp.groupby("route",sort=True):
                summary_rf.append(dict(channel=channel,correction=model,route=route,
                                       **desc_rf(sub,"BY_ROUTE")))
            for case,sub in grp.groupby("case",sort=True):
                summary_rf.append(dict(channel=channel,correction=model,case=case,
                                       **desc_rf(sub,"BY_CASE")))
            for group,sub in grp.groupby(pd.cut(grp["r_true_m"],
                                                [0,5,10,np.inf],
                                                labels=["lt5m","5to10m","ge10m"],
                                                include_lowest=True),observed=True):
                summary_rf.append(dict(channel=channel,correction=model,
                                       distance_bin=str(group),
                                       **desc_rf(sub,"BY_RANGE")))
        pd.DataFrame(summary_rf).to_csv(out/"RF_SIGNED_DISTRIBUTION.csv",index=False)
        pd.DataFrame(rf_parity).to_csv(out/"RF_PARITY_D04.csv",index=False)
        print("RF signed residual distributions finished",flush=True)

        dr_cache={}
        for route in sorted(routes):
            for cond,level in CONDITIONS:
                for seed in SEEDS:
                    dr=input_dr(p0,route,cond,level,seed)
                    for case in [v["id"] for v in p0["cases"] if v["route"]==route]:
                        ref=refd0[
                          (refd0["case"]==case)&(refd0["condition"]==cond)&
                          (refd0["level"]==level)&(refd0["seed"]==seed)]
                        if len(ref)!=1:raise RuntimeError("Missing D0 frozen reference")
                        for k in ("n","heading_rmse_deg","xy_rmse_m"):
                            if abs(float(ref.iloc[0][k])-dr["metrics"][k])>1e-8:
                                raise RuntimeError("D0 original parity failed: "+
                                                   str((case,cond,level,seed,k)))
                    dr_cache[route,cond,level,seed]=dr
        receipt["input_parity"]="PASS_D04_RF_AND_ARCHIVED_D0"
        print("All 84 frozen DR D0 parity cells PASS",flush=True)

        pairs=[]
        for (case_name,channel,model),data in rf.groupby(["case","channel","correction"],sort=True):
            case=next(v for v in p0["cases"] if v["id"]==case_name)
            route=case["route"]
            ax=np.asarray(case["anchor"][:2],float)
            dz=float(case["anchor"][2]-case["robot_z_m"])
            selected=data["sample"].to_numpy(int)
            zr=data["z_rf_m"].to_numpy(float)
            tr=data["r_true_m"].to_numpy(float)
            es=zr-tr
            for condition,level in CONDITIONS:
                for seed in SEEDS:
                    dr=dr_cache[route,condition,level,seed]
                    xr=dr["x"][selected]
                    P=dr["P"][selected]
                    if not np.array_equal(dr["pose_ids"][selected],data["pose_id"].to_numpy(int)):
                        raise RuntimeError("DR pose/measurement misalignment")
                    vec=xr[:,:2]-ax
                    rpred=np.sqrt(np.sum(vec**2,axis=1)+dz*dz)
                    Hxy=vec/rpred[:,None]
                    var=(Hxy[:,0]**2*P[:,0,0]+
                         2*Hxy[:,0]*Hxy[:,1]*P[:,0,1]+
                         Hxy[:,1]**2*P[:,1,1]+c.RR)
                    if not np.all(var>0):
                        raise RuntimeError("Invalid innovation variance")
                    delta=rpred-zr
                    nis=delta**2/var
                    absrf=np.abs(es)
                    absdr=np.abs(rpred-tr)
                    pairs.append(pd.DataFrame(dict(
                        case=case_name,route=route,channel=channel,correction=model,
                        condition=condition,level=level,seed=seed,
                        sample=selected,t_s=data["t_s"].to_numpy(float),
                        r_true_m=tr,z_rf_m=zr,r_DR_m=rpred,
                        rf_signed_error_m=es,dr_signed_error_m=rpred-tr,
                        delta_dr_minus_rf_m=delta,
                        rf_abs_error_m=absrf,dr_abs_error_m=absdr,
                        rf_wins=absrf+1e-12<absdr,
                        dr_wins=absdr+1e-12<absrf,
                        nis=nis,range_gate_rejected=nis>NIS99,
                        dr_pred_range_sigma_m=np.sqrt(var),
                        dr_xy_error_m=np.linalg.norm(xr[:,:2]-dr["truth"][selected,:2],axis=1)
                    )))
            print("PAIRED",case_name,channel,model,flush=True)
        allpairs=pd.concat(pairs,ignore_index=True)
        allpairs.to_csv(out/"DR_RF_PAIRED_TRACE.csv.gz",index=False,compression="gzip")
        metrics=[]
        # These are descriptive time/seed totals, NOT independent RF samples.
        for (ch,model,cond,level),grp in allpairs.groupby(
            ["channel","correction","condition","level"],sort=True):
            for subset,mask in subsets(grp).items():
                result=score_subset(grp.iloc[np.flatnonzero(mask)],subset,
                        dict(channel=ch,correction=model,condition=cond,level=level))
                if result:metrics.append(result)
        for (ch,model,cond,level,route),grp in allpairs.groupby(
            ["channel","correction","condition","level","route"],sort=True):
            for subset,mask in subsets(grp).items():
                if subset in ("RF_SHORTER_NIS_REJECT","RF_LONGER_NIS_REJECT"):
                    result=score_subset(grp.iloc[np.flatnonzero(mask)],subset,
                        dict(channel=ch,correction=model,condition=cond,level=level,route=route))
                    if result:metrics.append(result)
        for (ch,model,cond,level,case),grp in allpairs.groupby(
            ["channel","correction","condition","level","case"],sort=True):
            for subset,mask in subsets(grp).items():
                if subset in ("RF_SHORTER_NIS_REJECT","RF_LONGER_NIS_REJECT"):
                    result=score_subset(grp.iloc[np.flatnonzero(mask)],subset,
                        dict(channel=ch,correction=model,condition=cond,level=level,case=case))
                    if result:metrics.append(result)
        pd.DataFrame(metrics).to_csv(out/"SIGN_WIN_RATE_AND_NIS.csv",index=False)
        receipt["sample_count"]=dict(
            unique_RF_rows=len(rf),paired_condition_seed_rows=len(allpairs),
            rf_models=list(sorted(set(zip(rf["channel"],rf["correction"])))),
            distinct_cases=int(rf["case"].nunique()),
            distinct_routes=int(rf["route"].nunique()))
        receipt["rf_signed_global"]=[
            v for v in summary_rf if v["group"]=="ALL_CASES"]
        receipt["directional_summary"]=[
            v for v in metrics if v["subset"] in ("RF_SHORTER_NIS_REJECT","RF_LONGER_NIS_REJECT")
            and "route" not in v and "case" not in v]
        selected=allpairs[(allpairs["case"]=="R2_aA_m0")&
                  (allpairs["channel"]=="los")&(allpairs["correction"]=="B_OLD")&
                  (allpairs["condition"]=="gyro_bias")&(allpairs["level"]==2)&
                  (allpairs["seed"]==0)&(allpairs["sample"]==978)]
        if len(selected)!=1:raise RuntimeError("Failure case missing")
        example=selected.iloc[0]
        if abs(example["z_rf_m"]-3.6721958255)>1e-6 or abs(example["r_DR_m"]-6.414651253)>1e-6:
            raise RuntimeError("G3 failure sample reconstruction differs")
        receipt["confirmed_failure_case"]={k:(v.item() if isinstance(v,np.generic) else v)
            for k,v in example.to_dict().items()}
        # Sufficient-but-not-necessary one-sided logical identity
        safe=allpairs[(allpairs["delta_dr_minus_rf_m"]>1e-10)&
                      (allpairs["rf_signed_error_m"]>=0)]
        if len(safe) and not bool(safe["rf_wins"].all()):
            raise RuntimeError("One-sided RF truth inequality violated")
        receipt["one_sided_logical_check"]=dict(
            n_sufficient_condition=len(safe),
            rf_win_fraction=float(safe["rf_wins"].mean()) if len(safe) else None)
        receipt["status"]="PASS_DESCRIPTIVE_AUDIT_NO_FILTER_INFERENCE"
        receipt["next_action"]="Review RF-shorter NIS-reject win rates and conservative negative tail; write preregistered one-sided G2/G3 model plan. No algorithm performance claim."
        exit_code=0
    except Exception as exc:
        receipt.update(status="FAIL_CLOSED",error_type=type(exc).__name__,
                       error=str(exc),traceback=traceback.format_exc())
        exit_code=1
    finally:
        path=out/"AUDIT_RECEIPT.json"
        path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False,default=str),encoding="utf-8")
        print("AUDIT_FINAL",json.dumps({
            "status":receipt["status"],"sample_count":receipt.get("sample_count"),
            "error":receipt.get("error"),"next_action":receipt.get("next_action")
        },ensure_ascii=False),flush=True)
    return exit_code


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    sys.exit(main(args.out))
