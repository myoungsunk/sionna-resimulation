#!/usr/bin/env python3
"""Hindsight-selected P1 branch diagnostics at 1/5/10 seconds.

One action at selected k; all later updates use raw B with the unchanged
archived legacy shadow mask, their own main states, and original SourceFFD.
Event selection uses evaluated P1 losses and is not an online event detector.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np
from precheck_oracle import apply_action, pose_losses, relative_max

HORIZONS = (1., 5., 10.)
ACTIONS = {"FULL": (1., 1.), "R_SOFT": (.25, 1.), "S_SOFT": (1., .25),
           "RS_SOFT": (.25, .25), "SKIP": (0., 0.)}
METRICS = ("heading_deg2", "xy_m2")
TOL = (1e-12, 1e-14)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p):
    with np.load(p, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def write_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def write_csv(p, rows):
    if not rows:
        return
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def select_events(p1_path, t, mask):
    with np.load(p1_path, allow_pickle=False) as f:
        losses=f["losses"]
        names=f["actions"].tolist()
        assert np.array_equal(mask,f["mask"])
    full=losses[:,names.index("FULL")]
    skip=losses[:,names.index("SKIP")]
    eligible=mask & (t+max(HORIZONS)<=t[-1]+1e-9)
    assert eligible.any()
    events={}
    for d,metric in enumerate(METRICS):
        diff=full[:,d]-skip[:,d]
        for label,sign in (("largest_harmful_full_vs_skip",1), ("largest_beneficial_full_vs_skip",-1)):
            objective=np.where(eligible,sign*diff,-np.inf)
            k=int(np.argmax(objective))
            assert objective[k]>0, ("REQUESTED_EVENT_TYPE_NOT_PRESENT",metric,label)
            events.setdefault(k,[]).append({"metric":metric,"reason":label,
                                           "full_minus_skip_loss":float(diff[k])})
    return events, int(eligible.sum())


def propagate_branch(k, last, beta, on, zB, base, controls, core, online, model, spec):
    """No evaluator, htruth or event-selection losses are input arguments."""
    states,covs,gains=[],[],[]
    x,P,K,_=apply_action(base["prior"][k],base["Pprior"][k],base["H"][k],
                          base["nu"][k],base["Reff"][k],beta,bool(base["mask"][k]))
    states.append(x.copy());covs.append(P.copy());gains.append(K.copy())
    for j in range(k+1,last+1):
        rho=math.hypot(x[0]-spec["anchor"][0],x[1]-spec["anchor"][1])
        sig=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
        xp,pp=online.predict(core,x,P,j,controls)
        h,H=model.batch(xp[None],spec);h,H=h[0],H[0]
        v=zB[j]-h-on["muMB"][j]
        R=on["R"][j].copy();R[1,1]+=sig**2
        x,P,K,S=online.joseph(xp,pp,H,v,R,bool(base["mask"][j]),1.)
        states.append(x.copy());covs.append(P.copy());gains.append(K.copy())
    states,covs,gains=np.array(states),np.array(covs),np.array(gains)
    assert np.isfinite(states).all() and np.isfinite(covs).all()
    assert np.linalg.eigvalsh(covs).min()>-1e-12
    return {"x":states,"P":covs,"K":gains}


def event_rf_metadata(k, B, native, zB, on, ev, htruth, obs):
    raw=obs.cir_batch(on["Hrf"][k:k+1])[0]
    clean=obs.cir_batch(ev["clean_H"][k:k+1])[0]
    p=abs(raw)**2;pc=abs(clean)**2
    pow=p[B[k]]; clean_edges=np.argmax(abs(clean)>=.3*abs(clean).max(axis=0)[None],axis=0)
    cb=int(clean_edges.min());cp=pc[cb]
    lo,hi=max(0,cb-4),min(len(raw),cb+5)
    return {"B_tap":int(B[k]),"native_tap":int(native[k]),"clean_B_tap":cb,
            "B_range_m":float(zB[k,0]),"B_s":float(zB[k,1]),"native_s":float(on["z"][k,1]),
            "source_htruth_s":float(htruth[k,1]),"ideal_s_htruth_plus_muMB":float(htruth[k,1]+on["muMB"][k,1]),
            "B_s_minus_source_mu":float(zB[k,1]-htruth[k,1]-on["muMB"][k,1]),
            "clean_B_s":float((cp[0]-cp[1])/cp.sum()),
            "raw_B_power_port0":float(pow[0]),"raw_B_power_port1":float(pow[1]),
            "raw_B_power_ratio_0_over_1":float(pow[0]/pow[1]) if pow[1]>0 else None,
            "raw_port_peak_power_ratio_0_over_1":float(p[:,0].max()/p[:,1].max()) if p[:,1].max()>0 else None,
            "clean_reference_local_complex_distortion_norm":float(np.linalg.norm(raw[lo:hi]-clean[lo:hi])/max(np.linalg.norm(clean[lo:hi]),np.finfo(float).tiny)),
            "RF_metadata_role":"Evaluator-only descriptions; no CIR/model-truth features enter branch propagation."},raw,clean


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--traces",type=Path,required=True)
    p.add_argument("--p1",type=Path,required=True)
    p.add_argument("--model-truth",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();repo=a.repo.resolve();a.out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(repo/"research/FP_NATIVE_B_CAUSAL_ABLATION_20261108"))
    from fp_ns_ablation import load_original_replay,identical_input_condition
    r45,core,online,model,hashes=load_original_replay(repo)
    from qclean_uwb.drivesim import observation as obs
    all_rows,case_results=[],[]
    for route in ("R2","R4","R5"):
        case=route+"_B0_Full_10";on=r45.data(case,"online.npz")
        path=a.traces/route/f"{route}_B_FROZEN.npz"
        assert sha(path)==json.loads((path.parent/"SHA256.json").read_text())[path.name]
        base=load(path);B,native,zN,zB=identical_input_condition(on,r45,case)
        controls={key:on[key] for key in ("ds","gy","dt")};controls["x0"]=on["x0"][:3]
        p1_path=a.p1/f"{route}_B_FROZEN_ACTIONS.npz"
        p1_manifest=json.loads((a.p1/"SHA256.json").read_text());assert sha(p1_path)==p1_manifest[p1_path.name]
        events,eligible_n=select_events(p1_path,on["t"],base["mask"])
        pending=[]
        for k,reasons in sorted(events.items()):
            last=int(np.searchsorted(on["t"],on["t"][k]+max(HORIZONS)-1e-9))
            assert abs(on["t"][last]-on["t"][k]-max(HORIZONS))<1e-9
            branches={name:propagate_branch(k,last,beta,on,zB,base,controls,core,online,model,r45.SPEC) for name,beta in ACTIONS.items()}
            par={key:relative_max(branches["FULL"][key],base[key][k:last+1],2 if key=="x" else None) for key in ("x","P","K")}
            assert max(par.values())<=1e-10,("FULL_BRANCH_PARITY_FAILED",route,k,par)
            pending.append((k,last,reasons,branches,par))
            print("BRANCHES_COMPLETE",route,k,"actions",len(branches),flush=True)
        # No evaluator object was loaded or passed to propagate_branch above.
        ev=r45.data(case,"evaluator.npz")
        assert np.array_equal(ev["t"],on["t"]) and np.array_equal(ev["pose_id"],on["pose_id"])
        hp=a.model_truth/f"{route}_htruth.npz"
        hj=json.loads((a.model_truth/f"{route}_htruth.json").read_text())
        assert sha(hp)==hj["npz_sha256"]
        ht=load(hp);assert np.array_equal(ht["t"],on["t"]);htruth=ht["htruth"]
        event_results=[]
        for k,last,reasons,branches,par in pending:
            truth=ev["truth"][k:last+1]
            losses={name:pose_losses(tr["x"],truth) for name,tr in branches.items()}
            meta,raw,clean=event_rf_metadata(k,B,native,zB,on,ev,htruth,obs)
            for horizon in HORIZONS:
                end=int(np.searchsorted(on["t"][k:last+1]-on["t"][k],horizon-1e-9))
                assert abs(on["t"][k+end]-on["t"][k]-horizon)<1e-9
                for name in ACTIONS:
                    for d,metric in enumerate(METRICS):
                        immediate=float(losses[name][0,d]-losses["FULL"][0,d])
                        endpoint=float(losses[name][end,d]-losses["FULL"][end,d])
                        future_mean=float(losses[name][1:end+1,d].mean()-losses["FULL"][1:end+1,d].mean())
                        signs=[0 if abs(v)<=TOL[d] else int(np.sign(v)) for v in (immediate,endpoint,future_mean)]
                        all_rows.append({"route":route,"event_k":k,"event_t_s":float(on["t"][k]),
                                         "action":name,"horizon_s":horizon,"metric":metric,
                                         "immediate_loss":float(losses[name][0,d]),"immediate_delta_vs_full":immediate,
                                         "endpoint_loss":float(losses[name][end,d]),"endpoint_delta_vs_full":endpoint,
                                         "future_mean_loss_excluding_current":float(losses[name][1:end+1,d].mean()),
                                         "future_mean_delta_vs_full":future_mean,
                                         "immediate_to_endpoint_sign_reversal":bool(signs[0]*signs[1]<0),
                                         "immediate_to_future_mean_sign_reversal":bool(signs[0]*signs[2]<0)})
            event_results.append({"k":k,"t_s":float(on["t"][k]),"selection_reasons":reasons,
                                  "full_branch_parity":par,"RF":meta})
            np.savez_compressed(a.out/f"{route}_K{k}_BRANCHES.npz",
                                **{name+"_"+key:value for name,tr in branches.items() for key,value in tr.items()},
                                **{name+"_losses":v for name,v in losses.items()},t=on["t"][k:last+1],truth=truth,
                                future_fixed_legacy_mask=base["mask"][k:last+1],B_tap=B[k:last+1],
                                event_raw_CIR=raw,event_clean_CIR=clean)
        case_results.append({"route":route,"eligible_accepted_frames_with_full_10s_future":eligible_n,
                             "selected_unique_events":len(events),"events":event_results,
                             "input_hashes":{str(p):sha(p) for p in (path,p1_path,hp)}})
    write_csv(a.out/"HORIZON_LOSSES.csv",all_rows)
    selected=[r for r in all_rows if r["action"]!="FULL"]
    output={"status":"PASS_FULL_BRANCH_PARITY_AND_HORIZON_EVALUATION",
            "scope":"Diagnostic selected-event counterfactuals, not aggregate performance or policy utility",
            "selection":"Hindsight largest harmful/beneficial FULL-vs-SKIP heading/XY per route; deduplicate; require accepted current and full 10s followup",
            "future_gate":"Unchanged original raw-B shadow mask fixed. Main states/covariances and rho-dependent s R evolve per branch.",
            "intervention":"One initial action only; all following measurements receive original FULL update if legacy gate allows",
            "mean_definition":"Future k+1..k+h, excludes intervention sample; endpoints k+h",
            "truth_separation":"Event selection uses previously evaluated P1 losses. Runtime propagation gets no truth. Truth/CIR diagnostic evaluation loaded after branches.",
            "code_sha256":sha(__file__),"source_hashes":hashes,"actions":{n:list(b) for n,b in ACTIONS.items()},
            "cases":case_results,
            "reversal_counts_descriptive_only":{"nonfull_action_horizon_metric_comparisons":len(selected),
                "immediate_to_endpoint":sum(r["immediate_to_endpoint_sign_reversal"] for r in selected),
                "immediate_to_future_mean":sum(r["immediate_to_future_mean_sign_reversal"] for r in selected)}}
    write_json(a.out/"RESULTS.json",output)
    write_json(a.out/"SHA256.json",{p.name:sha(p) for p in sorted(a.out.iterdir()) if p.is_file() and p.name!="SHA256.json" and p.suffix!=".log"})
    print(json.dumps({"cases":[{"route":c["route"],"events":[e["k"] for e in c["events"]]} for c in case_results],
                      "reversals":output["reversal_counts_descriptive_only"]},indent=2))


if __name__=="__main__":main()
