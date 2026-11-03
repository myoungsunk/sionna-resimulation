"""R5 exact real-FFD terminal precision on pre-existing DEV2 K1/K2 inputs ONLY.

Never touches DEV3, HOLDOUT2/reserve or RT. Its result is diagnostic forensic,
not a global MAP uniqueness proof or independent auditor signature.
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"code"))

import a10_p0 as P0
import a10_canonical as CAN
import a10_cross_runner_replay as O
import a10_r5 as R5
import c3v5 as C3
import filters as FL
import s1v5 as T
import s1v2 as V
import s1_mc as M
import world as Wd


def check(ok,code):
    if not ok:
        raise RuntimeError(code)


def forensic(cid,archive,world,config,policy_sha):
    if cid not in ("K1","K2"):
        raise RuntimeError("ERR_R5_FORBIDDEN_FIELD_SCOPE")
    f,role,cell,seed,arm=P0.CASES[cid]
    inp_original=CAN.estimator_only(archive,cid)
    stored_bytes={k:CAN.sha_array(v) for k,v in inp_original.items()}
    w0=world["wins"][role]
    # Existing archived truth is used for provenance/scoring only; never
    # introduces an oracle start into operational candidate selection.
    w=dict(w0,taps=inp_original["taps"],dts=inp_original["dts"],
           Xtrue=archive[f"{cid}|Xtrue"],poses=archive[f"{cid}|poses"])
    inp={k:inp_original[k].copy() for k in ("z","x0","ds_m","gy_m")}
    Sm=inp_original["Sigma_model"].copy()
    boundary={n:inp_original[n] for n in R5.SEVEN} if hasattr(R5,"SEVEN") else {
        k:inp_original[k] for k in ("z","x0","ds_m","gy_m","Sigma_model","dts","taps")}
    key=(f,role,cell,seed,arm)
    base,Xpr,info,theta=T.eval_batch(w,arm,Sm,inp,key,
                                    boundary_expected=boundary)
    hb=lambda X,t=w["taps"]:Wd.h_H_tap(X,"A",t)
    z,x0,dsm,gym,dts=(inp_original[n] for n in ("z","x0","ds_m","gy_m","dts"))
    cert_seed=T.key_seed("R5_CERT",*key)
    certs=[]
    solutions={"E":(float(base["cost"]),Xpr)}
    item=R5.certify_at_terminal(T,hb,z,Sm,dsm,gym,dts,x0,theta,
                                  cert_seed,base["polish_steps"],
                                  base["polish_hit_cap"],"E")
    certs.append(item)
    sd=np.sqrt(np.diag(M.P0))
    starts={f"psi{k:+d}":(np.r_[x0[:2],FL.wrap(x0[2]+k*sd[2]),x0[3]],
                           np.zeros_like(z)) for k in FL.MS_K}
    starts["x+1"]=(x0+np.r_[sd[0],0,0,0],np.zeros_like(z))
    starts["y+1"]=(x0+np.r_[0,sd[1],0,0],np.zeros_like(z))
    check(set(starts)==set(R5.STARTS),"ERR_R5_DEV2_WRONG_START_SET")
    for name,th0 in starts.items():
        _,_,it=FL.batch_map_v2(hb,z,np.zeros_like(z),Sm,dsm,gym,dts,
                              x0,M.P0,theta0=th0)
        th,nstep,hit=T.polish(hb,z,Sm,dsm,gym,dts,x0,it["theta"],
                             T.key_seed("DIAG_POLISH",*key,name))
        item=R5.certify_at_terminal(T,hb,z,Sm,dsm,gym,dts,x0,th,
                                    cert_seed,nstep,hit,name)
        certs.append(item)
        cost,X=FL._v2_parts(hb,z,np.zeros_like(z),
                         *T.B3._mats(Sm,dsm,dts)[:2],
                         x0,T.B3._mats(Sm,dsm,dts)[2],
                         dsm,gym,dts,th[0],th[1],jac=False)
        solutions[name]=(float(cost),X)
    result=R5.validate_terminals(certs,config)
    mode=C3.mode_ambiguity(solutions)
    # Exact original estimator inputs have not been mutated by diagnostics.
    check(all(CAN.sha_array(inp_original[k])==s for k,s in stored_bytes.items()),
          "ERR_R5_MUTATED_ARCHIVED_ORIGINAL_INPUTS")
    failures=[]
    for variant in ("cap","descent","nonfinite"):
        bad=copy.deepcopy(certs)
        if variant=="cap":bad[2]["polish_hit_cap"]=True
        if variant=="descent":bad[2]["dmin"]=-.1
        if variant=="nonfinite":bad[2]["end_state"][0]=float("nan")
        state=R5.validate_terminals(bad,config)
        check(state["status"]=="UNRESOLVED_PRECISION","ERR_R5_NEGATIVE_ACCEPTED "+variant)
        failures.append(variant)
    return dict(case=cid,field=f,role=role,cell=cell,sensor_seed=seed,arm=arm,
                input_sha256=stored_bytes,policy_sha256=policy_sha,
                base_cost=float(base["cost"]),base_class=base["class_v31"],
                common_seed=int(cert_seed),R5_PRECISION=result,
                n_ambiguous_starts_pre_r5=int(mode["n_alt_ambiguous"]),
                R5_qualified_near_starts=(
                    int(mode["n_alt_ambiguous"]) if result["pass_"] else None),
                terminal_solutions=certs,
                negative_case_mutations_rejected=failures,
                claim_global_MAP_unique=False,
                scientific_release=False)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    cfg,h=R5.spec_with_sha()
    check(T.POLISH_TOL==cfg["polish"]["cost_descent_tol_chi2"] and
          T.POLISH_MAX==cfg["polish"]["max_steps"],"ERR_R5_PROPOSER_F2_MISMATCH")
    provenance,archive,hashes=O.guard_archive()
    check(hashes["frozen_input_zip_sha256"]==CAN.CANON_SHA,"ERR_R5_CANONICAL_MISMATCH")
    world=V.setup(P0.lock_p0())
    cases=[forensic(x,archive,world,cfg,h) for x in ("K1","K2")]
    out=dict(schema="MBVAR_A010_R5_DEV2_FORNSIC_PRECISION_V1",
             contract_id="MBVAR-INFO-001",role="IMPLEMENTER",
             scope="archived DEV2 K1/K2 only",
             source_hash=hashes,proposer_policy_sha256=h,
             cases=cases,
             any_unresolved_precision=any(not x["R5_PRECISION"]["pass_"] for x in cases),
             separate_independent_auditor_signed=False,
             A010_SCIENCE_FROZEN=False,DEV3="NO-GO",HOLDOUT2="NO-GO",RT="NO-GO")
    path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2,allow_nan=True,default=float)+"\n")
    print("A010_R5_ARCHIVED_DEV2_CERTIFICATE",json.dumps([{
        "case":x["case"],"precision_status":x["R5_PRECISION"]["status"],
        "failures":x["R5_PRECISION"]["failure_reasons"],
        "near_start_count_before":x["n_ambiguous_starts_pre_r5"]
        } for x in cases]),flush=True)


if __name__=="__main__":
    main()
