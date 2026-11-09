#!/usr/bin/env python3
"""Independent delivery evaluation from completed numerical artifacts only.

No SourceFFD replay, policy fitting, or result repair runs here. Missing routes
remain INCOMPLETE, missing lineage remains UNVERIFIED, and OFF/UNKNOWN bypass
cannot count as demonstrated guard utility. Scientific adoption is distinct
from executable/numerical correctness and from selected diagnostic success.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from scipy.stats import chi2

ROUTES = {"R2":979,"R4":742,"R5":1415}
STRATA = ("B_FROZEN","B_BIAS_COV")
MODES = ("OFF","OBSERVE_ONLY","ACTIVE_R","ACTIVE_S","ACTIVE_RS","DR_ONLY","NAIVE_YAW_CLIP")
GUARDS = ("ACTIVE_R","ACTIVE_S","ACTIVE_RS")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_npz(p, keys=None):
    with np.load(p,allow_pickle=False) as f:
        return {k:f[k] for k in (f.files if keys is None else keys)}


def read_json(p):
    return json.loads(Path(p).read_text())


def dump(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+"\n")


def csv_write(p,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi


def errors(x,truth):
    e=np.asarray(x)[:,:3]-truth;e[:,2]=wrap(e[:,2]);return e


def losses(x,truth):
    e=errors(x,truth)
    return np.column_stack((np.degrees(e[:,2])**2,np.sum(e[:,:2]**2,axis=1)))


def independently_score(tr,truth,used):
    x,P=tr["x"],tr["P"];n=len(x)
    if x.shape!=(n,4) or P.shape!=(n,4,4) or truth.shape!=(n,3):raise ValueError("STATE_GRAIN")
    if not np.isfinite(x).all() or not np.isfinite(P).all():raise ValueError("NONFINITE_STATE")
    sym=float(np.max(abs(P-P.transpose(0,2,1))))
    mineig=float(np.linalg.eigvalsh(P).min())
    if sym>1e-10 or mineig<=0:raise ValueError(f"COVARIANCE_INVALID symmetry={sym} mineig={mineig}")
    e=errors(x,truth);l=losses(x,truth)
    n3=np.einsum("ni,ni->n",e,np.linalg.solve(P[:,:3,:3],e[...,None])[...,0])
    nxy=np.einsum("ni,ni->n",e[:,:2],np.linalg.solve(P[:,:2,:2],e[:,:2,None])[...,0])
    nh=e[:,2]**2/P[:,2,2]
    return {"n":n,"heading_mse_deg2":float(l[:,0].mean()),"xy_mse_m2":float(l[:,1].mean()),
            "heading_rmse_deg":float(np.sqrt(l[:,0].mean())),"xy_rmse_cm":float(100*np.sqrt(l[:,1].mean())),
            "heading_MAE_deg":float(abs(np.degrees(e[:,2])).mean()),"mean_nees3":float(n3.mean()),
            "pose95_coverage":float(np.mean(n3<=chi2.ppf(.95,3))),
            "xy95_coverage":float(np.mean(nxy<=chi2.ppf(.95,2))),
            "heading95_coverage":float(np.mean(nh<=chi2.ppf(.95,1))),
            "accepted":int(np.count_nonzero(used)),"minimum_P_eigenvalue":mineig,"max_P_asymmetry":sym}


def independent_joseph(x,P,H,v,R,beta,allowed):
    """Independent algebra; does not import mcg.covariance_update."""
    re=R.copy();rows=np.flatnonzero(np.asarray(beta)>0) if allowed else np.array([],int)
    positive=np.asarray(beta)>0
    re[np.diag_indices(2)]+=np.where(positive,1/np.maximum(beta,1e-300)-1,0)*np.diag(R)
    K=np.zeros((4,2));out=x.copy();C=P.copy()
    if len(rows):
        h=H[rows];rr=re[np.ix_(rows,rows)];S=h@P@h.T+rr;S=(S+S.T)/2
        gain=np.linalg.solve(S,h@P).T;K[:,rows]=gain
        out+=gain@v[rows];out[2]=wrap(out[2]);A=np.eye(4)-gain@h
        C=A@P@A.T+gain@rr@gain.T;C=(C+C.T)/2
    return out,C,K,re,rows


def numerical_and_retention(tr,on,truth):
    required=("prior","Pprior","H","nu","Rbase","Reff","beta","K","used_r","used_s","mask")
    if any(k not in tr for k in required):return {"status":"UNVERIFIED_MISSING_UPDATE_INGREDIENTS","missing":[k for k in required if k not in tr]},None
    n=len(tr["x"]);beta=tr["beta"]
    if beta.shape!=(n,2) or not np.isfinite(beta).all() or np.any((beta<0)|(beta>1)):raise ValueError("INVALID_BETA")
    maximum={"x":0.,"P":0.,"K":0.,"Reff":0.}
    full=np.empty((n,4));actual_used=np.column_stack((tr["used_r"],tr["used_s"]))
    changed=0
    for k in range(n):
        out,C,K,re,rows=independent_joseph(tr["prior"][k],tr["Pprior"][k],tr["H"][k],tr["nu"][k],tr["Rbase"][k],beta[k],bool(tr["mask"][k]))
        for key,val in (("x",out),("P",C),("K",K),("Reff",re)):
            delta=val-tr[key][k]
            if key=="x":delta[2]=wrap(delta[2])
            maximum[key]=max(maximum[key],float(np.max(abs(delta)/np.maximum(1.,abs(tr[key][k])))))
        expected_used=np.zeros(2,bool);expected_used[rows]=True
        if not np.array_equal(expected_used,actual_used[k]):raise ValueError("USED_ROWS_INCONSISTENT")
        f,fc,fK,_,_=independent_joseph(tr["prior"][k],tr["Pprior"][k],tr["H"][k],tr["nu"][k],tr["Rbase"][k],np.ones(2),bool(tr["mask"][k]))
        full[k]=f
        changed+=int(bool(tr["mask"][k]) and (np.max(abs(K-fK))>1e-12 or np.max(abs(C-fc))>1e-12))
    if max(maximum.values())>1e-10:raise ValueError("INDEPENDENT_JOSEPH_MISMATCH:"+str(maximum))
    # Independently recompute the SE(2) position/yaw/bias mean transition from
    # previous actual outputs, detecting accidentally frozen baseline priors.
    prev=tr["x"][:-1];turn=on["gy"][1:]-prev[:,3]*on["dt"][1:]
    length=on["ds"][1:]*np.sinc(turn/(2*np.pi));phi=prev[:,2]+turn/2
    predicted=prev.copy();predicted[:,:2]+=np.column_stack((length*np.cos(phi),length*np.sin(phi)))
    predicted[:,2]=wrap(prev[:,2]+turn)
    delta=predicted-tr["prior"][1:];delta[:,2]=wrap(delta[:,2])
    prediction_error=float(np.max(abs(delta)/np.maximum(1.,abs(tr["prior"][1:]))))
    if prediction_error>1e-10:raise ValueError("OWN_STATE_RECURSION_MISMATCH")
    lf,ls,la=losses(full,truth),losses(tr["prior"],truth),losses(tr["x"],truth)
    retention={}
    for j,axis in enumerate(("heading_deg2","xy_m2")):
        good=tr["mask"] & (ls[:,j]>lf[:,j])
        den=float(np.sum(ls[good,j]-lf[good,j]));num=float(np.sum(np.maximum(la[good,j]-lf[good,j],0)))
        retention[axis]={"beneficial_gain_denominator":den,"beneficial_lost_numerator":num,
                         "beneficial_lost_gain_ratio":num/den if den>0 else None,
                         "status":"ESTIMABLE" if den>0 else "NOT_ESTIMABLE",
                         "five_percent_budget_pass":bool(num/den<=.05+1e-12) if den>0 else None,
                         "net_saved_loss_vs_same_prior_full":float(np.sum(lf[:,j]-la[:,j]))}
    return {"status":"PASS","max_normalized_update_errors":maximum,"own_previous_state_prediction_error":prediction_error,
            "accepted_updates_numerically_changed_by_guard":changed,
            "same_step_retention_scope":"Each active arm own prior; full hypothetical update at that prior. Not original-baseline closed-loop causal effect."},retention


def classify(meta):
    explicit=meta.get("execution_policy_role") or meta.get("policy_role") or meta.get("role")
    if explicit:return str(explicit)
    mode=meta["mode"]
    if mode in ("OFF","OBSERVE_ONLY"):return "BASELINE_OR_OBSERVE_COMPARATOR"
    if mode in ("DR_ONLY","NAIVE_YAW_CLIP"):return "NEGATIVE_OR_DR_COMPARATOR"
    c=meta.get("config",{})
    if c.get("tau_r")==2. and c.get("tau_s")==2.:return "FIXED_TAU2_DIAGNOSTIC_INFERRED_FROM_CONFIG"
    return "UNLABELLED_RESEARCH_REPLAY"


def code_lineage(meta,repo,path):
    fields=meta.get("runtime_code_sha256") or meta.get("run_started_code_sha256") or meta.get("execution_code_sha256")
    if fields is None and isinstance(meta.get("code_sha256"),dict):fields=meta["code_sha256"]
    result={"runtime_code":"UNVERIFIED_NOT_RECORDED","trace_bytes":"UNVERIFIED_NOT_RECORDED","source_files":{},"config":"UNVERIFIED_NOT_RECORDED"}
    if fields:
        checked={}
        for fn,digest in fields.items():
            target=repo/fn
            if not target.exists():target=repo/"research/B_MCG_V1_20261109"/Path(fn).name
            checked[fn]={"expected":digest,"current":sha(target) if target.is_file() else None,
                         "matches_current":target.is_file() and sha(target)==digest}
        result["runtime_code_checks"]=checked
        required_present={"mcg.py","experiment.py"} <= {Path(n).name for n in checked}
        result["runtime_code"]=("RECORDED_AND_CURRENT_MATCH" if required_present and all(v["matches_current"] for v in checked.values())
                                else "RECORDED_VERSION_DIFFERS_OR_MISSING")
    if meta.get("trace_sha256"):
        result["trace_bytes"]="PASS" if sha(path)==meta["trace_sha256"] else "FAIL"
    for fn,digest in meta.get("source_hashes",{}).items():
        target=repo/"research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources"/fn
        result["source_files"][fn]="PASS" if target.is_file() and sha(target)==digest else "FAIL_OR_UNAVAILABLE"
    if meta.get("config_sha256") and "config" in meta:
        computed=hashlib.sha256(json.dumps(meta["config"],sort_keys=True).encode()).hexdigest()
        result["config"]="PASS" if computed==meta["config_sha256"] else "FAIL"
    result["warning"]="Current source equality alone cannot establish an execution-time code snapshot when none was recorded. Numerical evaluation remains separately inspectable."
    return result


def discover(results,out):
    found=[]
    # Only final canonical streams count. Earlier off_parity/prototype artifacts
    # cannot fill a missing final run, even when their metrics happen to match.
    for stratum in STRATA:
        for mode in MODES:
            for route in ROUTES:
                p=results/"active"/stratum/mode/f"{route}_{mode}.json"
                if not p.is_file():continue
                try:meta=read_json(p)
                except (ValueError,OSError):continue
                if isinstance(meta,dict) and meta.get("route")==route and meta.get("stratum")==stratum and meta.get("mode")==mode:
                    found.append((p,meta))
    return sorted(found,key=lambda x:str(x[0]))


def compare_reported(meta,metrics):
    reported=meta.get("metrics",{});comp={}
    for key,val in metrics.items():
        if key not in reported:continue
        comp[key]=float(abs(float(reported[key])-val)/max(1.,abs(val)))
    return {"status":"PASS" if comp and max(comp.values())<=1e-9 else "FAIL_OR_MISSING",
            "max_normalized_error":max(comp.values()) if comp else None,"checks":comp}


def evaluate_record(path,meta,inputs,archives,repo):
    route,stratum,mode=meta["route"],meta["stratum"],meta["mode"]
    npz=path.with_suffix(".npz")
    result={"metadata_path":str(path),"trace_path":str(npz),"route":route,"stratum":stratum,"mode":mode,
            "role":classify(meta),"metadata_sha256":sha(path),"expected_n":ROUTES[route]}
    if not npz.is_file():return result|{"status":"MISSING_TRACE","n":None},None
    try:
        tr=read_npz(npz);on,ev=inputs[route]
        if len(tr["x"])!=ROUTES[route]:raise ValueError("INCOMPLETE_ROW_COUNT")
        if not np.array_equal(tr["t"],ev["t"]) or not np.array_equal(tr["pose_id"],ev["pose_id"]):raise ValueError("TIME_POSE_JOIN")
        oldp=archives/route/f"{route}_{stratum}.npz"
        assert sha(oldp)==read_json(oldp.parent/"SHA256.json")[oldp.name],"ARCHIVE_HASH"
        old=read_npz(oldp,("x","P","mask","prior","Pprior","K","h","nu","mu"))
        if not np.array_equal(tr["mask"],old["mask"]):raise ValueError("LEGACY_SHADOW_GATE_CHANGED")
        observation_error=float(np.max(abs((tr["nu"]+tr["h"]+tr["mu"])-(old["nu"]+old["h"]+old["mu"]))))
        calibration_error=float(np.max(abs(tr["mu"]-old["mu"])))
        if observation_error>1e-10 or calibration_error>1e-10:raise ValueError("B_OBSERVATION_OR_FROZEN_CALIBRATION_CHANGED")
        used=tr["used_r"]|tr["used_s"] if "used_r" in tr else tr["mask"]
        score=independently_score(tr,ev["truth"],used)
        baseline=independently_score(old,ev["truth"],old["mask"])
        numerical,retention=numerical_and_retention(tr,on,ev["truth"])
        activity=int(np.sum(tr["mask"] & np.any(tr["beta"]<1.-1e-14,axis=1))) if "beta" in tr else None
        status_counts={str(k):int(v) for k,v in zip(*np.unique(tr["status"],return_counts=True))} if "status" in tr else None
        score.update(heading_rmse_ratio=score["heading_rmse_deg"]/baseline["heading_rmse_deg"],
                     xy_rmse_ratio=score["xy_rmse_cm"]/baseline["xy_rmse_cm"],
                     actual_guard_damped_legacy_accepted=activity,
                     actual_guard_damped_fraction_legacy_accepted=activity/int(old["mask"].sum()) if activity is not None else None)
        for axis in ("pose","xy","heading"):
            score[axis+"95_coverage_delta_pp"]=100*(score[axis+"95_coverage"]-baseline[axis+"95_coverage"])
        lat={}
        for key in ("latency_ms","guard_ms"):
            if key in tr and np.isfinite(tr[key]).all():lat[key+"_p50_p95_p99"]=np.quantile(tr[key],[.5,.95,.99]).tolist()
            else:lat[key+"_p50_p95_p99"]=None
        valid=(tr.get("guard_valid_r",np.zeros(len(used),bool)) | tr.get("guard_valid_s",np.zeros(len(used),bool)))
        lat["guard_valid_frame_count"]=int(valid.sum())
        lat["guard_ms_valid_frames_p50_p95_p99"]=np.quantile(tr["guard_ms"][valid],[.5,.95,.99]).tolist() if valid.any() and "guard_ms" in tr else None
        criteria={"route_heading_ratio_le_1p05":score["heading_rmse_ratio"]<=1.05+1e-12,
                  "route_xy_ratio_le_1p05":score["xy_rmse_ratio"]<=1.05+1e-12,
                  "all_three_coverages_drop_le_3pp":all(score[x+"95_coverage_delta_pp"]>=-3.-1e-10 for x in ("pose","xy","heading")),
                  "actual_nontrivial_activity":bool(numerical.get("accepted_updates_numerically_changed_by_guard",0)>0 and activity),
                  "total_p99_le_200ms":lat["latency_ms_p50_p95_p99"][2]<=200. if lat["latency_ms_p50_p95_p99"] else None,
                  "guard_p95_goal_le_50ms":lat["guard_ms_p50_p95_p99"][1]<=50. if lat["guard_ms_p50_p95_p99"] else None,
                  "same_active_prior_good_gain_budget_both_axes":all(v["five_percent_budget_pass"] is True for v in retention.values()) if retention else None}
        offpar=None
        if mode in ("OFF","OBSERVE_ONLY"):
            offpar={k:float(np.max(abs(tr[k]-old[k])/np.maximum(1.,abs(old[k])))) for k in ("x","P","prior","Pprior","K")}
            if max(offpar.values())>1e-10:raise ValueError("OFF_PARITY_FAILURE")
        lineage=code_lineage(meta,repo,npz)
        lineage["archive_metadata"]=("PASS" if meta["archive_sha256"]==sha(oldp) else "FAIL") if meta.get("archive_sha256") else "UNVERIFIED_NOT_RECORDED"
        result.update(status="NUMERICALLY_EVALUATED",n=len(used),trace_sha256=sha(npz),archive_sha256=sha(oldp),
                      metrics=score,baseline=baseline,numerical=numerical,same_active_prior_retention=retention,
                      status_counts=status_counts,latency=lat,criteria=criteria,OFF_parity=offpar,
                      lineage=lineage,reported_metric_reconciliation=compare_reported(meta,score),
                      B_observation_identity_max_error=observation_error,frozen_mu_identity_max_error=calibration_error,
                      config=meta.get("config"),config_sha256=meta.get("config_sha256"),policy_lock_sha256=meta.get("policy_lock_sha256"))
        payload={"metrics":score,"baseline":baseline,"n":len(used),"retention":retention,"tr":tr}
        return result,payload
    except (AssertionError,ValueError,KeyError,np.linalg.LinAlgError) as e:
        return result|{"status":"INVALID_OR_UNVERIFIED_ARTIFACT","n":None,"error":str(e)},None


def pooled(records,payloads):
    n=sum(p["n"] for p in payloads)
    result={"n":n,"metrics":{},"baseline":{},"same_active_prior_retention":{}}
    mean_keys=("heading_mse_deg2","xy_mse_m2","mean_nees3","pose95_coverage","xy95_coverage","heading95_coverage")
    for side in ("metrics","baseline"):
        s={k:sum(p["n"]*p[side][k] for p in payloads)/n for k in mean_keys}
        s.update(heading_rmse_deg=float(np.sqrt(s["heading_mse_deg2"])),xy_rmse_cm=float(100*np.sqrt(s["xy_mse_m2"])))
        result[side]=s
    for axis in ("heading_deg2","xy_m2"):
        vals=[p["retention"][axis] for p in payloads if p["retention"]]
        den=sum(v["beneficial_gain_denominator"] for v in vals);num=sum(v["beneficial_lost_numerator"] for v in vals)
        result["same_active_prior_retention"][axis]={"denominator":den,"numerator":num,"ratio":num/den if den>0 else None,
              "five_percent_budget_pass":bool(num/den<=.05+1e-12) if den>0 and len(vals)==len(payloads) else None}
    activity=sum(r["metrics"]["actual_guard_damped_legacy_accepted"] or 0 for r in records)
    actual=sum(r["numerical"].get("accepted_updates_numerically_changed_by_guard",0) for r in records)
    lat={}
    for k in ("latency_ms","guard_ms"):
        v=[p["tr"][k] for p in payloads if k in p["tr"]]
        lat[k+"_p50_p95_p99"]=np.quantile(np.concatenate(v),[.5,.95,.99]).tolist() if len(v)==len(payloads) else None
    m,b=result["metrics"],result["baseline"]
    result.update(actual_guard_damped_legacy_accepted=activity,numerically_changed_updates=actual,latency=lat,
        criteria={"all_routes_heading_xy_ratio_le_1p05":all(r["criteria"]["route_heading_ratio_le_1p05"] and r["criteria"]["route_xy_ratio_le_1p05"] for r in records),
                  "pooled_both_axes_improve":m["heading_mse_deg2"]<b["heading_mse_deg2"]*(1-1e-12) and m["xy_mse_m2"]<b["xy_mse_m2"]*(1-1e-12),
                  "all_routes_all_coverages_drop_le_3pp":all(r["criteria"]["all_three_coverages_drop_le_3pp"] for r in records),
                  "actual_nontrivial_activity":activity>0 and actual>0,
                  "all_routes_total_p99_le_200ms":all(r["criteria"]["total_p99_le_200ms"] is True for r in records),
                  "active_prior_retention_both_axes_le_5pct":all(v["five_percent_budget_pass"] is True for v in result["same_active_prior_retention"].values())})
    return result


def load_inputs(assets,lock):
    inputs={};receipt={}
    records={v["asset_name"]:v for v in read_json(lock)["files"]}
    for route,n in ROUTES.items():
        files={k:assets/f"{route}_B0_Full_10__{k}.npz" for k in ("online","evaluator")}
        for p in files.values():
            rec=records[p.name]
            if not p.is_file() or p.stat().st_size!=rec["size"] or sha(p)!=rec["sha256"]:raise ValueError("LOCKED_INPUT_HASH:"+str(p))
        on=read_npz(files["online"],("t","pose_id","ds","gy","dt","x0","P0"))
        ev=read_npz(files["evaluator"],("t","pose_id","truth"))
        assert len(ev["t"])==n and np.array_equal(on["t"],ev["t"]) and np.array_equal(on["pose_id"],ev["pose_id"])
        inputs[route]=(on,ev);receipt[route]={k+"_sha256":sha(p) for k,p in files.items()}
    return inputs,receipt


def evidence_matrix(results,repo,policy_path,group_results):
    units=[]
    def add(unit,status,evidence,meaning):units.append({"development_unit":unit,"status":status,"evidence":evidence,"criterion_and_limit":meaning})
    p=results/"baseline";rs=[]
    for route in ROUTES:
        q=p/f"{route}_PARITY.json"
        if q.is_file():
            d=read_json(q);rs.append(d.get("status")=="PASS" and max(v for s in d.get("strata",{}).values() for v in s.values())<=1e-10)
    add("D00_SOURCE_BASELINE","PASS" if len(rs)==3 and all(rs) else "INCOMPLETE_OR_FAIL",str(p),"All 3 routes and both calibration strata must reproduce archived B within 1e-10.")
    p=results/"independent_unit_audit_final/UNIT_TESTS.json"
    if p.is_file():
        d=read_json(p);recorded=d.get("source_sha256",{})
        source_ok="mcg.py" in recorded and all((repo/"research/B_MCG_V1_20261109"/n).is_file() and sha(repo/"research/B_MCG_V1_20261109"/n)==h for n,h in recorded.items())
        st="PASS" if d.get("exit_code")==0 and d.get("test_count",0)>=27 and source_ok and d.get("entry_exit_runtime_hash_match") is True else "STALE_OR_FAIL"
    else:st="MISSING"
    add("D01_NUMERICAL_CAUSALITY_API_27_TESTS",st,str(p),"Recorded >=27 passing tests must match current tested source hashes and entry/exit identity; does not establish empirical utility or globally complete profile coverage.")
    for unit,file,status,meaning in (
        ("D02_P1_SAME_PRIOR_OPPORTUNITY","precheck_oracle/RESULTS.json","PASS_RECONSTRUCTION_AND_EVALUATOR_CHECKS","Oracle opportunity is diagnostic only; it is not a deployable selector or a closed-loop improvement guarantee."),
        ("D03_P2_CONTROL_PROVENANCE","precheck_motion/CONTROL_PROVENANCE_AUDIT.json","PASS_CONTROL_PROVENANCE_AND_P2_ALGEBRA","B0 gyro bias zero and controls reconstructed; common gyro-noise prefix prevents independent-seed generalization."),
        ("D04_WRONG_REFERENCE_MECHANISM","bias_feedback/RESULTS.json","PASS_EXACT_IDENTITIES_AND_ONE_FACTOR_REFERENCE_INTERVENTIONS","Frozen-trace RF->bg algebra plus same-anchor bg interventions; current B0 truth does not justify deploying bg=0 on unknown hardware."),
        ("D05_RESIDUAL_CAUSAL_REPLAY","bias_causal/RESULTS.json","PASS_REPLAY_AND_BASELINE_PARITY","Ideal observer is synthetic, not physical clean CIR; channel effects include state/gate interaction."),
        ("D06_1_5_10_SECOND_BRANCHES","horizons/RESULTS.json","PASS_FULL_BRANCH_PARITY_AND_HORIZON_EVALUATION","Hindsight extremes and one-time interventions; sign reversals are not population failure rates.")):
        p=results/file;st="PASS" if p.is_file() and read_json(p).get("status")==status else "MISSING_OR_FAIL"
        add(unit,st,str(p),meaning)
    if policy_path and policy_path.is_file():
        lock=read_json(policy_path);pol=lock.get("policies",{})
        selected=[v for s in pol.values() for v in s.values()]
        utility=all(v.get("selected_candidate")!="OFF" for v in selected) and len(selected)==6
        p=policy_path.parent/"SPLIT_GEOMETRY_RECEIPT.json"
        complete=all(v.get("all_requested_route_partitions_nonempty",False) for v in selected) and len(selected)==6
        add("D07_CHRONOLOGICAL_AND_POSE_PURGE","COMPLETE_SUPPORT" if complete else "NOT_ESTIMABLE_EMPTY_PARTITION",str(p),"No random-frame split; no relaxation after purge removes support. Geometry-only heldout access differs from loss leakage.")
        add("D08_SELECTED_POLICY_UTILITY","ELIGIBLE_SAME_PRIOR_ONLY" if utility else "NOT_DEMONSTRATED",str(policy_path),"OFF fallback is not a successful guard. Secondary B_BIAS_COV is not nested independent route holdout.")
    else:
        add("D07_CHRONOLOGICAL_AND_POSE_PURGE","MISSING_POLICY_LOCK",None,"No assumed pass from absent calibration evidence.")
        add("D08_SELECTED_POLICY_UTILITY","UNVERIFIED",None,"Need locked selection before heldout error assessment.")
    p=results/"source_adversarial_final/SOURCE_STRESS_SUMMARY.json"
    stress_status="MISSING"
    if p.is_file():
        stress=read_json(p)
        stress_status="EXECUTED_SELECTED_ONE_STEP_ONLY" if stress.get("implementation_sha256")==sha(repo/"research/B_MCG_V1_20261109/mcg.py") and stress.get("n_profiles")==105 else "STALE_OR_INCOMPLETE"
    add("D09_SELECTED_SOURCE_STRESS",stress_status,str(p),"105 selected one-step profiles at recorded tau3; no-damping and UNKNOWN cases do not establish useful guard activity. These cannot certify global feasibility or recursive clean-recovery time.")
    recovery=results/"recovery_final/RESULTS.json"
    recovery_status="NOT_VERIFIED"
    if recovery.is_file():
        rr=read_json(recovery);recorded=rr.get("contract",{}).get("runtime_code_sha256",{})
        current_mcg=repo/"research/B_MCG_V1_20261109/mcg.py"
        if recorded.get("mcg.py")!=sha(current_mcg):recovery_status="PROTOTYPE_VERSION_ONLY"
        else:
            vals=[v for c in rr.get("cases",[]) for name,v in c.get("metrics",{}).items() if name!="OFF"]
            if vals and not any(v.get("clean_guard_damped_legacy_accepted",0) or v.get("prefix_guard_damped_legacy_accepted",0) for v in vals):
                recovery_status="NO_ACTIVITY_IN_SELECTED_SCENARIOS"
            elif any(q.get("pass_le_1p1") is False for v in vals for q in v.get("recovery_ratio_vs_OFF",{}).values()):
                recovery_status="SELECTED_SCENARIO_BUDGET_FAIL"
            elif any(q.get("ratio") is None for v in vals for q in v.get("recovery_ratio_vs_OFF",{}).values()):
                recovery_status="SELECTED_SCENARIOS_PARTLY_CENSORED"
            elif vals:recovery_status="SELECTED_SCENARIO_BUDGET_PASS_ONLY"
    add("D10_RECURSIVE_CLEAN_RECOVERY_LE_1P1",recovery_status,str(recovery) if recovery.is_file() else None,
        "Two selected constructed SourceFFD scenarios; censor if OFF does not recover. Zero guard activity cannot demonstrate guard utility or a global recovery guarantee.")
    add("D11_NEW_SEED_SCENE_TRANSFER","NOT_TESTED",None,"Same corridor, exposed data, shared seed10 gyro-noise prefix; no external generalization claim.")
    add("D12_CLOSED_LOOP_COMPLETENESS","COMPLETE" if all(v["status"]=="COMPLETE_EVALUATED" for v in group_results) else "INCOMPLETE",None,"Every requested stratum/mode needs all 3136 rows; missing results are never zero.")
    add("D13_EXECUTION_PROVENANCE","PASS" if all(v.get("artifact_provenance_pass") is True for v in group_results) else "UNVERIFIED_OR_INCOMPLETE",None,
        "Chosen final traces require recorded runtime mcg/experiment hashes, trace/archive/config digests, original source hashes, and reconciliation; old prototype artifacts do not substitute.")
    p=results/"recovery_feasibility/R4_FIRST_CLEAN_FEASIBILITY.json"
    feasible_status="NOT_VERIFIED"
    if p.is_file():
        f=read_json(p)
        if f.get("runtime_sha256")!=sha(repo/"research/B_MCG_V1_20261109/mcg.py"):
            feasible_status="PROTOTYPE_VERSION_ONLY"
        elif f.get("compatible_tau3_witness_found") is True:
            feasible_status="FAIL_MISSING_COMPATIBLE_PROFILE_WITNESS"
        else:
            feasible_status="NO_WITNESS_FOUND_IS_NOT_A_GLOBAL_CERTIFICATE"
    add("D14_PROFILE_FEASIBLE_SET_COVERAGE",feasible_status,str(p) if p.is_file() else None,
        "A bounded, history-cost-feasible tau3-compatible witness was missed by the finite runtime candidates at the first clean R4 return. Best-fit stationarity and small sampled target spread do not prove full-set coverage.")
    p=results/"recovery_cause/RESULTS.json"
    cause_status="NOT_VERIFIED"
    if p.is_file():
        c=read_json(p)
        if c.get("runtime_code_sha256",{}).get("mcg.py")!=sha(repo/"research/B_MCG_V1_20261109/mcg.py"):
            cause_status="PROTOTYPE_VERSION_ONLY"
        elif c.get("status")=="PASS_FIXED_CURRENT_ONE_FACTOR_RECONSTRUCTION":
            cause_status="CONFIRMED_HISTORY_REFERENCE_FALSE_CONFLICT_IN_ONE_SCENARIO"
    add("D15_RECOVERY_FALSE_CONFLICT_CAUSE",cause_status,str(p) if p.is_file() else None,
        "Same current RF and main prior/P/H/nu/R fixed: ideal historical RF removes the first-clean conflict, while true anchor pose or zero anchor bg alone does not. Evaluator-only local intervention; candidate coverage failure remains separately identified.")
    return units


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--results",type=Path,required=True);p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--archives",type=Path,required=True);p.add_argument("--assets",type=Path,required=True)
    p.add_argument("--input-lock",type=Path,required=True);p.add_argument("--policy-lock",type=Path)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--require-complete",action="store_true")
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    inputs,input_receipt=load_inputs(a.assets,a.input_lock)
    policy=a.policy_lock or a.results/"policy_calibration_final/POLICY_LOCK.json"
    evaluated=[];payloads={};metadata={}
    for path,meta in discover(a.results,a.out):
        result,payload=evaluate_record(path,meta,inputs,a.archives,a.repo)
        evaluated.append(result);metadata[str(path)]=meta
        if payload is not None:payloads[str(path)]=payload
    groups=[];table=[]
    for stratum in STRATA:
        for mode in MODES:
            chosen=[];missing=[];duplicates={}
            for route in ROUTES:
                options=[r for r in evaluated if r["route"]==route and r["stratum"]==stratum and r["mode"]==mode]
                if not options:missing.append(route);continue
                canonical=a.results/"active"/stratum/mode/f"{route}_{mode}.json"
                options.sort(key=lambda r:(r["metadata_path"]==str(canonical),f"/{stratum}/" in r["metadata_path"],r["status"]=="NUMERICALLY_EVALUATED"),reverse=True)
                chosen.append(options[0])
                if len(options)>1:duplicates[route]=[r["metadata_path"] for r in options]
            complete=len(chosen)==3 and all(r["status"]=="NUMERICALLY_EVALUATED" for r in chosen)
            g={"stratum":stratum,"mode":mode,"expected_n":3136,"status":"COMPLETE_EVALUATED" if complete else "INCOMPLETE",
               "missing_routes":missing,"chosen_records":[r["metadata_path"] for r in chosen],"duplicate_candidates":duplicates,
               "execution_roles":sorted(set(r["role"] for r in chosen))}
            if complete:
                g["pooled"]=pooled(chosen,[payloads[r["metadata_path"]] for r in chosen])
                g["numerical_performance_gates_all_pass"]=all(g["pooled"]["criteria"].values())
                g["artifact_provenance_pass"]=all(r["lineage"]["runtime_code"]=="RECORDED_AND_CURRENT_MATCH"
                    and r["lineage"]["trace_bytes"]=="PASS" and r["lineage"]["archive_metadata"]=="PASS"
                    and r["lineage"]["config"]=="PASS" and bool(r["lineage"]["source_files"])
                    and all(v=="PASS" for v in r["lineage"]["source_files"].values())
                    and r["reported_metric_reconciliation"]["status"]=="PASS" and r["numerical"]["status"]=="PASS" for r in chosen)
                g["adoption_status"]="NOT_AUTHORIZED_BY_DIAGNOSTIC_RESULT"
            else:g["pooled"]=None
            groups.append(g)
    for r in evaluated:
        row={k:r.get(k) for k in ("stratum","mode","route","role","status","n","metadata_path")}
        row.update(r.get("metrics",{}));table.append(row)
    selection=None
    if policy and policy.is_file():
        lock=read_json(policy);folds=[]
        for stratum in STRATA:
            for route in ROUTES:
                q=lock.get("policies",{}).get(stratum,{}).get(route)
                if q is None:folds.append({"stratum":stratum,"route":route,"status":"MISSING_SELECTION"});continue
                entry={"stratum":stratum,"route":route,"selected_candidate":q["selected_candidate"],"selection_status":q.get("status"),"mode":q["mode"],
                       "selection_block_reason":q.get("selection_block_reason"),
                       "all_requested_route_partitions_nonempty":q.get("all_requested_route_partitions_nonempty"),
                       "split_remaining_train_n":q.get("split_remaining_train_n"),
                       "split_remaining_dev_n":q.get("split_remaining_dev_n"),
                       "eligible_candidates":q.get("eligible_candidates")}
                if q["mode"]=="OFF":
                    off=[r for r in evaluated if r["route"]==route and r["stratum"]==stratum and r["mode"]=="OFF" and r["status"]=="NUMERICALLY_EVALUATED"]
                    entry.update(status="LOCKED_OFF_NO_GUARD_UTILITY" if off else "LOCKED_OFF_REPLAY_MISSING",
                                 activity=0 if off else None,records=[r["metadata_path"] for r in off],performance_improvement_claim=False)
                else:
                    matches=[r for r in evaluated if r["route"]==route and r["stratum"]==stratum and "SELECTED" in r["role"].upper()
                             and r.get("policy_lock_sha256")==sha(policy) and r["status"]=="NUMERICALLY_EVALUATED"
                             and r["mode"]==q["mode"] and r.get("config")==q.get("config")]
                    entry["status"]="SELECTED_RECURSION_PRESENT" if matches else "SELECTED_RECURSION_MISSING"
                    entry["records"]=[r["metadata_path"] for r in matches]
                folds.append(entry)
        selection={"policy_lock_path":str(policy),"policy_lock_sha256":sha(policy),"folds":folds,
                   "adoption_status":"NOT_READY" if any(f["status"]!="SELECTED_RECURSION_PRESENT" for f in folds) else "REQUIRES_ALL_PERFORMANCE_AND_RECOVERY_GATES"}
    primary_snapshot=a.results/"policy_primary_precheck/POLICY_LOCK.json"
    policy_lineage={"final_lock_path":str(policy),"final_lock_sha256":sha(policy) if policy.is_file() else None,
                    "preserved_primary_lock_path":str(primary_snapshot) if primary_snapshot.is_file() else None,
                    "preserved_primary_lock_sha256":sha(primary_snapshot) if primary_snapshot.is_file() else None,
                    "primary_B_FROZEN_policy_exactly_matches_final":None,"trace_lock_reference_counts":{}}
    if policy.is_file() and primary_snapshot.is_file():
        final_primary=read_json(policy).get("policies",{}).get("B_FROZEN")
        earlier_primary=read_json(primary_snapshot).get("policies",{}).get("B_FROZEN")
        policy_lineage["primary_B_FROZEN_policy_exactly_matches_final"]=(earlier_primary is not None and earlier_primary==final_primary)
    for record in evaluated:
        digest=record.get("policy_lock_sha256") or "NOT_RECORDED"
        policy_lineage["trace_lock_reference_counts"][digest]=policy_lineage["trace_lock_reference_counts"].get(digest,0)+1
    policy_lineage["interpretation"]="Execution-time lock digests are preserved. A primary-only lock may have a different whole-file hash while its complete B_FROZEN policy objects exactly match the final two-stratum lock. Fixed diagnostic configuration is not a selected active policy; an OFF baseline need not have depended on a policy lock."
    units=evidence_matrix(a.results,a.repo,policy,groups)
    complete=all(g["status"]=="COMPLETE_EVALUATED" for g in groups)
    output={"status":"COMPLETED_NUMERICAL_DELIVERY_EVALUATION" if complete else "PARTIAL_DELIVERY_EVALUATION_MISSING_RESULTS",
            "implementation_complete_is_not_performance_adoption":True,
            "adoption_status":"NOT_READY_OR_NOT_DEMONSTRATED",
            "reason":"All required scientific gates, selected-policy utility, and recursive clean recovery must be proven; fixed diagnostics and OFF equivalence cannot substitute.",
            "code_sha256":sha(__file__),"input_receipt":input_receipt,"evaluated_records":evaluated,"groups":groups,
            "requested_scope":{"modes":list(MODES),"strata":list(STRATA),"routes":list(ROUTES),
                               "expected_streams":len(MODES)*len(STRATA)*len(ROUTES),"expected_rows_per_mode_stratum":3136},
            "NAIVE_YAW_CLIP_label":"Historical code label for a negative control: threshold the magnitude of the hypothetical heading correction, then jointly attenuate both measurement rows; no posterior output clipping.",
            "locked_policy_assessment":selection,"policy_lock_execution_lineage":policy_lineage,"development_unit_matrix":units,
            "coverage_interpretation":"Empirical 95% coverage with original filter P; no independence/normality calibration guarantee.",
            "latency_interpretation":"Measured in this execution environment including guard processing; parallel host contention/hardware portability not certified.",
            "activity_interpretation":"At least one numerically altered, legacy-accepted update; no statistical significance threshold is implied."}
    dump(a.out/"RESULTS.json",output);csv_write(a.out/"METRICS.csv",table);csv_write(a.out/"DEVELOPMENT_UNITS.csv",units)
    dump(a.out/"SHA256.json",{p.name:sha(p) for p in sorted(a.out.iterdir()) if p.is_file() and p.name!="SHA256.json" and p.suffix!=".log"})
    print(json.dumps({"status":output["status"],"records":len(evaluated),"groups":[{k:g[k] for k in ("stratum","mode","status","missing_routes")} for g in groups],"selection":selection},ensure_ascii=False,indent=2))
    if a.require_complete and not complete:sys.exit(2)


if __name__=="__main__":main()
