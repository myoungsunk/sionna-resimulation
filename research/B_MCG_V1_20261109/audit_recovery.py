#!/usr/bin/env python3
"""Evaluator-only, finite recursive recovery stress after coherent RF bias.

Constructed observations use the pinned SourceFFD observer; this is not a
physical clean-CIR replay or an independent-seed experiment. Offline truth is
used to build the test packet and score results; no truth enters replay_active.
"""
from __future__ import annotations
import argparse
import csv
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import time

for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[name]="1"
import numpy as np
from experiment import context,packet_for,read_npz,config_for,replay_active
from evaluate_delivery import independent_joseph,losses

EPISODES={"R4":186,"R5":682}
PREFIX_INTERVALS=25
PREFIX_SAMPLES=26
CLEAN_SAMPLES=50
TOTAL_SAMPLES=76
CONSECUTIVE=5
HEADING_LIMIT_DEG=1.
XY_LIMIT_M=.05
TRANSLATION=np.array([.3,.3])
YAW_ROTATION=.3


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi


def clean_json(x):
    if isinstance(x,dict):return {str(k):clean_json(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean_json(v) for v in x]
    if isinstance(x,np.ndarray):return clean_json(x.tolist())
    if isinstance(x,np.generic):return clean_json(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x


def save(p,x):p.write_text(json.dumps(clean_json(x),ensure_ascii=False,indent=2,allow_nan=False)+"\n")


def code_hashes():
    root=Path(__file__).parent
    return {n:sha(root/n) for n in ("mcg.py","experiment.py","audit_recovery.py","evaluate_delivery.py")}


def recovery_time(qualified,t):
    run=0
    for i,yes in enumerate(qualified):
        run=run+1 if yes else 0
        if run>=CONSECUTIVE:
            first=i-CONSECUTIVE+1
            return {"status":"RECOVERED","first_qualifying_run_start_index":first,
                    "confirmation_index":i,"onset_latency_s":float(t[first]-t[0]),
                    "confirmation_latency_s":float(t[i]-t[0]),"required_consecutive_samples":CONSECUTIVE}
    return {"status":"RIGHT_CENSORED_NOT_RECOVERED","onset_latency_s":None,"confirmation_latency_s":None,
            "observed_elapsed_s":float(t[-1]-t[0]),"required_consecutive_samples":CONSECUTIVE}


def compare_recovery(current,baseline):
    if baseline["status"]!="RECOVERED":
        return {"status":"NOT_ESTIMABLE_BASELINE_CENSORED","ratio":None,"pass_le_1p1":None}
    if current["status"]!="RECOVERED":
        return {"status":"FAIL_GUARD_CENSORED","ratio":None,"pass_le_1p1":False}
    b=baseline["confirmation_latency_s"];v=current["confirmation_latency_s"]
    if b<=0:return {"status":"NOT_ESTIMABLE_ZERO_BASELINE_TIME","ratio":None,"pass_le_1p1":None}
    return {"status":"ESTIMABLE","ratio":v/b,"pass_le_1p1":bool(v/b<=1.1+1e-12)}


def evaluate(tr,truth,t):
    e=tr["x"][:,:3]-truth;e[:,2]=wrap(e[:,2])
    h=abs(np.degrees(e[:,2]));xy=np.linalg.norm(e[:,:2],axis=1)
    clean=slice(PREFIX_SAMPLES,None);hc,xc,tc=h[clean],xy[clean],t[clean]
    quals={"heading":hc<=HEADING_LIMIT_DEG,"xy":xc<=XY_LIMIT_M,
           "joint":(hc<=HEADING_LIMIT_DEG)&(xc<=XY_LIMIT_M)}
    rec={name:recovery_time(mask,tc) for name,mask in quals.items()}
    full=np.empty_like(tr["x"])
    for k in range(len(full)):
        full[k]=independent_joseph(tr["prior"][k],tr["Pprior"][k],tr["H"][k],tr["nu"][k],tr["Rbase"][k],np.ones(2),bool(tr["mask"][k]))[0]
    lf,ls,lp=losses(full,truth),losses(tr["prior"],truth),losses(tr["x"],truth)
    gain={}
    for d,name in enumerate(("heading_deg2","xy_m2")):
        good=(ls[clean,d]>lf[clean,d])&tr["mask"][clean]
        denominator=float(np.sum((ls[clean,d]-lf[clean,d])[good]))
        numerator=float(np.sum(np.maximum(lp[clean,d]-lf[clean,d],0)[good]))
        gain[name]={"beneficial_legacy_accepted_n":int(good.sum()),"denominator":denominator,"lost_numerator":numerator,
                    "lost_gain_ratio":numerator/denominator if denominator>0 else None,
                    "status":"ESTIMABLE" if denominator>0 else "NOT_ESTIMABLE_NO_GOOD_UPDATE",
                    "five_percent_budget_pass":bool(numerator/denominator<=.05+1e-12) if denominator>0 else None}
    return {"recovery":rec,"clean_heading_rmse_deg":float(np.sqrt(np.mean(hc**2))),
            "clean_xy_rmse_cm":float(100*np.sqrt(np.mean(xc**2))),
            "clean_start_heading_error_deg":float(hc[0]),"clean_start_xy_error_cm":float(xc[0]*100),
            "clean_final_heading_error_deg":float(hc[-1]),"clean_final_xy_error_cm":float(xc[-1]*100),
            "clean_legacy_accepted":int(tr["mask"][clean].sum()),"clean_legacy_rejected":int((~tr["mask"][clean]).sum()),
            "clean_guard_damped_legacy_accepted":int(np.sum(tr["mask"][clean]&np.any(tr["beta"][clean]<1-1e-14,axis=1))),
            "prefix_guard_damped_legacy_accepted":int(np.sum(tr["mask"][:PREFIX_SAMPLES]&np.any(tr["beta"][:PREFIX_SAMPLES]<1-1e-14,axis=1))),
            "clean_good_gain_preservation_same_active_prior":gain,
            "clean_status_counts":{str(k):int(v) for k,v in zip(*np.unique(tr["status"][clean],return_counts=True))}},h,xy,lf,ls,lp


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archives",type=Path,required=True);p.add_argument("--model-truth",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if (args.out/"RESULTS.json").exists():raise FileExistsError("Completed recovery output is immutable; choose a new directory")
    frozen_code=code_hashes();started=time.perf_counter()
    r45,core,online,model,source_hashes=context()
    contract={"status":"RUNNING","diagnostic_only":True,"production_selected_policy":False,
              "stratum":"B_FROZEN","episodes":EPISODES,"runtime_code_sha256":frozen_code,"source_hashes":source_hashes,
              "n_samples_per_episode":TOTAL_SAMPLES,"prefix_RF_samples":PREFIX_SAMPLES,"prefix_motion_intervals":PREFIX_INTERVALS,
              "clean_RF_samples":CLEAN_SAMPLES,"rigid_transform":{"pivot":"truth XY at episode anchor","translation_m":TRANSLATION.tolist(),"yaw_rotation_rad":YAW_ROTATION},
              "prefix_observations":"SourceFFD(transformed truth)+original muMB",
              "clean_observations":"SourceFFD(original truth)+original muMB",
              "initial_state":"Archived original B pre-RF prior at selected anchor; initial main P and shadow P both archived Pprior",
              "first_control":"ds=gy=dt=0; pre-RF anchor is already at the first sample time",
              "time":"Epoch reset t-t_start; original absolute t and indices preserved for evaluation",
              "recovery_definition":{"heading_abs_error_deg_le":HEADING_LIMIT_DEG,"xy_error_m_le":XY_LIMIT_M,"consecutive_RF_samples":CONSECUTIVE,
                    "comparison_time":"Latency until 5th qualifying sample, measured from first clean RF sample; onset latency also reported",
                    "budget_ratio_max":1.1,"censoring":"No ratio if OFF does not recover within the observed window; guard censoring fails if OFF recovers"},
              "settings":"OFF comparator, ACTIVE_RS tau2 and tau3 predetermined diagnostic settings; no threshold tuning from outcomes",
              "runtime_truth_separation":"Observations constructed offline; replay_active receives only the whitelisted packet and source model, never truth or clean CIR",
              "scope_limits":["Two selected scenarios, not a global recovery guarantee","Original seed10 raw controls; no new seed or physical channel draw","Synthetic observer-consistent observations, not physical clean CIR","Legacy shadow may itself reject clean return; rejection is reported separately"]}
    save(args.out/"CONTRACT.json",contract)
    cases=[];csv_rows=[]
    for route,a in EPISODES.items():
        packet,_,_=packet_for(r45,route,"B_FROZEN",args.archives)
        ep=r45.data(route+"_B0_Full_10","evaluator.npz")
        oldp=args.archives/route/f"{route}_B_FROZEN.npz"
        assert sha(oldp)==json.loads((oldp.parent/"SHA256.json").read_text())[oldp.name]
        old=read_npz(oldp);end=a+TOTAL_SAMPLES
        assert end<=len(packet["t"])
        idx=np.arange(a,end);truth=ep["truth"][idx]
        hp=args.model_truth/f"{route}_htruth.npz";hj=json.loads((args.model_truth/f"{route}_htruth.json").read_text())
        assert sha(hp)==hj["npz_sha256"]
        ht=read_npz(hp);assert np.array_equal(ht["pose_id"],packet["pose_id"])
        rot=np.array([[np.cos(YAW_ROTATION),-np.sin(YAW_ROTATION)],[np.sin(YAW_ROTATION),np.cos(YAW_ROTATION)]])
        transformed=truth[:PREFIX_SAMPLES].copy()
        transformed[:,:2]=(transformed[:,:2]-truth[0,:2])@rot.T+truth[0,:2]+TRANSLATION
        transformed[:,2]=wrap(transformed[:,2]+YAW_ROTATION)
        hz=model.batch(transformed,r45.SPEC,gradient=False)[0]+packet["muMB"][idx[:PREFIX_SAMPLES]]
        ideal=ht["htruth"][idx]+packet["muMB"][idx]
        synthetic=np.concatenate((hz,ideal[PREFIX_SAMPLES:]))
        run_packet={k:(v[idx].copy() if k not in ("x0","P0") else v.copy()) for k,v in packet.items()}
        absolute_t=run_packet["t"].copy();run_packet["t"]-=run_packet["t"][0]
        run_packet["x0"]=old["prior"][a].copy();run_packet["P0"]=old["Pprior"][a].copy()
        for k in ("ds","gy","dt"):run_packet[k][0]=0.
        run_packet["z"]=synthetic
        # Everything passed to online recursion is an ordinary runtime packet.
        assert not any(k in run_packet for k in ("truth","clean_H","clean_Hrf","htruth"))
        traces={};configs={}
        for name,mode,tau in (("OFF","OFF",2.),("ACTIVE_RS_TAU2","ACTIVE_RS",2.),("ACTIVE_RS_TAU3","ACTIVE_RS",3.)):
            cfg=config_for(tau=tau,span=5.);configs[name]=asdict(cfg)
            print("RECOVERY_REPLAY",route,a,name,flush=True)
            traces[name]=replay_active(run_packet,core,online,model,r45.SPEC,cfg,mode)
            assert code_hashes()==frozen_code,"RUNTIME_CODE_CHANGED_DURING_EXPERIMENT"
        for name in traces:
            assert np.array_equal(traces[name]["mask"],traces["OFF"]["mask"]),"SHADOW_GATE_DIFFERED_ACROSS_GUARD_ARMS"
            assert np.array_equal(traces[name]["shadow_x"],traces["OFF"]["shadow_x"]),"SHADOW_STATE_CHANGED_BY_GUARD"
            assert np.array_equal(traces[name]["shadow_P"],traces["OFF"]["shadow_P"]),"SHADOW_COV_CHANGED_BY_GUARD"
        metrics={}
        for name,tr in traces.items():
            metric,heading,xy,lf,ls,lp=evaluate(tr,truth,run_packet["t"])
            metrics[name]=metric
            np.savez_compressed(args.out/f"{route}_A{a}_{name}.npz",**tr,truth=truth,t=run_packet["t"],absolute_t=absolute_t,
                                original_k=idx,constructed_z=synthetic,ideal_z=ideal,
                                same_prior_full_losses=lf,same_prior_skip_losses=ls,actual_losses=lp)
            for i,k in enumerate(idx):
                csv_rows.append({"route":route,"anchor_k":a,"arm":name,"episode_k":i,"original_k":int(k),"t_s":float(run_packet["t"][i]),
                                 "absolute_t_s":float(absolute_t[i]),"phase":"COHERENT_PREFIX" if i<PREFIX_SAMPLES else "IDEAL_CLEAN_RETURN",
                                 "heading_abs_error_deg":float(heading[i]),"xy_error_cm":float(xy[i]*100),"legacy_accepted":bool(tr["mask"][i]),
                                 "beta_r":float(tr["beta"][i,0]),"beta_s":float(tr["beta"][i,1]),"guard_status":str(tr["status"][i]),
                                 "guard_reason":str(tr["reason"][i]),"score_r":float(tr["scores"][i,0]) if np.isfinite(tr["scores"][i,0]) else None,
                                 "score_s":float(tr["scores"][i,1]) if np.isfinite(tr["scores"][i,1]) else None,
                                 "same_prior_heading_full_gain_vs_skip":float(ls[i,0]-lf[i,0]),
                                 "same_prior_xy_full_gain_vs_skip":float(ls[i,1]-lf[i,1]),
                                 "heading_loss_policy_minus_same_prior_full":float(lp[i,0]-lf[i,0]),
                                 "xy_loss_policy_minus_same_prior_full":float(lp[i,1]-lf[i,1])})
        for name in ("ACTIVE_RS_TAU2","ACTIVE_RS_TAU3"):
            metrics[name]["recovery_ratio_vs_OFF"]={axis:compare_recovery(metrics[name]["recovery"][axis],metrics["OFF"]["recovery"][axis]) for axis in ("heading","xy","joint")}
        result={"route":route,"anchor_k":a,"last_k":end-1,"n":TOTAL_SAMPLES,
                "absolute_start_t_s":float(absolute_t[0]),"clean_start_original_k":int(idx[PREFIX_SAMPLES]),
                "clean_start_t_s":float(run_packet["t"][PREFIX_SAMPLES]),
                "clean_elapsed_observed_s":float(run_packet["t"][-1]-run_packet["t"][PREFIX_SAMPLES]),
                "archive_sha256":sha(oldp),"htruth_sha256":sha(hp),"configs":configs,"metrics":metrics,
                "shadow_identical_all_arms":True,"runtime_code_sha256":frozen_code}
        cases.append(result);save(args.out/f"{route}_RECOVERY.json",result)
    contract["status"]="COMPLETED_SELECTED_RECURSIVE_RECOVERY_STRESS"
    output={"status":contract["status"],"contract":contract,"cases":cases,"elapsed_s":time.perf_counter()-started,
            "global_recovery_pass":False,"global_recovery_claim":"NOT_ESTABLISHED_BY_TWO_SELECTED_SYNTHETIC_SCENARIOS"}
    assert code_hashes()==frozen_code
    save(args.out/"RESULTS.json",output);save(args.out/"CONTRACT.json",contract)
    with (args.out/"RECOVERY_ROWS.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(csv_rows[0]));w.writeheader();w.writerows(csv_rows)
    save(args.out/"SHA256.json",{p.name:sha(p) for p in sorted(args.out.iterdir()) if p.is_file() and p.name!="SHA256.json" and p.suffix!=".log"})
    print(json.dumps(clean_json({"status":output["status"],"cases":[{"route":c["route"],"metrics":c["metrics"]} for c in cases]}),ensure_ascii=False,indent=2))


if __name__=="__main__":main()
